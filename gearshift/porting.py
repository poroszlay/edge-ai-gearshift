"""Strict PC/MCU comparison. Input identity and output tolerance are separate."""
import argparse
import json
from pathlib import Path
from .protocol import int8_vector

CLASS_ORDER = ['downshift', 'hold', 'upshift']


def porting_report(reference, actual):
    """Require complete, unique, ordered coverage. Never relax the one-code limit."""
    from pc.model import classification_report
    if not reference or len(reference) != len(actual):
        raise ValueError('incomplete coverage')
    expected_ids = [r['window_id'] for r in reference]
    if len(set(expected_ids)) != len(expected_ids) or expected_ids != [r.get('window_id') for r in actual]:
        raise ValueError('invalid coverage/order')
    differences, maximum, expected, predicted = [], 0, [], []
    for pc, mcu in zip(reference, actual):
        if (pc.get('status') != 'ok' or mcu.get('status') not in ('ok', 'late')
                or not int8_vector(pc.get('input_int8'), 100) or not int8_vector(mcu.get('input_int8'), 100)
                or not int8_vector(pc.get('output_int8'), 3) or not int8_vector(mcu.get('output_int8'), 3)
                or pc.get('model_id') != mcu.get('model_id') or not mcu.get('run_id')
                or mcu.get('simulated') is not False):
            raise ValueError(f'invalid comparison record: {pc["window_id"]}')
        identity = dict(run_id=mcu['run_id'], model_id=mcu['model_id'], window_id=mcu['window_id'])
        if pc['input_int8'] != mcu['input_int8']:
            differences.append(dict(identity, kind='input_mismatch', pc=pc['input_int8'], mcu=mcu['input_int8']))
        delta = [abs(a-b) for a,b in zip(pc['output_int8'], mcu['output_int8'])]
        maximum = max(maximum, *delta)
        pc_class = pc['output_int8'].index(max(pc['output_int8']))
        mcu_class = mcu['output_int8'].index(max(mcu['output_int8']))
        if pc.get('decision') != CLASS_ORDER[pc_class] or mcu.get('decision') != CLASS_ORDER[mcu_class]:
            raise ValueError('decision/output mismatch')
        if any(delta) or pc_class != mcu_class:
            differences.append(dict(identity, kind='output_difference', delta=delta,
                                    pc=pc['output_int8'], mcu=mcu['output_int8'],
                                    class_agreement=pc_class == mcu_class,
                                    within_tolerance=max(delta) <= 1 and pc_class == mcu_class))
        if 'reference_class_index' in pc:
            expected.append(pc['reference_class_index'])
            predicted.append(mcu_class)
    if expected and len(expected) != len(reference):
        raise ValueError('partial quality labels')
    quality = classification_report(expected, predicted) if expected else None
    return dict(schema='gearshift.porting.v1', count=len(reference), model_id=reference[0]['model_id'],
                run_ids=sorted({r['run_id'] for r in actual}), simulated=False,
                tolerance_int8_codes=1, max_output_code_difference=maximum,
                porting_passed=not any(d['kind'] == 'input_mismatch' or not d.get('within_tolerance', True)
                                      for d in differences),
                differences=differences, quality=quality,
                quality_target_met=quality is not None and quality['macro_f1'] >= .95)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--events', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        reference = [json.loads(line) for line in Path(args.reference).read_text().splitlines()]
        events = [json.loads(line) for line in Path(args.events).read_text().splitlines()]
        if not events or events[-1].get('event') != 'run_complete':
            raise ValueError('incomplete run')
        actual = [r for r in events if r['event'] == 'result']
        report = porting_report(reference, actual)
        with open(args.output, 'x') as output:
            json.dump(report, output, indent=2, allow_nan=False)
            output.write('\n')
        return 0 if report['porting_passed'] else 1
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
