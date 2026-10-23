"""Opt-in end-to-end INT8 regression against the flashed #7 firmware.

Run after sourcing ESP-IDF export.sh. This resets the identified panel and
owns the UART exclusively. No hardware is used by default CI.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PORT = os.environ.get('GEARSHIFT_INFERENCE_PORT')


@unittest.skipUnless(PORT, 'set GEARSHIFT_INFERENCE_PORT for the flashed #7 ESP32 firmware')
class InferenceHardwareTests(unittest.TestCase):
    def test_raw_reference_and_rounding_regression_match_the_frozen_pc(self):
        expected = [json.loads(line) for line in (ROOT / 'models/mlp-v2/pc-reference.jsonl').read_text().splitlines()]
        expected += [json.loads(line) for line in (ROOT / 'docs/evidence/issue-7/numeric-regression-reference.jsonl').read_text().splitlines()]
        inputs = (ROOT / 'models/mlp-v2/reference-windows.jsonl').read_text()
        inputs += (ROOT / 'docs/evidence/issue-7/numeric-regression-windows.jsonl').read_text()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'inputs.jsonl').write_text(inputs)
            output = root / 'run'
            result = subprocess.run(['bash', 'tools/run-esp32.sh', 'live', str(output), str(root / 'inputs.jsonl')],
                                    cwd=ROOT, env=dict(os.environ, GEARSHIFT_PORT=PORT),
                                    capture_output=True, text=True, timeout=30)
            diagnostic = (output / 'client.log').read_text() if (output / 'client.log').exists() else result.stderr
            self.assertEqual(result.returncode, 0, diagnostic)
            events = [json.loads(line) for line in (output / 'events.jsonl').read_text().splitlines()]
            self.assertEqual(events[-1]['event'], 'run_complete')
            actual = [r for r in events if r['event'] == 'result']
            self.assertEqual([r['window_id'] for r in actual], [r['window_id'] for r in expected])
            for pc, mcu in zip(expected, actual):
                with self.subTest(window_id=pc['window_id']):
                    self.assertFalse(mcu['simulated'])
                    self.assertEqual(mcu['status'], 'ok')
                    self.assertEqual(mcu['model_id'], pc['model_id'])
                    self.assertEqual(mcu['input_int8'], pc['input_int8'])
                    self.assertEqual(mcu['decision'], pc['decision'])
                    self.assertLessEqual(max(abs(a-b) for a,b in zip(mcu['output_int8'],pc['output_int8'])),1)
