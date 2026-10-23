"""User-approved hardware protocol, UART and comparison boundaries (#7)."""
import copy
import io
import json
import unittest
import importlib.util
from gearshift.protocol import validate_result

MODEL = '6d5ac8613d301ca06de2ca9a4cfbadf3cd40c7c75a7af419505eaa9fcbb25f79'


def hardware_record():
    return dict(index=0, window_id='w0', batch_id='b', scheduled_ms=0,
                status='ok', processing_ms=3, decision='upshift', decision_source='int8_mlp',
                model_id=MODEL, input_int8=[0] * 100, output_int8=[-128, -100, 100],
                started_us=0, inference_started_us=100, inference_finished_us=2900,
                finished_us=3000)


class HardwareContractTests(unittest.TestCase):
    def test_hardware_result_accepts_mlp_and_keeps_simulator_contract_strict(self):
        record = hardware_record()
        self.assertIsNone(validate_result(record, 50, simulated=False, model_id=MODEL))
        self.assertEqual(validate_result(record, 50), 'result_schema_mismatch')
        for field, bad in [('output_int8', [-128, -100, 128]), ('decision', 'hold'),
                           ('model_id', 'other'), ('input_int8', [0] * 99),
                           ('inference_finished_us', 4000)]:
            changed = dict(record, **{field: bad})
            self.assertEqual(validate_result(changed, 50, simulated=False, model_id=MODEL),
                             'result_schema_mismatch', field)

    def test_client_preserves_hardware_origin_numerics_and_memory_in_csv(self):
        from gearshift.client import Client, example_window
        from gearshift.measurement import export_csv, read_csv
        import tempfile
        from pathlib import Path
        # External byte transport double: no internal model/client mocks.
        class Peer:
            def settimeout(self, value):
                pass
            def sendall(self, data):
                r = json.loads(data)
                reply = {k: r[k] for k in ('v', 'request_id', 'run_id', 'mode')}
                reply.update(type='ack', simulated=False, model_id=MODEL)
                if r['type'] == 'start':
                    reply.update(dataset_id='d' * 64, class_order=['downshift', 'hold', 'upshift'])
                elif r['type'] == 'load':
                    reply.update(batch_id=r['batch_id'], count=1)
                elif r['type'] == 'execute':
                    snapshot = dict(free_heap_bytes=100000, minimum_free_heap_bytes=99000,
                                    largest_free_block_bytes=80000, stack_high_water_bytes=12000,
                                    result_buffer_bytes=60000, window_buffer_bytes=9000,
                                    model_workspace_bytes=32768, device_state_bytes=70000)
                    reply.update(batch_id=r['batch_id'], count=1, period_ms=50,
                                 uart_during_execution=False, end_us=50000, uart_wait_us=250,
                                 memory={'before': snapshot,
                                         'after': dict(snapshot, free_heap_bytes=99900)})
                else:
                    record = hardware_record()
                    record['batch_id'] = r['batch_id']
                    reply.update(type='results', batch_id=r['batch_id'], offset=0, total=1, records=[record])
                self.data = json.dumps(reply).encode() + b'\n'
            def recv(self, count):
                data, self.data = self.data[:count], self.data[count:]
                return data
        output = io.StringIO()
        Client(Peer(), output, 'live', simulated=False, model_id=MODEL).run([example_window(0)])
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertTrue(all(r['simulated'] is False for r in rows))
        result = next(r for r in rows if r['event'] == 'result')
        self.assertEqual(result['output_int8'], [-128, -100, 100])
        self.assertEqual(result['model_id'], MODEL)
        memory = next(r for r in rows if r['event'] == 'batch_memory')
        self.assertEqual(memory['memory']['after']['free_heap_bytes'], 99900)
        self.assertEqual(memory['uart_wait_us'], 250)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'hardware.csv'
            export_csv(path, rows)
            self.assertEqual(read_csv(path), rows)

        class MissingMemoryPeer(Peer):
            def sendall(self, data):
                super().sendall(data)
                reply = json.loads(self.data)
                if 'memory' in reply:
                    del reply['memory']['after']['minimum_free_heap_bytes']
                self.data = json.dumps(reply).encode() + b'\n'
        from gearshift.protocol import ProtocolError
        with self.assertRaisesRegex(ProtocolError, 'invalid_hardware_measurement'):
            Client(MissingMemoryPeer(), io.StringIO(), 'live', simulated=False, model_id=MODEL).run([example_window(0)])
        class ImpossibleWaitPeer(Peer):
            def sendall(self, data):
                super().sendall(data)
                reply = json.loads(self.data)
                if 'uart_wait_us' in reply:
                    reply['uart_wait_us'] = 10**12
                self.data = json.dumps(reply).encode() + b'\n'
        with self.assertRaisesRegex(ProtocolError, 'invalid_hardware_uart_wait'):
            Client(ImpossibleWaitPeer(), io.StringIO(), 'live', simulated=False, model_id=MODEL).run([example_window(0)])

