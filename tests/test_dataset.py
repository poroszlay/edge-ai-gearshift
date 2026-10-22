import csv
import hashlib
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from pc.dataset import Config, RunSpec, generate_run


class GenerationTests(unittest.TestCase):
    def test_reviewed_shift_windows_are_not_copied_across_profile_families(self):
        from pc.dataset import iter_windows, make_plan

        config = Config(duration_s=12)
        plan = make_plan(config)
        train = next(spec for spec in plan["train"] if spec.run_id == "acceleration-0008-v0")
        test = next(spec for spec in plan["test"] if spec.run_id == "acceleration-0014-v0")
        train_windows = {w.window_id: w for w in iter_windows(generate_run(train, config))}
        test_windows = {w.window_id: w for w in iter_windows(generate_run(test, config))}
        for train_index, test_index in ((119, 47), (234, 162)):
            with self.subTest(train_index=train_index, test_index=test_index):
                self.assertFalse(
                    train_windows[f"{train.run_id}:{train_index}"].features ==
                    test_windows[f"{test.run_id}:{test_index}"].features,
                    "a phase-shifted root profile leaked across train/test",
                )

    def test_all_split_pairs_have_disjoint_scaled_windows_including_noisy_derivatives(self):
        from pc.dataset import iter_windows, make_plan

        config = Config(duration_s=12)
        observed = []
        for split, specs in make_plan(config).items():
            features = set()
            for spec in specs:
                features.update(window.features for window in iter_windows(generate_run(spec, config)))
            for previous in observed:
                self.assertTrue(features.isdisjoint(previous), f"copied model input in {split}")
            observed.append(features)

    def test_bad_configuration_and_run_specs_are_rejected(self):
        for settings in ({"duration_s": 0}, {"duration_s": 1.5}, {"duration_s": True},
                         {"seed": "7"}, {"noise_v": float("nan")}, {"noise_u": -1},
                         {"noise_s": float("inf")}, {"noisy_variants": -1},
                         {"runs_per_type": 41}, {"runs_per_type": 0},
                         {"period_samples": 0}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                Config(**settings)
        for spec in (RunSpec("r", "f", "typo", 1), RunSpec("r", "f", "cruise", 3),
                     RunSpec("", "f", "cruise", 1), RunSpec("r", "f", "cruise", True)):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                generate_run(spec, Config(duration_s=1))

    def test_reference_decision_changes_only_the_next_sample_state(self):
        run = generate_run(RunSpec("r", "family", "threshold", 1),
                           Config(duration_s=4))
        self.assertEqual(len(run), 80)
        self.assertEqual([row["timestamp_ms"] for row in run], list(range(0, 4000, 50)))
        self.assertTrue(all(row["action"] is None for row in run[:19]))
        self.assertEqual((run[0]["g"], run[0]["tau"]), (1, 10))
        # Five-sample mean first exceeds 34 at sample 30.
        self.assertEqual((run[30]["g"], run[30]["action"]), (1, 1))
        self.assertEqual((run[31]["g"], run[31]["tau"]), (2, 0.05))
        # Opposite demand during lockout must hold; exactly 1 s unlocks.
        self.assertEqual((run[49]["tau"], run[49]["action"]), (0.95, 0))
        self.assertEqual((run[50]["tau"], run[50]["action"]), (1, -1))
        self.assertEqual((run[51]["g"], run[51]["tau"]), (1, 0.05))

    def test_plan_splits_whole_families_before_generation(self):
        from pc.dataset import make_plan

        plan = make_plan(Config())
        self.assertEqual({key: len(value) for key, value in plan.items()},
                         {"train": 140, "validation": 30, "test": 30})
        seen_runs, family_splits, family_roots = set(), {}, {}
        gears = {1: 0, 2: 0}
        for split, specs in plan.items():
            counts = {}
            for spec in specs:
                self.assertNotIn(spec.run_id, seen_runs)
                seen_runs.add(spec.run_id)
                self.assertEqual(family_splits.setdefault(spec.family_id, split), split)
                root = (spec.profile_seed, spec.phase_samples, spec.initial_gear)
                self.assertEqual(family_roots.setdefault(spec.family_id, root), root)
                gears[spec.initial_gear] += 1
                counts[spec.kind] = counts.get(spec.kind, 0) + 1
            self.assertEqual(sorted(counts.values()), [len(specs) // 5] * 5)
        self.assertEqual(gears, {1: 100, 2: 100})
        self.assertEqual(len(family_splits), 100)
        self.assertEqual(plan, make_plan(Config()))
        self.assertNotEqual(plan, make_plan(Config(seed=7)))

    def test_five_profiles_and_seeded_noise_use_only_reference_labels(self):
        from pc.dataset import KINDS
        from pc.reference import label_window

        profiles = []
        config = Config(duration_s=8)
        for kind in KINDS:
            spec = RunSpec("r", "family", kind, 2)
            base = generate_run(spec, config)
            profiles.append([(row["v"], row["u"], row["s"]) for row in base])
            noisy_spec = RunSpec("noisy", "family", kind, 2, variant=1)
            noisy = generate_run(noisy_spec, config)
            self.assertEqual(noisy, generate_run(noisy_spec, config))
            self.assertNotEqual(noisy, generate_run(noisy_spec, Config(duration_s=8, seed=7)))
            self.assertNotEqual([r["v"] for r in noisy], [r["v"] for r in base])
            for index, row in enumerate(noisy):
                if index >= 19:
                    expected = label_window(noisy[index - 19:index + 1])
                    self.assertEqual((row["status"], row["action"], row["class_index"]),
                                     (expected.status, expected.action, expected.class_index))
                if index:
                    previous = noisy[index - 1]
                    self.assertEqual(row["g"], previous["g"] + (previous["action"] or 0))
                    expected_tau = 0.05 if previous["action"] else previous["tau"] + 0.05
                    self.assertAlmostEqual(row["tau"], expected_tau)
        self.assertEqual(len({tuple(profile) for profile in profiles}), 5)

    def test_default_base_families_do_not_duplicate_complete_signal_profiles(self):
        from pc.dataset import KINDS, make_plan

        config = Config(duration_s=12)
        plan = make_plan(config)
        for kind in KINDS:
            signals = set()
            for specs in plan.values():
                for spec in specs:
                    if spec.kind == kind and spec.variant == 0:
                        rows = generate_run(spec, config)
                        fingerprint = tuple((r["v"], r["u"], r["s"]) for r in rows)
                        self.assertFalse(fingerprint in signals, f"duplicate base profile: {spec.run_id}")
                        signals.add(fingerprint)
            self.assertEqual(len(signals), 20)


class WindowTests(unittest.TestCase):
    def test_windows_start_at_sample_twenty_and_scale_without_changing_raw_tau(self):
        from pc.dataset import iter_windows

        run = generate_run(RunSpec("r", "f", "threshold", 1), Config(duration_s=4))
        windows = list(iter_windows(run))
        self.assertEqual(len(windows), 61)
        first = windows[0]
        self.assertEqual((first.run_id, first.window_id, first.timestamp_ms), ("r", "r:19", 950))
        self.assertEqual(len(first.features), 100)
        self.assertEqual(first.features, (34 / 80, 0.2, 0, 0, 1) * 20)
        self.assertEqual((first.action, first.class_index), (0, 1))
        self.assertEqual(run[19]["tau"], 10.95)
        self.assertEqual(windows[12].features[-5:], (46 / 80, 0.2, 0, 1, 0.005))
        self.assertEqual([w.timestamp_ms for w in windows], list(range(950, 4000, 50)))
        self.assertEqual(windows, list(iter_windows(run)))
        limits = [dict(run_id="limits", timestamp_ms=i * 50,
                       v=80, u=1, s=-10, g=2, tau=15) for i in range(20)]
        self.assertEqual(next(iter_windows(limits)).features, (1, 1, -1, 1, 1) * 20)
        altered_future = [row.copy() for row in run]
        altered_future[-1]["v"] = 80
        self.assertEqual(first, next(iter_windows(altered_future)))
        for change in ("missing", "sampling", "run"):
            broken = [row.copy() for row in run]
            if change == "missing":
                del broken[0]["v"]
            elif change == "sampling":
                broken[0]["timestamp_ms"] = 1
            else:
                broken[0]["run_id"] = "other"
            with self.subTest(change=change), self.assertRaises(ValueError):
                list(iter_windows(broken))


class ExportTests(unittest.TestCase):
    def cli(self, *args, success=True):
        result = subprocess.run([sys.executable, "-m", "pc.dataset", *map(str, args)],
                                capture_output=True, text=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def test_overlap_audit_compares_actual_scaled_windows_without_run_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            for split, extra_tau in (("train", 0), ("validation", 20), ("test", 40)):
                rows = generate_run(RunSpec(split, split, "threshold", 1), Config(duration_s=1))
                for row in rows:
                    row["tau"] += extra_tau
                with (output / f"{split}.csv").open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
            result = self.cli("audit-overlap", output, success=False)
            self.assertEqual(result.returncode, 1, result.stderr)
            audit = json.loads(result.stdout)
            self.assertEqual(audit["checked_windows"], 3)
            self.assertEqual(audit["matching_windows"], {
                "train:validation": 1, "train:test": 1, "validation:test": 1,
            })
            self.assertTrue(audit["examples"])

    def test_verify_and_seal_reject_checksum_valid_cross_split_copies(self):
        from pc.dataset import iter_windows, make_plan

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "data"
            config_file = root / "config.json"
            config_file.write_text(json.dumps({"duration_s": 4}))
            self.cli("generate", output, "--config", config_file)
            config = Config(duration_s=4)
            plan = make_plan(config)
            target = plan["test"][0]
            source = next(spec for spec in plan["train"] if spec.initial_gear == target.initial_gear)
            copied = [dict(row, run_id=target.run_id) for row in generate_run(source, config)]
            for name, replacement in (
                ("test.csv", copied),
                ("test-windows.csv", [dict(window_id=w.window_id, run_id=w.run_id,
                                           start_timestamp_ms=w.timestamp_ms - 950,
                                           timestamp_ms=w.timestamp_ms, action=w.action,
                                           class_index=w.class_index) for w in iter_windows(copied)]),
            ):
                with (output / name).open(newline="") as handle:
                    reader = csv.DictReader(handle)
                    fields = reader.fieldnames
                    remaining = [row for row in reader if row["run_id"] != target.run_id]
                with (output / name).open("w", newline="") as handle:
                    writer = csv.DictWriter(handle, fields, lineterminator="\n")
                    writer.writeheader()
                    writer.writerows(replacement + remaining)
            # This is a checksum-valid input fixture, not accidental corruption.
            # Its copied samples have valid state, labels and window indices.
            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            for name in ("test.csv", "test-windows.csv"):
                manifest["sha256"][name] = hashlib.sha256((output / name).read_bytes()).hexdigest()
            del manifest["dataset_id"]
            manifest["dataset_id"] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
            manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
            for command in ("verify", "seal"):
                result = self.cli(command, output, success=False)
                self.assertIn("cross-split model-window overlap", result.stderr)
            self.assertFalse((output / "test-lock.json").exists())

    def test_export_is_byte_reproducible_and_records_provenance_and_split_membership(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "settings.json"
            config.write_text(json.dumps({"duration_s": 4}), encoding="utf-8")
            a, b = root / "a", root / "b"
            self.cli("generate", a, "--config", config)
            self.cli("generate", b, "--config", config)
            files = sorted(p.name for p in a.iterdir())
            self.assertIn("manifest.json", files)
            self.assertNotIn("test-lock.json", files)
            self.assertEqual(files, sorted(p.name for p in b.iterdir()))
            for name in files:
                self.assertEqual((a / name).read_bytes(), (b / name).read_bytes(), name)
            manifest = json.loads((a / "manifest.json").read_text())
            self.assertEqual(manifest["config"]["seed"], 20261019)
            self.assertEqual(manifest["labeler"]["version"], "rule-reference-v1")
            self.assertEqual(manifest["labeler"]["sha256"],
                             hashlib.sha256(Path("pc/reference.py").read_bytes()).hexdigest())
            for name, expected in manifest["sha256"].items():
                self.assertEqual(hashlib.sha256((a / name).read_bytes()).hexdigest(), expected)
            families, runs = {}, set()
            with (a / "runs.csv").open() as handle:
                for spec in csv.DictReader(handle):
                    self.assertNotIn(spec["run_id"], runs)
                    runs.add(spec["run_id"])
                    self.assertEqual(families.setdefault(spec["family_id"], spec["split"]),
                                     spec["split"])
            self.assertEqual(len(runs), 200)
            with (a / "test.csv").open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2400)
            self.assertEqual(rows[0]["status"], "warmup")
            self.assertEqual(rows[0]["action"], "")
            self.cli("generate", a, "--config", config, success=False)

    def test_coverage_reports_every_split_and_missing_coverage_blocks_sealing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = root / "settings.json"
            config.write_text(json.dumps({"duration_s": 1}))
            short = root / "short"
            self.cli("generate", short, "--config", config)
            report = json.loads((short / "report.json").read_text())
            self.assertFalse(report["coverage_ok"])
            self.assertTrue(report["coverage_errors"])
            self.cli("seal", short, success=False)
            self.assertFalse((short / "test-lock.json").exists())
            config.write_text(json.dumps({"duration_s": 12}))
            complete = root / "complete"
            self.cli("generate", complete, "--config", config)
            report = json.loads((complete / "report.json").read_text())
            self.assertTrue(report["coverage_ok"], report["coverage_errors"])
            self.assertEqual(report["overlap"]["matching_windows"], {
                "train:validation": 0, "train:test": 0, "validation:test": 0,
            })
            self.assertEqual(report["overlap"]["checked_windows"], 44200)
            for split in ("train", "validation", "test"):
                stats = report["splits"][split]
                self.assertEqual(stats["samples"], stats["runs"] * 240)
                self.assertEqual(stats["windows"], stats["runs"] * 221)
                self.assertEqual(sum(stats["classes"].values()), stats["windows"])
                self.assertTrue(all(count > 0 for count in stats["classes"].values()))
                self.assertTrue(all(count > 0 for count in stats["events"].values()))
                self.assertTrue(all(count > 0 for count in stats["boundaries"].values()))
                self.assertEqual(len(stats["kinds"]), 5)
            self.cli("seal", complete)
            self.assertTrue((complete / "test-lock.json").exists())

    def test_invalid_cases_are_separate_standard_json_with_no_valid_labels(self):
        from pc.dataset import read_invalid_cases
        from pc.reference import label_window

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "data"
            config = Path(temp) / "settings.json"
            config.write_text(json.dumps({"duration_s": 1}))
            self.cli("generate", output, "--config", config)
            text = (output / "invalid.jsonl").read_text()
            for line in text.splitlines():
                json.loads(line, parse_constant=lambda value: self.fail(f"nonstandard JSON: {value}"))
            cases = list(read_invalid_cases(output / "invalid.jsonl"))
            self.assertGreaterEqual(len(cases), 5)
            self.assertTrue({"missing_signal", "non_finite_value", "invalid_window_length",
                             "out_of_range", "invalid_sampling_time"}
                            <= {case["status"] for case in cases})
            for case in cases:
                self.assertIsNone(case["action"])
                self.assertIsNone(case["class_index"])
                result = label_window(case["samples"])
                self.assertEqual(result.status, case["status"])
                self.assertIsNone(result.action)
                self.assertIsNone(result.class_index)

    def test_sealed_test_identity_is_preserved_and_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "data"
            config = root / "settings.json"
            config.write_text(json.dumps({"duration_s": 12}))
            self.cli("generate", output, "--config", config)
            self.cli("verify", output)
            damaged = root / "damaged"
            shutil.copytree(output, damaged)
            with (damaged / "train.csv").open("a") as handle:
                handle.write("corruption\n")
            self.cli("seal", damaged, success=False)
            self.assertFalse((damaged / "test-lock.json").exists())
            self.cli("seal", output)
            lock_bytes = (output / "test-lock.json").read_bytes()
            lock = json.loads(lock_bytes)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(lock["dataset_id"], manifest["dataset_id"])
            self.assertEqual(lock["test_sha256"], hashlib.sha256((output / "test.csv").read_bytes()).hexdigest())
            self.assertEqual(lock["test_windows_sha256"], hashlib.sha256((output / "test-windows.csv").read_bytes()).hexdigest())
            self.assertIn("no model selection", lock["policy"])
            self.cli("verify", output)
            self.cli("seal", output, success=False)
            self.cli("generate", output, "--config", config, success=False)
            self.assertEqual((output / "test-lock.json").read_bytes(), lock_bytes)
            with (output / "test.csv").open("a") as handle:
                handle.write("corruption\n")
            self.cli("verify", output, success=False)
            self.assertEqual((output / "test-lock.json").read_bytes(), lock_bytes)


if __name__ == "__main__":
    unittest.main()
