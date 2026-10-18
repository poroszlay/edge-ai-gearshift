"""Bounded deterministic device double. No trained model or hardware claims."""
import argparse
import socket
from .protocol import MAX_BATCH, MODES, VERSION, ProtocolError, Wire, identifier, validate_window


class Device:
    def __init__(self, duration_ms=3):
        self.duration = duration_ms
        self.run_id = None
        self.batch_id = None
        self.windows = []
        self.records = []
        self.executed = False
        self.fetched = set()

    def response(self, request, kind, **fields):
        return dict(v=VERSION, type=kind, request_id=request.get('request_id'),
                    run_id=request.get('run_id'), mode=self.mode if self.run_id else request.get('mode'),
                    simulated=True, **fields)

    def handle(self, r):
        def error(code):
            return self.response(r, 'error', code=code)
        if type(r.get('v')) is not int or r['v'] != VERSION:
            return error('unsupported_version')
        if not identifier(r.get('request_id')) or not identifier(r.get('run_id')):
            return error('invalid_identity')
        op = r.get('type')
        if op == 'start':
            if self.run_id is not None:
                return error('run_already_started')
            if r.get('mode') not in MODES:
                return error('invalid_mode')
            self.run_id, self.mode = r['run_id'], r['mode']
            return self.response(r, 'ack')
        if self.run_id != r['run_id'] or r.get('mode') != self.mode:
            return error('run_or_mode_mismatch')
        if op == 'load':
            windows = r.get('windows')
            if not identifier(r.get('batch_id')) or not isinstance(windows, list) or not 1 <= len(windows) <= MAX_BATCH:
                return error('invalid_batch')
            if self.windows and (not self.executed or len(self.fetched) < len(self.records)):
                return error('batch_pending')
            ids = [w.get('window_id') if isinstance(w, dict) else None for w in windows]
            if any(not identifier(i) for i in ids) or len(set(ids)) != len(ids):
                return error('invalid_identity')
            self.windows, self.batch_id = windows, r['batch_id']
            self.records, self.executed = [], False
            self.fetched.clear()
            return self.response(r, 'ack', batch_id=self.batch_id, count=len(windows))
        if op == 'execute':
            if not self.windows or self.executed or r.get('batch_id') != self.batch_id:
                return error('invalid_state')
            period, count = r.get('period_ms'), r.get('count')
            if self.mode == 'live':
                if type(count) is not int or count != 1 or len(self.windows) != 1:
                    return error('invalid_live_count')
                period = 50
            elif type(period) is not int or period not in (10, 20, 50, 100) or type(count) is not int or count not in (100, 1000):
                return error('invalid_profile')
            busy_until = 0
            for index in range(count):
                window = self.windows[index % len(self.windows)]
                record = dict(index=index, window_id=window['window_id'], batch_id=self.batch_id,
                              scheduled_ms=index * period)
                invalid = validate_window(window)
                if invalid:
                    record.update(status='invalid_window', error=invalid)
                elif index * period < busy_until:
                    record.update(status='missed')
                else:
                    busy_until = index * period + self.duration
                    record.update(status='late' if self.duration > period else 'ok',
                                  processing_ms=self.duration, decision='hold',
                                  decision_source='simulator_stub')
                self.records.append(record)
            self.executed = True
            return self.response(r, 'ack', batch_id=self.batch_id, count=count,
                                 period_ms=period, uart_during_execution=False,
                                 simulated_memory_bytes=len(self.windows) * 100 * 4)
        if op == 'fetch':
            offset = r.get('offset')
            if not self.executed or r.get('batch_id') != self.batch_id or type(offset) is not int or not 0 <= offset < len(self.records):
                return error('invalid_offset')
            page = self.records[offset:offset + 16]
            self.fetched.update(range(offset, offset + len(page)))
            return self.response(r, 'results', batch_id=self.batch_id, offset=offset,
                                 records=page, total=len(self.records))
        return error('unknown_command')


def serve_connection(sock, timeout=5, duration_ms=3):
    wire, device = Wire(sock, timeout), Device(duration_ms)
    while True:
        try:
            request = wire.receive()
        except ProtocolError as exc:
            if str(exc) != 'disconnected':
                try:
                    wire.send(dict(v=VERSION, type='error', code=str(exc), request_id=None,
                                   run_id=device.run_id, mode=getattr(device, 'mode', None), simulated=True))
                except ProtocolError:
                    pass
            return
        wire.send(device.handle(request))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--timeout', type=float, default=5)
    parser.add_argument('--duration-ms', type=int, default=3)
    args = parser.parse_args()
    if args.timeout <= 0 or args.duration_ms < 0:
        parser.error('timeout must be positive and duration nonnegative')
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('127.0.0.1', args.port))
        server.listen(1)
        while True:
            conn, _ = server.accept()
            with conn:
                try:
                    serve_connection(conn, args.timeout, args.duration_ms)
                except ProtocolError:
                    pass


if __name__ == '__main__':
    main()
