"""Check the published measurement evidence against its declared source versions."""
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/issue-5'


class MeasurementEvidenceTests(unittest.TestCase):
    def test_corrected_evidence_identifies_the_sources_it_built(self):
        manifests = [EVIDENCE / 'manifest.json',
                     EVIDENCE / 'review-4cb661c/manifest.json',
                     EVIDENCE / 'hardware-ee4cf53/manifest.json']
        for path in manifests:
            manifest = json.loads(path.read_text())
            for name, expected in manifest['source_sha256'].items():
                with self.subTest(version=manifest['source_commit'], source=name):
                    committed = subprocess.check_output(
                        ['git', 'show', manifest['source_commit'] + ':' + name], cwd=ROOT)
                    self.assertEqual(hashlib.sha256(committed).hexdigest(), expected)
                    if path.parent.name == 'hardware-ee4cf53':
                        self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(),
                                         expected)

    def test_documented_evidence_checksum_command_succeeds(self):
        result = subprocess.run(['sha256sum', '-c', 'docs/evidence/issue-5/SHA256SUMS'],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
