"""Tests at the user-approved PC reference, CLI and export-audit seams."""
import unittest
import importlib.util

MODEL_DEPS = all(importlib.util.find_spec(name) for name in ('numpy', 'tensorflow'))


@unittest.skipUnless(MODEL_DEPS, 'install requirements-model.txt to run model integration tests')
class ReferenceTests(unittest.TestCase):
    def test_quantization_rounds_half_away_from_zero_then_saturates(self):
        from pc.model import quantize
        self.assertEqual(quantize([-100, -0.75, -0.25, 0.25, 0.75, 100], 0.5, -3).tolist(),
                         [-128, -5, -4, -2, -1, 127])

    def test_quantization_distinguishes_half_from_adjacent_float32_values(self):
        import numpy as np
        from pc.model import quantize
        scale = 0.005345386452972889
        below = np.nextafter(np.float32(.5), np.float32(0))
        above = np.nextafter(np.float32(.5), np.float32(1))
        values = np.float32(scale) * np.array(
            [-above, -.5, -below, below, .5, above], dtype=np.float32)
        self.assertEqual(quantize(values, scale, -60).tolist(),
                         [-61, -61, -60, -60, -59, -59])

    def test_report_counts_rare_classes_instead_of_hiding_them_in_accuracy(self):
        from pc.model import classification_report
        report = classification_report([0, 0, 1, 1, 2, 2], [0, 1, 1, 1, 0, 2])
        self.assertEqual(report['confusion_matrix'], [[1, 1, 0], [0, 2, 0], [1, 0, 1]])
        self.assertAlmostEqual(report['macro_f1'], (0.5 + 0.8 + 2/3) / 3)
        self.assertEqual([c['support'] for c in report['classes']], [2, 2, 2])


@unittest.skipUnless(MODEL_DEPS, 'install requirements-model.txt to run model integration tests')
class ExportTests(unittest.TestCase):
    def test_audit_rejects_float_model_even_when_it_runs_in_tflite(self):
        import tempfile
        from pathlib import Path
        import tensorflow as tf
        from pc.model import audit_model
        model = tf.keras.Sequential([tf.keras.Input((100,)), tf.keras.layers.Dense(3, activation='softmax')])
        data = tf.lite.TFLiteConverter.from_keras_model(model).convert()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'float.tflite'
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'INT8'):
                audit_model(path)


@unittest.skipUnless(MODEL_DEPS, 'install requirements-model.txt to run model integration tests')
class PipelineTests(unittest.TestCase):
    def test_model_development_refuses_locked_test_and_validation_calibration(self):
        from pc.model import read_windows
        for split, purpose in [('test', 'train'), ('test', 'calibrate'),
                               ('test', 'select'), ('validation', 'calibrate')]:
            with self.subTest(split=split, purpose=purpose):
                with self.assertRaisesRegex(ValueError, 'forbidden'):
                    read_windows('/does-not-exist', split, purpose=purpose)


