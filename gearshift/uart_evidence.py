"""Audit lossless UART captures; report host-observed silence, not bus probing."""
import argparse
from bisect import bisect_right
from itertools import zip_longest
import json
from pathlib import Path
from .protocol import MAX_LINE


def audit_capture(prefix):
    prefix = str(prefix)
    streams = {d: [] for d in ('rx', 'tx')}
    lengths = dict(rx=0, tx=0)
    previous = -1
    with open(prefix + '.chunks.jsonl') as source:
        for line in source:
            c = json.loads(line)
            d = c.get('direction')
            if (d not in streams or type(c.get('offset')) is not int or c['offset'] != lengths[d]
                    or type(c.get('bytes')) is not int or c['bytes'] <= 0
                    or type(c.get('elapsed_s')) not in (int,float) or c['elapsed_s'] < previous):
                raise ValueError('invalid capture chunk coverage/time')
            previous = c['elapsed_s']
            streams[d].append((c['offset'], c['elapsed_s']))
            lengths[d] += c['bytes']
    for d in streams:
        if not streams[d] or Path(prefix+'.'+d).stat().st_size != lengths[d]:
            raise ValueError('incomplete capture bytes')
    def frames(direction):
        index = streams[direction]
        offsets = [item[0] for item in index]
        offset = 0
        with open(prefix+'.'+direction, 'rb') as source:
            while True:
                data = source.readline(MAX_LINE+1)
                if not data:
                    break
                if len(data)>MAX_LINE or not data.endswith(b'\n'):
                    raise ValueError('incomplete UART frame')
                start = index[bisect_right(offsets,offset)-1][1]
                end = index[bisect_right(offsets,offset+len(data)-1)-1][1]
                offset += len(data)
                # Boot, watchdog and diagnostic bytes cannot disappear in a
                # JSON-only extract: every captured byte must parse here.
                value = json.loads(data, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
                if not isinstance(value,dict):
                    raise ValueError('non-object UART frame')
                yield value,start,end
    executions = []
    count = 0
    for tx,rx in zip_longest(frames('tx'),frames('rx')):
        if tx is None or rx is None:
            raise ValueError('unmatched UART request/response')
        request,_,sent = tx
        reply,received,_ = rx
        if (any(request.get(k) != reply.get(k) for k in ('v','request_id','run_id','mode'))
                or reply.get('simulated') is not False or reply.get('type') == 'error'
                or received < sent):
            raise ValueError('invalid UART response pairing')
        count += 1
        if request.get('type') == 'execute':
            end = reply.get('end_us')
            if (reply.get('type') != 'ack' or reply.get('uart_during_execution') is not False
                    or type(end) is not int or end < 0
                    or reply.get('batch_id') != request.get('batch_id')
                    or reply.get('count') != request.get('count')):
                raise ValueError('invalid execution ACK')
            gap = received-sent
            # Host timestamps bracket writes queued to the tty and reads from
            # the tty. A 2ms allowance is explicit, never an INT8 tolerance.
            if gap + .002 < end/1e6:
                raise ValueError('UART response observed before execution ended')
            executions.append(dict(batch_id=request['batch_id'], count=request['count'],
                                   end_us=end, observed_quiet_interval_s=gap))
    if not executions:
        raise ValueError('no execution evidence')
    return dict(schema='gearshift.uart-audit.v1', simulated=False,
                observation='host_read_write_timestamps', requests=count,
                execution_count=len(executions), observed_uart_silence=True,
                timestamp_allowance_us=2000, executions=executions,
                captured_bytes=lengths)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prefix')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        report = audit_capture(args.prefix)
        with open(args.output,'x') as output:
            json.dump(report,output,indent=2,allow_nan=False)
            output.write('\n')
    except (ValueError,OSError,KeyError,TypeError) as exc:
        parser.exit(1,f'invalid UART evidence: {exc}\n')


if __name__ == '__main__':
    main()
