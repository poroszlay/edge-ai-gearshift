"""Command-line client and reproducible simulator smoke test."""
import argparse
import json
import socket
import sys
import threading
import time
import uuid
from .protocol import MAX_BATCH, VERSION, ProtocolError, Wire, encode, identifier, number, validate_result
from .simulator import serve_connection


def example_window(index):
    return dict(window_id=f'w{index}', trip_id='demo-trip',
                timestamps_ms=[index * 50 + i * 50 for i in range(20)],
                samples=[[40, .4, 0, 1, 12] for _ in range(20)])


class Client:
    def __init__(self, sock, output, mode, timeout=5):
        self.wire, self.output = Wire(sock, timeout), output
        self.mode, self.run_id = mode, uuid.uuid4().hex
        self.sequence = 0
        self.started = self.last_batch_end = time.monotonic()

    def log(self, event, **fields):
        # Every line is independently identifiable as simulation evidence.
        self.output.write(json.dumps(dict(v=VERSION, run_id=self.run_id, mode=self.mode,
                                          simulated=True, event=event,
                                          host_elapsed_ms=(time.monotonic() - self.started) * 1000, **fields), allow_nan=False) + '\n')
        self.output.flush()

    def request(self, kind, **fields):
        self.sequence += 1
        request = dict(v=VERSION, type=kind, request_id=str(self.sequence),
                       run_id=self.run_id, mode=self.mode, **fields)
        start = time.monotonic()
        self.log('send', message=request)
        try:
            self.wire.send(request)
            reply = self.wire.receive()
            if any(reply.get(k) != request[k] for k in ('v', 'run_id', 'request_id', 'mode')) or reply.get('simulated') is not True:
                raise ProtocolError('response_identity_mismatch')
            self.log('receive', message=reply, uart_wait_ms=(time.monotonic() - start) * 1000)
            if reply.get('type') == 'error':
                raise ProtocolError(reply.get('code', 'device_error'))
            if reply.get('type') != ('results' if kind == 'fetch' else 'ack'):
                raise ProtocolError('unexpected_response')
            return reply
        except (ProtocolError, OSError) as exc:
            self.log('failure', error=str(exc), request_id=request['request_id'])
            raise

    def batch(self, windows, batch_id, count=1, period=50, phase='live', series=0):
        self.log('batch_start', batch_id=batch_id, window_ids=[w['window_id'] for w in windows],
                 phase=phase, series=series, period_ms=period,
                 inter_batch_wait_ms=(time.monotonic() - self.last_batch_end) * 1000)
        ack = self.request('load', batch_id=batch_id, windows=windows)
        if ack.get('batch_id') != batch_id or ack.get('count') != len(windows):
            raise ProtocolError('load_ack_mismatch')
        ack = self.request('execute', batch_id=batch_id, count=count, period_ms=period)
        if ack.get('count') != count or ack.get('batch_id') != batch_id or ack.get('uart_during_execution') is not False:
            raise ProtocolError('execute_ack_mismatch')
        memory = ack.get('simulated_memory_bytes')
        if type(memory) is not int or not number(memory) or memory < 0:
            self.log('failure', error='invalid_simulated_memory_bytes', request_id=str(self.sequence))
            raise ProtocolError('invalid_simulated_memory_bytes')
        # Raw receive events remain lossless, including malformed ACKs. Only
        # validated measurement events are suitable for presentation.
        self.log('batch_memory', batch_id=batch_id, phase=phase, series=series,
                 period_ms=period, simulated_memory_bytes=memory)
        offset = 0
        while offset < count:
            reply = self.request('fetch', batch_id=batch_id, offset=offset)
            records = reply.get('records')
            if reply.get('batch_id') != batch_id or reply.get('offset') != offset or reply.get('total') != count or not isinstance(records, list) or not 1 <= len(records) <= min(16, count - offset):
                raise ProtocolError('result_page_mismatch')
            for i, record in enumerate(records, offset):
                error = validate_result(record, period)
                if error:
                    self.log('failure', error=error, request_id=str(self.sequence))
                    raise ProtocolError(error)
                if record.get('index') != i or record.get('window_id') != windows[i % len(windows)]['window_id'] or record.get('batch_id') != batch_id:
                    self.log('failure', error='result_identity_mismatch', request_id=str(self.sequence))
                    raise ProtocolError('result_identity_mismatch')
                # Wire extensions must not become arguments or metadata in the export.
                result = {key: record[key] for key in (
                    'index', 'window_id', 'batch_id', 'scheduled_ms', 'status',
                    'processing_ms', 'decision', 'decision_source', 'error') if key in record}
                self.log('result', phase=phase, series=series, period_ms=period, **result)
            offset += len(records)
        self.log('batch_end', batch_id=batch_id, count=count)
        self.last_batch_end = time.monotonic()

    def run(self, windows, profiles=(10, 20, 50, 100), cancelled=None):
        if not profiles or any(type(p) is not int or p not in (10, 20, 50, 100) for p in profiles) or len(set(profiles)) != len(profiles):
            raise ProtocolError('invalid_profile')
        def check_cancelled():
            if cancelled is not None and cancelled():
                raise ProtocolError('cancelled')
        check_cancelled()
        if not windows or (self.mode == 'benchmark' and len(windows) > MAX_BATCH) or any(
                not isinstance(w, dict) or not identifier(w.get('window_id'))
                or not identifier(w.get('trip_id')) for w in windows):
            raise ProtocolError('invalid_input_identity')
        ids = [w['window_id'] for w in windows]
        if len(set(ids)) != len(ids):
            raise ProtocolError('duplicate_window_id')
        self.request('start')
        if self.mode == 'live':
            for i, window in enumerate(windows):
                check_cancelled()
                self.batch([window], f'live-{i}')
        else:
            for period in profiles:
                check_cancelled()
                self.batch(windows, f'p{period}-warmup', 100, period, 'warmup')
                for series in range(1, 4):
                    check_cancelled()
                    self.batch(windows, f'p{period}-s{series}', 1000, period, 'measured', series)
        check_cancelled()
        self.log('run_complete')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--demo', action='store_true', help='run an in-process socket simulator')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--mode', choices=('live', 'benchmark'), default='live')
    parser.add_argument('--timeout', type=float, default=5)
    parser.add_argument('--input', help='JSON Lines windows; benchmark working set is at most eight windows')
    parser.add_argument('--output', default='simulation.jsonl')
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('timeout must be positive')
    worker = None
    try:
        windows = []
        if args.input:
            with open(args.input, 'rb') as source:
                while True:
                    line = source.readline(16385)
                    if not line:
                        break
                    if len(line) > 16384 or (args.mode == 'benchmark' and len(windows) == MAX_BATCH):
                        raise ProtocolError('input_limit_exceeded')
                    windows.append(json.loads(line))
        else:
            windows = [example_window(i) for i in range(3)]
        if not windows:
            raise ProtocolError('empty_input')
        # Live sends one window per load; only benchmark loads the whole working set.
        batches = ([w] for w in windows) if args.mode == 'live' else [windows]
        for batch in batches:
            encode(dict(v=1, type='load', windows=batch, batch_id='b', request_id='1',
                        run_id='x' * 32, mode=args.mode))
        if args.demo:
            sock, peer = socket.socketpair()
            def simulate():
                with peer:
                    serve_connection(peer, args.timeout)
            worker = threading.Thread(target=simulate, daemon=True)
            worker.start()
        else:
            sock = socket.create_connection((args.host, args.port), timeout=args.timeout)
        with sock, open(args.output, 'w', encoding='utf-8') as output:
            Client(sock, output, args.mode, args.timeout).run(windows)
        if worker:
            worker.join(args.timeout)
        print(f'Simulated {args.mode} run complete: {args.output}')
        return 0
    except (ProtocolError, OSError, ValueError) as exc:
        print(f'Run failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
