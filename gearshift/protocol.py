"""Shared version-1 wire contract, also normative for firmware implementations."""
import json
import math
import socket
import time

VERSION = 1
MAX_LINE = 16384
MAX_BATCH = 8
MODES = ('live', 'benchmark')


class ProtocolError(Exception):
    pass


def encode(message):
    data = json.dumps(message, allow_nan=False, separators=(',', ':')).encode() + b'\n'
    if len(data) > MAX_LINE:
        raise ProtocolError('message_too_large')
    return data


class Wire:
    def __init__(self, sock, timeout=5):
        self.sock, self.timeout, self.buffer = sock, timeout, bytearray()

    def send(self, message):
        self.sock.settimeout(self.timeout)
        try:
            self.sock.sendall(encode(message))
        except (OSError, TimeoutError) as exc:
            raise ProtocolError('send_failed') from exc

    def receive(self):
        deadline = time.monotonic() + self.timeout
        while b'\n' not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProtocolError('timeout')
            self.sock.settimeout(remaining)
            try:
                chunk = self.sock.recv(min(4096, MAX_LINE + 1 - len(self.buffer)))
            except socket.timeout as exc:
                raise ProtocolError('timeout') from exc
            except OSError as exc:
                raise ProtocolError('disconnected') from exc
            if not chunk:
                raise ProtocolError('disconnected')
            self.buffer.extend(chunk)
            if len(self.buffer) > MAX_LINE and b'\n' not in self.buffer:
                raise ProtocolError('message_too_large')
        line, _, rest = self.buffer.partition(b'\n')
        self.buffer = bytearray(rest)
        if len(line) + 1 > MAX_LINE:
            raise ProtocolError('message_too_large')
        try:
            message = json.loads(line, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise ProtocolError('invalid_json') from exc
        if not isinstance(message, dict):
            raise ProtocolError('invalid_message')
        return message


def identifier(value):
    return isinstance(value, str) and 0 < len(value) <= 64 and value.isascii() and value.isprintable()


def number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def validate_window(window):
    if not isinstance(window, dict) or not identifier(window.get('window_id')) or not identifier(window.get('trip_id')):
        return 'invalid_identity'
    times, samples = window.get('timestamps_ms'), window.get('samples')
    if not isinstance(times, list) or len(times) != 20 or any(type(t) is not int or t < 0 for t in times):
        return 'invalid_timestamps'
    if any(b - a != 50 for a, b in zip(times, times[1:])):
        return 'invalid_sampling'
    if not isinstance(samples, list) or len(samples) != 20:
        return 'invalid_length'
    for row in samples:
        if not isinstance(row, list) or len(row) != 5 or not all(number(x) for x in row):
            return 'invalid_signals'
        v, u, s, g, tau = row
        if not (0 <= v <= 80 and 0 <= u <= 1 and -10 <= s <= 10 and g in (1, 2) and tau >= 0):
            return 'out_of_range'
    return None


def int8_vector(values, count):
    return (isinstance(values, list) and len(values) == count
            and all(type(x) is int and -128 <= x <= 127 for x in values))


def validate_result(record, period_ms, *, simulated=True, model_id=None, quality=False):
    """Validate origin-specific results before they become export rows."""
    if not isinstance(record, dict):
        return 'result_schema_mismatch'
    if (quality and (simulated or period_ms != 0 or record.get('status') in ('late', 'missed'))
            or (not quality and period_ms not in (10, 20, 50, 100))):
        return 'result_schema_mismatch'
    if (type(record.get('index')) is not int or record['index'] < 0
            or not identifier(record.get('window_id')) or not identifier(record.get('batch_id'))
            or type(record.get('scheduled_ms')) is not int
            or record['scheduled_ms'] != record['index'] * period_ms):
        return 'result_schema_mismatch'
    status = record.get('status')
    if status in ('ok', 'late'):
        duration = record.get('processing_ms')
        if (not number(duration) or duration < 0
                or (simulated and (duration > period_ms) != (status == 'late'))
                or 'error' in record):
            return 'result_schema_mismatch'
        if simulated:
            if record.get('decision') != 'hold' or record.get('decision_source') != 'simulator_stub':
                return 'result_schema_mismatch'
        else:
            output = record.get('output_int8')
            times = [record.get(k) for k in ('started_us', 'inference_started_us',
                                            'inference_finished_us', 'finished_us')]
            if (not int8_vector(record.get('input_int8'), 100) or not int8_vector(output, 3)
                    or record.get('decision_source') != 'int8_mlp'
                    or record.get('model_id') != model_id or model_id is None
                    or record.get('decision') != ('downshift', 'hold', 'upshift')[output.index(max(output))]
                    or any(type(t) is not int or t < 0 for t in times)
                    or times != sorted(times) or times[0] < record['scheduled_ms'] * 1000
                    or (not quality and times[0] >= (record['scheduled_ms'] + period_ms) * 1000)
                    or abs(duration * 1000 - (times[-1] - times[0])) > .001
                    or (not quality and (times[-1] > (record['scheduled_ms'] + period_ms) * 1000) != (status == 'late'))):
                return 'result_schema_mismatch'
    elif status in ('missed', 'invalid_window', 'model_error', 'memory_error'):
        if simulated and status in ('model_error', 'memory_error'):
            return 'result_schema_mismatch'
        if any(key in record for key in ('processing_ms', 'decision', 'decision_source', 'output_int8')):
            return 'result_schema_mismatch'
        if status != 'missed':
            if not isinstance(record.get('error'), str) or not record['error']:
                return 'result_schema_mismatch'
        elif 'error' in record:
            return 'result_schema_mismatch'
    else:
        return 'result_schema_mismatch'
    return None


def preprocess(window):
    error = validate_window(window)
    if error:
        raise ProtocolError(error)
    return [x for v, u, s, g, tau in window['samples']
            for x in (v / 80, u, s / 10, g - 1, min(tau, 10) / 10)]
