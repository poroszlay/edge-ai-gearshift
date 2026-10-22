#!/usr/bin/env python3
"""Capture physical UART after reset, until run_complete or timeout.

Usage: python capture.py PORT TIMEOUT_SECONDS OUTPUT.log
RX chunk timestamps are host observations, not electrical edge timestamps.
"""
import datetime
import json
from pathlib import Path
import sys
import time

import serial

port, seconds, output = sys.argv[1:]
limit = float(seconds)
path = Path(output)
uart = serial.Serial(port=None, baudrate=115200, timeout=0.02)
uart.dtr = uart.rts = False
uart.port = port
uart.open()
uart.reset_input_buffer()
uart.rts = True
time.sleep(0.1)
started = time.monotonic()
metadata = dict(port=port, baud=115200,
                start_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                controlled_reset='RTS/EN 100 ms, DTR deasserted', chunks=[], complete=False,
                malformed_json_lines=0)
buffer = b''
try:
    with path.open('wb') as log:
        uart.rts = False
        while time.monotonic() - started < limit:
            data = uart.read(max(1, uart.in_waiting))
            if not data:
                continue
            metadata['chunks'].append(dict(elapsed_s=time.monotonic() - started,
                                            offset=log.tell(), bytes=len(data)))
            log.write(data)
            log.flush()
            buffer += data
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                if not line.startswith(b'{'):
                    continue
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    metadata['malformed_json_lines'] += 1
                    continue
                if event.get('event') == 'run_complete':
                    metadata['complete'] = True
            if metadata['complete']:
                break
finally:
    metadata['elapsed_s'] = time.monotonic() - started
    uart.close()
    Path(str(path) + '.json').write_text(json.dumps(metadata, indent=2) + '\n')
print(json.dumps({k: v for k, v in metadata.items() if k != 'chunks'}))
if not metadata['complete'] or metadata['malformed_json_lines']:
    raise SystemExit('Incomplete capture')
