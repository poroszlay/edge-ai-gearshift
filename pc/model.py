"""Training, audited integer export and PC reference for the gearshift MLP.

Public boundaries and reproduction commands are documented in docs/model.md.
"""
import numpy as np


def quantize(values, scale, zero_point):
    """Round x/scale half away from zero, add zero point, then saturate."""
    if not np.isfinite(scale) or scale <= 0 or type(zero_point) is not int or not -128 <= zero_point <= 127:
        raise ValueError("invalid quantization parameters")
    values = np.asarray(values, dtype=np.float32)
    if not np.all(np.isfinite(values)):
        raise ValueError("non-finite model input")
    scaled = values / np.float32(scale)
    # Preserve adjacent float32 values around half-integers during addition.
    rounded = np.copysign(np.floor(np.abs(scaled).astype(np.float64) + 0.5), scaled)
    return np.clip(rounded + zero_point, -128, 127).astype(np.int8)


CLASS_ORDER = ['downshift', 'hold', 'upshift']
INPUT_VERSION = 'window-v1:20x5:sample-major:fixed-scaling:float32'


def classification_report(expected, predicted):
    """Three-class metrics; rows=true, columns=predicted; zero divisions are 0."""
    expected, predicted = np.asarray(expected), np.asarray(predicted)
    if (expected.ndim != 1 or expected.shape != predicted.shape or not len(expected)
            or expected.dtype.kind not in 'iu' or predicted.dtype.kind not in 'iu'
            or np.any((expected < 0) | (expected > 2)) or np.any((predicted < 0) | (predicted > 2))):
        raise ValueError('expected equally sized nonempty integer class vectors in 0..2')
    matrix = np.bincount(expected * 3 + predicted, minlength=9).reshape(3, 3)
    classes = []
    for index, name in enumerate(CLASS_ORDER):
        tp = int(matrix[index, index])
        support = int(matrix[index].sum())
        count = int(matrix[:, index].sum())
        precision = tp / count if count else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * tp / (support + count) if support + count else 0.0
        classes.append(dict(class_index=index, action=index-1, name=name,
                            support=support, precision=precision, recall=recall, f1=f1))
    return dict(count=len(expected), confusion_matrix=matrix.tolist(), classes=classes,
                macro_f1=sum(c['f1'] for c in classes) / 3,
                accuracy=float(np.trace(matrix) / matrix.sum()))