class UartTests(unittest.TestCase):
    def test_uart_adapter_frames_real_pty_bytes_and_times_out(self):
        from gearshift.uart import SerialTransport
        from gearshift.protocol import Wire, ProtocolError
        import os
        import pty
        master, slave = pty.openpty()
        try:
            with SerialTransport(os.ttyname(slave)) as port:
                wire = Wire(port, .03)
                os.write(master, b'{"v":1,"type":"ack"}\n')
                self.assertEqual(wire.receive(), {'v': 1, 'type': 'ack'})
                wire.send({'v': 1, 'type': 'start'})
                self.assertEqual(json.loads(os.read(master, 1024)), {'v': 1, 'type': 'start'})
                with self.assertRaisesRegex(ProtocolError, 'timeout'):
                    wire.receive()
        finally:
            os.close(master)
            os.close(slave)

class FirmwareInputTests(unittest.TestCase):
    def test_firmware_raw_path_matches_frozen_pc_reference_and_boundary_rounding(self):
        import subprocess
        import tempfile
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        references = [json.loads(line) for line in (root / 'models/mlp-v2/pc-reference.jsonl').read_text().splitlines()]
        windows = [json.loads(line) for line in (root / 'models/mlp-v2/reference-windows.jsonl').read_text().splitlines()]
        meta = json.loads((root / 'models/mlp-v2/export.json').read_text())
        scale, zero = meta['input']['scales'][0], meta['input']['zero_points'][0]
        cases = []
        for window, reference in zip(windows, references):
            times = ','.join(str(t) for t in window['timestamps_ms'])
            samples = ','.join('{' + ','.join(repr(x) for x in sample) + '}' for sample in window['samples'])
            expected = ','.join(str(x) for x in reference['input_int8'])
            cases.append('''{ Window w; w.valid = true;
                const int64_t times[20] = {%s}; const double samples[20][5] = {%s};
                for(int i=0;i<20;++i) { w.timestamps[i]=times[i]; for(int j=0;j<5;++j) w.samples[i][j]=samples[i][j]; }
                int8_t actual[100]; const int expected[100] = {%s};
                assert(prepare_input(w, %.18g, %d, actual) == Error::none);
                for(int i=0;i<100;++i) assert(actual[i] == expected[i]);
                w.samples[0][0] = -1; assert(prepare_input(w, %.18g, %d, actual) == Error::invalid_window);
            }''' % (times, samples, expected, scale, zero, scale, zero))
        source = '''#include "inference.h"
#include <cassert>
#include <cmath>
using namespace gearshift::inference;
using gearshift::measurement::Error;
int main() { %s
assert(quantize(-.25f,.5f,-3)==-4); assert(quantize(.25f,.5f,-3)==-2);
assert(quantize(std::nextafter(.5f,0.f),1.f,0)==0);
assert(quantize(std::nextafter(-.5f,0.f),1.f,0)==0);
assert(quantize(100.f,.5f,-3)==127);
}''' % '\n'.join(cases)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'test.cc').write_text(source)
            build = subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pedantic',
                '-I', str(root / 'firmware/esp32/inference/main'),
                '-I', str(root / 'firmware/esp32/components/measurement/include'),
                str(path / 'test.cc'), '-o', str(path / 'test')], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(path / 'test')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

