"""Shared frozen-export contract, usable without NumPy or TensorFlow."""
import hashlib
import json
from pathlib import Path


def validate_freeze(metadata, freeze, checksums):
    """Validate supplied metadata and actual digests without I/O or mutation."""
    if (freeze.get('frozen') is not True
            or freeze.get('model_id') != metadata['model_id']
            or checksums['model.tflite'] != metadata['model_id']
            or freeze.get('dataset_id') != metadata['dataset_id']):
        raise ValueError('frozen model contract mismatch')
    for name, expected in freeze['sha256'].items():
        if checksums[name] != expected:
            raise ValueError(f'frozen checksum mismatch: {name}')


def read_frozen_export(directory):
    """Read a package, validate its freeze contract, and return metadata/bytes."""
    root = Path(directory)
    metadata = json.loads((root / 'export.json').read_text())
    freeze = json.loads((root / 'freeze.json').read_text())
    blob = (root / 'model.tflite').read_bytes()
    checksums = {'model.tflite': hashlib.sha256(blob).hexdigest()}
    for name in freeze['sha256']:
        if name not in checksums:
            checksums[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    validate_freeze(metadata, freeze, checksums)
    return metadata, blob
