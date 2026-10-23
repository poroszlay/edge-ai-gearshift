#!/usr/bin/env python3
"""Generate a model header only from a self-consistent frozen INT8 export."""
import hashlib
import json
from pathlib import Path
import sys

root, destination = map(Path, sys.argv[1:])
meta = json.loads((root / 'export.json').read_text())
freeze = json.loads((root / 'freeze.json').read_text())
blob = (root / 'model.tflite').read_bytes()
identity = hashlib.sha256(blob).hexdigest()
if (identity != meta['model_id'] or identity != freeze['model_id']
        or not freeze['frozen'] or meta['class_order'] != ['downshift', 'hold', 'upshift']
        or meta['input_version'] != 'window-v1:20x5:sample-major:fixed-scaling:float32'
        or meta['input']['shape'] != [1, 100] or meta['output']['shape'] != [1, 3]
        or meta['input']['dtype'] != 'int8' or meta['output']['dtype'] != 'int8'):
    raise ValueError('frozen model contract mismatch')
for name, digest in freeze['sha256'].items():
    if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
        raise ValueError(f'freeze checksum mismatch: {name}')
lines = ['#pragma once', '#include <cstdint>', 'namespace embedded {',
         f'constexpr char model_id[] = {json.dumps(identity)};',
         f'constexpr char dataset_id[] = {json.dumps(meta["dataset_id"])};',
         f'constexpr float input_scale = {meta["input"]["scales"][0]:.18g}f;',
         f'constexpr int input_zero = {meta["input"]["zero_points"][0]};',
         f'constexpr float output_scale = {meta["output"]["scales"][0]:.18g}f;',
         f'constexpr int output_zero = {meta["output"]["zero_points"][0]};',
         'alignas(16) const unsigned char model_data[] = {']
for offset in range(0, len(blob), 16):
    lines.append(','.join(f'0x{x:02x}' for x in blob[offset:offset+16]) + ',')
lines += ['};', '}']
destination.write_text('\n'.join(lines) + '\n')
print(json.dumps(dict(model_id=identity, dataset_id=meta['dataset_id'], model_bytes=len(blob))))
