"""Replace one managed output folder after a complete run succeeds."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

MARKER = '.processing-output.json'
_FRAME_FILES = {'R.npy', 'G1.npy', 'G2.npy', 'B.npy', 'R.png', 'G1.png', 'G2.png', 'B.png',
                'preview.png', 'metadata.json', 'bands.tif', 'valid_mask.tif', '.gitignore'}


def validate_output(path: Path, input_id: str | None = None) -> None:
    """Refuse unrelated files, links and outputs owned by another input."""
    if path.is_symlink():
        raise ValueError('Output must not be a symbolic link')
    if not path.exists():
        return
    if not path.is_dir():
        raise ValueError('Output must be a directory')
    if not any(path.iterdir()):
        return
    try:
        summary = json.loads((path / 'summary.json').read_text(encoding='utf-8'))
        if (not isinstance(summary, dict) or summary.get('schema_version') not in (1, 2)
                or not isinstance(summary.get('frames'), list)
                or any(type(summary.get(key)) is not int for key in ('input_count', 'processed_count', 'failed_count'))):
            raise ValueError('Unrecognized processing summary')
        if (path / MARKER).exists():
            marker = json.loads((path / MARKER).read_text(encoding='utf-8'))
            if not isinstance(marker, dict) or marker.get('tool') != 'survey-processing':
                raise ValueError('Unrecognized output ownership marker')
            if input_id is not None and marker.get('input_id') != input_id:
                raise ValueError('Output belongs to a different input; choose another --output')
        if summary['schema_version'] == 2:
            manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
            if not isinstance(manifest, dict) or manifest.get('stage') != 'week2_radiometry':
                raise ValueError('Unrecognized processing manifest')
        allowed = {Path(name) for name in ('summary.json', 'manifest.json', '.gitignore', MARKER)}
        for frame in summary['frames']:
            folder = Path(frame['output'])
            if folder.is_absolute() or '..' in folder.parts or folder == Path('.'):
                raise ValueError('Invalid frame output path')
            allowed.update(folder / name for name in _FRAME_FILES)
        directories = {parent for item in allowed for parent in item.parents}
        for item in path.rglob('*'):
            relative = item.relative_to(path)
            if item.is_symlink():
                raise ValueError('Output contains a symbolic link')
            if item.is_file() and relative not in allowed:
                raise ValueError(f'Output contains an unrelated file: {relative}')
            if item.is_dir() and relative not in directories:
                raise ValueError(f'Output contains an unrelated directory: {relative}')
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f'Refusing to replace an unrecognized output directory: {path.name}') from exc


@contextmanager
def output_lock(path: Path):
    """OS locks release on exit/crash; lock files live outside the repository."""
    key = hashlib.sha256(os.fsencode(str(path))).hexdigest()
    lock_dir = Path(tempfile.gettempdir()) / 'survey-processing-locks'
    lock_dir.mkdir(mode=0o700, exist_ok=True)
    with (lock_dir / f'{key}.lock').open('a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            if stream.seek(0, os.SEEK_END) == 0:
                stream.write(b'\0')
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ValueError('Another process is already writing this output') from exc
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ValueError('Another process is already writing this output') from exc
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


@contextmanager
def stage_output(input_path: Path, output_path: Path):
    """Keep previous data intact until promotion; remove temporary data on exit."""
    # Check links before resolving: following an output link could delete its target.
    output_path = output_path.absolute()
    if any(path.is_symlink() for path in (output_path, *output_path.parents)):
        raise ValueError('Output path must not contain symbolic links')
    output_path = output_path.resolve()
    source = input_path.resolve()
    if not source.exists():
        raise ValueError(f'Input does not exist: {source}')
    input_root = source if source.is_dir() else source.parent
    if output_path.is_relative_to(input_root) or input_root.is_relative_to(output_path):
        raise ValueError('Output must be separate from the input directory; source images stay unchanged')
    input_id = hashlib.sha256(os.fsencode(str(source))).hexdigest()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_lock(output_path):
        validate_output(output_path, input_id)
        work = Path(tempfile.mkdtemp(prefix=f'.{output_path.name}.tmp-', dir=output_path.parent))
        backup = work / 'previous'
        try:
            (work / '.gitignore').write_text('*\n', encoding='utf-8')
            stage = work / 'result'
            transaction = {'path': stage, 'existed': output_path.exists() and any(output_path.iterdir()),
                           'publish': False}
            yield transaction
            if not transaction['publish']:
                return
            (stage / MARKER).write_text(json.dumps({'tool': 'survey-processing', 'input_id': input_id}) + '\n',
                                       encoding='utf-8')
            # Recheck ownership before touching the existing result.
            validate_output(output_path, input_id)
            try:
                if output_path.exists():
                    output_path.rename(backup)
                stage.rename(output_path)
            except BaseException:
                if backup.exists() and not output_path.exists():
                    try:
                        backup.rename(output_path)
                    except BaseException as exc:
                        raise RuntimeError(f'Previous results retained for recovery at: {backup}') from exc
                raise
            if backup.exists():
                shutil.rmtree(backup)
        finally:
            # Never discard the previous output if restoring it failed.
            if not backup.exists():
                shutil.rmtree(work)
