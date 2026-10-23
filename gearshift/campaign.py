"""Prepare the locked test exactly once for final PC/MCU evaluation.

Writes immutable PC outputs and prequantized UART windows; never trains,
selects or changes the frozen model. Raw preprocessing is verified separately.
"""
import argparse
import json
from pathlib import Path
from .protocol import encode
from .frozen_export import read_frozen_export


def prepare(dataset, export, output):
    from pc.model import ReferenceModel, read_windows, quantize, classification_report, file_hash
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    read_frozen_export(export)
    reference = ReferenceModel(export)
    x, y, ids, manifest = read_windows(dataset, 'test', purpose='final-evaluation')
    if manifest['dataset_id'] != reference.metadata['dataset_id']:
        raise ValueError('frozen model/dataset mismatch')
    params = reference.audit['input']
    inputs = quantize(x, params['scales'][0], params['zero_points'][0])
    predicted = []
    with (output / 'reference.jsonl').open('x') as pc, (output / 'windows.jsonl').open('x') as windows:
        for values, label, identity in zip(inputs, y, ids):
            trip = identity.rsplit(':', 1)[0]
            result = reference.predict_int8(values, window_id=identity, trip_id=trip)
            if result['status'] != 'ok':
                raise ValueError(f'PC inference failed: {identity}')
            result.update(run_id='locked-test-pc', reference_class_index=int(label))
            pc.write(json.dumps(result, separators=(',', ':'), allow_nan=False) + '\n')
            window = dict(window_id=identity, trip_id=trip, input_int8=values.tolist())
            windows.write(encode(window).decode())
            predicted.append(result['class_index'])
    report = dict(schema='gearshift.final-test.v1', model_id=reference.model_id,
                  dataset_id=manifest['dataset_id'], split='test', count=len(ids),
                  selection_split='validation', tuning_on_test=False,
                  pc_quality=classification_report(y, predicted),
                  model_sha256=file_hash(Path(export) / 'model.tflite'),
                  manifest_sha256=file_hash(Path(dataset) / 'manifest.json'),
                  sha256={name: file_hash(output / name) for name in ('reference.jsonl', 'windows.jsonl')})
    # Validation target stays a validation claim; test metrics never select a model.
    (output / 'pc-quality.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(count=len(ids), model_id=reference.model_id,
                          macro_f1=report['pc_quality']['macro_f1'])), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True)
    parser.add_argument('--export', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        prepare(args.dataset, args.export, args.output)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
