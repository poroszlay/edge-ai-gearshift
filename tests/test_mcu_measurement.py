"""Exercise the public C++ runner with a host compiler, without ESP-IDF."""
import pathlib
import json
import subprocess
import tempfile
import unittest


class McuMeasurementTests(unittest.TestCase):
    def test_public_runner(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        module = root / 'firmware/esp32/components/measurement'
        with tempfile.TemporaryDirectory() as directory:
            executable = str(pathlib.Path(directory) / 'measurement-test')
            build = subprocess.run([
                'g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pedantic',
                '-I', str(module / 'include'), str(root / 'tests/mcu_measurement_test.cc'),
                str(module / 'measurement.cc'), '-o', executable,
            ], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run([executable], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_probe_exports_all_12400_scheduled_tasks_without_a_model(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        module = root / 'firmware/esp32/components/measurement'
        with tempfile.TemporaryDirectory() as directory:
            executable = str(pathlib.Path(directory) / 'probe')
            build = subprocess.run([
                'g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pedantic',
                '-I', str(module / 'include'), str(module / 'measurement.cc'),
                str(root / 'firmware/esp32/measurement/main/probe.cc'), '-o', executable,
            ], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([executable], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            rows = [json.loads(line) for line in run.stdout.splitlines()]
            self.assertTrue(rows[0]['simulated'])
            self.assertEqual(rows[-1], dict(event='run_complete', batches=16, tasks=12400))
            source = pathlib.Path(directory) / 'probe.jsonl'
            source.write_text(run.stdout)
            analysis = subprocess.run([
                'python3', '-m', 'gearshift.profiler', str(source), '--require-benchmark',
            ], cwd=root, capture_output=True, text=True, timeout=10)
            self.assertEqual(analysis.returncode, 0, analysis.stderr)
            batches = json.loads(analysis.stdout)['batches']
            self.assertEqual(sum(b['scheduled'] for b in batches if b['phase'] == 'warmup'), 400)
            self.assertEqual(sum(b['scheduled'] for b in batches if b['phase'] == 'measured'), 12000)
            first = next(b for b in batches if b['phase'] == 'measured' and b['period_us'] == 10000)
            self.assertEqual(first['counts'], dict(ok=0, late=334, missed=666, failed=0))

    def test_live_probe_exports_one_result_per_window_outside_processing(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        module = root / 'firmware/esp32/components/measurement'
        with tempfile.TemporaryDirectory() as directory:
            executable = str(pathlib.Path(directory) / 'live-probe')
            build = subprocess.run([
                'g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pedantic',
                '-I', str(module / 'include'), str(module / 'measurement.cc'),
                str(root / 'firmware/esp32/measurement/main/probe.cc'), '-o', executable,
            ], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([executable, '--live'], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            rows = [json.loads(line) for line in run.stdout.splitlines()]
            self.assertEqual(rows[0]['mode'], 'live')
            self.assertEqual(rows[-1], dict(event='run_complete', batches=3, tasks=3))
            tasks = [r for r in rows if r['event'] == 'task']
            self.assertEqual([r['window_index'] for r in tasks], [0, 0, 0])
            self.assertEqual([r['finished_us'] for r in tasks], [25000, 25000, 25000])
            self.assertTrue(all(r['status'] == 'ok' and 'decision' not in r for r in tasks))
            again = subprocess.run([executable, '--live'], capture_output=True, text=True, timeout=10)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertNotEqual(rows[0]['run_id'], json.loads(again.stdout.splitlines()[0])['run_id'])
