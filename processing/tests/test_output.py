"""Protect prior results when replacing a managed processing output."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from processing.output import MARKER, output_lock, stage_output, validate_output


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'assets'
        self.source.mkdir()
        self.output = self.root / 'output'
        self.input_id = hashlib.sha256(os.fsencode(str(self.source.resolve()))).hexdigest()

    def write_output(self, path, label='previous', *, schema=2, marker=True, frame=None):
        path.mkdir(parents=True)
        summary = {'schema_version': schema, 'input_count': int(frame is not None),
                   'processed_count': int(frame is not None), 'failed_count': 0,
                   'frames': [{'output': frame}] if frame else [], 'run_label': label}
        (path / 'summary.json').write_text(json.dumps(summary), encoding='utf-8')
        if schema == 2:
            (path / 'manifest.json').write_text(
                json.dumps({'stage': 'week2_radiometry', 'items': []}), encoding='utf-8')
        (path / '.gitignore').write_text('*\n', encoding='utf-8')
        if marker:
            (path / MARKER).write_text(
                json.dumps({'tool': 'survey-processing', 'input_id': self.input_id}), encoding='utf-8')
        if frame:
            folder = path / frame
            folder.mkdir(parents=True)
            (folder / 'metadata.json').write_text('{}', encoding='utf-8')
            (folder / 'R.npy').write_bytes(b'fixture raster')

    def snapshot(self, path):
        return {item.relative_to(path).as_posix(): item.read_bytes()
                for item in path.rglob('*') if item.is_file()}

    def assert_no_staging(self):
        self.assertEqual(list(self.root.glob('.output.tmp-*')), [])

    def test_success_replaces_managed_result_and_removes_obsolete_frames(self):
        self.write_output(self.output, frame='old_RAW_processed')
        with stage_output(self.source, self.output) as transaction:
            self.assertTrue(transaction['existed'])
            self.write_output(transaction['path'], 'new', marker=False)
            transaction['publish'] = True
        summary = json.loads((self.output / 'summary.json').read_text())
        self.assertEqual(summary['run_label'], 'new')
        self.assertFalse((self.output / 'old_RAW_processed').exists())
        validate_output(self.output, self.input_id)
        self.assert_no_staging()

    def test_unpublished_result_keeps_previous_output_byte_for_byte(self):
        self.write_output(self.output)
        before = self.snapshot(self.output)
        with stage_output(self.source, self.output) as transaction:
            self.write_output(transaction['path'], 'failed attempt', marker=False)
        self.assertEqual(self.snapshot(self.output), before)
        self.assert_no_staging()

    def test_empty_output_is_treated_as_a_first_run(self):
        self.output.mkdir()
        with stage_output(self.source, self.output) as transaction:
            self.assertFalse(transaction['existed'])
            self.write_output(transaction['path'], 'first diagnostics', marker=False)
            transaction['publish'] = True
        self.assertEqual(json.loads((self.output / 'summary.json').read_text())['run_label'],
                         'first diagnostics')
        self.assert_no_staging()

    def test_legacy_summary_without_marker_or_manifest_is_recognized(self):
        self.write_output(self.output, schema=1, marker=False, frame='old_processed')
        validate_output(self.output, self.input_id)
        with stage_output(self.source, self.output) as transaction:
            self.write_output(transaction['path'], 'upgraded', marker=False)
            transaction['publish'] = True
        self.assertTrue((self.output / MARKER).is_file())
        self.assertFalse((self.output / 'old_processed').exists())

    def test_rejects_unmanaged_directory_without_touching_private_files(self):
        self.output.mkdir()
        private = self.output / 'notes.txt'
        private.write_text('private field notes', encoding='utf-8')
        with self.assertRaises(ValueError), stage_output(self.source, self.output):
            self.fail('Unmanaged output must not be opened for replacement')
        self.assertEqual(private.read_text(), 'private field notes')
        self.assert_no_staging()

    def test_rejects_foreign_file_inside_otherwise_managed_result(self):
        self.write_output(self.output)
        (self.output / 'notes.txt').write_text('keep this', encoding='utf-8')
        before = self.snapshot(self.output)
        with self.assertRaisesRegex(ValueError, 'unrelated file'):
            validate_output(self.output, self.input_id)
        self.assertEqual(self.snapshot(self.output), before)

    def test_rejects_result_owned_by_a_different_input(self):
        self.write_output(self.output)
        other = self.root / 'other-assets'
        other.mkdir()
        before = self.snapshot(self.output)
        with self.assertRaisesRegex(ValueError, 'different input'), stage_output(other, self.output):
            self.fail('Another input must not overwrite this result')
        self.assertEqual(self.snapshot(self.output), before)
        self.assert_no_staging()

    def test_rejects_frame_paths_outside_output(self):
        self.write_output(self.output)
        summary_path = self.output / 'summary.json'
        summary = json.loads(summary_path.read_text())
        for unsafe in ('../assets', str(self.source.resolve()), '.'):
            summary['frames'] = [{'output': unsafe}]
            summary_path.write_text(json.dumps(summary), encoding='utf-8')
            with self.subTest(path=unsafe), self.assertRaisesRegex(ValueError, 'frame output path'):
                validate_output(self.output, self.input_id)

    def test_rejects_output_and_nested_symlinks_without_touching_targets(self):
        target = self.root / 'private'
        target.mkdir()
        private = target / 'secret.txt'
        private.write_text('private data', encoding='utf-8')
        try:
            self.output.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('Symbolic links are unavailable')
        with self.assertRaisesRegex(ValueError, 'symbolic link'), stage_output(self.source, self.output):
            self.fail('Output link must be rejected')
        self.assertEqual(private.read_text(), 'private data')
        self.output.unlink()
        self.write_output(self.output)
        (self.output / 'linked-notes').symlink_to(private)
        with self.assertRaisesRegex(ValueError, 'symbolic link'):
            validate_output(self.output, self.input_id)
        self.assertEqual(private.read_text(), 'private data')

    def test_rejects_dangling_output_symlink(self):
        try:
            self.output.symlink_to(self.root / 'missing', target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('Symbolic links are unavailable')
        with self.assertRaisesRegex(ValueError, 'symbolic link'), stage_output(self.source, self.output):
            self.fail('Dangling link must be rejected')
        self.assertTrue(self.output.is_symlink())
        self.assert_no_staging()

    def test_processing_interrupt_removes_staging_and_preserves_previous_result(self):
        self.write_output(self.output)
        before = self.snapshot(self.output)
        with self.assertRaises(KeyboardInterrupt):
            with stage_output(self.source, self.output) as transaction:
                self.write_output(transaction['path'], 'interrupted', marker=False)
                raise KeyboardInterrupt()
        self.assertEqual(self.snapshot(self.output), before)
        self.assert_no_staging()

    def test_publication_interrupt_restores_previous_result(self):
        self.write_output(self.output)
        before = self.snapshot(self.output)
        rename = Path.rename

        def interrupted_promotion(path, target):
            if path.name == 'result':
                raise KeyboardInterrupt()
            return rename(path, target)

        with patch.object(Path, 'rename', interrupted_promotion), self.assertRaises(KeyboardInterrupt):
            with stage_output(self.source, self.output) as transaction:
                self.write_output(transaction['path'], 'interrupted promotion', marker=False)
                transaction['publish'] = True
        self.assertEqual(self.snapshot(self.output), before)
        self.assert_no_staging()

    def test_failed_rollback_keeps_previous_result_recoverable(self):
        self.write_output(self.output)
        before = self.snapshot(self.output)
        rename = Path.rename

        def failed_promotion_and_rollback(path, target):
            if path.name == 'result':
                raise KeyboardInterrupt()
            if path.name == 'previous':
                raise OSError('Simulated restore failure')
            return rename(path, target)

        with patch.object(Path, 'rename', failed_promotion_and_rollback):
            with self.assertRaisesRegex(RuntimeError, 'retained for recovery') as raised:
                with stage_output(self.source, self.output) as transaction:
                    self.write_output(transaction['path'], 'cannot publish', marker=False)
                    transaction['publish'] = True
        backups = list(self.root.glob('.output.tmp-*/previous'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(self.snapshot(backups[0]), before)
        self.assertIn(str(backups[0]), str(raised.exception))
        self.assertFalse(self.output.exists())

    def test_output_lock_rejects_another_process_and_releases_after_exit(self):
        script = (
            'from pathlib import Path\n'
            'import sys\n'
            'from processing.output import output_lock\n'
            'try:\n'
            '    with output_lock(Path(sys.argv[1])):\n'
            '        pass\n'
            'except ValueError:\n'
            '    sys.exit(3)\n'
        )
        command = [sys.executable, '-c', script, str(self.output)]
        with output_lock(self.output):
            blocked = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(blocked.returncode, 3, blocked.stderr)
        released = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(released.returncode, 0, released.stderr)
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()
