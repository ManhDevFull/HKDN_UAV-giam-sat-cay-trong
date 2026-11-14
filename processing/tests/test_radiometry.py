"""Independent signal-recovery checks; no private inputs or network fixtures."""

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from processing.radiometry import RelativeCorrector, evaluate_lens, load_lens_profile, load_settings


CHANNELS = ("R", "G1", "G2", "B")


def small_profile():
    return {
        "profile_id": "test-lens-only",
        "sensor_shape": [12, 16],
        "channels": {
            color: {
                "coefficients": [[base, 0.03, -0.02], [0.05, 0.01, 0], [-0.04, 0, 0]],
                "validation": {"scope": "synthetic fixture only"},
            }
            for color, base in (("R", 0.8), ("G", 0.9), ("B", 0.7))
        },
    }


def independent_attenuation(color, sensor_row, sensor_column):
    """Handwritten T0/T1/T2 expansion; independent of NumPy's Chebyshev API."""
    base = {"R": 0.8, "G": 0.9, "B": 0.7}[color]
    x = 2 * sensor_column / 15 - 1
    y = 2 * sensor_row / 11 - 1
    return base + 0.03*y - 0.02*(2*y*y - 1) + 0.05*x + 0.01*x*y - 0.04*(2*x*x - 1)


def raw_metadata(height=12, width=16):
    return {"decoder": "mapir-survey3-packed12", "pattern": "RGGB",
            "width": width, "height": height, "white_level": 4095,
            "black_level_source": "unknown; zero offset assumed", "warnings": [],
            "vignetting_corrected": False}


class LensEvaluationTests(unittest.TestCase):
    def test_polynomial_axes_and_all_bayer_phases_match_handwritten_expansion(self):
        for pattern in ("RGGB", "BGGR", "GRBG", "GBRG"):
            with self.subTest(pattern=pattern):
                maps = evaluate_lens(small_profile(), (6, 8), pattern)
                greens = 0
                for phase, color in enumerate(pattern):
                    name = color
                    if color == "G":
                        greens += 1
                        name = f"G{greens}"
                    row_phase, column_phase = divmod(phase, 2)
                    expected = np.array([
                        [independent_attenuation(color, 2*y + row_phase, 2*x + column_phase)
                         for x in range(8)] for y in range(6)
                    ])
                    np.testing.assert_allclose(maps[name], expected, rtol=1e-7, atol=1e-7)
                self.assertFalse(np.array_equal(maps["G1"], maps["G2"]))

    def test_invalid_geometry_nonfinite_and_nonpositive_attenuation_are_rejected(self):
        for shape, pattern in (((5, 8), "RGGB"), ((6, 8), "RGBG")):
            with self.subTest(shape=shape, pattern=pattern), self.assertRaises(ValueError):
                evaluate_lens(small_profile(), shape, pattern)
        for coefficients in ([[float("nan")]], [[-1]], [1, 2]):
            profile = small_profile()
            profile["channels"]["R"]["coefficients"] = coefficients
            with self.subTest(coefficients=coefficients), self.assertRaises(ValueError):
                evaluate_lens(profile, (6, 8), "RGGB")

    def test_shipped_profile_is_finite_positive_at_all_native_sampling_locations(self):
        profile = load_lens_profile()
        self.assertEqual(profile["sensor_shape"], [3000, 4000])
        maps = evaluate_lens(profile, (1500, 2000), "RGGB")
        for name, attenuation in maps.items():
            with self.subTest(channel=name):
                self.assertTrue(np.all(np.isfinite(attenuation)))
                self.assertTrue(np.all(attenuation > 0))
        self.assertIn("not a measurement of this individual camera", " ".join(profile["limitations"]))
        self.assertIn("not an estimate of reflectance accuracy", " ".join(profile["limitations"]))


