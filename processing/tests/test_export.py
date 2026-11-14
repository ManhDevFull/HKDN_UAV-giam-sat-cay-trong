"""Public TIFF handoff checks without private image fixtures."""

import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import tifffile

from processing.export import save_multiband


class MultibandExportTests(unittest.TestCase):
    def planes(self):
        return {'R': np.array([[1, 2], [3, 4]], dtype=np.float32),
                'G1': np.array([[10, 20], [30, 40]], dtype=np.float32),
                'G2': np.array([[12, 24], [36, 48]], dtype=np.float32),
                'B': np.array([[100, 200], [300, 400]], dtype=np.float32)}

    def test_roundtrip_preserves_values_nodata_and_band_metadata_without_georeferencing(self):
        planes = self.planes()
        planes['R'][0, 0] = np.nan
        planes['G1'][0, 1] = np.nan
        originals = {name: value.copy() for name, value in planes.items()}
        metadata = {'units': 'relative_signal', 'status': 'relative_corrected',
                    'source': 'capture.RAW'}
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)
            result = save_multiband(destination, planes, metadata)
            self.assertEqual(result, {'raster': 'bands.tif', 'valid_mask': 'valid_mask.tif',
                                     'bands': ['red', 'green', 'nir'],
                                     'units': 'relative_signal', 'georeferenced': False, 'nodata': 'NaN'})
            with tifffile.TiffFile(destination / 'bands.tif') as image:
                raster = image.asarray()
                self.assertEqual(raster.shape, (2, 2, 3))
                self.assertEqual(raster.dtype, np.float32)
                np.testing.assert_array_equal(raster[..., 0], planes['R'])
                np.testing.assert_array_equal(raster[..., 1], (planes['G1'] + planes['G2']) / 2)
                np.testing.assert_array_equal(raster[..., 2], planes['B'])
                page = image.pages[0]
                self.assertEqual(page.photometric.name, 'MINISBLACK')
                self.assertEqual(page.planarconfig.name, 'CONTIG')
                self.assertEqual(json.loads(page.description),
                                 {'schema_version': 1, 'bands': ['red', 'green', 'nir'],
                                  'units': 'relative_signal', 'correction_status': 'relative_corrected',
                                  'source': 'capture.RAW', 'georeferenced': False, 'nodata': 'NaN'})
                # Neither EXIF GPS nor the GeoTIFF coordinate system tags exist.
                self.assertFalse(set(page.tags.keys()) & {34853, 33550, 33922, 34264, 34735, 34736, 34737})
            mask = tifffile.imread(destination / 'valid_mask.tif')
            self.assertEqual(mask.dtype, np.uint8)
            np.testing.assert_array_equal(mask, [[0, 0], [1, 1]])
        for name, original in originals.items():
            np.testing.assert_array_equal(planes[name], original)
        self.assertEqual(metadata, {'units': 'relative_signal', 'status': 'relative_corrected',
                                    'source': 'capture.RAW'})

    def test_rgb_export_preserves_encoded_units_and_all_input_channels_control_mask(self):
        planes = self.planes()
        planes['G2'][1, 0] = np.nan
        with tempfile.TemporaryDirectory() as directory:
            result = save_multiband(Path(directory), planes,
                                    {'units': 'jpeg_encoded_DN', 'correction_status': 'jpeg_fallback'}, 'RGB')
            self.assertEqual(result['bands'], ['red', 'green', 'blue'])
            with tifffile.TiffFile(Path(directory) / 'bands.tif') as image:
                info = json.loads(image.pages[0].description)
                self.assertEqual(info['units'], 'jpeg_encoded_DN')
                self.assertEqual(info['correction_status'], 'jpeg_fallback')
            np.testing.assert_array_equal(tifffile.imread(Path(directory) / 'valid_mask.tif'),
                                          [[1, 1], [0, 1]])

    def test_refuses_overwrite_of_either_existing_output(self):
        for filename in ('bands.tif', 'valid_mask.tif'):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory)
                (destination / filename).write_bytes(b'original')
                with self.assertRaises(FileExistsError):
                    save_multiband(destination, self.planes(), {'units': 'relative_signal'})
                self.assertEqual((destination / filename).read_bytes(), b'original')
                self.assertEqual(len(list(destination.iterdir())), 1)

    def test_rejects_invalid_inputs_before_creating_output(self):
        cases = []
        missing = self.planes()
        del missing['B']
        cases.append((missing, 'RGN', {'units': 'relative_signal'}))
        extra = self.planes()
        extra['NIR'] = extra['B']
        cases.append((extra, 'RGN', {'units': 'relative_signal'}))
        for invalid in (np.zeros((3, 2)), np.zeros((2, 2, 1)), np.zeros((0, 2)),
                        np.full((2, 2), 'x'), np.ones((2, 2), dtype=complex),
                        np.full((2, 2), np.inf), np.full((2, 2), 1e100)):
            planes = self.planes()
            planes['G2'] = invalid
            cases.append((planes, 'RGN', {'units': 'relative_signal'}))
        cases.extend([(self.planes(), 'INVALID', {'units': 'relative_signal'}),
                      (self.planes(), 'RGN', {}), (self.planes(), 'RGN', {'units': ''})])
        for index, (planes, filter_name, metadata) in enumerate(cases):
            with self.subTest(case=index), tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / 'new'
                with self.assertRaises(ValueError):
                    save_multiband(destination, planes, metadata, filter_name)
                self.assertFalse(destination.exists())

    def test_green_average_does_not_overflow_large_float32_inputs(self):
        planes = self.planes()
        planes['G1'].fill(np.finfo(np.float32).max)
        planes['G2'].fill(np.finfo(np.float32).max)
        with tempfile.TemporaryDirectory() as directory:
            save_multiband(Path(directory), planes, {'units': 'relative_signal'})
            raster = tifffile.imread(Path(directory) / 'bands.tif')
            self.assertTrue(np.all(np.isfinite(raster[..., 1])))

    def test_unicode_source_path_roundtrips_in_tiff_description(self):
        with tempfile.TemporaryDirectory() as directory:
            save_multiband(Path(directory), self.planes(),
                           {'units': 'relative_signal', 'source': 'ảnh/khảo-sát.RAW'})
            with tifffile.TiffFile(Path(directory) / 'bands.tif') as image:
                self.assertEqual(json.loads(image.pages[0].description)['source'], 'ảnh/khảo-sát.RAW')


if __name__ == '__main__':
    unittest.main()
