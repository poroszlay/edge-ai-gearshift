import math
import unittest

from pc.reference import label_window


def window(v=45, u=0.2, s=0, g=1, tau=3):
    return [dict(run_id="run-1", timestamp_ms=1000 + i * 50,
                 v=v, u=u, s=s, g=g, tau=tau) for i in range(20)]


class ReferenceTests(unittest.TestCase):
    def assert_label(self, samples, action, index):
        result = label_window(samples)
        self.assertEqual((result.status, result.action, result.class_index),
                         ("ok", action, index))

    def test_documented_upshift(self):
        self.assert_label(window(), 1, 2)

    def test_documented_downshift(self):
        self.assert_label(window(v=20, u=0.8, s=5, g=2), -1, 0)

    def test_documented_upper_threshold_equality_holds(self):
        self.assert_label(window(v=34), 0, 1)

    def test_documented_lockout_holds(self):
        self.assert_label(window(tau=0.3), 0, 1)

    def test_lower_threshold_equality_holds(self):
        self.assert_label(window(v=38.5, u=0.8, s=5, g=2), 0, 1)

    def test_one_second_unlocks_both_directions(self):
        for g, v, action, index in [(1, 45, 1, 2), (2, 20, -1, 0)]:
            with self.subTest(g=g):
                self.assert_label(window(g=g, v=v, tau=1), action, index)
                self.assert_label(window(g=g, v=v, tau=math.nextafter(1, 0)), 0, 1)

    def test_only_last_five_samples_are_averaged(self):
        samples = window(v=0, u=1, s=10)
        for sample, v, u, s in zip(samples[-5:],
                                   [60, 50, 40, 30, 20],
                                   [0, 0.25, 0.5, 0.75, 1],
                                   [-10, -5, 0, 5, 10]):
            sample.update(v=v, u=u, s=s)
        # Means 40, 0.5, 0: upper threshold 40; latest-only would downshift.
        samples[-1]["g"] = 2
        self.assert_label(samples, 0, 1)
        samples[-1]["g"] = 1
        samples[-5]["v"] = 65  # mean v=41; whole-window mean remains below 40.
        self.assert_label(samples, 1, 2)

    def test_latest_predecision_state_is_used(self):
        samples = window(g=2, tau=0.3)
        samples[-1].update(g=1, tau=1)
        self.assert_label(samples, 1, 2)
        samples[-1]["tau"] = 0.3
        self.assert_label(samples, 0, 1)

    def assert_error(self, samples, status):
        result = label_window(samples)
        self.assertEqual((result.status, result.action, result.class_index),
                         (status, None, None))

    def test_invalid_window_length_has_no_label(self):
        for count in (0, 19, 21):
            with self.subTest(count=count):
                self.assert_error((window() + window())[:count], "invalid_window_length")

    def test_missing_signal_anywhere_has_no_label_even_during_lockout(self):
        for field in ("v", "u", "s", "g", "tau", "timestamp_ms", "run_id"):
            for position in (0, 19):
                with self.subTest(field=field, position=position):
                    samples = window(tau=0.3)
                    del samples[position][field]
                    self.assert_error(samples, "missing_signal")

    def test_non_finite_signal_anywhere_has_no_label(self):
        for field in ("v", "u", "s", "g", "tau", "timestamp_ms"):
            for value in (math.nan, math.inf, -math.inf):
                for position in (0, 19):
                    with self.subTest(field=field, value=value, position=position):
                        samples = window(tau=0.3)
                        samples[position][field] = value
                        self.assert_error(samples, "non_finite_value")

    def test_out_of_range_signal_anywhere_has_no_label(self):
        cases = [("v", -0.001), ("v", 80.001), ("u", -0.001),
                 ("u", 1.001), ("s", -10.001), ("s", 10.001),
                 ("g", 0), ("g", 3), ("g", 1.5), ("tau", -0.001)]
        for field, value in cases:
            for position in (0, 19):
                with self.subTest(field=field, value=value, position=position):
                    samples = window(tau=0.3)
                    samples[position][field] = value
                    self.assert_error(samples, "out_of_range")

    def test_sampling_requires_nonnegative_integer_milliseconds_and_50ms_steps(self):
        for position, value in [(0, -50), (0, 1000.0), (1, 1000),
                                (10, 1501), (19, 1900), (19, 2000)]:
            with self.subTest(position=position, value=value):
                samples = window(tau=0.3)
                samples[position]["timestamp_ms"] = value
                self.assert_error(samples, "invalid_sampling_time")
        self.assert_error(list(reversed(window())), "invalid_sampling_time")

    def test_window_cannot_cross_runs(self):
        samples = window()
        samples[10]["run_id"] = "run-2"
        self.assert_error(samples, "invalid_run")
        for value in (None, "", 1, True):
            with self.subTest(value=value):
                samples = window()
                samples[0]["run_id"] = value
                self.assert_error(samples, "invalid_run")

    def test_wrong_types_are_reported_without_coercion(self):
        for value in (None, True, "45", [], {}):
            for field in ("v", "u", "s", "g", "tau"):
                with self.subTest(field=field, value=value):
                    samples = window()
                    samples[0][field] = value
                    self.assert_error(samples, "invalid_type")
        for value in (None, "1000", True, []):
            with self.subTest(timestamp=value):
                samples = window()
                samples[0]["timestamp_ms"] = value
                self.assert_error(samples, "invalid_sampling_time")
        for value in (None, "bad", 123):
            with self.subTest(sample=value):
                samples = window()
                samples[0] = value
                self.assert_error(samples, "invalid_type")
        self.assert_error(None, "invalid_type")

    def test_inclusive_range_limits_and_tau_above_ten_are_valid(self):
        self.assert_label(window(v=0, u=0, s=-10, g=1, tau=0), 0, 1)
        self.assert_label(window(v=80, u=1, s=10, g=1, tau=11), 1, 2)
        self.assert_label(window(v=0, u=0, s=-10, g=2, tau=11), -1, 0)

    def test_labeling_does_not_change_replayed_state(self):
        samples = window()
        original = [sample.copy() for sample in samples]
        self.assert_label(samples, 1, 2)
        self.assertEqual(samples, original)

    def test_each_of_v_u_s_is_averaged_over_all_five_recent_samples(self):
        # Each case reverses the result if u/s are taken from the latest sample only.
        samples = window(v=40, u=0, s=0)
        for sample in samples[-5:-1]:
            sample["u"] = 1
        self.assert_label(samples, 0, 1)  # u mean .8 => threshold 46.
        samples = window(v=32, u=0, s=0)
        for sample in samples[-5:-1]:
            sample["s"] = 10
        self.assert_label(samples, 0, 1)  # s mean 8 => threshold 34.

    def test_downshift_uses_latest_gear_not_the_preceding_four(self):
        samples = window(v=20, g=1)
        samples[-1]["g"] = 2
        self.assert_label(samples, -1, 0)

    def test_action_is_not_the_class_index(self):
        for samples, pair in [(window(v=20, g=2), (-1, 0)),
                              (window(v=34), (0, 1)),
                              (window(), (1, 2))]:
            with self.subTest(pair=pair):
                result = label_window(samples)
                self.assertEqual((result.action, result.class_index), pair)
                self.assertNotEqual(result.action, result.class_index)

    def test_large_integers_have_explicit_status_instead_of_overflow(self):
        samples = window()
        samples[0]["v"] = 10 ** 400
        self.assert_error(samples, "out_of_range")
        samples = window(tau=10 ** 400)
        for i, sample in enumerate(samples):
            sample["timestamp_ms"] = 10 ** 400 + i * 50
        self.assert_label(samples, 1, 2)
