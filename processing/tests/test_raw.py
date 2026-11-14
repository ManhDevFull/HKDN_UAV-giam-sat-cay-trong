"""Survey3 bit packing and CFA metadata checks without private image fixtures."""

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch

import numpy as np

from processing import raw


class CameraDecodeError(Exception):
    """Stand in for rawpy.LibRawError without requiring the optional wheel."""


class PackedRawTests(unittest.TestCase):
    def test_known_values_preserve_twelve_bit_scale(self):
        packed = np.array([0x00, 0xF0, 0xFF, 0x01, 0x00, 0x80, 0x23, 0xC1, 0xAB], dtype=np.uint8)
        decoded = raw._unpack_survey3(packed)
        np.testing.assert_array_equal(decoded, [0, 4095, 1, 2048, 0x123, 0xABC])
        self.assertEqual(decoded.dtype, np.uint16)

    def test_matches_manufacturer_nibble_reordering(self):
        # Independent oracle: MAPIR's converter swaps neighboring nibbles,
        # inserts a zero nibble and reads little-endian uint16 values.
        data = np.random.default_rng(51).integers(0, 256, 288, dtype=np.uint8)
        nibbles = np.unpackbits(data).reshape(-1, 4)
        nibbles[::2], nibbles[1::2] = nibbles[1::2].copy(), nibbles[::2].copy()
        count = data.size * 2 // 3
        rearranged = np.concatenate(
            [nibbles[::3], np.zeros((count, 4), dtype=np.uint8), nibbles[2::3], nibbles[1::3]],
            axis=1,
        )
        reference = np.packbits(rearranged.reshape(-1)).view('<u2') >> 4
        np.testing.assert_array_equal(raw._unpack_survey3(data), reference)

    def test_rejects_incomplete_or_wrongly_typed_packing(self):
        for data in (np.zeros(2, dtype=np.uint8), np.zeros((1, 3), dtype=np.uint8),
                     np.zeros(3, dtype=np.uint16)):
            with self.subTest(shape=data.shape, dtype=data.dtype):
                with self.assertRaises(ValueError):
                    raw._unpack_survey3(data)

    def test_survey3_size_guard_does_not_try_to_reshape_truncated_data(self):
        with patch.object(raw.np, 'fromfile', return_value=np.zeros(3, dtype=np.uint8)):
            with self.assertRaisesRegex(ValueError, '18,000,000'):
                raw._decode_survey3(Path('truncated.RAW'))

    def test_native_adapter_dispatch_is_case_insensitive_and_size_specific(self):
        result = (np.zeros((2, 2), dtype=np.uint16), {'pattern': 'RGGB'})
        with patch.object(Path, 'stat', return_value=SimpleNamespace(st_size=18_000_000)), \
                patch.object(raw, '_decode_survey3', return_value=result) as adapter:
            self.assertIs(raw.decode_raw(Path('capture.rAw')), result)
            adapter.assert_called_once_with(Path('capture.rAw'))


class RawpyMetadataTests(unittest.TestCase):
    def camera(self, **overrides):
        camera = SimpleNamespace(
            raw_pattern=np.array([[0, 1], [3, 2]]),
            raw_image_visible=np.arange(16, dtype=np.uint16).reshape(4, 4),
            # The visible image begins one sensor row later: GBRG, not RGGB.
            raw_colors_visible=np.tile([[3, 2], [0, 1]], (2, 2)),
            color_desc=b'RGBG',
            black_level_per_channel=[10, 20, 30, 40],
            white_level=4095,
        )
        camera.__dict__.update(overrides)
        return camera

    def decode(self, camera):
        imread = Mock(return_value=nullcontext(camera))
        with patch.dict(sys.modules, {'rawpy': SimpleNamespace(imread=imread, LibRawError=CameraDecodeError)}):
            result = raw.decode_raw(Path('capture.dng'))
        imread.assert_called_once_with('capture.dng')
        return result

    def test_libraw_failures_are_normalized_for_batch_error_handling(self):
        imread = Mock(side_effect=CameraDecodeError('unsupported format'))
        with patch.dict(sys.modules, {'rawpy': SimpleNamespace(imread=imread, LibRawError=CameraDecodeError)}):
            with self.assertRaisesRegex(ValueError, 'capture.dng: cannot decode camera RAW') as error:
                raw.decode_raw(Path('capture.dng'))
        self.assertIsInstance(error.exception.__cause__, CameraDecodeError)

    def test_visible_crop_controls_bayer_and_green_black_level_mapping(self):
        camera = self.camera()
        mosaic, metadata = self.decode(camera)
        self.assertEqual(metadata['pattern'], 'GBRG')
        self.assertEqual(metadata['black_levels'], {'G1': 40, 'B': 30, 'R': 10, 'G2': 20})
        self.assertEqual(metadata['white_level'], 4095)
        np.testing.assert_array_equal(mosaic, camera.raw_image_visible)
        mosaic[0, 0] = 999
        self.assertEqual(camera.raw_image_visible[0, 0], 0)

    def test_rejects_non_bayer_and_invalid_cfa_metadata(self):
        cameras = (
            self.camera(raw_pattern=None),
            self.camera(raw_pattern=np.zeros((6, 6), dtype=np.uint8)),
            self.camera(raw_colors_visible=np.tile([[0, 0], [2, 2]], (2, 2))),
            self.camera(raw_colors_visible=np.tile([[0, 1], [3, 4]], (2, 2))),
        )
        for camera in cameras:
            with self.subTest(camera=camera):
                with self.assertRaises(ValueError):
                    self.decode(camera)


class BayerSplitTests(unittest.TestCase):
    def test_all_four_layouts_preserve_positions_and_independent_green_planes(self):
        mosaic = np.arange(16).reshape(4, 4)
        for pattern in ('RGGB', 'BGGR', 'GRBG', 'GBRG'):
            with self.subTest(pattern=pattern):
                planes = raw.split_bayer_channels(mosaic, pattern.lower())
                self.assertEqual(set(planes), {'R', 'G1', 'G2', 'B'})
                green = 0
                for position, channel in enumerate(pattern):
                    if channel == 'G':
                        green += 1
                        channel = f'G{green}'
                    expected = mosaic[position // 2::2, position % 2::2]
                    np.testing.assert_array_equal(planes[channel], expected)
                    self.assertFalse(np.shares_memory(planes[channel], mosaic))

    def test_rejects_invalid_patterns_and_mosaic_geometry(self):
        for pattern in ('RRBB', 'RGBB', 'RGBG', 'GGGG', 'RGG'):
            with self.subTest(pattern=pattern):
                with self.assertRaises(ValueError):
                    raw.split_bayer_channels(np.zeros((4, 4)), pattern)
        for shape in ((3, 4), (4, 3), (2, 2, 3), (0, 4)):
            with self.subTest(shape=shape):
                with self.assertRaises(ValueError):
                    raw.split_bayer_channels(np.zeros(shape))


if __name__ == '__main__':
    unittest.main()
