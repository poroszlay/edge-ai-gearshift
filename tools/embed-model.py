#!/usr/bin/env python3
"""Generate a model header only from a self-consistent frozen INT8 export."""
import json
from pathlib import Path
import sys

# CMake invokes this file by absolute path from its build directory, with
# the SDK's stdlib-only Python environment rather than an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gearshift.frozen_export import read_frozen_export

root, destination = map(Path, sys.argv[1:])
meta, blob = read_frozen_export(root)
identity = meta['model_id']
if (meta['class_order'] != ['downshift', 'hold', 'upshift']
        or meta['input_version'] != 'window-v1:20x5:sample-major:fixed-scaling:float32'
        or meta['input']['shape'] != [1, 100] or meta['output']['shape'] != [1, 3]
        or meta['input']['dtype'] != 'int8' or meta['output']['dtype'] != 'int8'):
    raise ValueError('frozen model contract mismatch')
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
