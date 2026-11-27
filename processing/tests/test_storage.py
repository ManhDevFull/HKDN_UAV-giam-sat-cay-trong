"""Failure and concurrency checks for replacing generated survey output."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys

import pytest

from agriscan.pipeline import storage


def _paths(tmp_path):
    source = tmp_path / 'input'
    source.mkdir()
    (source / 'capture.RAW').write_bytes(b'immutable original input')
    return source, tmp_path / 'output'


def _run(source, target, *, name='result.txt', text='first'):
    with storage.transaction(source, target) as stage:
        (stage / name).parent.mkdir(parents=True, exist_ok=True)
        (stage / name).write_text(text)


def test_repeat_run_replaces_old_products_without_duplicate_directories(tmp_path):
    source, target = _paths(tmp_path)
    _run(source, target, name='old/stale.txt')
    _run(source, target, name='new/map.tif', text='replacement')
    assert not (target / 'old').exists()
    assert (target / 'new/map.tif').read_text() == 'replacement'
    assert not list(tmp_path.glob('.output.work-*'))
    marker = json.loads((target / storage.MARKER).read_text())
    assert marker['tool'] == 'agriscan-workflow'
    assert marker['directories'] == ['new']
    assert 'new/map.tif' in marker['files']
    assert (source / 'capture.RAW').read_bytes() == b'immutable original input'


def test_failure_during_processing_preserves_prior_output(tmp_path):
    source, target = _paths(tmp_path)
    _run(source, target)
    previous_marker = (target / storage.MARKER).read_bytes()
    with pytest.raises(RuntimeError, match='processing failed'):
        with storage.transaction(source, target) as stage:
            (stage / 'partial.tif').write_text('partial')
            raise RuntimeError('processing failed')
    assert (target / 'result.txt').read_text() == 'first'
    assert (target / storage.MARKER).read_bytes() == previous_marker
    assert not (target / 'partial.tif').exists()
    assert not list(tmp_path.glob('.output.work-*'))
    _run(source, target, text='next run still works')
    assert (target / 'result.txt').read_text() == 'next run still works'


def test_failed_first_run_leaves_no_public_output(tmp_path):
    source, target = _paths(tmp_path)
    with pytest.raises(RuntimeError):
        with storage.transaction(source, target):
            raise RuntimeError('no valid products')
    assert not target.exists()
    assert not list(tmp_path.glob('.output.work-*'))


@pytest.mark.parametrize('foreign', ['notes.txt', 'private-empty-directory'])
def test_foreign_files_and_directories_are_preserved(tmp_path, foreign):
    source, target = _paths(tmp_path)
    _run(source, target)
    item = target / foreign
    item.write_text('keep me') if item.suffix else item.mkdir()
    with pytest.raises(ValueError, match='foreign'):
        _run(source, target, text='not committed')
    assert item.exists()
    assert (target / 'result.txt').read_text() == 'first'


def test_foreign_file_added_while_processing_blocks_commit(tmp_path):
    source, target = _paths(tmp_path)
    _run(source, target)
    with pytest.raises(ValueError, match='foreign'):
        with storage.transaction(source, target) as stage:
            (stage / 'result.txt').write_text('replacement')
            (target / 'notes.txt').write_text('created while processing')
    assert (target / 'notes.txt').read_text() == 'created while processing'
    assert (target / 'result.txt').read_text() == 'first'


def test_arbitrary_existing_directory_is_not_overwritten(tmp_path):
    source, target = _paths(tmp_path)
    target.mkdir()
    (target / 'important.txt').write_text('unrelated data')
    with pytest.raises(ValueError, match='not created'):
        _run(source, target)
    assert (target / 'important.txt').read_text() == 'unrelated data'


def test_existing_result_belongs_to_same_input(tmp_path):
    source, target = _paths(tmp_path)
    _run(source, target)
    other = tmp_path / 'other_input'
    other.mkdir()
    with pytest.raises(ValueError, match='different input'):
        _run(other, target)
    assert (target / 'result.txt').read_text() == 'first'


@pytest.mark.parametrize('relationship', ['same', 'output_inside_source', 'source_inside_output'])
def test_source_output_overlap_is_rejected(tmp_path, relationship):
    source, target = _paths(tmp_path)
    if relationship == 'same':
        target = source
    elif relationship == 'output_inside_source':
        target = source / 'generated'
    else:
        target = tmp_path
    with pytest.raises(ValueError, match='separate'):
        _run(source, target)
    assert (source / 'capture.RAW').read_bytes() == b'immutable original input'


@pytest.mark.parametrize('kind', ['target', 'broken_target', 'parent'])
def test_output_symlinks_are_rejected(tmp_path, kind):
    source, target = _paths(tmp_path)
    actual = tmp_path / 'actual'
    actual.mkdir()
    (actual / 'private.txt').write_text('private')
    if kind == 'parent':
        linked = tmp_path / 'linked-parent'
        linked.symlink_to(actual, target_is_directory=True)
        target = linked / 'output'
    else:
        target.symlink_to(actual if kind == 'target' else tmp_path / 'missing', target_is_directory=True)
    with pytest.raises(ValueError, match='symbolic links'):
        _run(source, target)
    assert (actual / 'private.txt').read_text() == 'private'


@pytest.mark.parametrize('link_name', ['link', storage.MARKER])
def test_symlinks_inside_existing_output_are_rejected(tmp_path, link_name):
    source, target = _paths(tmp_path)
    _run(source, target)
    outside = tmp_path / 'private.txt'
    outside.write_text('private')
    link = target / link_name
    link.unlink(missing_ok=True)
    link.symlink_to(outside)
    with pytest.raises(ValueError, match='symbolic link'):
        _run(source, target)
    assert outside.read_text() == 'private'
    assert link.is_symlink()


def test_generated_symlink_is_not_published_or_followed(tmp_path):
    source, target = _paths(tmp_path)
    _run(source, target)
    with pytest.raises(ValueError, match='symbolic link'):
        with storage.transaction(source, target) as stage:
            (stage / 'link').symlink_to(source, target_is_directory=True)
    assert (target / 'result.txt').read_text() == 'first'
    assert (source / 'capture.RAW').exists()


@pytest.mark.parametrize('files', [['../private.txt'], ['/private.txt'], ['.'], 'not-a-list'])
def test_malformed_marker_inventory_is_not_trusted(tmp_path, files):
    source, target = _paths(tmp_path)
    _run(source, target)
    marker = json.loads((target / storage.MARKER).read_text())
    marker['files'] = files
    (target / storage.MARKER).write_text(json.dumps(marker))
    with pytest.raises(ValueError, match='Invalid'):
        _run(source, target)
    assert (target / 'result.txt').read_text() == 'first'


def test_valid_legacy_output_migrates_only_for_same_input(tmp_path):
    source, target = _paths(tmp_path)
    target.mkdir()
    input_id = hashlib.sha256(os.fsencode(str(source.resolve()))).hexdigest()
    (target / '.processing-output.json').write_text(json.dumps({'tool': 'survey-processing', 'input_id': input_id}))
    (target / 'summary.json').write_text(json.dumps({'schema_version': 2, 'frames': [{'output': 'raw/frame_processed'}]}))
    (target / 'manifest.json').write_text(json.dumps({'stage': 'week2_radiometry'}))
    frame = target / 'raw/frame_processed'
    frame.mkdir(parents=True)
    (frame / 'R.npy').write_bytes(b'old data')
    other = tmp_path / 'other'
    other.mkdir()
    with pytest.raises(ValueError, match='different input'):
        _run(other, target)
    _run(source, target)
    assert (target / 'result.txt').read_text() == 'first'
    assert not (target / 'raw').exists()


def test_fallback_rename_failure_restores_previous_output(tmp_path, monkeypatch):
    source, target = _paths(tmp_path)
    _run(source, target)
    monkeypatch.setattr(storage, '_exchange_directories', lambda *_: False)
    original_rename = Path.rename

    def fail_publish(path, destination):
        if path.name == 'result':
            raise OSError('publish failed')
        return original_rename(path, destination)

    monkeypatch.setattr(Path, 'rename', fail_publish)
    with pytest.raises(OSError, match='publish failed'):
        _run(source, target, text='replacement')
    assert (target / 'result.txt').read_text() == 'first'
    assert not list(tmp_path.glob('.output.work-*'))


def test_failed_rollback_retains_only_previous_copy(tmp_path, monkeypatch):
    source, target = _paths(tmp_path)
    _run(source, target)
    monkeypatch.setattr(storage, '_exchange_directories', lambda *_: False)
    original_rename = Path.rename

    def fail_publish_and_rollback(path, destination):
        if path.name in {'result', 'previous'}:
            raise OSError('injected rename failure')
        return original_rename(path, destination)

    monkeypatch.setattr(Path, 'rename', fail_publish_and_rollback)
    with pytest.raises(RuntimeError, match='prior result is preserved'):
        _run(source, target, text='replacement')
    backups = list(tmp_path.glob('.output.work-*/previous/result.txt'))
    assert len(backups) == 1
    assert backups[0].read_text() == 'first'
    assert not target.exists()


def test_target_changed_during_fallback_does_not_erase_backup_or_foreign_data(tmp_path, monkeypatch):
    source, target = _paths(tmp_path)
    _run(source, target)
    monkeypatch.setattr(storage, '_exchange_directories', lambda *_: False)
    original_rename = Path.rename

    def replace_target_before_publish(path, destination):
        if path.name == 'result':
            target.mkdir()
            (target / 'foreign.txt').write_text('do not erase')
            raise OSError('foreign target appeared')
        return original_rename(path, destination)

    monkeypatch.setattr(Path, 'rename', replace_target_before_publish)
    with pytest.raises(RuntimeError, match='prior result is preserved'):
        _run(source, target, text='replacement')
    assert (target / 'foreign.txt').read_text() == 'do not erase'
    backups = list(tmp_path.glob('.output.work-*/previous/result.txt'))
    assert len(backups) == 1
    assert backups[0].read_text() == 'first'


def test_concurrent_writer_is_rejected_then_lock_can_be_reused(tmp_path):
    source, target = _paths(tmp_path)
    with storage.transaction(source, target) as stage:
        (stage / 'result.txt').write_text('first')
        with pytest.raises(ValueError, match='locked by another run'):
            _run(source, target)
    _run(source, target, text='second')
    assert (target / 'result.txt').read_text() == 'second'
    assert (tmp_path / '.output.lock').is_file()
    assert (tmp_path / '.output.lock').stat().st_size == 0


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX kernel lock test')
def test_killed_process_releases_kernel_lock_without_manual_deletion(tmp_path):
    _, target = _paths(tmp_path)
    code = '''from pathlib import Path
import sys, time
from agriscan.pipeline.storage import _output_lock
with _output_lock(Path(sys.argv[1])):
    print('locked', flush=True)
    time.sleep(60)
'''
    env = dict(os.environ)
    env['PYTHONPATH'] = str(Path(storage.__file__).resolve().parents[2])
    process = subprocess.Popen([sys.executable, '-c', code, str(target)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    try:
        ready, _, _ = select.select([process.stdout], [], [], 5)
        assert ready, 'child did not acquire lock promptly'
        assert process.stdout.readline().strip() == 'locked'
        with pytest.raises(ValueError, match='locked by another run'):
            with storage._output_lock(target):
                pass
        process.kill()
        process.wait(timeout=5)
        with storage._output_lock(target):
            pass
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'unrelated'])
def test_lock_path_never_modifies_unrelated_files(tmp_path, kind):
    source, target = _paths(tmp_path)
    outside = tmp_path / 'private.txt'
    outside.write_text('private data')
    lock = tmp_path / '.output.lock'
    if kind == 'symlink':
        lock.symlink_to(outside)
    elif kind == 'hardlink':
        os.link(outside, lock)
    else:
        lock.write_text('unrelated file')
    with pytest.raises(ValueError):
        _run(source, target)
    assert outside.read_text() == 'private data'
    if kind == 'unrelated':
        assert lock.read_text() == 'unrelated file'


def test_linux_exchange_is_atomic_when_supported(tmp_path):
    old, new = tmp_path / 'old', tmp_path / 'new'
    old.mkdir()
    new.mkdir()
    (old / 'value').write_text('old')
    (new / 'value').write_text('new')
    if not storage._exchange_directories(old, new):
        pytest.skip('atomic directory exchange unavailable on this host/filesystem')
    assert (old / 'value').read_text() == 'new'
    assert (new / 'value').read_text() == 'old'
