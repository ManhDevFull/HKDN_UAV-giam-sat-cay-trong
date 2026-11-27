"""Public, generated fixtures for JPEG signal handling and capture pairing."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from processing.images import pair_jpegs, read_jpeg, read_jpeg_metadata


class JpegTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def jpeg(self, name="capture.JPG", pixels=None, exif=None):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if pixels is None:
            pixels = np.full((4, 6, 3), [25, 75, 125], dtype=np.uint8)
        Image.fromarray(pixels).save(path, quality=100, subsampling=0, exif=exif or b"")
        return path

    def test_block_means_preserve_encoded_values_and_original_orientation(self):
        pixels = np.arange(6 * 4 * 3, dtype=np.uint8).reshape(4, 6, 3) * 3
        exif = Image.Exif()
        exif[274] = 6
        path = self.jpeg(pixels=pixels, exif=exif)
        planes, metadata = read_jpeg(path)
        # Compare with decoded pixels, avoiding assumptions about JPEG losses.
        with Image.open(path) as image:
            decoded = np.asarray(image.convert("RGB"), dtype=np.float32)
        expected = np.empty((2, 3, 3), dtype=np.float32)
        for y in range(2):
            for x in range(3):
                expected[y, x] = decoded[2*y:2*y+2, 2*x:2*x+2].mean(axis=(0, 1))
        for component, name in enumerate(("R", "G1", "B")):
            np.testing.assert_array_equal(planes[name], expected[:, :, component])
            self.assertEqual(planes[name].dtype, np.float32)
        np.testing.assert_array_equal(planes["G1"], planes["G2"])
        self.assertFalse(np.shares_memory(planes["G1"], planes["G2"]))
        self.assertEqual((metadata["width"], metadata["height"]), (6, 4))
        self.assertEqual(metadata["orientation"], 6)
        self.assertEqual(metadata["units"], "jpeg_encoded_DN")
        self.assertEqual(metadata["transfer"], "camera_processed_unknown")

    def test_exif_allowlist_supplies_exposure_but_never_private_tags(self):
        exif = Image.Exif()
        exif[271], exif[272], exif[274] = "MAPIR", "Survey3W_RGN", 1
        exif[34665] = {33434: 0.008, 34855: 100, 36867: "2026:11:02 04:11:48",
                       42033: "PRIVATE-SERIAL"}
        exif[34853] = {1: "N", 2: (10.0, 0.0, 0.0)}
        _, metadata = read_jpeg(self.jpeg(exif=exif))
        self.assertAlmostEqual(metadata["exposure_seconds"], 0.008)
        self.assertEqual(metadata["iso"], 100)
        self.assertEqual(metadata["datetime_original"], "2026-11-02T04:11:48")
        self.assertEqual(metadata["model"], "Survey3W_RGN")
        self.assertNotIn("PRIVATE-SERIAL", str(metadata))
        self.assertNotIn("gps", str(metadata).lower())

    def test_metadata_only_reader_does_not_decode_pixels(self):
        path = self.jpeg()
        with patch.object(Image.Image, "load", side_effect=AssertionError("decoded pixels")):
            metadata = read_jpeg_metadata(path)
        self.assertEqual((metadata["width"], metadata["height"]), (6, 4))
        self.assertEqual(metadata["units"], "jpeg_encoded_DN")

    def test_bad_or_disguised_jpeg_and_odd_geometry_are_rejected(self):
        corrupt = self.root / "broken.JPG"
        corrupt.write_bytes(b"not a JPEG")
        with self.assertRaisesRegex(ValueError, "cannot decode JPEG"):
            read_jpeg(corrupt)
        fake = self.root / "fake.JPG"
        Image.new("RGB", (4, 4)).save(fake, format="PNG")
        with self.assertRaisesRegex(ValueError, "expected JPEG"):
            read_jpeg(fake)
        with self.assertRaisesRegex(ValueError, "must be even"):
            read_jpeg(self.jpeg("odd.JPG", pixels=np.zeros((3, 4, 3), dtype=np.uint8)))

    def test_exact_stem_works_without_exif_and_takes_priority(self):
        raw = self.root / "2026_1102_041147_001.RAW"
        exact = self.jpeg("2026_1102_041147_001.JPG")
        fallback = self.jpeg("2026_1102_041149_002.JPG")
        pairs, unmatched, reasons = pair_jpegs([raw], [fallback, exact])
        self.assertEqual(pairs, {raw: exact})
        self.assertEqual(unmatched, [fallback])
        self.assertEqual(reasons, {raw: "exact_stem"})

    def test_survey_sequence_and_forward_time_are_both_required(self):
        raw = self.root / "2026_1102_041147_001.RAW"
        valid = self.jpeg("2026_1102_041149_002.JPG")
        wrong_sequence = self.jpeg("2026_1102_041148_004.JPG")
        backwards = self.jpeg("2026_1102_041146_002.JPG")
        too_late = self.jpeg("2026_1102_041151_002.JPG")
        elsewhere = self.jpeg("other/2026_1102_041148_002.JPG")
        invalid_date = self.jpeg("2026_1332_041149_002.JPG")
        candidates = [valid, wrong_sequence, backwards, too_late, elsewhere, invalid_date]
        pairs, unmatched, reasons = pair_jpegs([raw], candidates)
        self.assertEqual(pairs, {raw: valid})
        self.assertEqual(set(unmatched), set(candidates) - {valid})
        self.assertEqual(reasons[raw], "survey3_sequence_timestamp")

    def test_ambiguous_candidates_and_competing_raws_remain_separate(self):
        first = self.root / "2026_1102_041147_001.RAW"
        second = self.root / "2026_1102_041148_001.RAW"
        jpeg = self.jpeg("2026_1102_041149_002.JPG")
        pairs, unmatched, reasons = pair_jpegs([first, second], [jpeg])
        self.assertEqual(pairs, {})
        self.assertEqual(unmatched, [jpeg])
        self.assertEqual(set(reasons.values()), {"ambiguous_jpeg_candidates"})
        other = self.jpeg("2026_1102_041150_002.JPG")
        pairs, unmatched, reasons = pair_jpegs([first], [jpeg, other])
        self.assertEqual(pairs, {})
        self.assertEqual(set(unmatched), {jpeg, other})
        self.assertEqual(reasons[first], "ambiguous_jpeg_candidates")

    def test_duplicate_extension_exact_matches_are_ambiguous_and_never_reused(self):
        first = self.root / "capture.RAW"
        second = self.root / "capture.dng"
        jpeg = self.jpeg("capture.JPG")
        pairs, unmatched, _ = pair_jpegs([first, second], [jpeg])
        self.assertEqual(pairs, {})
        self.assertEqual(unmatched, [jpeg])
        lower = self.jpeg("capture.jpg")
        pairs, unmatched, reasons = pair_jpegs([first], [jpeg, lower])
        self.assertEqual(pairs, {})
        self.assertEqual(set(unmatched), {jpeg, lower})
        self.assertEqual(reasons[first], "ambiguous_jpeg_candidates")

    def test_exif_timestamp_conflicts_and_corrupt_jpeg_are_not_associated(self):
        raw = self.root / "2026_1102_041147_001.RAW"
        exif = Image.Exif()
        exif[34665] = {36867: "2026:11:05 04:11:48"}
        jpeg = self.jpeg("2026_1102_041149_002.JPG", exif=exif)
        pairs, unmatched, reasons = pair_jpegs([raw], [jpeg])
        self.assertEqual(pairs, {})
        self.assertEqual(unmatched, [jpeg])
        self.assertEqual(reasons[raw], "no_matching_jpeg")
        exif[34665] = {36867: "not a datetime"}
        self.jpeg(jpeg.name, exif=exif)
        self.assertEqual(pair_jpegs([raw], [jpeg])[0], {})
        jpeg.write_bytes(b"broken JPEG")
        self.assertEqual(pair_jpegs([raw], [jpeg])[0], {})

    def test_valid_exif_and_zero_second_sequence_interval(self):
        raw = self.root / "2026_1102_041147_001.RAW"
        exif = Image.Exif()
        exif[34665] = {36867: "2026:11:02 04:11:47"}
        jpeg = self.jpeg("2026_1102_041147_002.JPG", exif=exif)
        self.assertEqual(pair_jpegs([raw], [jpeg], max_delta_seconds=0)[0], {raw: jpeg})
        for limit in (-1, float("inf"), float("nan"), True):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                pair_jpegs([raw], [jpeg], max_delta_seconds=limit)


if __name__ == "__main__":
    unittest.main()
