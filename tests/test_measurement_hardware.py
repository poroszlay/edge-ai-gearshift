"""Opt-in regression on a panel already flashed with the benchmark firmware."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('GEARSHIFT_TEST_ESP32_PORT'), 'ESP32 port not requested')
class MeasurementHardwareTests(unittest.TestCase):
    def test_benchmark_export_does_not_trigger_idle_watchdog(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / 'uart.log'
            result = subprocess.run([
                sys.executable,
                str(root / 'docs/evidence/issue-2/hardware-2026-10-19/capture_serial.py'),
                os.environ['GEARSHIFT_TEST_ESP32_PORT'], '25', str(log),
            ], capture_output=True, text=True, timeout=35)
            self.assertEqual(result.returncode, 0, result.stderr)
            raw = log.read_bytes()
            self.assertIn(b'"batch_id":"b2"', raw, 'reproducer did not reach measured export')
            self.assertFalse(b'task_wdt:' in raw, 'idle task starved during benchmark export')
            self.assertNotIn(b'Guru Meditation', raw)
