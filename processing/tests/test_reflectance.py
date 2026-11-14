"""Numerical and independent-capture checks for reflectance calibration."""

import json
import unittest

import numpy as np

from processing.reflectance import apply_reflectance, fit_empirical_line, validate_timepoints


CHANNELS = ("R", "G1", "G2", "B")


def captures(values=(0.40, 0.41, 0.40)):
    return [
        {"session": session, "object_id": "leaf", "means": dict.fromkeys(CHANNELS, value)}
        for session, value in zip(("morning", "noon", "afternoon"), values)
    ]


class EmpiricalLineTests(unittest.TestCase):
    def test_recovers_independent_channel_models_and_predicts_heldout(self):
        models = {"R": (0.0001, -0.02), "G1": (0.0002, 0.01),
                  "G2": (0.00015, -0.01), "B": (0.00012, 0.03)}
        references = {channel: [0.0, 0.22, 0.51, 0.9] for channel in CHANNELS}
        raw = {channel: [(rho - offset) / gain for rho in references[channel]]
               for channel, (gain, offset) in models.items()}
        fitted = fit_empirical_line(raw, references)
        for channel, (gain, offset) in models.items():
            with self.subTest(channel=channel):
                self.assertAlmostEqual(fitted[channel]["gain"], gain, places=12)
                self.assertAlmostEqual(fitted[channel]["offset"], offset, places=12)
                self.assertLess(fitted[channel]["rmse"], 1e-12)
                self.assertEqual(fitted[channel]["sample_count"], 4)
                heldout = np.array([[(0.63 - offset) / gain]])
                self.assertAlmostEqual(float(apply_reflectance(heldout, fitted[channel])[0, 0]),
                                       0.63, places=6)
        json.dumps(fitted, allow_nan=False)

    def test_rejects_degenerate_and_invalid_inputs(self):
        cases = [
            ({}, {}),
            ({"R": [1, 2]}, {"B": [0.1, 0.5]}),
            ({"NIR": [1, 2]}, {"NIR": [0.1, 0.5]}),
            ({"R": [1]}, {"R": [0.1]}),
            ({"R": [1, 1]}, {"R": [0.1, 0.5]}),
            ({"R": [1, 2]}, {"R": [0.5, 0.1]}),
            ({"R": [1, 2]}, {"R": [0.1, 0.1]}),
            ({"R": [1, 2]}, {"R": [-0.1, 0.5]}),
            ({"R": [1, 2]}, {"R": [0.1, 1.1]}),
            ({"R": [1, float("nan")]}, {"R": [0.1, 0.5]}),
            ({"R": [1, 2]}, {"R": [0.1, float("inf")]}),
            ({"R": [1, 2, 3]}, {"R": [0.1, 0.5]}),
            ({"R": [[1, 2]]}, {"R": [0.1, 0.5]}),
        ]
        for raw, references in cases:
            with self.subTest(raw=raw, references=references):
                with self.assertRaises(ValueError):
                    fit_empirical_line(raw, references)

    def test_preserves_nan_and_unclipped_values_without_changing_input(self):
        image = np.array([[0, 50, 150, np.nan]], dtype=np.float32)
        before = image.copy()
        result = apply_reflectance(image, {"gain": 0.01, "offset": -0.1})
        self.assertEqual(result.dtype, np.float32)
        np.testing.assert_allclose(result, [[-0.1, 0.4, 1.4, np.nan]], equal_nan=True)
        np.testing.assert_array_equal(image, before)

    def test_rejects_invalid_coefficients(self):
        for coefficients in ({}, {"gain": 0, "offset": 0}, {"gain": -1, "offset": 0},
                             {"gain": 1, "offset": float("nan")}):
            with self.subTest(coefficients=coefficients):
                with self.assertRaises(ValueError):
                    apply_reflectance(np.ones((2, 2)), coefficients)


class TimepointTests(unittest.TestCase):
    sessions = ["morning", "noon", "afternoon"]

    def test_three_independent_sessions_pass(self):
        result = validate_timepoints(captures(), self.sessions)
        self.assertEqual(result["status"], "passed")
        channel = result["objects"]["leaf"]["channels"]["R"]
        self.assertAlmostEqual(channel["relative_spread_percent"], 100 * 0.01 / (1.21 / 3))
        json.dumps(result, allow_nan=False)

    def test_channel_failure_prevents_object_and_run_pass(self):
        records = captures()
        records[1]["means"]["B"] = 0.5
        result = validate_timepoints(records, self.sessions)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["objects"]["leaf"]["channels"]["R"]["status"], "passed")
        self.assertEqual(result["objects"]["leaf"]["channels"]["B"]["status"], "failed")

    def test_threshold_is_strict(self):
        # 10, 10.5, 11 percent reflectance has exactly 9.5238...% spread.
        records = captures((0.1, 0.105, 0.11))
        metric = 100 * (0.11 - 0.1) / np.mean([0.1, 0.105, 0.11])
        result = validate_timepoints(records, self.sessions, threshold_percent=metric)
        self.assertEqual(result["status"], "failed")

    def test_missing_channel_or_session_is_incomplete(self):
        for records in (captures()[:2], captures()):
            if len(records) == 3:
                del records[1]["means"]["G2"]
            with self.subTest(records=records):
                result = validate_timepoints(records, self.sessions)
                self.assertEqual(result["status"], "incomplete")

    def test_empty_or_insufficient_distinct_slots_are_incomplete(self):
        self.assertEqual(validate_timepoints([], self.sessions)["status"], "incomplete")
        self.assertEqual(validate_timepoints(captures()[:2], self.sessions[:2])["status"],
                         "incomplete")
        self.assertEqual(validate_timepoints(captures()[:2], ["morning", "noon", "noon"])
                         ["status"], "incomplete")

    def test_invalid_means_never_pass_or_emit_non_json_floats(self):
        for value in (float("nan"), float("inf"), -0.1, 1.1, "invalid"):
            records = captures()
            records[1]["means"]["R"] = value
            with self.subTest(value=value):
                result = validate_timepoints(records, self.sessions)
                self.assertEqual(result["status"], "failed")
                json.dumps(result, allow_nan=False)
        self.assertEqual(validate_timepoints(captures((0, 0, 0)), self.sessions)["status"],
                         "failed")

    def test_unknown_channels_and_unexpected_sessions_never_pass(self):
        records = captures()
        records[1]["means"]["NIR"] = 0.4
        self.assertEqual(validate_timepoints(records, self.sessions)["status"], "failed")
        records = captures()
        records.append({"session": "evening", "object_id": "leaf",
                        "means": dict.fromkeys(CHANNELS, 0.4)})
        self.assertEqual(validate_timepoints(records, self.sessions)["status"], "failed")

    def test_duplicate_object_session_rejected(self):
        records = captures()
        records.append(records[0].copy())
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_timepoints(records, self.sessions)

    def test_distinct_objects_are_not_pooled(self):
        records = captures()
        records[2]["object_id"] = "different-leaf"
        result = validate_timepoints(records, self.sessions)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(set(result["objects"]), {"leaf", "different-leaf"})


if __name__ == "__main__":
    unittest.main()