import hashlib
import json
from pathlib import Path


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def audit_model(path):
    """Inspect the actual FlatBuffer, including unused tensors and all op codes."""
    import tensorflow as tf
    from tensorflow.lite.python import schema_py_generated as schema
    data = Path(path).read_bytes()
    if len(data) < 8 or data[4:8] != b'TFL3':
        raise ValueError('not a TFLite FlatBuffer')
    model = schema.Model.GetRootAsModel(data, 0)
    if model.Version() != 3 or model.SubgraphsLength() != 1:
        raise ValueError('unsupported schema/subgraphs')
    graph = model.Subgraphs(0)
    allowed = {schema.BuiltinOperator.FULLY_CONNECTED: 'FULLY_CONNECTED',
               schema.BuiltinOperator.SOFTMAX: 'SOFTMAX',
               schema.BuiltinOperator.RESHAPE: 'RESHAPE', schema.BuiltinOperator.RELU: 'RELU'}
    operators = []
    for i in range(model.OperatorCodesLength()):
        code = model.OperatorCodes(i)
        if code.BuiltinCode() not in allowed or code.CustomCode():
            raise ValueError('unsupported integer operator')
        operators.append(dict(name=allowed[code.BuiltinCode()], version=code.Version()))
    tensors = []
    for i in range(graph.TensorsLength()):
        tensor = graph.Tensors(i)
        if tensor.Type() not in (schema.TensorType.INT8, schema.TensorType.INT32):
            raise ValueError('full INT8 required: floating/hybrid tensor')
        q = tensor.Quantization()
        scales = [float(q.Scale(j)) for j in range(q.ScaleLength())] if q else []
        zeros = [int(q.ZeroPoint(j)) for j in range(q.ZeroPointLength())] if q else []
        if tensor.Type() == schema.TensorType.INT8:
            if not scales or len(scales) != len(zeros) or any(not np.isfinite(s) or s <= 0 for s in scales):
                raise ValueError('invalid INT8 quantization')
            if any(z < -128 or z > 127 for z in zeros):
                raise ValueError('invalid INT8 zero point')
        tensors.append(dict(index=i, name=tensor.Name().decode(),
                            dtype='int8' if tensor.Type() == schema.TensorType.INT8 else 'int32',
                            shape=[int(tensor.Shape(j)) for j in range(tensor.ShapeLength())],
                            scales=scales, zero_points=zeros,
                            quantized_dimension=int(q.QuantizedDimension()) if q else None))
    if graph.InputsLength() != 1 or graph.OutputsLength() != 1:
        raise ValueError('one input and output required')
    input_tensor, output_tensor = tensors[graph.Inputs(0)], tensors[graph.Outputs(0)]
    for tensor, shape in ((input_tensor, [1, 100]), (output_tensor, [1, 3])):
        if tensor['dtype'] != 'int8' or tensor['shape'] != shape or len(tensor['scales']) != 1:
            raise ValueError('INT8 IO shapes must be [1,100] -> [1,3], per-tensor quantization')
    interpreter = tf.lite.Interpreter(model_content=data, num_threads=1,
                                     experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_REF)
    interpreter.allocate_tensors()
    interpreter.set_tensor(input_tensor['index'], np.full((1, 100), input_tensor['zero_points'][0], np.int8))
    interpreter.invoke()
    return dict(schema_version='int8-audit-v1', model_id=hashlib.sha256(data).hexdigest(),
                bytes=len(data), operators=operators, tensors=tensors,
                input=input_tensor, output=output_tensor, full_integer=True)


import csv
from itertools import groupby
from pc.dataset import iter_windows


def read_windows(root, split, *, purpose):
    """Read verified v2 windows; development cannot access the locked test split.

    Hash checks are structural integrity checks, never model evaluation. Only
    the requested split is opened, so fitting/calibration cannot consume test.
    """
    allowed = {'train': {'train'}, 'calibrate': {'train'}, 'select': {'validation'},
               'reference': {'train', 'validation'}, 'final-evaluation': {'test'}}
    if split not in allowed.get(purpose, set()):
        raise ValueError(f'forbidden split/purpose: {split}/{purpose}')
    root = Path(root)
    manifest = json.loads((root / 'manifest.json').read_text())
    identity = dict(manifest)
    dataset_id = identity.pop('dataset_id')
    if (manifest['schema_version'] != 'dataset-v2'
            or hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest() != dataset_id):
        raise ValueError('invalid dataset-v2 manifest identity')
    lock = json.loads((root / 'test-lock.json').read_text())
    if lock['dataset_id'] != dataset_id or lock['manifest_sha256'] != file_hash(root / 'manifest.json'):
        raise ValueError('dataset lock mismatch')
    for name in (f'{split}.csv', f'{split}-windows.csv', 'runs.csv', 'config.json'):
        if file_hash(root / name) != manifest['sha256'][name]:
            raise ValueError(f'checksum mismatch: {name}')
    features, labels, ids = [], [], []
    with (root / f'{split}.csv').open(newline='') as handle:
        for run_id, group in groupby(csv.DictReader(handle), key=lambda r: r['run_id']):
            rows = list(group)
            for row in rows:
                for key in ('timestamp_ms', 'g'):
                    row[key] = int(row[key])
                for key in ('v', 'u', 's', 'tau'):
                    row[key] = float(row[key])
            for index, window in enumerate(iter_windows(rows), 19):
                row = rows[index]
                if (row['status'] != 'ok' or int(row['class_index']) != window.class_index
                        or int(row['action']) != window.action):
                    raise ValueError(f'label mismatch: {window.window_id}')
                features.append(window.features)
                labels.append(window.class_index)
                ids.append(window.window_id)
    if not features:
        raise ValueError('no valid windows')
    return np.asarray(features, dtype=np.float32), np.asarray(labels, dtype=np.int64), ids, manifest


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')


