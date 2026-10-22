#!/usr/bin/env python3
"""Extract strict JSONL and host-observed UART silence from a raw capture.

Usage: python analyze_uart.py CAPTURE.log OUTPUT_PREFIX
The capture.py .log.json chunk timeline must accompany the raw bytes.
The profiler separately validates task accounting and memory values.
"""
import bisect
import json
from pathlib import Path
import sys

source, prefix = map(Path, sys.argv[1:])
raw = source.read_bytes()
metadata = json.loads(Path(str(source) + '.json').read_text())
assert metadata['complete'] and not metadata.get('malformed_json_lines', 0), 'incomplete or corrupt capture'
for diagnostic in (b'task_wdt:', b'Guru Meditation', b'Brownout', b'CORRUPT HEAP', b'abort()'):
    assert diagnostic not in raw, diagnostic
chunks = metadata['chunks']
assert sum(chunk['bytes'] for chunk in chunks) == len(raw), 'capture byte accounting mismatch'
offsets = [chunk['offset'] for chunk in chunks]


def received_at(offset):
    chunk = chunks[bisect.bisect_right(offsets, offset) - 1]
    assert chunk['offset'] <= offset < chunk['offset'] + chunk['bytes']
    return chunk['elapsed_s']


rows, silence, position, start, memory_begin = [], [], 0, None, None
for line in raw.splitlines(keepends=True):
    if line.startswith(b'{'):
        event = json.loads(line)
        rows.append(event)
        if event['event'] == 'series_start':
            start = (event, received_at(position + len(line) - 1))
        elif event['event'] == 'series_memory':
            memory_begin = received_at(position)
        elif event['event'] == 'series_end':
            gap = memory_begin - start[1]
            expected = event['end_us'] / 1_000_000
            # CP2102/USB/host timing is not an electrical edge measurement.
            assert abs(gap - expected) < .05, (event['batch_id'], gap, expected)
            silence.append(dict(batch_id=event['batch_id'], execution_s=expected,
                                last_header_byte_received_s=start[1],
                                first_result_byte_received_s=memory_begin,
                                observed_no_rx_s=gap,
                                complete_uart_pause_us=event['uart_wait_us']))
    elif rows:
        raise ValueError('Unexpected non-JSON output after run_start')
    position += len(line)
assert rows[-1]['event'] == 'run_complete'
prefix.with_suffix('.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
prefix.with_suffix('.silence.json').write_text(json.dumps(dict(
    run_id=rows[0]['run_id'], simulated=rows[0]['simulated'],
    method='Physical CP2102 RX, host monotonic chunk timestamps; tolerance 50 ms',
    limitation='Host receive silence does not measure electrical edge timing or prove a future WCET',
    elapsed_s=metadata['elapsed_s'], series=silence), indent=2) + '\n')
print(f'{len(rows)} events, {len(silence)} observed UART-silent execution intervals')
