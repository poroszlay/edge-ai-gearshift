"""Validate hardware client events using the existing #5 measurement analyzer."""
import argparse
import json
from pathlib import Path
from .protocol import validate_result, number
from .profiler import analyze, check


def analyze_run(rows, *, require_benchmark=False):
    check(bool(rows) and rows[-1].get('event') == 'run_complete', 'incomplete run')
    run_id, mode = rows[0]['run_id'], rows[0]['mode']
    check(all(r.get('simulated') is False and r.get('run_id') == run_id and r.get('mode') == mode
              for r in rows), 'inconsistent run origin')
    infos = [r for r in rows if r['event'] == 'model_info']
    check(len(infos) == 1, 'missing model identity')
    info = infos[0]
    events = []
    active = memory = None
    records = []
    seen = set()
    batches = tasks = 0
    previous_execute_ack_ms = 0
    for row in rows:
        kind = row['event']
        if kind == 'receive' and row.get('message', {}).get('type') == 'ack' and 'end_us' in row['message']:
            host_ms = row.get('host_elapsed_ms')
            wait = row['message'].get('uart_wait_us')
            check(number(host_ms) and host_ms >= previous_execute_ack_ms
                  and type(wait) is int and 0 <= wait <= (host_ms-previous_execute_ack_ms)*1000+1_000_000,
                  'implausible UART pause relative to host elapsed time')
            previous_execute_ack_ms = host_ms
        if kind in ('failure', 'run_failed', 'run_stopped'):
            raise ValueError('failed run')
        if kind == 'batch_start':
            check(active is None and row['batch_id'] not in seen, 'overlapping batch')
            active, memory, records = row, None, []
            seen.add(row['batch_id'])
        elif kind == 'batch_memory':
            check(active is not None and row['batch_id'] == active['batch_id'] and memory is None,
                  'orphan or duplicate memory')
            memory = row
        elif kind == 'result':
            check(active is not None and memory is not None and row['batch_id'] == active['batch_id'],
                  'orphan result')
            check(row['phase'] == active['phase'] and row['series'] == active['series']
                  and row['period_ms'] == active['period_ms'], 'incorrect result metadata')
            check(validate_result(row, active['period_ms'], simulated=False, model_id=info['model_id']) is None,
                  'invalid model result')
            check(row['window_id'] == active['window_ids'][len(records) % len(active['window_ids'])],
                  'incorrect window identity')
            records.append(row)
        elif kind == 'batch_end':
            check(active is not None and row['batch_id'] == active['batch_id']
                  and memory is not None and row['count'] == len(records), 'incomplete batch')
            events.append(dict(event='series_start', batch_id=active['batch_id'],
                phase=active['phase'], series=active['series'], period_us=active['period_ms']*1000,
                count=row['count'], window_ids=active['window_ids'], uart_wait_us=memory['uart_wait_us'],
                memory=memory['memory']['before']))
            events.append(dict(event='series_memory', batch_id=active['batch_id'], memory=memory['memory']['after']))
            for r in records:
                failed = r['status'] in ('invalid_window', 'memory_error', 'model_error')
                events.append(dict(event='task', batch_id=r['batch_id'], index=r['index'],
                    window_index=r['index'] % len(active['window_ids']), scheduled_us=r['scheduled_ms']*1000,
                    status='failed' if failed else r['status'], error=r.get('error'),
                    **{key: r.get(key) for key in ('started_us', 'inference_started_us',
                                                 'inference_finished_us', 'finished_us')}))
            events.append(dict(event='series_end', batch_id=row['batch_id'], count=row['count'],
                               end_us=memory['end_us'], uart_wait_us=memory['uart_wait_us'],
                               uart_during_execution=False))
            batches += 1
            tasks += row['count']
            active = None
    check(active is None, 'unfinished batch')
    evidence = [dict(event='run_start', schema='gearshift.measurement.v1', run_id=run_id,
                     mode=mode, simulated=False, workload='int8_mlp', model_id=info['model_id'],
                     dataset_id=info['dataset_id'], expected_batches=batches, expected_tasks=tasks),
                *events, dict(event='run_complete', batches=batches, tasks=tasks)]
    report = analyze(evidence)
    if require_benchmark:
        expected = [(p, phase, series, count) for p in (10000,20000,50000,100000)
                    for phase,series,count in [('warmup',0,100),('measured',1,1000),
                                               ('measured',2,1000),('measured',3,1000)]]
        actual = [(b['period_us'],b['phase'],b['series'],b['scheduled']) for b in report['batches']]
        check(mode == 'benchmark' and actual == expected, 'incomplete benchmark')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--require-benchmark', action='store_true')
    args = parser.parse_args()
    try:
        rows = [json.loads(x) for x in args.input.read_text().splitlines()]
        print(json.dumps(analyze_run(rows, require_benchmark=args.require_benchmark), indent=2, allow_nan=False))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f'invalid measurement: {exc}\n')


if __name__ == '__main__':
    main()
