import copy
import io
import json
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from gearshift.client import Client, example_window
from gearshift.protocol import MAX_LINE, ProtocolError, Wire, preprocess
from gearshift.simulator import Device, serve_connection


class CommunicationTests(unittest.TestCase):
    def connection(self, timeout=.5):
        a, b = socket.socketpair()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        def serve():
            with b:
                serve_connection(b, timeout)
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 1)
        return a

    def test_both_modes_complete_and_every_export_is_marked(self):
        for mode, expected in [('live', 3), ('benchmark', 12400)]:
            with self.subTest(mode=mode):
                output = io.StringIO()
                Client(self.connection(2), output, mode, 2).run([example_window(i) for i in range(3)])
                rows = [json.loads(line) for line in output.getvalue().splitlines()]
                self.assertTrue(all(r['simulated'] and r['mode'] == mode for r in rows))
                results = [r for r in rows if r['event'] == 'result']
                self.assertEqual(len(results), expected)
                self.assertEqual(rows[-1]['event'], 'run_complete')
                if mode == 'benchmark':
                    self.assertEqual(sum(r['phase'] == 'measured' for r in results), 12000)
                    self.assertTrue(all(r['uart_during_execution'] is False for r in
                                        [x['message'] for x in rows if x['event'] == 'receive' and 'uart_during_execution' in x['message']]))

    def test_live_cli_processes_more_than_eight_windows(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'input.jsonl', Path(directory) / 'output.jsonl'
            source.write_text(''.join(json.dumps(example_window(i)) + '\n' for i in range(25)))
            result = subprocess.run([sys.executable, '-m', 'gearshift.client', '--demo',
                                     '--input', str(source), '--output', str(output)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            rows = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual([r['window_id'] for r in rows if r['event'] == 'result'],
                             [f'w{i}' for i in range(25)])
            self.assertEqual(sum(r['event'] == 'batch_end' for r in rows), 25)
            self.assertEqual(rows[-1]['event'], 'run_complete')

    def test_benchmark_working_set_remains_bounded(self):
        a, b = socket.socketpair()
        with a, b:
            output = io.StringIO()
            with self.assertRaisesRegex(ProtocolError, 'invalid_input_identity'):
                Client(a, output, 'benchmark').run([example_window(i) for i in range(9)])
            self.assertEqual(output.getvalue(), '')

    def test_load_preserves_unfetched_results(self):
        device = Device()
        def send(kind, **fields):
            return device.handle(dict(v=1, request_id='1', run_id='r', mode='benchmark',
                                      type=kind, **fields))
        send('start')
        send('load', batch_id='a', windows=[example_window(0)])
        send('execute', batch_id='a', count=100, period_ms=10)
        original = copy.deepcopy(device.records)
        def assert_pending():
            reply = send('load', batch_id='b', windows=[example_window(1)])
            self.assertEqual(reply.get('code'), 'batch_pending')
            self.assertEqual(device.batch_id, 'a')
            self.assertEqual(device.records, original)
        assert_pending()
        # Fetching the final page alone must not conceal earlier gaps.
        send('fetch', batch_id='a', offset=96)
        assert_pending()
        send('fetch', batch_id='a', offset=0)
        send('fetch', batch_id='a', offset=0)
        assert_pending()
        for offset in range(16, 96, 16):
            self.assertEqual(send('fetch', batch_id='a', offset=offset)['type'], 'results')
        self.assertEqual(send('load', batch_id='b', windows=[example_window(1)])['type'], 'ack')
        send('execute', batch_id='b', count=100, period_ms=10)
        self.assertEqual(send('load', batch_id='c', windows=[example_window(2)]).get('code'),
                         'batch_pending')

    def test_malformed_oversized_version_and_disconnect(self):
        for data, code in [(b'{oops}\n', 'invalid_json'), (b'NaN\n', 'invalid_json'),
                           (b'x' * (MAX_LINE + 1), 'message_too_large'),
                           (b'{"v":2}\n', 'unsupported_version')]:
            with self.subTest(code=code):
                sock = self.connection()
                sock.sendall(data)
                self.assertEqual(Wire(sock).receive()['code'], code)
        a, b = socket.socketpair()
        with a:
            b.close()
            with self.assertRaisesRegex(ProtocolError, 'disconnected'):
                Wire(a).receive()

    def test_timeout_and_partial_line(self):
        a, b = socket.socketpair()
        with a, b:
            b.sendall(b'{')
            with self.assertRaisesRegex(ProtocolError, 'timeout'):
                Wire(a, .02).receive()
        sock = self.connection(.03)
        self.assertEqual(Wire(sock).receive()['code'], 'timeout')

    def test_fragmented_and_coalesced_frames(self):
        a, b = socket.socketpair()
        with a, b:
            b.sendall(b'{"v":')
            b.sendall(b'1}\n{"v":2}\n')
            wire = Wire(a)
            self.assertEqual(wire.receive(), {'v': 1})
            self.assertEqual(wire.receive(), {'v': 2})

    def test_validation_and_scaling(self):
        w = example_window(0)
        self.assertEqual(preprocess(w)[:5], [.5, .4, 0, 0, 1])
        mutations = [lambda w: w['samples'].pop(),
                     lambda w: w['samples'][0].__setitem__(0, 81),
                     lambda w: w['samples'][0].__setitem__(1, float('nan')),
                     lambda w: w['samples'][0].__setitem__(0, 10 ** 400),
                     lambda w: w['timestamps_ms'].__setitem__(2, 101)]
        for mutation in mutations:
            invalid = copy.deepcopy(w)
            mutation(invalid)
            with self.assertRaises(ProtocolError):
                preprocess(invalid)

    def test_overload_and_invalid_windows(self):
        device = Device(duration_ms=25)
        seq = 0
        def send(kind, **fields):
            nonlocal seq
            seq += 1
            return device.handle(dict(v=1, request_id=str(seq), run_id='r', mode='benchmark', type=kind, **fields))
        send('start')
        windows = [example_window(0)]
        self.assertEqual(send('load', batch_id='b', windows=windows)['type'], 'ack')
        self.assertEqual(send('load', batch_id='c', windows=windows)['code'], 'batch_pending')
        send('execute', batch_id='b', period_ms=10, count=100)
        self.assertEqual([r['status'] for r in device.records[:4]], ['late', 'missed', 'missed', 'late'])
        self.assertEqual(len(device.records), 100)
        self.assertEqual(device.records[3]['scheduled_ms'], 30)
        for offset in range(0, 100, 16):
            send('fetch', batch_id='b', offset=offset)
        windows[0]['samples'][0][0] = -1
        send('load', batch_id='c', windows=windows)
        send('execute', batch_id='c', period_ms=10, count=100)
        self.assertTrue(all(r['status'] == 'invalid_window' and 'decision' not in r for r in device.records))

    def test_wrong_pairing_is_rejected(self):
        a, b = socket.socketpair()
        with a, b:
            b.sendall(b'{"v":1,"type":"ack","request_id":"wrong"}\n')
            output = io.StringIO()
            with self.assertRaisesRegex(ProtocolError, 'response_identity_mismatch'):
                Client(a, output, 'live').request('start')
            self.assertEqual(json.loads(output.getvalue().splitlines()[-1])['event'], 'failure')


if __name__ == '__main__':
    unittest.main()
