"""Analyze the measurement module's evidence JSONL (not the v1 device wire)."""
import argparse
import json
import math
from pathlib import Path
import statistics
import sys


def distribution(values):
    if not values:
        return None
    ordered = sorted(values)
    return dict(median=statistics.median(ordered),
                p95=ordered[math.ceil(.95 * len(ordered)) - 1], maximum=ordered[-1])


def check(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def validate_task(record, start, count):
    period = start['period_us']
    check(integer(record['index']) and record['index'] == count, 'invalid task index')
    check(integer(record['window_index']) and
          record['window_index'] == count % len(start['window_ids']), 'incorrect window order')
    check(integer(record['scheduled_us']) and record['scheduled_us'] == count * period,
          'incorrect scheduled time')
    times = [record[key] for key in ('started_us', 'inference_started_us',
                                     'inference_finished_us', 'finished_us')]
    status, error = record['status'], record['error']
    check(status in ('ok', 'late', 'missed', 'failed'), 'invalid status')
    if status == 'missed':
        check(times == [None] * 4 and error is None, 'missed task has invented measurements')
        return
    begin, inference_begin, inference_end, end = times
    check(integer(begin) and integer(end) and
          record['scheduled_us'] <= begin < record['scheduled_us'] + period and end >= begin,
          'invalid processing interval')
    if status == 'failed':
        check(error in ('invalid_window', 'model_error', 'memory_error'), 'missing failure reason')
        check((inference_begin is None and inference_end is None) or
              (integer(inference_begin) and integer(inference_end) and
               begin <= inference_begin <= inference_end <= end), 'invalid failed inference interval')
    else:
        check(error is None and integer(inference_begin) and integer(inference_end) and
              begin <= inference_begin <= inference_end <= end, 'invalid inference interval')
        check((status == 'late') == (end > record['scheduled_us'] + period),
              'status disagrees with scheduled deadline')


def validate_memory(memory, simulated):
    check(isinstance(memory, dict), 'missing memory snapshot')
    for key in ('free_heap_bytes', 'minimum_free_heap_bytes', 'largest_free_block_bytes',
                'stack_high_water_bytes', 'result_buffer_bytes', 'window_buffer_bytes'):
        check(integer(memory[key]) or (simulated and memory[key] is None), 'invalid memory bytes')
    check(memory['model_workspace_bytes'] is None or integer(memory['model_workspace_bytes']),
          'invalid workspace bytes')
    free = memory['free_heap_bytes']
    if free is not None:
        check(memory['minimum_free_heap_bytes'] <= free and memory['largest_free_block_bytes'] <= free,
              'contradictory heap snapshot')


def validate(events):
    check(bool(events) and all(isinstance(e, dict) for e in events), 'empty or non-object capture')
    header, final = events[0], events[-1]
    check(header['event'] == 'run_start' and final['event'] == 'run_complete', 'incomplete run')
    check(header['schema'] == 'gearshift.measurement.v1', 'unknown evidence schema')
    check(type(header['simulated']) is bool, 'missing or invalid measurement origin')
    check(header['mode'] in ('live', 'benchmark') and isinstance(header['run_id'], str) and
          bool(header['run_id']) and isinstance(header['workload'], str) and bool(header['workload']),
          'invalid run metadata')
    check(integer(header['expected_batches'], 1) and integer(header['expected_tasks'], 1) and
          integer(final['batches'], 1) and integer(final['tasks'], 1), 'invalid run counts')
    batches, total, seen, active = 0, 0, set(), None
    for event in events[1:-1]:
        kind = event['event']
        if kind == 'series_start':
            check(active is None and event['batch_id'] not in seen, 'duplicate or overlapping series')
            active, count = event, 0
            check(integer(event['count'], 1) and event['count'] <= 1000 and
                  type(event['period_us']) is int and event['period_us'] in (10000, 20000, 50000, 100000),
                  'invalid profile')
            check(integer(event['series']) and integer(event['uart_wait_us']) and
                  ((header['mode'] == 'live' and event['phase'] == 'live' and event['series'] == 0 and
                    event['count'] == 1) or
                   (header['mode'] == 'benchmark' and
                    ((event['phase'] == 'warmup' and event['series'] == 0) or
                     (event['phase'] == 'measured' and 1 <= event['series'] <= 3)))),
                  'invalid series metadata')
            check(isinstance(event['window_ids'], list) and 1 <= len(event['window_ids']) <= 8 and
                  all(isinstance(w, str) and w for w in event['window_ids']) and
                  len(set(event['window_ids'])) == len(event['window_ids']), 'invalid window identifiers')
            latest_finish = 0
            memory_seen = False
            if 'memory' in event or not header['simulated']:
                validate_memory(event.get('memory'), header['simulated'])
            seen.add(event['batch_id'])
        elif kind == 'task':
            check(active is not None and event['batch_id'] == active['batch_id'], 'orphan task')
            check(event['index'] == count, 'missing or duplicated task')
            validate_task(event, active, count)
            if event['finished_us'] is not None:
                check(event['started_us'] >= latest_finish, 'overlapping work')
                latest_finish = event['finished_us']
            count += 1
        elif kind == 'series_memory':
            check(active is not None and event['batch_id'] == active['batch_id'], 'orphan memory snapshot')
            check(not memory_seen, 'duplicate memory snapshot')
            validate_memory(event['memory'], header['simulated'])
            memory_seen = True
        elif kind == 'series_end':
            check(active is not None and event['batch_id'] == active['batch_id'], 'orphan series end')
            check(integer(event['count'], 1) and event['count'] == count == active['count'], 'incomplete series')
            check(header['simulated'] or memory_seen, 'missing hardware memory snapshot')
            check(integer(event['end_us']) and
                  event['end_us'] >= max(count * active['period_us'], latest_finish) and
                  event['uart_during_execution'] is False, 'invalid execution end or UART in execution')
            if 'uart_wait_us' in event:
                check(integer(event['uart_wait_us']) and
                      event['uart_wait_us'] >= active['uart_wait_us'], 'invalid complete UART pause')
            total += count
            batches += 1
            active = None
        else:
            raise ValueError('unexpected event')
    check(active is None and batches == final['batches'] == header['expected_batches'] and
          total == final['tasks'] == header['expected_tasks'] and total > 0, 'incomplete accounting')


def analyze(events):
    validate(events)
    header = events[0]
    batches = []
    for event in events[1:]:
        if event['event'] == 'series_start':
            start, records, memory_after = event, [], None
        elif event['event'] == 'series_memory':
            memory_after = event['memory']
        elif event['event'] == 'task':
            records.append(event)
        elif event['event'] == 'series_end':
            counts = {status: sum(r['status'] == status for r in records)
                      for status in ('ok', 'late', 'missed', 'failed')}
            completed = [r for r in records if r['status'] in ('ok', 'late')]
            batches.append(dict(
                batch_id=start['batch_id'], phase=start['phase'], series=start['series'],
                period_us=start['period_us'], scheduled=len(records), counts=counts,
                deadline_failure_percent=100 * (len(records) - counts['ok']) / len(records),
                processing_ms=distribution([(r['finished_us'] - r['started_us']) / 1000
                                            for r in completed]),
                inference_ms=distribution([(r['inference_finished_us'] - r['inference_started_us']) / 1000
                                           for r in completed]),
                inferences_per_second=len(completed) * 1_000_000 / event['end_us'],
                uart_wait_us=event.get('uart_wait_us', start['uart_wait_us']),
                uart_wait_scope='complete' if 'uart_wait_us' in event else 'before_header',
                memory_before=start.get('memory'),
                memory_after=memory_after))
    return dict(schema=header['schema'], run_id=header['run_id'], simulated=header['simulated'],
                mode=header['mode'], workload=header['workload'], metadata=dict(header), batches=batches)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--require-benchmark', action='store_true',
                        help='require the complete four-profile 100 + 3 x 1000 protocol')
    args = parser.parse_args()
    try:
        events = [json.loads(line) for line in args.input.read_text().splitlines()]
        report = analyze(events)
        if args.require_benchmark:
            expected = [(period, phase, series, count)
                        for period in (10000, 20000, 50000, 100000)
                        for phase, series, count in [('warmup', 0, 100),
                                                    ('measured', 1, 1000),
                                                    ('measured', 2, 1000),
                                                    ('measured', 3, 1000)]]
            actual = [(b['period_us'], b['phase'], b['series'], b['scheduled'])
                      for b in report['batches']]
            check(report['mode'] == 'benchmark' and actual == expected, 'incomplete benchmark protocol')
        print(json.dumps(report, indent=2, allow_nan=False))
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f'invalid measurement: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