def make_training_fixture(root):
    """Small public CSV contract fixture, independent of the locked dataset."""
    import csv
    import hashlib
    import json
    from pc.dataset import Config, RunSpec, generate_run
    rows = generate_run(RunSpec('fixture', 'fixture-family', 'threshold', 1), Config(duration_s=4))
    fields = ['run_id', 'timestamp_ms', 'v', 'u', 's', 'g', 'tau', 'action', 'class_index', 'status']
    with (root / 'train.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row[key] for key in fields} for row in rows)
    for name in ('train-windows.csv', 'runs.csv', 'config.json'):
        (root / name).write_text('{}')
    manifest = {'schema_version': 'dataset-v2', 'sha256': {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in ('train.csv', 'train-windows.csv', 'runs.csv', 'config.json')}}
    manifest['dataset_id'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    (root / 'manifest.json').write_text(json.dumps(manifest))
    (root / 'test-lock.json').write_text(json.dumps({
        'dataset_id': manifest['dataset_id'],
        'manifest_sha256': hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest()}))
    return manifest['dataset_id']


@unittest.skipUnless(MODEL_DEPS, 'install requirements-model.txt to run model integration tests')
class IntegerExportTests(unittest.TestCase):
    def test_export_runs_real_int8_model_and_records_training_only_calibration(self):
        import tempfile
        import json
        from pathlib import Path
        import tensorflow as tf
        from pc.model import export_model, audit_model
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_id = make_training_fixture(root)
            model = tf.keras.Sequential([tf.keras.Input((100,)),
                tf.keras.layers.Dense(32, activation='relu'),
                tf.keras.layers.Dense(16, activation='relu'),
                tf.keras.layers.Dense(3, activation='softmax')])
            model.save(root / 'model.keras')
            export_model(root / 'model.keras', root, root / 'export', calibration_size=10)
            audit = audit_model(root / 'export/model.tflite')
            metadata = json.loads((root / 'export/export.json').read_text())
            self.assertEqual((audit['input']['shape'], audit['output']['shape']), ([1, 100], [1, 3]))
            self.assertTrue(audit['full_integer'])
            self.assertEqual(metadata['dataset_id'], dataset_id)
            self.assertEqual(metadata['calibration_split'], 'train')
            self.assertEqual(len(metadata['calibration_window_ids']), 10)
            self.assertTrue(all(i.startswith('fixture:') for i in metadata['calibration_window_ids']))


@unittest.skipUnless(MODEL_DEPS, 'install requirements-model.txt to run model integration tests')
class TrainingCLITests(unittest.TestCase):
    def test_cli_trains_and_preserves_selection_without_test_files(self):
        import tempfile
        import json
        import hashlib
        import subprocess
        import sys
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_training_fixture(root)
            for suffix in ('.csv', '-windows.csv'):
                (root / ('validation' + suffix)).write_bytes((root / ('train' + suffix)).read_bytes())
            manifest = json.loads((root / 'manifest.json').read_text())
            for name in ('validation.csv', 'validation-windows.csv'):
                manifest['sha256'][name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
            del manifest['dataset_id']
            manifest['dataset_id'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
            (root / 'manifest.json').write_text(json.dumps(manifest))
            (root / 'test-lock.json').write_text(json.dumps({'dataset_id': manifest['dataset_id'],
                'manifest_sha256': hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest()}))
            config = json.loads(Path('config/model-v1.json').read_text())
            config.update(epochs=2, patience=2, batch_size=8)
            (root / 'settings.json').write_text(json.dumps(config))
            result = subprocess.run([sys.executable, '-m', 'pc.model', 'train', '--dataset', str(root),
                '--output', str(root / 'trained'), '--config', str(root / 'settings.json')],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / 'trained/model.keras').exists())
            provenance = json.loads((root / 'trained/training.json').read_text())
            self.assertEqual(provenance['selection_split'], 'validation')
            self.assertEqual(provenance['training_split'], 'train')
            self.assertEqual(provenance['dataset_id'], manifest['dataset_id'])


@unittest.skipUnless(MODEL_DEPS, 'install requirements-model.txt to run model integration tests')
class PCModelTests(unittest.TestCase):
    def test_ragged_int8_input_returns_error_without_decision(self):
        from pc.model import ReferenceModel
        reference = ReferenceModel('models/mlp-v1')
        result = reference.predict_int8([[1], [1, 2]], window_id='w', trip_id='t')
        self.assertEqual(result['status'], 'invalid_input')
        self.assertTrue(result['error'])
        self.assertEqual((result['window_id'], result['trip_id']), ('w', 't'))
        self.assertEqual(result['model_id'], reference.model_id)
        for field in ('action', 'decision', 'class_index', 'output_int8'):
            self.assertNotIn(field, result)
        valid = reference.predict_int8([0] * 100, window_id='next', trip_id='t')
        self.assertEqual(valid['status'], 'ok')

    def test_raw_and_prequantized_reference_agree_and_invalid_window_has_no_decision(self):
        import tempfile
        from pathlib import Path
        import numpy as np
        import tensorflow as tf
        from gearshift.client import example_window
        from pc.model import ReferenceModel, export_model
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset_id = make_training_fixture(root)
            model = tf.keras.Sequential([tf.keras.Input((100,)), tf.keras.layers.Dense(3, activation='softmax',
                kernel_initializer=tf.keras.initializers.Constant(0.01), bias_initializer='zeros')])
            model.save(root / 'model.keras')
            export_model(root / 'model.keras', root, root / 'export', calibration_size=10)
            reference = ReferenceModel(root / 'export')
            window = example_window(0)
            window['samples'] = [[40, .5, -5, 2, 25] for _ in range(20)]
            result = reference.predict(window)
            direct = reference.predict_int8(result['input_int8'], window_id=window['window_id'], trip_id=window['trip_id'])
            self.assertEqual(result['input_float32'], [.5, .5, -.5, 1., 1.] * 20)
            self.assertEqual(result['output_int8'], [-43, -43, -43])
            self.assertEqual((result['class_index'], result['action']), (0, -1))
            self.assertEqual(result['output_int8'], direct['output_int8'])
            self.assertEqual(result['dataset_id'], dataset_id)
            self.assertEqual(result['model_id'], reference.model_id)
            window['samples'][0][0] = float('nan')
            invalid = reference.predict(window)
            self.assertEqual(invalid['status'], 'invalid_window')
            self.assertNotIn('action', invalid)

    def test_evaluate_cli_reports_full_validation_and_fp32_int8_comparison(self):
        import tempfile
        import json
        import hashlib
        import subprocess
        import sys
        from pathlib import Path
        import tensorflow as tf
        from pc.model import export_model
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_training_fixture(root)
            manifest = json.loads((root / 'manifest.json').read_text())
            for suffix in ('.csv', '-windows.csv'):
                name = 'validation' + suffix
                (root / name).write_bytes((root / ('train' + suffix)).read_bytes())
                manifest['sha256'][name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
            del manifest['dataset_id']
            manifest['dataset_id'] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
            (root / 'manifest.json').write_text(json.dumps(manifest))
            (root / 'test-lock.json').write_text(json.dumps({'dataset_id': manifest['dataset_id'],
                'manifest_sha256': hashlib.sha256((root / 'manifest.json').read_bytes()).hexdigest()}))
            model = tf.keras.Sequential([tf.keras.Input((100,)), tf.keras.layers.Dense(3, activation='softmax',
                kernel_initializer=tf.keras.initializers.Constant(.01), bias_initializer='zeros')])
            model.save(root / 'model.keras')
            export_model(root / 'model.keras', root, root / 'export', calibration_size=10)
            result = subprocess.run([sys.executable, '-m', 'pc.model', 'evaluate', '--dataset', str(root),
                '--export', str(root / 'export'), '--keras', str(root / 'model.keras'),
                '--output', str(root / 'validation.json')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((root / 'validation.json').read_text())
            self.assertEqual(report['split'], 'validation')
            self.assertEqual(report['int8']['confusion_matrix'], [[1, 0, 0], [59, 0, 0], [1, 0, 0]])
            self.assertEqual(report['decision_agreement'], 1.0)
            self.assertFalse(report['quality_target_met'])

    def test_reference_cli_exports_window_identity_and_reports_invalid_input(self):
        import tempfile
        import subprocess
        import sys
        import json
        from pathlib import Path
        import tensorflow as tf
        from pc.model import export_model
        from gearshift.client import example_window
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_training_fixture(root)
            model = tf.keras.Sequential([tf.keras.Input((100,)), tf.keras.layers.Dense(3, activation='softmax',
                kernel_initializer=tf.keras.initializers.Constant(.01), bias_initializer='zeros')])
            model.save(root / 'model.keras')
            export_model(root / 'model.keras', root, root / 'export', calibration_size=10)
            window = example_window(0)
            bad = example_window(1)
            bad['samples'][0][0] = -1
            (root / 'windows.jsonl').write_text(json.dumps(window) + '\n' + json.dumps(bad) + '\n')
            result = subprocess.run([sys.executable, '-m', 'pc.model', 'reference', '--export', str(root / 'export'),
                '--input', str(root / 'windows.jsonl'), '--output', str(root / 'outputs.jsonl'), '--run-id', 'fixture-run'],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            records = [json.loads(line) for line in (root / 'outputs.jsonl').read_text().splitlines()]
            self.assertEqual([r['window_id'] for r in records], [window['window_id'], bad['window_id']])
            self.assertEqual(records[0]['run_id'], 'fixture-run')
            self.assertEqual(records[0]['output_int8'], [-43, -43, -43])
            self.assertEqual(records[1]['status'], 'invalid_window')
            self.assertNotIn('decision', records[1])
