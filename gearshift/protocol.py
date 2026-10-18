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


def preprocess(window):
    error = validate_window(window)
    if error:
        raise ProtocolError(error)
    return [x for v, u, s, g, tau in window['samples']
            for x in (v / 80, u, s / 10, g - 1, min(tau, 10) / 10)]
