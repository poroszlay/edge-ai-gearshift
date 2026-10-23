"""Freeze-contract regressions at the approved firmware/PC entry points."""
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'models/mlp-v2'
SCRIPT = ROOT / 'tools/embed-model.py'
MODEL_DEPS = all(importlib.util.find_spec(name) for name in ('numpy', 'tensorflow'))
INVALID_FREEZES = (
    ('numeric_frozen', {'frozen': 1}),
    ('string_frozen', {'frozen': 'true'}),
    ('not_frozen', {'frozen': False}),
    ('dataset_mismatch', {'dataset_id': '0' * 64}),
    ('model_mismatch', {'model_id': '0' * 64}),
    ('checksum_mismatch', None),
)


def invalid_package(root, changes):
    package = root / 'model'
    shutil.copytree(MODEL, package)
    if changes is None:
        (package / 'audit.json').write_bytes(b'corrupted audit')
    else:
        freeze = json.loads((package / 'freeze.json').read_text())
        freeze.update(changes)
        (package / 'freeze.json').write_text(json.dumps(freeze))
    return package


class EmbeddedFreezeTests(unittest.TestCase):
    def test_generator_rejects_the_same_invalid_freeze_contracts_as_final_evaluation(self):
        for name, changes in INVALID_FREEZES:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                package = invalid_package(root, changes)
                destination = root / 'model_data.h'
                # Isolated Python + a foreign cwd also exercise the SDK entry point.
                result = subprocess.run([sys.executable, '-I', str(SCRIPT), str(package), str(destination)],
                                        cwd=root, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertFalse(destination.exists())

    def test_generator_preserves_the_valid_frozen_model_bytes_and_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'model_data.h'
            result = subprocess.run([sys.executable, '-I', str(SCRIPT), str(MODEL), str(destination)],
                                    cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            metadata = json.loads(result.stdout)
            self.assertEqual(metadata['model_id'],
                             '6d5ac8613d301ca06de2ca9a4cfbadf3cd40c7c75a7af419505eaa9fcbb25f79')
            blob = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-f]{2})', destination.read_text()))
            self.assertEqual(blob, (MODEL / 'model.tflite').read_bytes())
            self.assertEqual(metadata['model_bytes'], 13696)


@unittest.skipUnless(MODEL_DEPS, 'install requirements-model.txt for final evaluation')
class CampaignFreezeTests(unittest.TestCase):
    def test_campaign_rejects_invalid_frozen_packages_before_reading_locked_test(self):
        from gearshift.campaign import prepare
        for name, changes in INVALID_FREEZES:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                package = invalid_package(root, changes)
                with self.assertRaisesRegex(ValueError, 'frozen'):
                    prepare(root / 'unreadable-test', package, root / 'output')
                self.assertFalse((root / 'output/reference.jsonl').exists())