class FirmwareProtocolTests(unittest.TestCase):
    def test_firmware_quality_batch_visits_each_preloaded_window_once(self):
        import subprocess
        import tempfile
        from pathlib import Path
        from gearshift.client import example_window
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'firmware'
            build = subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pedantic',
                '-Itests/vendor/cjson', '-Ifirmware/esp32/inference/main',
                '-Ifirmware/esp32/components/measurement/include', 'tests/inference_host.cc',
                'firmware/esp32/inference/main/device.cc',
                'firmware/esp32/components/measurement/measurement.cc', 'tests/vendor/cjson/cJSON.c',
                '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            windows = [example_window(i) for i in range(3)]
            requests = [dict(type='start'), dict(type='load', batch_id='q', windows=windows),
                        dict(type='execute', batch_id='q', count=3, period_ms=0, purpose='quality'),
                        dict(type='fetch', batch_id='q', offset=0)]
            run = subprocess.run([str(binary)], input=''.join(json.dumps(dict(v=1,
                request_id=str(i+1), run_id='q', mode='benchmark', **r))+'\n' for i,r in enumerate(requests)),
                capture_output=True, text=True, timeout=10)
            replies = [json.loads(line) for line in run.stdout.splitlines()]
            self.assertEqual(replies[2]['type'], 'ack')
            self.assertEqual([r['window_id'] for r in replies[3]['records']], ['w0', 'w1', 'w2'])
            self.assertTrue(all(r['status'] == 'ok' for r in replies[3]['records']))
            self.assertEqual(replies[2]['end_us'], 75000)
            self.assertEqual([r['scheduled_ms'] for r in replies[3]['records']], [0, 0, 0])

    def test_native_firmware_protocol_preloads_executes_fetches_and_accounts_benchmark(self):
        import subprocess
        import tempfile
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'firmware'
            build = subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pedantic',
                '-Itests/vendor/cjson', '-Ifirmware/esp32/inference/main',
                '-Ifirmware/esp32/components/measurement/include',
                'tests/inference_host.cc', 'firmware/esp32/inference/main/device.cc',
                'firmware/esp32/components/measurement/measurement.cc', 'tests/vendor/cjson/cJSON.c',
                '-o', str(binary)], cwd=root, capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            from gearshift.client import example_window
            window = example_window(0)
            requests = []
            def request(kind, **fields):
                requests.append(dict(v=1, type=kind, request_id=str(len(requests)+1),
                                     run_id='native-fixture', mode='benchmark', **fields))
            request('start')
            request('load', batch_id='b', windows=[window])
            request('execute', batch_id='b', count=100, period_ms=10)
            request('load', batch_id='illegal', windows=[window])
            for offset in range(0, 100, 8):
                request('fetch', batch_id='b', offset=offset)
            bad = copy.deepcopy(window)
            bad['samples'][0][0] = -1
            request('load', batch_id='bad', windows=[bad])
            request('execute', batch_id='bad', count=100, period_ms=20)
            request('fetch', batch_id='bad', offset=0)
            run = subprocess.run([str(binary)], input=''.join(json.dumps(r)+'\n' for r in requests),
                                 capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)
            replies = [json.loads(line) for line in run.stdout.splitlines()]
            self.assertEqual(len(replies), len(requests))
            self.assertTrue(all(r['simulated'] is True for r in replies))
            self.assertEqual(replies[3]['code'], 'batch_pending')
            records = [r for reply in replies[4:-3] for r in reply['records']]
            self.assertEqual([r['index'] for r in records], list(range(100)))
            # A 25ms runtime double on a 10ms grid: no queue, 34 late + 66 missed.
            from collections import Counter
            self.assertEqual(Counter(r['status'] for r in records), {'late': 34, 'missed': 66})
            successful = [r for r in records if r['status'] == 'late']
            self.assertTrue(all(r['output_int8'] == [-128, 100, -100] for r in successful))
            self.assertTrue(all(r['decision'] == 'hold' for r in successful))
            self.assertTrue(all(r['status'] == 'invalid_window' and 'decision' not in r
                                for r in replies[-1]['records']))
            self.assertFalse(replies[2]['uart_during_execution'])
            self.assertGreaterEqual(replies[2]['end_us'], 1000000)
            for argument, status in [('--model-error', 'model_error'), ('--memory-error', 'memory_error')]:
                failed = subprocess.run([str(binary), argument],
                    input=''.join(json.dumps(r)+'\n' for r in requests[:3]+[requests[4]]),
                    capture_output=True, text=True, timeout=10)
                errors = [json.loads(line) for line in failed.stdout.splitlines()][-1]['records']
                expected_statuses = (['model_error', 'missed', 'missed', 'model_error',
                                      'missed', 'missed', 'model_error', 'missed']
                                     if argument == '--model-error' else ['memory_error'] * 8)
                self.assertEqual([r['status'] for r in errors], expected_statuses)
                self.assertTrue(all('decision' not in r and 'output_int8' not in r for r in errors))
                self.assertTrue(all(r['error'] == status for r in errors if r['status'] != 'missed'))

