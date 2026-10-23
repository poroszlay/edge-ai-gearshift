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
    def __init__(self, sock, output, mode, timeout=5, *, simulated=True, model_id=None):
        if not simulated and (not isinstance(model_id, str) or len(model_id) != 64
                              or any(c not in '0123456789abcdef' for c in model_id)):
            raise ProtocolError('expected_model_id_required')
        self.wire, self.output = Wire(sock, timeout), output
        self.simulated, self.model_id = simulated, model_id
        self.mode, self.run_id = mode, uuid.uuid4().hex
        self.sequence = 0
        self.started = self.last_batch_end = time.monotonic()
        self.last_execute_ack = self.started

    def log(self, event, **fields):
        # Every event retains the explicitly selected origin.
        self.output.write(json.dumps(dict(v=VERSION, run_id=self.run_id, mode=self.mode,
                                          simulated=self.simulated, event=event,
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
            if (any(reply.get(k) != request[k] for k in ('v', 'run_id', 'request_id', 'mode'))
                    or reply.get('simulated') is not self.simulated
                    or (not self.simulated and reply.get('model_id') != self.model_id)):
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
        extra = dict(purpose='quality') if phase == 'quality' else {}
        ack = self.request('execute', batch_id=batch_id, count=count, period_ms=period, **extra)
        if ack.get('count') != count or ack.get('batch_id') != batch_id or ack.get('uart_during_execution') is not False:
            raise ProtocolError('execute_ack_mismatch')
        memory = ack.get('simulated_memory_bytes')
        if self.simulated:
            if type(memory) is not int or not number(memory) or memory < 0:
                self.log('failure', error='invalid_simulated_memory_bytes', request_id=str(self.sequence))
                raise ProtocolError('invalid_simulated_memory_bytes')
            memory_fields = dict(simulated_memory_bytes=memory)
        else:
            memory = ack.get('memory')
            required = {'free_heap_bytes', 'minimum_free_heap_bytes', 'largest_free_block_bytes',
                        'stack_high_water_bytes', 'result_buffer_bytes', 'window_buffer_bytes',
                        'model_workspace_bytes', 'device_state_bytes'}
            if (not isinstance(memory, dict) or set(memory) != {'before', 'after'}
                    or any(not isinstance(snapshot, dict) or not required <= set(snapshot)
                           or any(type(value) is not int or value < 0 for value in snapshot.values())
                           or snapshot['minimum_free_heap_bytes'] > snapshot['free_heap_bytes']
                           or snapshot['largest_free_block_bytes'] > snapshot['free_heap_bytes']
                           for snapshot in memory.values())
                    or type(ack.get('end_us')) is not int or ack['end_us'] < count * period * 1000
                    or type(ack.get('uart_wait_us')) is not int or ack['uart_wait_us'] < 0):
                raise ProtocolError('invalid_hardware_measurement')
            memory_fields = dict(memory=memory, end_us=ack['end_us'], uart_wait_us=ack['uart_wait_us'],
                                 model_id=self.model_id)
            now = time.monotonic()
            # This is an upper-bound sanity check, not a correction or a task
            # deadline tolerance. Host ACK spacing includes this execution too.
            if ack['uart_wait_us'] > (now - self.last_execute_ack) * 1_000_000 + 1_000_000:
                self.log('failure', error='invalid_hardware_uart_wait', request_id=str(self.sequence))
                raise ProtocolError('invalid_hardware_uart_wait')
            self.last_execute_ack = now
        # Raw receive events remain lossless, including malformed ACKs. Only
        # validated measurement events are suitable for presentation.
        self.log('batch_memory', batch_id=batch_id, phase=phase, series=series,
                 period_ms=period, **memory_fields)
        offset = 0
        while offset < count:
            reply = self.request('fetch', batch_id=batch_id, offset=offset)
            records = reply.get('records')
            if reply.get('batch_id') != batch_id or reply.get('offset') != offset or reply.get('total') != count or not isinstance(records, list) or not 1 <= len(records) <= min(16, count - offset):
                raise ProtocolError('result_page_mismatch')
            for i, record in enumerate(records, offset):
                error = validate_result(record, period, simulated=self.simulated, model_id=self.model_id,
                                        quality=phase == 'quality')
                if error:
                    self.log('failure', error=error, request_id=str(self.sequence))
                    raise ProtocolError(error)
                if record.get('index') != i or record.get('window_id') != windows[i % len(windows)]['window_id'] or record.get('batch_id') != batch_id:
                    self.log('failure', error='result_identity_mismatch', request_id=str(self.sequence))
                    raise ProtocolError('result_identity_mismatch')
                # Wire extensions must not become arguments or metadata in the export.
                result = {key: record[key] for key in (
                    'index', 'window_id', 'batch_id', 'scheduled_ms', 'status',
                    'processing_ms', 'decision', 'decision_source', 'error', 'model_id',
                    'input_int8', 'output_int8', 'started_us', 'inference_started_us',
                    'inference_finished_us', 'finished_us') if key in record}
                self.log('result', phase=phase, series=series, period_ms=period, **result)
            offset += len(records)
        self.log('batch_end', batch_id=batch_id, count=count)
        self.last_batch_end = time.monotonic()

    def run(self, windows, profiles=(10, 20, 50, 100), cancelled=None, *, quality=False):
        if not profiles or any(type(p) is not int or p not in (10, 20, 50, 100) for p in profiles) or len(set(profiles)) != len(profiles):
            raise ProtocolError('invalid_profile')
        def check_cancelled():
            if cancelled is not None and cancelled():
                raise ProtocolError('cancelled')
        check_cancelled()
        if quality and (self.simulated or self.mode != 'benchmark'):
            raise ProtocolError('quality_requires_hardware_benchmark')
        if not windows or (self.mode == 'benchmark' and not quality and len(windows) > MAX_BATCH) or any(
                not isinstance(w, dict) or not identifier(w.get('window_id'))
                or not identifier(w.get('trip_id')) for w in windows):
            raise ProtocolError('invalid_input_identity')
        ids = [w['window_id'] for w in windows]
        if len(set(ids)) != len(ids):
            raise ProtocolError('duplicate_window_id')
        start = self.request('start')
        if not self.simulated:
            if (start.get('class_order') != ['downshift', 'hold', 'upshift']
                    or not isinstance(start.get('dataset_id'), str) or len(start['dataset_id']) != 64):
                raise ProtocolError('model_contract_mismatch')
            self.log('model_info', model_id=self.model_id, dataset_id=start['dataset_id'],
                     class_order=start['class_order'])
        if quality:
            offset = batch = 0
            while offset < len(windows):
                check_cancelled()
                size = min(MAX_BATCH, len(windows) - offset)
                while True:
                    current = windows[offset:offset+size]
                    try:
                        encode(dict(v=1, type='load', run_id=self.run_id, mode=self.mode,
                                    request_id=str(self.sequence+1), batch_id=f'quality-{batch}', windows=current))
                        break
                    except ProtocolError:
                        size -= 1
                        if not size:
                            raise
                self.batch(current, f'quality-{batch}', size, 0, 'quality')
                offset += size
                batch += 1
        elif self.mode == 'live':
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
    parser.add_argument('--serial', help='POSIX UART path; explicitly selects real hardware')
    parser.add_argument('--model-id', help='expected embedded model SHA-256 (required for UART)')
    parser.add_argument('--baud', type=int, default=115200, choices=(115200, 921600))
    parser.add_argument('--capture-prefix', help='create lossless .rx/.tx/.chunks.jsonl UART evidence files')
    parser.add_argument('--quality', action='store_true', help='visit all input windows once, in bounded hardware batches')
    parser.add_argument('--mode', choices=('live', 'benchmark'), default='live')
    parser.add_argument('--timeout', type=float, default=5)
    parser.add_argument('--input', help='JSON Lines windows; benchmark working set is at most eight windows')
    parser.add_argument('--output', default='simulation.jsonl')
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error('timeout must be positive')
    if args.serial and (args.demo or not args.model_id):
        parser.error('--serial requires --model-id and excludes --demo')
    if args.quality and (not args.serial or args.mode != 'benchmark'):
        parser.error('--quality requires --serial and --mode benchmark')
    worker = None
    try:
        windows = []
        if args.input:
            with open(args.input, 'rb') as source:
                while True:
                    line = source.readline(16385)
                    if not line:
                        break
                    if len(line) > 16384 or (args.mode == 'benchmark' and not args.quality and len(windows) == MAX_BATCH):
                        raise ProtocolError('input_limit_exceeded')
                    windows.append(json.loads(line))
        else:
            windows = [example_window(i) for i in range(3)]
        if not windows:
            raise ProtocolError('empty_input')
        # Live sends one window per load; only benchmark loads the whole working set.
        batches = ([w] for w in windows) if args.mode == 'live' or args.quality else [windows]
        for batch in batches:
            encode(dict(v=1, type='load', windows=batch, batch_id='b', request_id='1',
                        run_id='x' * 32, mode=args.mode))
        if args.serial:
            from .uart import SerialTransport
            sock = SerialTransport(args.serial, baud=args.baud, capture_prefix=args.capture_prefix)
        elif args.demo:
            sock, peer = socket.socketpair()
            def simulate():
                with peer:
                    serve_connection(peer, args.timeout)
            worker = threading.Thread(target=simulate, daemon=True)
            worker.start()
        else:
            sock = socket.create_connection((args.host, args.port), timeout=args.timeout)
        with sock, open(args.output, 'w', encoding='utf-8') as output:
            Client(sock, output, args.mode, args.timeout, simulated=not bool(args.serial),
                   model_id=args.model_id).run(windows, quality=args.quality)
        if worker:
            worker.join(args.timeout)
        print(f'{"Hardware" if args.serial else "Simulated"} {args.mode} run complete: {args.output}')
        return 0
    except (ProtocolError, OSError, ValueError) as exc:
        print(f'Run failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
