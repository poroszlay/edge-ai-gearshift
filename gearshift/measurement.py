"""GUI-independent session orchestration and lossless CSV event archive.

Client owns protocol validation, scheduling and result accounting. This module
only provides cancellable background execution and presentation/export data.
"""
import csv
import json
import os
import queue
import socket
import tempfile
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .client import Client, example_window
from .protocol import ProtocolError
from .simulator import serve_connection


@dataclass(frozen=True)
class Settings:
    mode: str = 'live'
    demo: bool = True
    host: str = '127.0.0.1'
    port: int = 8765
    timeout: float = 5
    profiles: tuple = (10, 20, 50, 100)
    input_path: str = ''
    duration_ms: int = 3


def summary(rows):
    """Keep warmup separate; never count missed and late twice."""
    groups = {}
    for row in rows:
        if row['event'] == 'result':
            key = (row['phase'], row['period_ms'], row['series'])
            counts = groups.setdefault(key, Counter())
            counts[row['status']] += 1
            counts['scheduled'] += 1
    return {key: dict(value) for key, value in groups.items()}


# Readable scalar columns plus the original event preserve all protocol fields,
# raw inputs, window order, acknowledgements, errors and timing metadata.
CSV_FIELDS = ('v', 'run_id', 'mode', 'simulated', 'event', 'host_elapsed_ms',
              'batch_id', 'phase', 'series', 'period_ms', 'index', 'window_id',
              'scheduled_ms', 'status', 'processing_ms', 'decision',
              'decision_source', 'error', 'request_id', 'event_json')


def export_csv(path, rows):
    """Atomic replacement: a failed export cannot leave a successful-looking file."""
    target = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                         dir=target.parent, delete=False) as output:
            temporary = output.name
            writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for row in rows:
                values = {k: row[k] for k in CSV_FIELDS[:-1] if k in row}
                values['event_json'] = json.dumps(row, ensure_ascii=True, allow_nan=False)
                writer.writerow(values)
        os.replace(temporary, target)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def read_csv(path):
    with open(path, encoding='utf-8', newline='') as source:
        return [json.loads(row['event_json']) for row in csv.DictReader(source)]


class Session:
    """One worker owns rows. Inspect/export rows only after done is set.

    The bounded notification queue applies backpressure outside device execution.
    Polling never performs network or file IO on the GUI thread.
    """
    def __init__(self, settings):
        self.settings = settings
        self.rows = []
        self.events = queue.Queue(maxsize=512)
        self.cancelled = threading.Event()
        self.done = threading.Event()
        self.sock = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.cancelled.set()
        sock = self.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def write(self, line):
        row = json.loads(line)
        self.rows.append(row)
        while not self.cancelled.is_set():
            try:
                self.events.put(row, timeout=.05)
                break
            except queue.Full:
                pass
        # Playback pacing is host waiting, outside measured execution. No
        # pacing or notifications are inserted inside a benchmark execute.
        if row['event'] == 'batch_end' and self.settings.mode == 'live':
            self.cancelled.wait(.05)

    def flush(self):
        pass

    def _run(self):
        s = self.settings
        client = Client(None, self, s.mode, s.timeout)
        simulator = None
        try:
            client.log('session_start', settings=vars(s))
            if s.input_path:
                windows = []
                with open(s.input_path, encoding='utf-8') as source:
                    while True:
                        if self.cancelled.is_set():
                            raise ProtocolError('cancelled')
                        line = source.readline(16385)
                        if not line:
                            break
                        if len(line) > 16384 or len(windows) >= 100000:
                            raise ProtocolError('input_limit_exceeded')
                        windows.append(json.loads(line))
            else:
                windows = [example_window(i) for i in range(8 if s.mode == 'benchmark' else 200)]
            if self.cancelled.is_set():
                raise ProtocolError('cancelled')
            if s.demo:
                self.sock, peer = socket.socketpair()
                def simulate():
                    with peer:
                        try:
                            serve_connection(peer, s.timeout, s.duration_ms)
                        except (ProtocolError, OSError):
                            pass
                simulator = threading.Thread(target=simulate, daemon=True)
                simulator.start()
            else:
                self.sock = socket.create_connection((s.host, s.port), timeout=s.timeout)
            client.wire.sock = self.sock
            client.run(windows, s.profiles, self.cancelled.is_set)
        except Exception as exc:
            # Client already logs transport errors. This terminal event also
            # covers input, connect, ack validation and unexpected worker errors.
            client.log('run_stopped' if self.cancelled.is_set() else 'run_failed',
                       error=str(exc) or type(exc).__name__)
        finally:
            if self.sock is not None:
                self.sock.close()
            if simulator:
                simulator.join(min(s.timeout, 1))
            self.done.set()