@unittest.skipUnless(importlib.util.find_spec('numpy'), 'install requirements-model.txt for quality metrics')
class PortingReportTests(unittest.TestCase):
    def test_porting_report_separates_raw_input_mismatch_from_output_tolerance_and_quality(self):
        from gearshift.porting import porting_report
        pc = dict(window_id='w0', trip_id='t', model_id=MODEL, run_id='pc', status='ok',
                  input_int8=[0]*100, output_int8=[-128, -100, 100], decision='upshift',
                  reference_class_index=1)
        actual = dict(hardware_record(), run_id='mcu', simulated=False)
        actual['output_int8'] = [-127, -101, 99]
        report = porting_report([pc], [actual])
        self.assertTrue(report['porting_passed'])
        self.assertEqual(report['max_output_code_difference'], 1)
        self.assertEqual(report['quality']['confusion_matrix'], [[0,0,0], [0,0,1], [0,0,0]])
        self.assertFalse(report['quality_target_met'])
        actual['input_int8'][0] = 1
        report = porting_report([pc], [actual])
        self.assertFalse(report['porting_passed'])
        self.assertEqual(report['differences'][0]['kind'], 'input_mismatch')
        self.assertEqual((report['differences'][0]['run_id'], report['differences'][0]['model_id'],
                          report['differences'][0]['window_id']), ('mcu', MODEL, 'w0'))
        actual['input_int8'][0] = 0
        actual['output_int8'][0] = -125
        self.assertFalse(porting_report([pc], [actual])['porting_passed'])
        actual['output_int8'] = [100, -100, -128]
        actual['decision'] = 'downshift'
        self.assertFalse(porting_report([pc], [actual])['porting_passed'])
        with self.assertRaisesRegex(ValueError, 'coverage'):
            porting_report([pc], [])
        with self.assertRaisesRegex(ValueError, 'coverage'):
            porting_report([pc], [actual, actual])

class HardwareSessionTests(unittest.TestCase):
    def test_missing_uart_keeps_hardware_origin_and_never_completes(self):
        from gearshift.measurement import Session, Settings
        session = Session(Settings(demo=False, serial_port='/no/such/uart', model_id=MODEL))
        session.start()
        self.assertTrue(session.done.wait(2))
        self.assertEqual(session.rows[-1]['event'], 'run_failed')
        self.assertTrue(all(r['simulated'] is False for r in session.rows))
        self.assertFalse(any(r['event'] == 'run_complete' for r in session.rows))

class UartCaptureTests(unittest.TestCase):
    def test_capture_keeps_received_bytes_and_transmit_boundaries(self):
        import os
        import pty
        import tempfile
        from pathlib import Path
        from gearshift.uart import SerialTransport
        master, slave = pty.openpty()
        try:
            with tempfile.TemporaryDirectory() as directory:
                prefix = Path(directory) / 'wire'
                with SerialTransport(os.ttyname(slave), capture_prefix=prefix) as port:
                    os.write(master, b'raw boot\r\n')
                    self.assertEqual(port.recv(100), b'raw boot\r\n')
                    port.sendall(b'{"v":1}\n')
                    self.assertEqual(os.read(master, 100), b'{"v":1}\n')
                self.assertEqual(Path(str(prefix)+'.rx').read_bytes(), b'raw boot\r\n')
                self.assertEqual(Path(str(prefix)+'.tx').read_bytes(), b'{"v":1}\n')
                chunks = [json.loads(x) for x in Path(str(prefix)+'.chunks.jsonl').read_text().splitlines()]
                self.assertEqual([c['direction'] for c in chunks], ['rx', 'tx'])
                self.assertEqual([c['offset'] for c in chunks], [0, 0])
        finally:
            os.close(master)
            os.close(slave)

