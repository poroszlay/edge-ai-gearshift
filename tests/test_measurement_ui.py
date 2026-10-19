"""Offscreen acceptance tests exercise real widgets, workers and simulator IO."""
import json
import os
import queue
import socket
import tempfile
import threading
import time
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from gearshift.client import example_window
from gearshift.measurement import Settings, Session, export_csv, read_csv, summary
from gearshift.protocol import Wire
from gearshift.simulator import Device

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtCore import QTimer, QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication, QFileDialog
    from gearshift.gui import Window
    HAS_QT = True
except ImportError:
    HAS_QT = False


class ArchiveTests(unittest.TestCase):
    def test_export_roundtrip_preserves_every_event_and_accounting(self):
        session = Session(Settings(mode='benchmark', duration_ms=25))
        session.start()
        deadline = time.monotonic() + 15
        while not session.done.is_set() and time.monotonic() < deadline:
            try:
                session.events.get(timeout=.05)
            except queue.Empty:
                pass
        self.assertTrue(session.done.is_set())
        session.thread.join(1)
        self.assertEqual(session.rows[-1]['event'], 'run_complete')
        results = [r for r in session.rows if r['event'] == 'result']
        self.assertEqual(len(results), 12400)
        self.assertTrue(any(r['status'] == 'missed' for r in results))
        self.assertTrue(any(r['status'] == 'late' for r in results))
        self.assertTrue(all(r['simulated'] for r in session.rows))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'result.csv'
            export_csv(path, session.rows)
            loaded = read_csv(path)
            # JSON roundtrip changes tuple settings to a list, intentionally.
            self.assertEqual(loaded, json.loads(json.dumps(session.rows)))
            self.assertEqual(summary(loaded), summary(session.rows))
            self.assertEqual(sum(g['scheduled'] for k, g in summary(loaded).items()
                                 if k[0] == 'measured'), 12000)
            for counts in summary(loaded).values():
                self.assertEqual(counts['scheduled'], sum(counts.get(k, 0)
                    for k in ('ok', 'late', 'missed', 'invalid_window')))


