"""Reproducible synthetic runs; all decisions come from pc.reference."""

from dataclasses import asdict, dataclass
from collections import deque
from collections.abc import Iterable, Iterator
import hashlib
import math
import random
import argparse
import csv
import json
from pathlib import Path
import platform
import struct
from itertools import groupby, zip_longest

from pc.reference import label_window


@dataclass(frozen=True)
class Config:
    duration_s: int = 120
    seed: int = 20261019
    runs_per_type: int = 40
    noisy_variants: int = 1
    noise_v: float = 0.15
    noise_u: float = 0.005
    noise_s: float = 0.03
    period_samples: int = 240

    def __post_init__(self):
        for name, minimum in (("duration_s", 1), ("seed", 0), ("runs_per_type", 1),
                              ("noisy_variants", 0), ("period_samples", 40)):
            value = getattr(self, name)
            if type(value) is not int or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        group_size = self.noisy_variants + 1
        if self.runs_per_type % (20 * group_size):
            raise ValueError("runs_per_type must be divisible by 20 * (noisy_variants + 1)")
        for name in ("noise_v", "noise_u", "noise_s"):
            value = getattr(self, name)
            if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")


@dataclass(frozen=True)
class RunSpec:
    run_id: str
    family_id: str
    kind: str
    initial_gear: int
    variant: int = 0
    phase_samples: int = 0
    profile_seed: int = 0