def export_model(keras_path, dataset, output, *, calibration_size=1024):
    """Export using only verified training windows and save their provenance."""
    import tensorflow as tf
    if type(calibration_size) is not int or calibration_size <= 0:
        raise ValueError('positive calibration_size required')
    output = Path(output)
    if output.exists():
        raise ValueError('export directory already exists')
    x, y, ids, manifest = read_windows(dataset, 'train', purpose='calibrate')
    # Include every training class before uniformly spanning the remaining windows.
    selected = []
    for label in range(3):
        positions = np.flatnonzero(y == label)
        if len(positions):
            selected.extend(positions[np.linspace(0, len(positions)-1,
                            min(len(positions), max(1, calibration_size//3)), dtype=int)].tolist())
    selected = list(dict.fromkeys(selected))[:calibration_size]
    if len(selected) < min(calibration_size, len(x)):
        used = set(selected)
        for index in np.linspace(0, len(x)-1, len(x), dtype=int):
            if int(index) not in used:
                selected.append(int(index))
                if len(selected) == min(calibration_size, len(x)):
                    break
    model = tf.keras.models.load_model(keras_path, compile=False)
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.representative_dataset = lambda: ([x[i:i+1]] for i in selected)
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    data = converter.convert()
    output.mkdir(parents=True)
    (output / 'model.tflite').write_bytes(data)
    audit = audit_model(output / 'model.tflite')
    write_json(output / 'audit.json', audit)
    write_json(output / 'export.json', dict(
        schema_version='mlp-export-v1', model_id=audit['model_id'], dataset_id=manifest['dataset_id'],
        source_model_sha256=file_hash(keras_path), class_order=CLASS_ORDER,
        input_version=INPUT_VERSION, normalization='[v/80,u,s/10,g-1,min(tau,10)/10]',
        arithmetic='float32; round-half-away-from-zero(x/scale)+zero_point; saturate [-128,127]',
        calibration_split='train', calibration_window_ids=[ids[i] for i in selected],
        converter=dict(supported_ops=['TFLITE_BUILTINS_INT8'], input_type='int8', output_type='int8',
                       optimization='DEFAULT', tensorflow=tf.__version__),
        input=audit['input'], output=audit['output']))
    return audit


def fp32_predictions(model, x):
    return np.concatenate([np.asarray(model(x[i:i+4096], training=False))
                           for i in range(0, len(x), 4096)])


def train_model(dataset, output, config):
    """Fit on train, checkpoint exclusively by validation macro-F1."""
    import tensorflow as tf
    config = dict(config)
    architecture = config.get('architecture')
    if (not isinstance(architecture, list) or len(architecture) != 4
            or architecture[0] != 100 or architecture[-1] != 3
            or any(type(width) is not int or width <= 0 for width in architecture)):
        raise ValueError('architecture must be [100, positive hidden width, positive hidden width, 3]')
    if architecture != [100, 32, 16, 3] and not config.get('architecture_reason'):
        raise ValueError('changed architecture requires architecture_reason')
    for key in ('epochs', 'patience', 'batch_size', 'seed', 'calibration_size'):
        if type(config.get(key)) is not int or config[key] <= 0:
            raise ValueError(f'positive integer required: {key}')
    if config.get('class_weight') not in ('none', 'inverse_sqrt'):
        raise ValueError('class_weight must be none or inverse_sqrt')
    if not 0 < config.get('learning_rate', 0) < 1:
        raise ValueError('invalid learning rate')
    output = Path(output)
    if output.exists():
        raise ValueError('training directory already exists')
    x, y, ids, manifest = read_windows(dataset, 'train', purpose='train')
    vx, vy, _, validation_manifest = read_windows(dataset, 'validation', purpose='select')
    if manifest['dataset_id'] != validation_manifest['dataset_id']:
        raise ValueError('dataset changed while loading')
    tf.keras.utils.set_random_seed(config['seed'])
    tf.config.experimental.enable_op_determinism()
    model = tf.keras.Sequential([tf.keras.Input(shape=(100,), name='window'),
        tf.keras.layers.Dense(architecture[1], activation='relu'),
        tf.keras.layers.Dense(architecture[2], activation='relu'),
        tf.keras.layers.Dense(3, activation='softmax')])
    model.compile(optimizer=tf.keras.optimizers.Adam(config['learning_rate']),
                  loss='sparse_categorical_crossentropy')
    counts = np.bincount(y, minlength=3)
    if np.any(counts == 0):
        raise ValueError('all three classes required in training')
    weights = np.ones(3, dtype=np.float32)
    if config['class_weight'] == 'inverse_sqrt':
        weights = np.sqrt(len(y) / (3 * counts)).astype(np.float32)
        weights /= np.mean(weights[y])
    rng = np.random.default_rng(config['seed'])
    output.mkdir(parents=True)
    write_json(output / 'config.json', config)
    history, best, best_epoch = [], -1.0, -1
    for epoch in range(config['epochs']):
        order = rng.permutation(len(y))
        model.reset_metrics()
        for start in range(0, len(y), config['batch_size']):
            indices = order[start:start + config['batch_size']]
            loss = float(model.train_on_batch(x[indices], y[indices], sample_weight=weights[y[indices]]))
        report = classification_report(vy, fp32_predictions(model, vx).argmax(axis=1))
        score = report['macro_f1']
        history.append(dict(epoch=epoch+1, training_loss=loss, validation_macro_f1=score))
        write_json(output / 'history.json', history)
        print(json.dumps(history[-1]), flush=True)
        if score > best:
            best, best_epoch = score, epoch
            model.save(output / 'model.keras')
            write_json(output / 'validation-fp32.json', report)
        if epoch - best_epoch >= config['patience']:
            break
    write_json(output / 'training.json', dict(
        schema_version='mlp-training-v1', dataset_id=manifest['dataset_id'],
        manifest_sha256=file_hash(Path(dataset) / 'manifest.json'),
        training_split='train', selection_split='validation', selection_metric='macro_f1',
        best_epoch=best_epoch+1, validation_macro_f1=best, train_windows=len(y), validation_windows=len(vy),
        class_counts=counts.tolist(), class_weights=weights.tolist(), class_order=CLASS_ORDER,
        input_version=INPUT_VERSION, seed=config['seed'], tensorflow=tf.__version__,
        model_sha256=file_hash(output / 'model.keras'),
        train_window_ids_sha256=hashlib.sha256('\n'.join(ids).encode()).hexdigest()))
    return best


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    train = commands.add_parser('train', help='train only on train; select only on validation')
    train.add_argument('--dataset', type=Path, required=True)
    train.add_argument('--output', type=Path, required=True)
    train.add_argument('--config', type=Path, required=True)
    export = commands.add_parser('export', help='calibrate only on train; export full INT8')
    export.add_argument('--dataset', type=Path, required=True)
    export.add_argument('--keras', type=Path, required=True)
    export.add_argument('--output', type=Path, required=True)
    export.add_argument('--calibration-size', type=int, default=1024)
    audit = commands.add_parser('audit', help='inspect actual integer tensors/operators and run inference')
    audit.add_argument('model', type=Path)
    evaluate = commands.add_parser('evaluate', help='compare FP32/INT8 on train or validation')
    evaluate.add_argument('--split', choices=['train', 'validation'], default='validation')
    evaluate.add_argument('--dataset', type=Path, required=True)
    evaluate.add_argument('--export', type=Path, required=True)
    evaluate.add_argument('--keras', type=Path, required=True)
    evaluate.add_argument('--output', type=Path, required=True)
    reference = commands.add_parser('reference', help='JSONL raw windows to PC integer reference records')
    reference.add_argument('--export', type=Path, required=True)
    reference.add_argument('--input', type=Path, required=True)
    reference.add_argument('--output', type=Path, required=True)
    reference.add_argument('--run-id', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'train':
            train_model(args.dataset, args.output, json.loads(args.config.read_text()))
        elif args.command == 'export':
            export_model(args.keras, args.dataset, args.output, calibration_size=args.calibration_size)
        elif args.command == 'audit':
            print(json.dumps(audit_model(args.model), indent=2))
        elif args.command == 'evaluate':
            evaluate_model(args.export, args.keras, args.dataset, args.output, split=args.split)
        elif args.command == 'reference':
            reference_file(args.export, args.input, args.output, run_id=args.run_id)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f'{error}\n')


class ReferenceModel:
    """PC reference with the TFLite reference integer kernels (no delegate)."""

    def __init__(self, export_directory):
        import tensorflow as tf
        root = Path(export_directory)
        self.audit = audit_model(root / 'model.tflite')
        self.metadata = json.loads((root / 'export.json').read_text())
        self.model_id = self.audit['model_id']
        if (self.metadata['model_id'] != self.model_id or self.metadata['class_order'] != CLASS_ORDER
                or self.metadata['input_version'] != INPUT_VERSION
                or self.metadata['input'] != self.audit['input'] or self.metadata['output'] != self.audit['output']):
            raise ValueError('export metadata/model mismatch')
        self.interpreter = tf.lite.Interpreter(model_path=str(root / 'model.tflite'), num_threads=1,
            experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_REF)
        self.interpreter.allocate_tensors()

    def _identity(self, window_id, trip_id):
        return dict(window_id=window_id, trip_id=trip_id, model_id=self.model_id,
                    dataset_id=self.metadata['dataset_id'], input_version=INPUT_VERSION,
                    schema_version='pc-reference-v1', decision_source='int8_mlp')

    def predict_int8(self, values, *, window_id, trip_id):
        """Run already quantized values; errors never become a hold decision."""
        result = self._identity(window_id, trip_id)
        try:
            values = np.asarray(values)
        except (ValueError, TypeError) as error:
            return dict(result, status='invalid_input', error=str(error))
        if values.shape != (100,) or values.dtype.kind not in 'iu' or np.any((values < -128) | (values > 127)):
            return dict(result, status='invalid_input', error='expected 100 integer INT8 codes')
        values = values.astype(np.int8)
        try:
            self.interpreter.set_tensor(self.audit['input']['index'], values.reshape(1, 100))
            self.interpreter.invoke()
            output = self.interpreter.get_tensor(self.audit['output']['index'])[0]
        except (RuntimeError, ValueError) as error:
            return dict(result, status='model_error', error=str(error))
        index = int(np.argmax(output))
        return dict(result, status='ok', input_int8=values.tolist(), output_int8=output.tolist(),
                    class_index=index, action=index-1, decision=CLASS_ORDER[index])

    def predict(self, window):
        """Accept the existing JSON Lines window contract; validate before scaling."""
        from gearshift.protocol import preprocess, ProtocolError
        try:
            features = np.asarray(preprocess(window), dtype=np.float32)
        except ProtocolError as error:
            return dict(self._identity(window.get('window_id') if isinstance(window, dict) else None,
                                       window.get('trip_id') if isinstance(window, dict) else None),
                        status='invalid_window', error=str(error))
        params = self.audit['input']
        values = quantize(features, params['scales'][0], params['zero_points'][0])
        result = self.predict_int8(values, window_id=window['window_id'], trip_id=window['trip_id'])
        result['input_float32'] = features.tolist()
        return result


def evaluate_model(export_directory, keras_path, dataset, output, *, split='validation'):
    """Compare original FP32, input-quantized FP32 and INT8, without test access."""
    import tensorflow as tf
    output = Path(output)
    if output.exists():
        raise ValueError('evaluation output already exists')
    reference = ReferenceModel(export_directory)
    if file_hash(keras_path) != reference.metadata['source_model_sha256']:
        raise ValueError('FP32 source model mismatch')
    if split not in ('train', 'validation'):
        raise ValueError('evaluation split must be train or validation')
    x, y, ids, manifest = read_windows(dataset, split, purpose='reference')
    if manifest['dataset_id'] != reference.metadata['dataset_id']:
        raise ValueError('reference/dataset mismatch')
    model = tf.keras.models.load_model(keras_path, compile=False)
    fp32 = fp32_predictions(model, x).argmax(axis=1)
    params = reference.audit['input']
    quantized = quantize(x, params['scales'][0], params['zero_points'][0])
    restored = (quantized.astype(np.float32) - params['zero_points'][0]) * params['scales'][0]
    input_fp32 = fp32_predictions(model, restored).argmax(axis=1)
    predicted = []
    for values, identity in zip(quantized, ids):
        result = reference.predict_int8(values, window_id=identity, trip_id=identity.rsplit(':', 1)[0])
        if result['status'] != 'ok':
            raise ValueError(f'inference failed: {identity}: {result}')
        predicted.append(result['class_index'])
    predicted = np.asarray(predicted)
    def changes(before, after):
        new = (before == y) & (after != y)
        corrected = (before != y) & (after == y)
        changed = before != after
        return dict(new_errors=int(np.count_nonzero(new)),
                    corrected_errors=int(np.count_nonzero(corrected)),
                    decision_changes=int(np.count_nonzero(changed)),
                    classes=[dict(class_index=label,
                        new_errors=int(np.count_nonzero(new & (y == label))),
                        corrected_errors=int(np.count_nonzero(corrected & (y == label))),
                        decision_changes=int(np.count_nonzero(changed & (y == label))))
                        for label in range(3)])
    examples = []
    for label in range(3):
        errors = np.flatnonzero((y == label) & ((fp32 != y) | (predicted != y)))
        # Sample across each class rather than allowing hold to hide rare shifts.
        for index in errors[np.linspace(0, len(errors)-1, min(20, len(errors)), dtype=int)]:
            recent = x[index].reshape(20, 5)[-5:]
            v, u, s = recent[:, :3].mean(axis=0) * [80, 1, 10]
            gear = int(x[index, -2]) + 1
            margin = float(v - (30 + 20*u + .5*s - (10 if gear == 2 else 0)))
            examples.append(dict(window_id=ids[index], expected_class=label,
                fp32_class=int(fp32[index]), input_quantized_fp32_class=int(input_fp32[index]),
                int8_class=int(predicted[index]), gear=gear, tau_s=float(x[index, -1]*10),
                speed_threshold_margin_kmh=margin))
    report = dict(schema_version='mlp-validation-v1', split=split,
                  dataset_id=manifest['dataset_id'], model_id=reference.model_id,
                  fp32=classification_report(y, fp32), int8=classification_report(y, predicted),
                  input_quantized_fp32=classification_report(y, input_fp32),
                  quantization_errors=dict(input=changes(fp32, input_fp32),
                      network=changes(input_fp32, predicted), total=changes(fp32, predicted)),
                  error_examples=examples,
                  decision_agreement=float(np.mean(fp32 == np.asarray(predicted))),
                  disagreements=int(np.count_nonzero(fp32 != np.asarray(predicted))),
                  window_ids_sha256=hashlib.sha256('\n'.join(ids).encode()).hexdigest())
    report['quality_target_met'] = split == 'validation' and report['int8']['macro_f1'] >= 0.95
    write_json(output, report)
    return report


def reference_file(export_directory, input_path, output_path, *, run_id):
    """Write one record per raw window; existing output files are never replaced."""
    from gearshift.protocol import identifier
    if not identifier(run_id):
        raise ValueError('invalid run_id')
    reference = ReferenceModel(export_directory)
    def reject_constant(value):
        raise ValueError(f'non-standard JSON number: {value}')
    with Path(input_path).open() as source, Path(output_path).open('x') as destination:
        for line in source:
            window = json.loads(line, parse_constant=reject_constant)
            result = reference.predict(window)
            result['run_id'] = run_id
            destination.write(json.dumps(result, allow_nan=False, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