@unittest.skipUnless(HAS_QT, 'Install requirements-ui.txt for GUI acceptance tests')
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = Window()
        self.window.show()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.cleanup_window)

    def cleanup_window(self):
        if self.window.session and not self.window.finished:
            self.window.stop()
            self.wait_for(lambda: self.window.finished)
        self.window.close()
        self.window.timer.stop()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def wait_for(self, predicate, seconds=15):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(predicate(), self.window.status.text())

    def click(self, button):
        button.click()

    def export(self, name='result.csv'):
        path = str(Path(self.directory.name) / name)
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(path, 'CSV')):
            self.click(self.window.export_button)
        self.wait_for(lambda: self.window.export_button.isEnabled())
        loaded = read_csv(path)
        self.assertEqual(summary(loaded), summary(self.window.session.rows))
        self.assertEqual(Counter((r['phase'], r['status']) for r in loaded
                                 if r['event'] == 'result'), self.window.counts)
        return loaded

    def test_select_start_stop_export_and_restart(self):
        self.window.device.setCurrentIndex(0)
        self.click(self.window.start_button)
        self.wait_for(lambda: self.window.result_index >= 3)
        self.assertTrue(self.window.time_curve.getData()[0].size > 0)
        self.click(self.window.stop_button)
        self.wait_for(lambda: self.window.finished)
        self.assertIn('részleges', self.window.status.text())
        loaded = self.export()
        self.assertEqual(loaded[-1]['event'], 'run_stopped')
        self.assertNotIn('run_complete', [r['event'] for r in loaded])
        old_id = loaded[0]['run_id']
        source = Path(self.directory.name) / 'windows.jsonl'
        source.write_text(json.dumps(example_window(0)) + '\n')
        self.window.input.setText(str(source))
        self.click(self.window.start_button)
        self.wait_for(lambda: self.window.finished)
        self.assertEqual(self.window.session.rows[-1]['event'], 'run_complete')
        self.assertNotEqual(old_id, self.window.session.rows[0]['run_id'])
        self.export('restart.csv')

    def test_benchmark_four_profiles_post_execute_fetch_and_invalid_input(self):
        self.window.mode.setCurrentIndex(1)
        self.window.duration.setValue(25)
        source = Path(self.directory.name) / 'windows.jsonl'
        invalid = example_window(1)
        invalid['samples'][0][0] = -1
        source.write_text('\n'.join(json.dumps(w) for w in [example_window(0), invalid]) + '\n')
        self.window.input.setText(str(source))
        self.click(self.window.start_button)
        self.wait_for(lambda: self.window.finished)
        rows = self.export()
        self.assertEqual(rows[-1]['event'], 'run_complete')
        results = [r for r in rows if r['event'] == 'result']
        self.assertEqual(len(results), 12400)
        self.assertEqual({r['period_ms'] for r in results}, {10, 20, 50, 100})
        self.assertTrue(any(r['status'] == 'invalid_window' and r['error'] for r in results))
        self.assertTrue(any(r['status'] == 'missed' for r in results))
        self.assertTrue(any(r['status'] == 'late' for r in results))
        executing = False
        for row in rows:
            if row['event'] == 'send' and row['message']['type'] == 'execute':
                executing = True
            elif row['event'] == 'receive' and 'uart_during_execution' in row['message']:
                self.assertFalse(row['message']['uart_during_execution'])
                executing = False
            elif row['event'] == 'result':
                self.assertFalse(executing)
        self.assertTrue(self.window.memory_curve.getData()[0].size > 0)
        self.assertLessEqual(len(self.window.points), 2000)
        evidence = os.environ.get('UI_EVIDENCE_DIR')
        if evidence:
            directory = Path(evidence)
            directory.mkdir(parents=True, exist_ok=True)
            self.assertTrue(self.window.grab().save(str(directory / 'benchmark.png')))

    def test_selected_profile_only(self):
        self.window.mode.setCurrentIndex(1)
        for period, box in self.window.profiles:
            box.setChecked(period == 20)
        self.click(self.window.start_button)
        self.wait_for(lambda: self.window.finished)
        rows = self.export()
        self.assertEqual({r['period_ms'] for r in rows if r['event'] == 'result'}, {20})
        self.assertEqual(sum(r['event'] == 'result' for r in rows), 3100)

    def test_invalid_memory_ack_can_finish_export_and_restart_in_both_modes(self):
        source = Path(self.directory.name) / 'windows.jsonl'
        source.write_text('\n'.join(json.dumps(example_window(i)) for i in range(2)) + '\n')
        self.window.input.setText(str(source))
        original_handle = Device.handle
        for mode in (0, 1):
            with self.subTest(mode=mode):
                self.window.mode.setCurrentIndex(mode)
                # Fail the second execute so earlier results must survive too.
                def malformed_ack(device, request):
                    reply = original_handle(device, request)
                    if request['type'] == 'execute':
                        device.ui_test_executes = getattr(device, 'ui_test_executes', 0) + 1
                        if device.ui_test_executes == 2:
                            reply['simulated_memory_bytes'] = 'bad'
                    return reply
                self.window.timer.stop()  # Propagate poll exceptions into the test.
                with patch.object(Device, 'handle', malformed_ack):
                    self.click(self.window.start_button)
                    deadline = time.monotonic() + 5
                    while not self.window.finished and time.monotonic() < deadline:
                        self.window.poll()
                        self.app.processEvents()
                        time.sleep(.005)
                    self.assertTrue(self.window.finished)
                self.window.timer.start()
                self.assertIn('Hibás', self.window.status.text())
                self.assertTrue(self.window.start_button.isEnabled())
                self.assertTrue(self.window.export_button.isEnabled())
                self.assertFalse(self.window.stop_button.isEnabled())
                self.assertTrue(all(isinstance(y, (int, float)) for _, y in self.window.memory))
                for _ in range(3):
                    self.window.poll()  # A later tick must not repeat a plotting error.
                rows = self.export(f'invalid-memory-{mode}.csv')
                self.assertEqual(rows, json.loads(json.dumps(self.window.session.rows)))
                self.assertEqual(rows[-1]['event'], 'run_failed')
                self.assertEqual(rows[-1]['error'], 'invalid_simulated_memory_bytes')
                self.assertNotIn('run_complete', [r['event'] for r in rows])
                bad_ack, = [r for r in rows if r['event'] == 'receive'
                            and r['message'].get('simulated_memory_bytes') == 'bad']
                self.assertTrue(bad_ack['simulated'])
                self.assertTrue(any(r['event'] == 'result' for r in rows))
                self.assertIn('Hibás', self.window.status.text())
                evidence = os.environ.get('UI_EVIDENCE_DIR')
                if evidence:
                    directory = Path(evidence)
                    directory.mkdir(parents=True, exist_ok=True)
                    self.assertTrue(self.window.grab().save(str(directory / f'invalid-memory-{mode}.png')))
                old_id = rows[0]['run_id']
                self.click(self.window.start_button)
                self.wait_for(lambda: self.window.finished)
                self.assertEqual(self.window.session.rows[-1]['event'], 'run_complete')
                self.assertNotEqual(self.window.session.rows[0]['run_id'], old_id)
                self.export(f'restarted-memory-{mode}.csv')

    def test_timeout_disconnect_device_error_are_visible_and_exportable(self):
        for fault in ('timeout', 'disconnected', 'firmware_error'):
            with self.subTest(fault=fault):
                listener = socket.socket()
                listener.bind(('127.0.0.1', 0))
                listener.listen(1)
                def serve():
                    with listener:
                        conn, _ = listener.accept()
                        with conn:
                            request = Wire(conn).receive()
                            if fault == 'timeout':
                                time.sleep(.4)
                            elif fault == 'firmware_error':
                                device = Device()
                                response = device.handle(request)
                                response.update(type='error', code='invalid_state')
                                Wire(conn).send(response)
                server = threading.Thread(target=serve, daemon=True)
                server.start()
                self.window.device.setCurrentIndex(1)
                self.window.port.setValue(listener.getsockname()[1])
                self.window.timeout.setValue(.2)
                ticks = []
                timer = QTimer()
                timer.timeout.connect(lambda: ticks.append(1))
                timer.start(10)
                self.click(self.window.start_button)
                self.wait_for(lambda: self.window.finished)
                timer.stop()
                rows = self.export(f'{fault}.csv')
                self.assertEqual(rows[-1]['event'], 'run_failed')
                self.assertNotIn('run_complete', [r['event'] for r in rows])
                expected = 'invalid_state' if fault == 'firmware_error' else fault
                self.assertIn(expected, rows[-1]['error'])
                if fault == 'timeout':
                    self.assertGreater(len(ticks), 5, 'GUI timer must run during IO')
                self.assertIn('Hibás', self.window.status.text())
                server.join(1)

    def test_slow_file_operations_keep_event_loop_running_and_export_error(self):
        source = Path(self.directory.name) / 'windows.jsonl'
        source.write_text(json.dumps(example_window(0)) + '\n')
        self.window.input.setText(str(source))
        original_open = open
        def slow_open(*args, **kwargs):
            if args[0] == str(source):
                time.sleep(.25)
            return original_open(*args, **kwargs)
        ticks = []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(10)
        with patch('gearshift.measurement.open', slow_open, create=True):
            self.click(self.window.start_button)
            self.wait_for(lambda: self.window.finished)
        self.assertGreater(len(ticks), 10)
        ticks.clear()
        original_export = export_csv
        def slow_export(*args):
            time.sleep(.25)
            original_export(*args)
        with patch('gearshift.gui.export_csv', slow_export):
            self.export()
        self.assertGreater(len(ticks), 10)
        self.window.export_to(str(Path(self.directory.name) / 'absent' / 'fail.csv'))
        self.wait_for(lambda: self.window.export_button.isEnabled())
        self.assertIn('Exporthiba', self.window.export_status.text())
        timer.stop()

    def test_stop_interrupts_pending_socket_and_close_waits_without_blocking(self):
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        accepted = threading.Event()
        def serve():
            with listener:
                conn, _ = listener.accept()
                with conn:
                    Wire(conn).receive()
                    accepted.set()
                    conn.recv(1)  # Stop must interrupt the client's pending receive.
        server = threading.Thread(target=serve, daemon=True)
        server.start()
        self.window.device.setCurrentIndex(1)
        self.window.port.setValue(listener.getsockname()[1])
        self.window.timeout.setValue(30)
        self.click(self.window.start_button)
        self.wait_for(accepted.is_set)
        started = time.monotonic()
        self.window.close()
        self.wait_for(lambda: self.window.finished, seconds=2)
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(self.window.session.rows[-1]['event'], 'run_stopped')
        server.join(1)


if __name__ == '__main__':
    unittest.main()
