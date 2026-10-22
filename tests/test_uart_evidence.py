"""UART silence evidence is checked through its documented analyzer CLI."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def live_capture():
    memory = dict(free_heap_bytes=100, minimum_free_heap_bytes=80,
                  largest_free_block_bytes=90, stack_high_water_bytes=256,
                  result_buffer_bytes=56000, window_buffer_bytes=2640,
                  model_workspace_bytes=None)
    return [
        (0, dict(event='run_start', schema='gearshift.measurement.v1', run_id='fixture',
                 mode='live', workload='synthetic_delay_25ms', simulated=False,
                 expected_batches=1, expected_tasks=1)),
        (.001, dict(event='series_start', batch_id='b1', phase='live', series=0,
                    period_us=50000, count=1, window_ids=['w0'], uart_wait_us=0,
                    memory=memory)),
        (.051, dict(event='series_memory', batch_id='b1', memory=memory)),
        (.052, dict(event='task', batch_id='b1', index=0, window_index=0, scheduled_us=0,
                    started_us=0, inference_started_us=0, inference_finished_us=25000,
                    finished_us=25000, status='ok', error=None)),
        (.053, dict(event='series_end', batch_id='b1', count=1, end_us=50000,
                    uart_wait_us=1000, uart_during_execution=False)),
        (.054, dict(event='run_complete', batches=1, tasks=1)),
    ]


class UartEvidenceTests(unittest.TestCase):
    def test_json_task_during_execution_cannot_be_reported_as_uart_silence(self):
        events = live_capture()
        task = events.pop(3)[1]
        events.insert(2, (.025, task))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'capture.log'
            chunks, raw = [], b''
            for elapsed, event in events:
                line = (json.dumps(event) + '\r\n').encode()
                chunks.append(dict(offset=len(raw), bytes=len(line), elapsed_s=elapsed))
                raw += line
            source.write_bytes(raw)
            Path(str(source) + '.json').write_text(json.dumps(dict(
                complete=True, malformed_json_lines=0, elapsed_s=.054, chunks=chunks)))
            prefix = Path(directory) / 'analysis'
            result = subprocess.run([
                sys.executable, str(ROOT / 'docs/evidence/issue-5/analyze_uart.py'),
                str(source), str(prefix),
            ], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(prefix.with_suffix('.silence.json').exists())

    def test_quiet_execution_ends_at_first_memory_byte_received(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'capture.log'
            chunks, raw = [], b''
            for elapsed, event in live_capture():
                line = (json.dumps(event) + '\r\n').encode()
                chunks.append(dict(offset=len(raw), bytes=len(line), elapsed_s=elapsed))
                raw += line
            source.write_bytes(raw)
            Path(str(source) + '.json').write_text(json.dumps(dict(
                complete=True, malformed_json_lines=0, elapsed_s=.054, chunks=chunks)))
            prefix = Path(directory) / 'analysis'
            result = subprocess.run([
                sys.executable, str(ROOT / 'docs/evidence/issue-5/analyze_uart.py'),
                str(source), str(prefix),
            ], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(prefix.with_suffix('.silence.json').read_text())
            self.assertEqual(report['series'][0]['first_result_byte_received_s'], .051)
            self.assertAlmostEqual(report['series'][0]['observed_no_rx_s'], .05)
