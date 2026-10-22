"""Tests at the public raw-export/analysis CLI seam."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


def capture():
    return [
        dict(event='run_start', schema='gearshift.measurement.v1', run_id='fixture',
             mode='benchmark', workload='synthetic_delay_25ms', simulated=True,
             expected_batches=1, expected_tasks=4),
        dict(event='series_start', batch_id='b1', phase='measured', series=1,
             period_us=10000, count=4, window_ids=['w0', 'w1'], uart_wait_us=200),
        dict(event='task', batch_id='b1', index=0, window_index=0, scheduled_us=0,
             started_us=0, inference_started_us=0, inference_finished_us=25000,
             finished_us=25000, status='late', error=None),
        dict(event='task', batch_id='b1', index=1, window_index=1, scheduled_us=10000,
             started_us=None, inference_started_us=None, inference_finished_us=None,
             finished_us=None, status='missed', error=None),
        dict(event='task', batch_id='b1', index=2, window_index=0, scheduled_us=20000,
             started_us=None, inference_started_us=None, inference_finished_us=None,
             finished_us=None, status='missed', error=None),
        dict(event='task', batch_id='b1', index=3, window_index=1, scheduled_us=30000,
             started_us=30000, inference_started_us=30000, inference_finished_us=55000,
             finished_us=55000, status='late', error=None),
        dict(event='series_end', batch_id='b1', count=4, end_us=55000,
             uart_during_execution=False),
        dict(event='run_complete', batches=1, tasks=4),
    ]


class ProfilerTests(unittest.TestCase):
    def analyze(self, events, *args):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'capture.jsonl'
            source.write_text(''.join(json.dumps(row) + '\n' for row in events))
            return subprocess.run([sys.executable, '-m', 'gearshift.profiler', str(source), *args],
                                  capture_output=True, text=True, timeout=10)

    def test_overload_statistics_are_recomputed_from_raw_timestamps(self):
        result = self.analyze(capture())
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        batch = report['batches'][0]
        self.assertEqual(batch['counts'], dict(ok=0, late=2, missed=2, failed=0))
        self.assertEqual(batch['deadline_failure_percent'], 100)
        self.assertEqual(batch['processing_ms'], dict(median=25, p95=25, maximum=25))
        self.assertEqual(batch['inference_ms'], dict(median=25, p95=25, maximum=25))
        self.assertAlmostEqual(batch['inferences_per_second'], 36.3636363636)
        self.assertTrue(report['simulated'])

    def test_partial_or_duplicated_capture_cannot_be_reported_as_complete(self):
        original = capture()
        missing_task = original[:3] + original[4:]
        duplicate = original[:3] + [copy.deepcopy(original[2])] + original[3:]
        for events in ([], original[:-1], original[:-2], missing_task, duplicate):
            with self.subTest(events=len(events)):
                result = self.analyze(events)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')

    def test_hardware_memory_snapshots_remain_separate_and_are_validated(self):
        events = capture()
        events[0].update(simulated=False, model_bytes=None)
        before = dict(free_heap_bytes=100, minimum_free_heap_bytes=80,
                      largest_free_block_bytes=90, stack_high_water_bytes=256,
                      result_buffer_bytes=64000, window_buffer_bytes=2048,
                      model_workspace_bytes=None)
        after = dict(before, free_heap_bytes=96, minimum_free_heap_bytes=72,
                     largest_free_block_bytes=80, stack_high_water_bytes=240)
        events[1]['memory'] = before
        events.insert(2, dict(event='series_memory', batch_id='b1', memory=after))
        result = self.analyze(events)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['batches'][0]['memory_before'], before)
        self.assertEqual(report['batches'][0]['memory_after'], after)
        self.assertIsNone(report['metadata']['model_bytes'])
        for value in (-1, True, None, '100'):
            bad = copy.deepcopy(events)
            bad[2]['memory']['free_heap_bytes'] = value
            self.assertNotEqual(self.analyze(bad).returncode, 0)

    def test_contradictory_task_timestamps_and_status_are_rejected(self):
        changes = [dict(status='ok'), dict(scheduled_us=1), dict(started_us=-1),
                   dict(index=True), dict(inference_finished_us=26000),
                   dict(finished_us=float('nan')), dict(status='unknown'),
                   dict(window_index=1), dict(error='model_error')]
        for change in changes:
            events = capture()
            events[2].update(change)
            with self.subTest(change=change):
                result = self.analyze(events)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')

    def test_invalid_run_and_series_metadata_are_not_silently_accepted(self):
        for index, fields in [(0, dict(expected_batches=True)), (0, dict(mode=None)),
                              (1, dict(series=1.5)), (1, dict(phase='unknown')),
                              (1, dict(uart_wait_us=-1)), (-2, dict(count=4.0)),
                              (-1, dict(tasks=4.0))]:
            events = capture()
            events[index].update(fields)
            with self.subTest(fields=fields):
                result = self.analyze(events)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
