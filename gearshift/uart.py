"""POSIX UART byte transport for the shared Wire framing (115200, 8N1).

Opening a port does not reset or silently discard firmware output. Reset and
wait for boot before connecting; one firmware boot accepts one run.
"""
import errno
import fcntl
import os
import select
import socket
import termios
import time
import tty
import json


class SerialTransport:
    def __init__(self, path, *, baud=115200, capture_prefix=None):
        if baud not in (115200, 921600):
            raise ValueError('unsupported UART baud rate')
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        self.timeout = 5
        self.capture = {}
        self.chunks = None
        self.started = time.monotonic()
        try:
            fcntl.ioctl(self.fd, termios.TIOCEXCL)
            tty.setraw(self.fd, termios.TCSANOW)
            settings = termios.tcgetattr(self.fd)
            settings[4] = settings[5] = getattr(termios, f'B{baud}')
            settings[2] = ((settings[2] | termios.CLOCAL | termios.CREAD)
                           & ~getattr(termios, 'CRTSCTS', 0))
            termios.tcsetattr(self.fd, termios.TCSANOW, settings)
            if capture_prefix is not None:
                for direction in ('rx', 'tx'):
                    self.capture[direction] = open(str(capture_prefix) + '.' + direction, 'xb')
                self.chunks = open(str(capture_prefix) + '.chunks.jsonl', 'x')
        except BaseException:
            self.close()
            raise

    def record(self, direction, data):
        if self.chunks is not None:
            stream = self.capture[direction]
            offset = stream.tell()
            stream.write(data)
            stream.flush()
            self.chunks.write(json.dumps(dict(direction=direction, offset=offset, bytes=len(data),
                                              elapsed_s=time.monotonic()-self.started)) + '\n')
            self.chunks.flush()

    def settimeout(self, seconds):
        self.timeout = seconds

    def recv(self, count):
        if not select.select([self.fd], [], [], self.timeout)[0]:
            raise socket.timeout('timeout')
        try:
            data = os.read(self.fd, count)
            self.record('rx', data)
            return data
        except OSError as error:
            if error.errno == errno.EIO:
                return b''
            raise

    def sendall(self, data):
        deadline = time.monotonic() + self.timeout
        remaining = memoryview(data)
        while remaining:
            timeout = deadline - time.monotonic()
            if timeout <= 0 or not select.select([], [self.fd], [], timeout)[1]:
                raise socket.timeout('timeout')
            try:
                written = os.write(self.fd, remaining)
                self.record('tx', remaining[:written])
                remaining = remaining[written:]
            except BlockingIOError:
                continue

    def shutdown(self, how):
        self.close()

    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)
        for stream in self.capture.values():
            stream.close()
        if self.chunks is not None:
            self.chunks.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