KINDS = ("acceleration", "cruise", "uphill", "deceleration", "threshold")
SPLITS = ("train", "validation", "test")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_plan(config: Config) -> dict[str, tuple[RunSpec, ...]]:
    """Assign base runs and noisy variants as indivisible, stratified families."""
    family_count = config.runs_per_type // (config.noisy_variants + 1)
    plan = {split: [] for split in SPLITS}
    for kind in KINDS:
        families = sorted(range(family_count),
                          key=lambda i: _digest(f"{config.seed}:split:{kind}:{i}"))
        for rank, number in enumerate(families):
            split = ("train" if rank < family_count * 70 // 100 else "validation"
                     if rank < family_count * 85 // 100 else "test")
            family_id = f"{kind}-{number:04d}"
            period = 200 if kind == "threshold" else config.period_samples
            offset = int(_digest(f"{config.seed}:phase:{kind}")[:8], 16) % period
            phase = (number * period // family_count + offset) % period
            profile_seed = int(_digest(f"{config.seed}:profile:{family_id}"), 16)
            for variant in range(config.noisy_variants + 1):
                plan[split].append(RunSpec(f"{family_id}-v{variant}", family_id, kind,
                                           1 + number % 2, variant, phase, profile_seed))
    return {split: tuple(specs) for split, specs in plan.items()}


@dataclass(frozen=True)
class _Profile:
    period: int
    speed_scale: float = 1
    demand_scale: float = 1
    slope_shift: float = 0
    slope_scale: float = 1
    threshold_demand: float = 0.2


def _profile(spec: RunSpec, config: Config) -> _Profile:
    # The root realization is shared by every derivative in a family, independent
    # of split membership. Seed zero exposes the canonical worked-example profile.
    if spec.profile_seed == 0:
        return _Profile(config.period_samples)
    rng = random.Random(spec.profile_seed)
    return _Profile(
        max(40, rng.randint(config.period_samples * 3 // 4, config.period_samples * 5 // 4)),
        rng.uniform(0.85, 1.1), rng.uniform(0.85, 1.05),
        rng.randint(-256, 256) / 128, rng.uniform(0.75, 1),
        rng.randint(16, 192) / 256,
    )


def _signals(index: int, spec: RunSpec, profile: _Profile) -> tuple[float, float, float]:
    shifted = index + spec.phase_samples
    triangle = 1 - abs(2 * (shifted % profile.period) / profile.period - 1)
    if spec.kind == "acceleration":
        return ((12 + 52 * triangle) * profile.speed_scale,
                (0.55 + 0.3 * triangle) * profile.demand_scale, profile.slope_shift)
    if spec.kind == "cruise":
        return ((35 + 1.5 * triangle) * profile.speed_scale,
                (0.05 + 0.9 * triangle) * profile.demand_scale, profile.slope_shift)
    if spec.kind == "uphill":
        return ((20 + 40 * triangle) * profile.speed_scale,
                0.5 * profile.demand_scale, (2 + 8 * triangle) * profile.slope_scale)
    if spec.kind == "deceleration":
        return ((64 - 52 * triangle) * profile.speed_scale,
                (0.1 + 0.1 * triangle) * profile.demand_scale, -2 + profile.slope_shift)
    phase = shifted % 200
    demand, slope = profile.threshold_demand, profile.slope_shift
    up = 30 + 20 * demand + 0.5 * slope
    down = up - 10
    v = (up if phase < 30 else up + 12 if phase < 35 else down - 9 if phase < 51
         else up + 12 if phase < 56 else down - 9 if phase < 60
         else down if phase < 90 else down - 0.2 if phase < 120 else up
         if phase < 150 else up + 0.2 if phase < 180 else down + 0.2 if phase < 190 else down)
    return v, demand, slope


def generate_run(spec: RunSpec, config: Config) -> list[dict]:
    """Return predecision samples, with no decisions during the 19-sample warmup."""
    if (spec.kind not in KINDS or type(spec.initial_gear) is not int
            or spec.initial_gear not in (1, 2)
            or any(not isinstance(value, str) or not value.strip()
                   for value in (spec.run_id, spec.family_id))
            or type(spec.variant) is not int or not 0 <= spec.variant <= config.noisy_variants
            or type(spec.phase_samples) is not int or spec.phase_samples < 0
            or type(spec.profile_seed) is not int or spec.profile_seed < 0):
        raise ValueError("invalid run specification")
    rows = []
    gear, elapsed_ms = spec.initial_gear, 10000
    rng = random.Random(_digest(f"{config.seed}:noise:{spec.run_id}"))
    profile = _profile(spec, config)
    for index in range(config.duration_s * 20):
        v, u, s = _signals(index, spec, profile)
        if spec.variant:
            v, u, s = (min(high, max(low, value + rng.uniform(-noise, noise)))
                       for value, noise, low, high in
                       ((v, config.noise_v, 0, 80), (u, config.noise_u, 0, 1),
                        (s, config.noise_s, -10, 10)))
        row = dict(run_id=spec.run_id, timestamp_ms=index * 50,
                   v=v, u=u, s=s, g=gear, tau=elapsed_ms / 1000,
                   action=None, class_index=None, status="warmup")
        rows.append(row)
        if index >= 19:
            result = label_window(rows[-20:])
            if result.status != "ok":
                raise ValueError(f"generated invalid window: {result.status}")
            row.update(action=result.action, class_index=result.class_index, status="ok")
        if row["action"]:
            gear += row["action"]
            elapsed_ms = 50
        else:
            elapsed_ms += 50
    return rows


@dataclass(frozen=True)
class Window:
    run_id: str
    window_id: str
    timestamp_ms: int
    features: tuple[float, ...]
    action: int
    class_index: int


class _OverlapAudit:
    """Compare actual model inputs; identifiers and labels are not features."""

    def __init__(self):
        self.seen = {split: {} for split in SPLITS}
        self.counts = {f"{left}:{right}": 0 for i, left in enumerate(SPLITS)
                       for right in SPLITS[i + 1:]}
        self.examples = []
        self.checked = 0

    def observe(self, split: str, window: Window):
        # IEEE-754 binary64, big-endian, with signed zeros canonicalized so the
        # fingerprint has the same equality semantics as Window.features.
        values = (0.0 if value == 0 else value for value in window.features)
        digest = hashlib.sha256(struct.pack("!100d", *values)).digest()
        for other in SPLITS[:SPLITS.index(split)]:
            if digest in self.seen[other]:
                pair = f"{other}:{split}"
                self.counts[pair] += 1
                if len(self.examples) < 6:
                    self.examples.append(dict(pair=pair, left=self.seen[other][digest],
                                              right=window.window_id, class_index=window.class_index))
        self.seen[split].setdefault(digest, window.window_id)
        self.checked += 1

    def result(self) -> dict:
        return dict(checked_windows=self.checked, matching_windows=self.counts,
                    examples=self.examples, fingerprint="sha256 of 100 big-endian binary64 values; -0=+0")


def iter_windows(samples: Iterable[dict]) -> Iterator[Window]:
    """Validate raw chronological windows, then scale sample-major [v,u,s,g,tau]."""
    recent = deque(maxlen=20)
    for index, row in enumerate(samples):
        recent.append(row)
        if index < 19:
            continue
        raw = list(recent)
        result = label_window(raw)
        if result.status != "ok":
            raise ValueError(f"invalid window: {result.status}")
        features = tuple(value for sample in raw for value in
                         (sample["v"] / 80, sample["u"], sample["s"] / 10,
                          sample["g"] - 1, min(sample["tau"], 10) / 10))
        yield Window(row["run_id"], f"{row['run_id']}:{index}", row["timestamp_ms"],
                     features, result.action, result.class_index)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: object):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


BOUNDARIES = ("upper_equal", "lower_equal", "upper_near", "lower_near",
              "tau_0_95", "tau_1", "blocked_up", "blocked_down", "tau_above_10")


def _stats() -> dict:
    return dict(runs=0, families=0, samples=0, windows=0,
                kinds=dict.fromkeys(KINDS, 0), initial_gears={"1": 0, "2": 0},
                classes={"0": 0, "1": 0, "2": 0}, events={"up": 0, "down": 0},
                boundaries=dict.fromkeys(BOUNDARIES, 0))


def _summarize_run(rows: list[dict], spec: RunSpec, stats: dict, writer,
                   overlap: _OverlapAudit, split: str):
    stats["runs"] += 1
    stats["families"] += spec.variant == 0
    stats["samples"] += len(rows)
    stats["kinds"][spec.kind] += 1
    stats["initial_gears"][str(spec.initial_gear)] += 1
    for index, row in enumerate(rows):
        previous = rows[index - 1] if index else None
        gear = (previous["g"] + (previous["action"] or 0)) if previous else spec.initial_gear
        elapsed_ms = ((50 if previous["action"] else round(previous["tau"] * 1000) + 50)
                      if previous else 10000)
        if (row["run_id"] != spec.run_id or row["timestamp_ms"] != index * 50
                or row["g"] != gear or row["tau"] != elapsed_ms / 1000):
            raise ValueError(f"state/time invariant violated: {spec.run_id}:{index}")
        if index < 19 and (row["status"] != "warmup" or row["action"] is not None
                           or row["class_index"] is not None):
            raise ValueError("warmup must have no label")
    for index, window in enumerate(iter_windows(rows), start=19):
        overlap.observe(split, window)
        row = rows[index]
        if (row["status"], row["action"], row["class_index"]) != ("ok", window.action, window.class_index):
            raise ValueError("stored label differs from rule reference")
        stats["windows"] += 1
        stats["classes"][str(window.class_index)] += 1
        if window.action:
            stats["events"]["up" if window.action == 1 else "down"] += 1
        boundaries = stats["boundaries"]
        boundaries["tau_0_95"] += row["tau"] == 0.95
        boundaries["tau_1"] += row["tau"] == 1
        boundaries["tau_above_10"] += row["tau"] > 10
        raw = rows[index - 19:index + 1]
        # Threshold arithmetic is diagnostic only; decisions always use label_window.
        recent = raw[-5:]
        speed = sum(sample["v"] for sample in recent) / 5
        demand = sum(sample["u"] for sample in recent) / 5
        slope = sum(sample["s"] for sample in recent) / 5
        up = 30 + 20 * demand + 0.5 * slope
        if row["tau"] >= 1:
            direction = "upper" if row["g"] == 1 else "lower"
            distance = abs(speed - (up if row["g"] == 1 else up - 10))
            boundaries[f"{direction}_equal"] += distance == 0
            boundaries[f"{direction}_near"] += 0 < distance <= 0.25
        else:
            unlocked = raw[:-1] + [dict(raw[-1], tau=1)]
            action = label_window(unlocked).action
            if action:
                boundaries["blocked_up" if action == 1 else "blocked_down"] += 1
        writer.writerow(dict(window_id=window.window_id, run_id=window.run_id,
                             start_timestamp_ms=window.timestamp_ms - 950,
                             timestamp_ms=window.timestamp_ms, action=window.action,
                             class_index=window.class_index))


def _coverage_errors(splits: dict) -> list[str]:
    return [f"{split}: missing {category}/{name}" for split, stats in splits.items()
            for category in ("kinds", "initial_gears", "classes", "events", "boundaries")
            for name, count in stats[category].items() if count == 0]


def _report(stats: dict, overlap: dict) -> dict:
    errors = _coverage_errors(stats)
    errors.extend(f"cross-split model-window overlap: {pair}={count}"
                  for pair, count in overlap["matching_windows"].items() if count)
    return {
        "coverage_ok": not errors, "coverage_errors": errors, "splits": stats,
        "overlap": overlap,
        "invariants_checked": ["50ms chronology", "predecision state", "next-sample gear/tau",
                               "reference labels", "20 past/present samples", "family split before windows",
                               "no identical model windows across splits"],
    }


def _invalid_cases() -> list[dict]:
    cases = []
    for name, status in (("missing", "missing_signal"), ("nan", "non_finite_value"),
                         ("inf", "non_finite_value"), ("-inf", "non_finite_value"),
                         ("short", "invalid_window_length"), ("range", "out_of_range"),
                         ("sampling", "invalid_sampling_time"), ("run", "invalid_run"),
                         ("type", "invalid_type")):
        samples = [dict(run_id="invalid-fixture", timestamp_ms=i * 50,
                        v=45, u=0.2, s=0, g=1, tau=3) for i in range(20)]
        if name == "missing":
            del samples[0]["v"]
        elif name in ("nan", "inf", "-inf"):
            samples[0]["v"] = float(name)
        elif name == "short":
            samples.pop()
        elif name == "range":
            samples[0]["v"] = 81
        elif name == "sampling":
            samples[-1]["timestamp_ms"] += 1
        elif name == "run":
            samples[-1]["run_id"] = "other"
        else:
            samples[0]["v"] = "45"
        result = label_window(samples)
        if (result.status, result.action, result.class_index) != (status, None, None):
            raise ValueError(f"invalid fixture changed: {name}")
        cases.append(dict(case_id=name, samples=samples, **asdict(result)))
    return cases


def _encode_special(value):
    if isinstance(value, dict):
        return {key: _encode_special(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_encode_special(item) for item in value]
    if type(value) is float and not math.isfinite(value):
        return {"$float": str(value)}
    return value


def read_invalid_cases(path: Path) -> Iterator[dict]:
    """Decode the explicit $float tags in the separate invalid-window fixture."""
    def decode(value):
        if set(value) == {"$float"} and value["$float"] in ("nan", "inf", "-inf"):
            return float(value["$float"])
        return value

    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line, object_hook=decode)


def _generate(output: Path, config: Config):
    plan = make_plan(config)  # Split before any samples or windows exist.
    output.mkdir(parents=True, exist_ok=False)
    _write_json(output / "config.json", asdict(config))
    with (output / "invalid.jsonl").open("w", encoding="utf-8") as handle:
        for case in _invalid_cases():
            handle.write(json.dumps(_encode_special(case), sort_keys=True, allow_nan=False) + "\n")
    with (output / "runs.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["split", *RunSpec.__dataclass_fields__]
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        for split, specs in plan.items():
            writer.writerows(dict(split=split, **asdict(spec)) for spec in specs)
    stats = {split: _stats() for split in SPLITS}
    overlap = _OverlapAudit()
    for split, specs in plan.items():
        with ((output / f"{split}.csv").open("w", encoding="utf-8", newline="") as handle,
              (output / f"{split}-windows.csv").open("w", encoding="utf-8", newline="") as windows):
            fields = ["run_id", "timestamp_ms", "v", "u", "s", "g", "tau",
                      "action", "class_index", "status"]
            writer = csv.DictWriter(handle, fields, lineterminator="\n")
            writer.writeheader()
            window_writer = csv.DictWriter(windows, ["window_id", "run_id", "start_timestamp_ms",
                                                    "timestamp_ms", "action", "class_index"],
                                           lineterminator="\n")
            window_writer.writeheader()
            for spec in specs:
                rows = generate_run(spec, config)
                writer.writerows(rows)
                _summarize_run(rows, spec, stats[split], window_writer, overlap, split)
    _write_json(output / "report.json", _report(stats, overlap.result()))
    manifest = {
        "schema_version": "dataset-v2",
        "config": asdict(config),
        "generator": {"version": "synthetic-v2", "sha256": _file_hash(Path(__file__))},
        "labeler": {"version": "rule-reference-v1",
                    "sha256": _file_hash(Path(__file__).with_name("reference.py"))},
        "python_version": platform.python_version(),
        "profile_policy": "independent parameter realization per family; derivatives share profile_seed",
        "split_policy": "70/15/15, stratified by kind, whole root-profile families before windows",
        "sha256": {path.name: _file_hash(path) for path in sorted(output.iterdir())},
    }
    manifest["dataset_id"] = _digest(json.dumps(manifest, sort_keys=True))
    _write_json(output / "manifest.json", manifest)


def _verify_hashes(output: Path) -> dict:
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    identity = dict(manifest)
    dataset_id = identity.pop("dataset_id")
    if _digest(json.dumps(identity, sort_keys=True)) != dataset_id:
        raise ValueError("manifest identity mismatch")
    required = {"config.json", "runs.csv", "report.json", "invalid.jsonl"}
    required.update(f"{split}{suffix}.csv" for split in SPLITS for suffix in ("", "-windows"))
    if set(manifest["sha256"]) != required:
        raise ValueError("manifest file set mismatch")
    for name, expected in manifest["sha256"].items():
        if Path(name).name != name or _file_hash(output / name) != expected:
            raise ValueError(f"checksum mismatch: {name}")
    return manifest


def _lock(output: Path, manifest: dict) -> dict:
    return dict(dataset_id=manifest["dataset_id"],
                manifest_sha256=_file_hash(output / "manifest.json"),
                test_sha256=manifest["sha256"]["test.csv"],
                test_windows_sha256=manifest["sha256"]["test-windows.csv"],
                policy="Evaluation only; no model selection, normalization fitting or INT8 calibration.")


def _raw_rows(handle) -> Iterator[dict]:
    for row in csv.DictReader(handle):
        for field in ("timestamp_ms", "g"):
            row[field] = int(row[field])
        for field in ("v", "u", "s", "tau"):
            row[field] = float(row[field])
        for field in ("action", "class_index"):
            row[field] = int(row[field]) if row[field] else None
        yield row


def _audit_overlap(output: Path) -> dict:
    audit = _OverlapAudit()
    for split in SPLITS:
        with (output / f"{split}.csv").open(encoding="utf-8", newline="") as handle:
            for _, group in groupby(_raw_rows(handle), key=lambda row: row["run_id"]):
                for window in iter_windows(group):
                    audit.observe(split, window)
    return audit.result()


class _CheckWindows:
    def __init__(self, handle):
        self.rows = iter(csv.DictReader(handle))

    def writerow(self, row):
        if next(self.rows, None) != {key: str(value) for key, value in row.items()}:
            raise ValueError("window index differs from chronological raw samples")


def _verify(output: Path) -> dict:
    manifest = _verify_hashes(output)
    if manifest["schema_version"] != "dataset-v2":
        raise ValueError("historical dataset-v1 is not leakage-safe; use audit-overlap for read-only diagnosis")
    if manifest["labeler"]["sha256"] != _file_hash(Path(__file__).with_name("reference.py")):
        raise ValueError("verification requires the recorded rule reference")
    config_data = json.loads((output / "config.json").read_text(encoding="utf-8"))
    if manifest["config"] != config_data:
        raise ValueError("manifest/config mismatch")
    config = Config(**config_data)
    plan = make_plan(config)
    with (output / "runs.csv").open(encoding="utf-8", newline="") as handle:
        recorded = list(csv.DictReader(handle))
    expected = [{key: str(value) for key, value in dict(split=split, **asdict(spec)).items()}
                for split, specs in plan.items() for spec in specs]
    if recorded != expected:
        raise ValueError("run/family split differs from the recorded configuration")
    stats = {split: _stats() for split in SPLITS}
    overlap = _OverlapAudit()
    for split, specs in plan.items():
        with ((output / f"{split}.csv").open(encoding="utf-8", newline="") as handle,
              (output / f"{split}-windows.csv").open(encoding="utf-8", newline="") as windows):
            writer = _CheckWindows(windows)
            groups = groupby(_raw_rows(handle), key=lambda row: row["run_id"])
            for spec, group in zip_longest(specs, groups):
                if spec is None or group is None or spec.run_id != group[0]:
                    raise ValueError("unexpected/missing/overlapping run")
                rows = list(group[1])
                if len(rows) != config.duration_s * 20:
                    raise ValueError("run sample count mismatch")
                _summarize_run(rows, spec, stats[split], writer, overlap, split)
            if next(writer.rows, None) is not None:
                raise ValueError("extra windows in index")
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    if any(overlap.result()["matching_windows"].values()):
        raise ValueError("cross-split model-window overlap detected")
    if report != _report(stats, overlap.result()):
        raise ValueError("coverage report differs from raw data")
    invalid = list(read_invalid_cases(output / "invalid.jsonl"))
    if len(invalid) != 9:
        raise ValueError("invalid fixture count mismatch")
    for case in invalid:
        result = label_window(case["samples"])
        if (result.status == "ok" or asdict(result) !=
                {key: case[key] for key in ("status", "action", "class_index")}):
            raise ValueError("invalid fixture has a valid label or wrong status")
    if (output / "test-lock.json").exists():
        if json.loads((output / "test-lock.json").read_text(encoding="utf-8")) != _lock(output, manifest):
            raise ValueError("sealed test identity mismatch")
    return manifest


def _seal(output: Path):
    if (output / "test-lock.json").exists():
        raise ValueError("test dataset is already sealed")
    manifest = _verify(output)
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    if not report["coverage_ok"] or report["coverage_errors"]:
        raise ValueError("coverage gate failed; test dataset remains unsealed")
    with (output / "test-lock.json").open("x", encoding="utf-8") as handle:
        json.dump(_lock(output, manifest), handle, indent=2, sort_keys=True)
        handle.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="write a new, unsealed dataset directory")
    generate.add_argument("output", type=Path)
    generate.add_argument("--config", type=Path)
    seal = commands.add_parser("seal", help="seal only after inspecting the coverage report")
    seal.add_argument("output", type=Path)
    verify = commands.add_parser("verify", help="audit checksums, raw state, labels, windows and coverage")
    verify.add_argument("output", type=Path)
    overlap = commands.add_parser("audit-overlap", help="read-only comparison of all scaled model windows, including historical datasets")
    overlap.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "generate":
            settings = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
            _generate(args.output, Config(**settings))
        elif args.command == "seal":
            _seal(args.output)
        elif args.command == "audit-overlap":
            audit = _audit_overlap(args.output)
            print(json.dumps(audit, sort_keys=True))
            if any(audit["matching_windows"].values()):
                parser.exit(1, "cross-split model-window overlap detected\n")
        else:
            manifest = _verify(args.output)
            print(json.dumps(dict(dataset_id=manifest["dataset_id"], verified=True,
                                  sealed=(args.output / "test-lock.json").exists()), sort_keys=True))
    except (ValueError, TypeError, OSError, KeyError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
