"""Deterministic rule reference for raw, chronological sample windows."""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class LabelResult:
    status: str
    action: int | None = None
    class_index: int | None = None


def label_window(samples: object) -> LabelResult:
    """Label 20 raw samples; invalid windows have no action or class index.

    See docs/rule-reference.md for fields, units, validation and status codes.
    The input is never modified and all samples are checked before labeling.
    """
    if not isinstance(samples, (list, tuple)):
        return LabelResult("invalid_type")
    if len(samples) != 20:
        return LabelResult("invalid_window_length")
    for position, sample in enumerate(samples):
        if not isinstance(sample, dict):
            return LabelResult("invalid_type")
        if any(field not in sample for field in
               ("run_id", "timestamp_ms", "v", "u", "s", "g", "tau")):
            return LabelResult("missing_signal")
        if (not isinstance(sample["run_id"], str) or not sample["run_id"].strip()
                or sample["run_id"] != samples[0]["run_id"]):
            return LabelResult("invalid_run")
        if any(type(sample[field]) not in (int, float)
               for field in ("v", "u", "s", "g", "tau")):
            return LabelResult("invalid_type")
        if type(sample["timestamp_ms"]) not in (int, float):
            return LabelResult("invalid_sampling_time")
        if any(type(sample[field]) is float and not math.isfinite(sample[field]) for field in
               ("timestamp_ms", "v", "u", "s", "g", "tau")):
            return LabelResult("non_finite_value")
        if not (0 <= sample["v"] <= 80 and 0 <= sample["u"] <= 1
                and -10 <= sample["s"] <= 10 and sample["g"] in (1, 2)
                and sample["tau"] >= 0):
            return LabelResult("out_of_range")
        timestamp = sample["timestamp_ms"]
        if (type(timestamp) is not int or timestamp < 0
                or (position and timestamp - samples[position - 1]["timestamp_ms"] != 50)):
            return LabelResult("invalid_sampling_time")
    if samples[-1]["tau"] < 1:
        return LabelResult("ok", 0, 1)
    recent = samples[-5:]
    v = sum(sample["v"] for sample in recent) / 5
    u = sum(sample["u"] for sample in recent) / 5
    s = sum(sample["s"] for sample in recent) / 5
    up = 30 + 20 * u + 0.5 * s
    action = 1 if samples[-1]["g"] == 1 and v > up else 0
    if samples[-1]["g"] == 2 and v < up - 10:
        action = -1
    return LabelResult("ok", action, action + 1)
