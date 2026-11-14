"""Integration checks against held-out synthetic scenes and failure scenarios."""

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

from processing.config import load_config, sample_roi
from processing.pipeline import Preprocessor, run_batch
from processing.synthetic import make_calibration_demo
from processing.vignetting import correct_vignetting


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assets = self.root / 'assets'
        make_calibration_demo(self.assets)
        self.config_path = self.assets / 'calibration.json'
        self.config = json.loads(self.config_path.read_text())

    def save_config(self):
        self.config_path.write_text(json.dumps(self.config))

    def run_pipeline(self, name='output'):
        with redirect_stdout(io.StringIO()):
            return run_batch(self.assets, self.root / name)

    def test_end_to_end_recovers_heldout_scene_and_preserves_sources(self):
        before = {p: hashlib.sha256(p.read_bytes()).digest() for p in self.assets.rglob('*') if p.is_file()}
        report = self.run_pipeline()
        self.assertEqual((report['input_count'], report['calibrated_count'], report['failed_count']), (3, 3, 0))
        self.assertEqual(report['validation']['status'], 'passed')
        truth = {'R': 0.35, 'G1': 0.4, 'G2': 0.4, 'B': 0.55}
        for frame in report['frames']:
            folder = self.root / 'output' / frame['output']
            metadata = json.loads((folder / 'metadata.json').read_text())
            self.assertEqual(metadata['units'], 'reflectance_fraction')
            self.assertTrue(metadata['vignetting_corrected'])
            for channel, expected in truth.items():
                actual = np.load(folder / f'{channel}.npy')
                self.assertEqual(actual.dtype, np.float32)
                np.testing.assert_allclose(actual.mean(), expected, atol=0.0001)
                self.assertLess(float(actual.std()), 0.0003)
        for path, checksum in before.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), checksum)

    def test_changed_object_fails_independent_check_and_cli_gate(self):
        path = self.assets / 'afternoon' / 'scene.npy'
        # Change only the held-out object; calibration target remains unchanged.
        mosaic = np.load(path)
        np.save(path, (mosaic - 64) * 1.3 + 64)
        completed = subprocess.run(
            [sys.executable, '-m', 'processing.cli', str(self.assets), '--output', str(self.root / 'output'),
             '--require-validation'], text=True, capture_output=True)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        report = json.loads((self.root / 'output' / 'summary.json').read_text())
        self.assertEqual(report['status'], 'calibrated')
        self.assertEqual(report['validation']['status'], 'failed')

    def test_missing_calibration_is_honest_and_jpeg_not_treated_as_linear(self):
        source = self.root / 'uncalibrated'
        source.mkdir()
        np.save(source / 'scene.npy', np.full((16, 16), 1000, dtype=np.uint16))
        Image.fromarray(np.full((16, 16, 3), 180, dtype=np.uint8)).save(source / 'preview.JPG')
        with redirect_stdout(io.StringIO()):
            report = run_batch(source, self.root / 'output')
        self.assertEqual(report['input_count'], 2)
        self.assertEqual(report['status'], 'relative_corrected')
        self.assertEqual(report['relative_corrected_count'], 1)
        self.assertEqual(report['preview_only_count'], 1)
        self.assertEqual(report['validation']['status'], 'incomplete')
        manifest = json.loads((self.root / 'output' / 'manifest.json').read_text())
        raw_item = next(item for item in manifest['items'] if item['status'] == 'relative_corrected')
        jpeg_item = next(item for item in manifest['items'] if item['status'] == 'preview_only')
        self.assertNotIn('raster', jpeg_item)
        self.assertFalse(jpeg_item['analysis_eligibility']['cross_survey_comparison'])
        metadata = json.loads((self.root / 'output' / raw_item['metadata']).read_text())
        self.assertFalse(metadata['vignetting_corrected'])
        self.assertEqual(metadata['units'], 'relative_DN')

    def test_input_filter_conflict_is_rejected_before_output(self):
        for camera in ({'model': 'Survey3W_OCN', 'filter': 'OCN'},
                       {'model': 'Survey3W_RGN', 'filter': 'OCN'},
                       {'model': 'Survey3W_OCN', 'filter': 'RGN'}):
            (self.assets / 'metadata.json').write_text(json.dumps({'camera': camera}))
            with self.subTest(camera=camera), self.assertRaisesRegex(ValueError, 'never mix RGN and OCN'):
                self.run_pipeline()
        self.assertFalse((self.root / 'output').exists())

    def test_jpeg_only_run_does_not_claim_raw_correction(self):
        source = self.root / 'jpeg-only'
        source.mkdir()
        Image.fromarray(np.full((16, 16, 3), 100, dtype=np.uint8)).save(source / 'view.JPG')
        with redirect_stdout(io.StringIO()):
            report = run_batch(source, self.root / 'output')
        self.assertEqual(report['status'], 'preview_only')
        self.assertEqual(report['relative_corrected_count'], 0)
        manifest = json.loads((self.root / 'output' / 'manifest.json').read_text())
        eligibility = manifest['items'][0]['analysis_eligibility']
        self.assertIs(eligibility['quantitative_input'], False)
        self.assertEqual(eligibility['source_encoding'], 'JPEG')
        self.assertNotIn('raster', manifest['items'][0])

    def test_declared_other_camera_cannot_use_survey3w_factory_profile(self):
        (self.assets / 'metadata.json').write_text(json.dumps({'camera': {'model': 'OtherCamera', 'filter': 'RGN'}}))
        with self.assertRaisesRegex(ValueError, 'does not match camera'):
            self.run_pipeline()
        self.assertFalse((self.root / 'output').exists())

    def test_custom_output_always_contains_ignore_rule_and_portable_manifest(self):
        self.run_pipeline('custom-result')
        output = self.root / 'custom-result'
        self.assertEqual((output / '.gitignore').read_text(), '*\n')
        manifest = json.loads((output / 'manifest.json').read_text())
        self.assertFalse(manifest['georeferenced'])
        for item in manifest['items']:
            for key in ('raster', 'valid_mask', 'preview', 'metadata'):
                self.assertFalse(Path(item[key]).is_absolute())
                self.assertTrue((output / item[key]).is_file())

    def test_failed_image_cannot_remove_all_checks_for_an_expected_object(self):
        # A second validation object is configured in every session, but every
        # ROI is invalid. It must still appear as incomplete in the QA report.
        for session in self.config['sessions']:
            session['checks'].append({'image': session['checks'][0]['image'], 'object_id': 'missing-object',
                                      'roi': [0, 0, 10000, 10000]})
        self.save_config()
        report = self.run_pipeline()
        self.assertEqual(report['failed_count'], 3)
        self.assertEqual(report['validation']['status'], 'incomplete')
        self.assertIn('missing-object', report['validation']['objects'])
        self.assertNotEqual(report['validation']['objects']['missing-object']['status'], 'passed')

    def test_corrupt_frame_does_not_abort_other_images_or_skip_summary(self):
        (self.assets / 'broken.RAW').write_bytes(b'corrupt')
        (self.assets / 'empty.npy').write_bytes(b'')
        report = self.run_pipeline()
        self.assertEqual((report['processed_count'], report['failed_count']), (3, 2))
        self.assertEqual(report['status'], 'failed')
        self.assertTrue((self.root / 'output' / 'summary.json').is_file())

    def test_outputs_cannot_overwrite_sources_and_successful_rerun_replaces_old_run(self):
        with self.assertRaises(ValueError):
            run_batch(self.assets, self.assets / 'output')
        first = self.run_pipeline()
        second = self.run_pipeline()
        self.assertTrue(second['output_updated'])
        self.assertEqual(first['input_count'], second['input_count'])

    def test_successful_rerun_removes_stale_images(self):
        orphan = self.assets / 'removed.npy'
        np.save(orphan, np.full((96, 96), 1000, dtype=np.uint16))
        first = self.run_pipeline()
        old = next(frame for frame in first['frames'] if frame['source'] == 'removed.npy')
        old_output = self.root / 'output' / old['output']
        self.assertTrue(old_output.is_dir())
        orphan.unlink()
        second = self.run_pipeline()
        self.assertTrue(second['output_updated'])
        self.assertFalse(old_output.exists())
        self.assertFalse(list(self.root.glob('.output.tmp-*')))

    def test_failed_rerun_preserves_existing_results(self):
        self.run_pipeline()
        output = self.root / 'output'
        before = {p.relative_to(output): hashlib.sha256(p.read_bytes()).digest()
                  for p in output.rglob('*') if p.is_file()}
        (self.assets / 'broken.RAW').write_bytes(b'corrupt')
        second = self.run_pipeline()
        self.assertEqual(second['failed_count'], 1)
        self.assertFalse(second['output_updated'])
        self.assertTrue(second['previous_output_retained'])
        after = {p.relative_to(output): hashlib.sha256(p.read_bytes()).digest()
                 for p in output.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(list(self.root.glob('.output.tmp-*')))

    def test_failed_validation_keeps_previous_output_and_cli_exit_two(self):
        self.run_pipeline()
        summary_path = self.root / 'output' / 'summary.json'
        previous = summary_path.read_bytes()
        scene = self.assets / 'afternoon' / 'scene.npy'
        np.save(scene, (np.load(scene) - 64) * 1.3 + 64)
        completed = subprocess.run(
            [sys.executable, '-m', 'processing.cli', str(self.assets), '--output', str(self.root / 'output'),
             '--require-validation'], text=True, capture_output=True)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn('previous output kept unchanged', completed.stdout)
        self.assertEqual(summary_path.read_bytes(), previous)

    def test_first_failed_run_into_empty_folder_keeps_diagnostics(self):
        (self.root / 'output').mkdir()
        (self.assets / 'broken.RAW').write_bytes(b'corrupt')
        result = self.run_pipeline()
        self.assertTrue(result['output_updated'])
        self.assertEqual(result['failed_count'], 1)
        self.assertTrue((self.root / 'output' / 'summary.json').is_file())

    def test_overlapping_sessions_and_calibration_rois_are_rejected(self):
        self.config['sessions'][1]['images'] = self.config['sessions'][0]['images']
        self.save_config()
        with self.assertRaisesRegex(ValueError, 'more than one session'):
            self.run_pipeline()
        self.config['sessions'][1]['images'] = ['noon/scene.npy']
        self.config['sessions'][0]['panels'][1]['roi'] = [16, 16, 32, 32]
        self.save_config()
        with self.assertRaisesRegex(ValueError, 'overlap'):
            self.run_pipeline()
        self.assertFalse((self.root / 'output').exists())

    def test_configuration_rejects_typos_and_unconfirmed_exposure(self):
        for setting in ({'pattern': []}, {'black_level': -1}, {'filter': []}, {'schema_version': True},
                        {'flat': ''}, {'unknown': 2}):
            config = dict(self.config, **setting)
            self.config_path.write_text(json.dumps(config))
            with self.subTest(setting=setting), self.assertRaises(ValueError):
                load_config(self.config_path)
        self.config['sessions'][0]['exposure_confirmed'] = False
        self.save_config()
        with self.assertRaisesRegex(ValueError, 'exposure'):
            self.run_pipeline()

    def test_bad_panel_reference_and_invalid_rois_are_rejected(self):
        self.config['sessions'][0]['panels'][0]['reflectance']['NIR'] = None
        self.save_config()
        with self.assertRaises(ValueError):
            self.run_pipeline()
        plane = np.ones((16, 16), dtype=np.float32)
        for roi in ([1, 0, 8, 8], [0, 0, 2, 2], [0, 0, 34, 8], [True, 0, 8, 8]):
            with self.subTest(roi=roi), self.assertRaises(ValueError):
                sample_roi(plane, roi)
        plane[0, 0] = np.nan
        with self.assertRaisesRegex(ValueError, 'saturated or invalid'):
            sample_roi(plane, [0, 0, 8, 8])

    def test_flat_field_correction_and_invalid_flats(self):
        flat = np.array([[1, 2], [2, 4]], dtype=np.float32)
        np.testing.assert_allclose(correct_vignetting(100 * flat, flat), np.full((2, 2), 200))
        for bad in (np.zeros((2, 2)), np.full((2, 2), np.nan), np.full((2, 2), -1)):
            with self.assertRaises(ValueError):
                correct_vignetting(flat, bad)
        np.save(self.assets / 'bad-flat.npy', np.zeros((16, 16)))
        with self.assertRaisesRegex(ValueError, 'positive'):
            Preprocessor(flat=self.assets / 'bad-flat.npy')


if __name__ == '__main__':
    unittest.main()
