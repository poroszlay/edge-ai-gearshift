#!/usr/bin/env python3
"""Select small, fixed validation examples for the #7 porting handoff.

This does not evaluate a model or read test data. Run from the repository root.
"""
import argparse
from collections import deque
import csv
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dataset', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
counts = [0, 0, 0]
boundaries = set()
selected = {}
recent = deque(maxlen=20)
run_id = None
index = -1
with (args.dataset / 'validation.csv').open(newline='') as handle:
    for raw in csv.DictReader(handle):
        if raw['run_id'] != run_id:
            recent.clear()
            run_id, index = raw['run_id'], -1
        index += 1
        sample = dict(raw)
        for key in ('timestamp_ms', 'g'):
            sample[key] = int(sample[key])
        for key in ('v', 'u', 's', 'tau'):
            sample[key] = float(sample[key])
        recent.append(sample)
        if len(recent) != 20 or raw['status'] != 'ok':
            continue
        label = int(raw['class_index'])
        boundary = ('tau=0.95' if sample['tau'] == .95 else 'tau=1' if sample['tau'] == 1
                    else 'tau>10' if sample['tau'] > 10 else None)
        if counts[label] < 3 or (boundary and boundary not in boundaries):
            identity = f'{run_id}:{index}'
            selected[identity] = dict(window_id=identity, trip_id=run_id,
                timestamps_ms=[s['timestamp_ms'] for s in recent],
                samples=[[s[k] for k in ('v', 'u', 's', 'g', 'tau')] for s in recent],
                source_split='validation', reference_class_index=label)
            counts[label] += 1
            if boundary:
                boundaries.add(boundary)
        if min(counts) >= 3 and len(boundaries) == 3:
            break
if min(counts) < 3 or len(boundaries) != 3:
    parser.exit(1, 'insufficient validation examples; no output written\n')
with args.output.open('x') as handle:
    for window in selected.values():
        handle.write(json.dumps(window, sort_keys=True, allow_nan=False) + '\n')
print(json.dumps(dict(windows=len(selected), minimum_per_class=3, boundaries=sorted(boundaries))))