class RelativeCorrectionTests(unittest.TestCase):
    def test_known_flat_exposure_and_black_distortions_recover_signal_and_band_ratios(self):
        settings = load_settings()
        settings["raw_black_level"] = 16
        corrector = RelativeCorrector(settings, lens_profile=small_profile())
        y, x = np.mgrid[:6, :8]
        common_scene = (20 + 2*x + 3*y).astype(np.float32)
        truth = {name: common_scene*ratio for name, ratio in zip(CHANNELS, (2, 3, 3, 4))}
        source = {}
        for name, color, row, column in (("R", "R", 0, 0), ("G1", "G", 0, 1),
                                         ("G2", "G", 1, 0), ("B", "B", 1, 1)):
            attenuation = np.array([
                [independent_attenuation(color, 2*iy + row, 2*ix + column)
                 for ix in range(8)] for iy in range(6)
            ], dtype=np.float32)
            source[name] = truth[name]*attenuation*2 + 16
        metadata = raw_metadata()
        metadata["warnings"].append("Vignetting not corrected: no measured flat field supplied")
        capture = {"exposure_seconds": 0.016, "iso": 100}
        original_source, original_metadata, original_capture = deepcopy(source), deepcopy(metadata), deepcopy(capture)
        result, info = corrector.apply(source, metadata, capture)
        for name in CHANNELS:
            np.testing.assert_allclose(result[name], truth[name]/4095, rtol=3e-7, atol=1e-8)
            np.testing.assert_array_equal(source[name], original_source[name])
            self.assertFalse(np.shares_memory(result[name], source[name]))
        np.testing.assert_allclose(result["B"]/result["R"], 2, rtol=3e-7)
        np.testing.assert_allclose(result["G1"]/result["R"], 1.5, rtol=3e-7)
        self.assertEqual(metadata, original_metadata)
        self.assertEqual(capture, original_capture)
        self.assertTrue(info["correction"]["factory_flat_applied"])
        self.assertTrue(info["correction"]["exposure_normalized"])
        self.assertEqual(info["correction"]["exposure_factor"], 0.5)
        self.assertEqual(info["absolute_reflectance_accuracy"]["status"], "not_measured")
        self.assertFalse(info["absolute_reflectance_accuracy"]["below_5_percent_verified"])
        for flag in ("absolute_reflectance", "cross_survey_comparison", "ndvi_time_series"):
            self.assertFalse(info["analysis_eligibility"][flag])

    def test_missing_exposure_and_unsupported_iso_never_claim_normalization(self):
        settings = load_settings()
        settings["lens_profile"] = None
        corrector = RelativeCorrector(settings)
        planes = {name: np.full((6, 8), 100, dtype=np.float32) for name in CHANNELS}
        captures = ({}, {"exposure_seconds": 0.016}, {"exposure_seconds": 0.016, "iso": 200},
                    {"exposure_seconds": 0, "iso": 100}, {"exposure_seconds": True, "iso": 100},
                    {"exposure_seconds": float("nan"), "iso": 100})
        for capture in captures:
            with self.subTest(capture=capture):
                result, info = corrector.apply(planes, raw_metadata(), capture)
                self.assertFalse(info["correction"]["exposure_normalized"])
                self.assertEqual(info["correction"]["exposure_factor"], 1)
                np.testing.assert_allclose(result["R"], 100/4095)
                self.assertTrue(any("normalization skipped" in warning for warning in info["warnings"]))

    def test_jpeg_is_rejected_as_quantitative_input(self):
        corrector = RelativeCorrector(load_settings(), lens_profile=small_profile())
        planes = {name: np.ones((6, 8), dtype=np.float32) for name in CHANNELS}
        with self.assertRaisesRegex(ValueError, "JPEG is preview-only"):
            corrector.apply(planes, {"decoder": "pillow-jpeg"})

    def test_black_capture_is_flagged_without_inventing_scene_detail(self):
        settings = load_settings()
        settings['lens_profile'] = None
        planes = {name: np.zeros((6, 8), dtype=np.float32) for name in CHANNELS}
        result, info = RelativeCorrector(settings).apply(
            planes, raw_metadata(), {'exposure_seconds': 0.008, 'iso': 100})
        self.assertIn('low_signal', info['quality']['flags'])
        self.assertFalse(info['analysis_eligibility']['quantitative_input'])
        for plane in result.values():
            np.testing.assert_array_equal(plane, 0)

    def test_non_native_geometry_skips_lens_map_instead_of_resizing_it(self):
        corrector = RelativeCorrector(load_settings(), lens_profile=small_profile())
        planes = {name: np.full((5, 8), 10, dtype=np.float32) for name in CHANNELS}
        result, info = corrector.apply(planes, raw_metadata(height=10))
        self.assertFalse(info["correction"]["factory_flat_applied"])
        self.assertFalse(info["vignetting_corrected"])
        np.testing.assert_allclose(result["R"], 10/4095)
        self.assertTrue(any("not native" in warning for warning in info["warnings"]))

    def test_existing_measured_flat_prevents_double_correction(self):
        corrector = RelativeCorrector(load_settings(), lens_profile=small_profile())
        planes = {name: np.full((6, 8), 10, dtype=np.float32) for name in CHANNELS}
        metadata = raw_metadata()
        metadata["vignetting_corrected"] = True
        result, info = corrector.apply(planes, metadata)
        self.assertFalse(info["correction"]["factory_flat_applied"])
        self.assertTrue(info["vignetting_corrected"])
        np.testing.assert_allclose(result["R"], 10/4095)


class SettingsValidationTests(unittest.TestCase):
    def write_settings(self, settings):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name)/"settings.json"
        path.write_text(json.dumps(settings), encoding="utf-8")
        return path

    def base_settings(self):
        settings = load_settings()
        settings.pop("settings_sha256")
        return settings

    def test_shipped_defaults_and_saved_custom_settings_have_stable_provenance(self):
        defaults = load_settings()
        self.assertEqual(defaults["reference_iso"], 100)
        self.assertEqual(len(defaults["settings_sha256"]), 64)
        custom = self.base_settings()
        custom["raw_black_level"] = 12.5
        path = self.write_settings(custom)
        loaded = load_settings(path)
        self.assertEqual(loaded["raw_black_level"], 12.5)
        self.assertEqual(loaded["settings_sha256"], load_settings(path)["settings_sha256"])
        self.assertNotEqual(loaded["settings_sha256"], defaults["settings_sha256"])

    def test_invalid_settings_are_rejected_before_processing(self):
        cases = (("schema_version", 2), ("camera_model", "Survey3N"), ("filter", "OCN"),
                 ("lens_profile", "other.json"), ("normalize_exposure", "true"),
                 ("reference_exposure_seconds", 0), ("reference_exposure_seconds", True),
                 ("reference_iso", float("nan")), ("min_signal_fraction", -0.1),
                 ("min_signal_fraction", 1.1), ("schema_version", True),
                 ("raw_black_level", -1), ("max_jpeg_delta_seconds", float("inf")))
        for key, value in cases:
            settings = self.base_settings()
            settings[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                load_settings(self.write_settings(settings))
        for action in ("extra", "missing"):
            settings = self.base_settings()
            if action == "extra":
                settings["unexpected"] = 1
            else:
                del settings["raw_black_level"]
            with self.subTest(action=action), self.assertRaises(ValueError):
                load_settings(self.write_settings(settings))


if __name__ == "__main__":
    unittest.main()