class HardwareMeasurementReportTests(unittest.TestCase):
    def test_real_live_log_is_analyzable_and_incomplete_accounting_is_rejected(self):
        from gearshift.run_report import analyze_run
        from pathlib import Path
        rows = [json.loads(x) for x in Path('docs/evidence/issue-7/initial-live.jsonl').read_text().splitlines()]
        report = analyze_run(rows)
        self.assertFalse(report['simulated'])
        self.assertEqual(sum(b['scheduled'] for b in report['batches']), 11)
        self.assertEqual(report['workload'], 'int8_mlp')
        self.assertTrue(all(b['inference_ms']['maximum'] > 0 for b in report['batches']))
        changed = copy.deepcopy(rows)
        changed.pop(next(i for i,r in enumerate(changed) if r['event'] == 'result'))
        with self.assertRaises(ValueError):
            analyze_run(changed)
        changed = copy.deepcopy(rows)
        for r in changed:
            if r['event'] == 'batch_memory':
                r['uart_wait_us'] = 10**12
            elif r['event'] == 'receive' and 'end_us' in r['message']:
                r['message']['uart_wait_us'] = 10**12
        with self.assertRaisesRegex(ValueError, 'UART'):
            analyze_run(changed)

class DeadlineTests(unittest.TestCase):
    def test_quality_visits_every_window_without_a_realtime_deadline(self):
        record = hardware_record()
        record.update(index=1, started_us=25000, inference_started_us=25100,
                      inference_finished_us=27900, finished_us=28000)
        self.assertIsNone(validate_result(record, 0, simulated=False, model_id=MODEL, quality=True))
        self.assertEqual(validate_result(record, 0, simulated=False, model_id=MODEL), 'result_schema_mismatch')

    def test_hardware_deadline_is_measured_from_scheduled_start(self):
        record = hardware_record()
        record.update(status='late', started_us=1000, inference_started_us=1500,
                      inference_finished_us=50900, finished_us=51000, processing_ms=50)
        self.assertIsNone(validate_result(record, 50, simulated=False, model_id=MODEL))

class HardwareSessionFailureTests(unittest.TestCase):
    def test_invalid_expected_model_terminates_the_worker_without_losing_origin(self):
        from gearshift.measurement import Session, Settings
        session = Session(Settings(demo=False, serial_port='/no/such/uart', model_id=''))
        session.start()
        self.assertTrue(session.done.wait(2), 'worker must finish even when the model ID is missing')
        self.assertEqual(session.rows[-1]['event'], 'run_failed')
        self.assertFalse(session.rows[-1]['simulated'])
        self.assertIn('expected_model_id_required', session.rows[-1]['error'])

@unittest.skipUnless(importlib.util.find_spec('tensorflow'), 'install requirements-model.txt for final evaluation')
class FrozenCampaignTests(unittest.TestCase):
    def test_final_evaluation_rejects_unfrozen_model_before_reading_locked_test(self):
        from gearshift.campaign import prepare
        import tempfile
        import shutil
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree('models/mlp-v2', root / 'model')
            freeze = json.loads((root / 'model/freeze.json').read_text())
            freeze['frozen'] = False
            (root / 'model/freeze.json').write_text(json.dumps(freeze))
            with self.assertRaisesRegex(ValueError, 'frozen'):
                prepare(root / 'not-readable-test', root / 'model', root / 'output')

class UartSilenceTests(unittest.TestCase):
    def test_capture_rejects_response_bytes_before_execution_finished(self):
        from gearshift.uart_evidence import audit_capture
        import tempfile
        from pathlib import Path
        from gearshift.protocol import encode
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / 'capture'
            request = dict(v=1, type='execute', request_id='1', run_id='r', mode='benchmark',
                           batch_id='b', count=100, period_ms=10)
            response = dict(v=1, type='ack', request_id='1', run_id='r', mode='benchmark',
                            simulated=False, model_id=MODEL, batch_id='b', count=100,
                            end_us=1000000, uart_during_execution=False)
            tx, rx = encode(request), encode(response)
            Path(str(prefix)+'.tx').write_bytes(tx)
            Path(str(prefix)+'.rx').write_bytes(rx)
            chunks = [dict(direction='tx', offset=0, bytes=len(tx), elapsed_s=.1),
                      dict(direction='rx', offset=0, bytes=len(rx), elapsed_s=1.11)]
            def save():
                Path(str(prefix)+'.chunks.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in chunks))
            save()
            report = audit_capture(prefix)
            self.assertEqual(report['execution_count'], 1)
            self.assertTrue(report['observed_uart_silence'])
            chunks[1]['elapsed_s'] = .2
            save()
            with self.assertRaisesRegex(ValueError, 'execution'):
                audit_capture(prefix)
