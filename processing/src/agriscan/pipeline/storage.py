"""One output per input, kernel-held writer locks, and safe replacement."""

from contextlib import contextmanager
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

try:
    import fcntl
except ImportError:  # pragma: no cover - the ODM workflow targets POSIX hosts.
    fcntl = None


MARKER = '.agriscan-output.json'


def _relative_names(values, *, label: str) -> set[str]:
    if not isinstance(values, list):
        raise ValueError(f'Invalid {label} inventory in output marker')
    names = set()
    for value in values:
        if not isinstance(value, str):
            raise ValueError(f'Invalid {label} path in output marker')
        path = Path(value)
        if not value or value == '.' or path.is_absolute() or '..' in path.parts or path.as_posix() != value:
            raise ValueError(f'Invalid {label} path in output marker')
        names.add(value)
    return names


def _parent_names(files: set[str]) -> set[str]:
    return {parent.as_posix() for filename in files for parent in Path(filename).parents if parent != Path('.')}


def _inventory(path: Path) -> tuple[set[str], set[str]]:
    """Do not follow symlinks or silently erase FIFOs, sockets or other files."""
    files, directories = set(), set()
    for item in path.rglob('*'):
        mode = item.lstat().st_mode
        name = item.relative_to(path).as_posix()
        if stat.S_ISLNK(mode):
            raise ValueError('Output contains a symbolic link')
        if stat.S_ISREG(mode):
            files.add(name)
        elif stat.S_ISDIR(mode):
            directories.add(name)
        else:
            raise ValueError('Output contains a special file; refusing to replace it')
    return files, directories


def _validate_output(path: Path, input_id: str) -> None:
    if path.is_symlink():
        raise ValueError('Output path cannot be a symbolic link')
    if not path.exists():
        return
    if not path.is_dir():
        raise ValueError('Output must be a directory')
    files, directories = _inventory(path)
    if not files and not directories:
        return
    marker = path / MARKER
    try:
        if marker.is_file():
            data = json.loads(marker.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('tool') != 'agriscan-workflow' or data.get('input_id') != input_id:
                raise ValueError('Output belongs to a different input')
            allowed_files = _relative_names(data.get('files'), label='file') | {MARKER}
            allowed_directories = _relative_names(data.get('directories', []), label='directory') | _parent_names(allowed_files)
            if not files <= allowed_files or not directories <= allowed_directories:
                raise ValueError('Output contains foreign files or directories; refusing to replace it')
            return
        # Migrate only this same input's previously generated week-2 output.
        legacy = json.loads((path / '.processing-output.json').read_text(encoding='utf-8'))
        summary = json.loads((path / 'summary.json').read_text(encoding='utf-8'))
        manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
        if (legacy.get('tool') != 'survey-processing' or legacy.get('input_id') != input_id
                or summary.get('schema_version') != 2 or manifest.get('stage') != 'week2_radiometry'):
            raise ValueError('Unrecognized prior output or output belongs to a different input')
        allowed_files = {'summary.json', 'manifest.json', '.gitignore', '.processing-output.json'}
        names = {'R.npy', 'G1.npy', 'G2.npy', 'B.npy', 'preview.png', 'metadata.json', 'bands.tif', 'valid_mask.tif', '.gitignore'}
        for frame in summary['frames']:
            folder_names = _relative_names([frame['output']], label='prior output')
            folder = Path(next(iter(folder_names)))
            allowed_files |= {(folder / name).as_posix() for name in names}
        if not files <= allowed_files or not directories <= _parent_names(allowed_files):
            raise ValueError('Unrecognized files or directories in previous output')
    except (OSError, KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError('Refusing to overwrite a directory not created by this pipeline') from exc


@contextmanager
def _output_lock(target: Path):
    """Keep the lock inode: unlinking it would allow two independent writers.

    flock state belongs to the open descriptor, so process termination releases
    the lock immediately. The small persistent file itself never means locked.
    """
    if fcntl is None:
        raise RuntimeError('Safe output locking requires a POSIX host (Linux/macOS); run the workflow in Linux or WSL')
    lock = target.parent / f'.{target.name}.lock'
    flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_CLOEXEC', 0) | getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(lock, flags, 0o600)
    except OSError as exc:
        raise ValueError(f'Cannot open output lock safely: {lock}') from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_nlink != 1:
            raise ValueError('Output lock must be a regular file without hard links')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError(f'Output is locked by another run ({lock.name}); wait for that run to finish') from exc
        # Keep the inode empty and immutable. A killed metadata write must not
        # turn a released kernel lock into an unusable half-written lock file.
        if os.fstat(fd).st_size:
            raise ValueError('Output lock path contains an unrelated file')
        yield
    finally:
        os.close(fd)


def _exchange_directories(left: Path, right: Path) -> bool:
    """On Linux, atomically exchange old/new nonempty output directories.

    A killed process therefore leaves either the old or the new output at the
    public path, never a gap between two renames. Other hosts/filesystems use
    the rollback-protected rename fallback below.
    """
    if not sys.platform.startswith('linux'):
        return False
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, 'renameat2', None)
    if renameat2 is None:
        return False
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(-100, os.fsencode(left), -100, os.fsencode(right), 2)  # AT_FDCWD, RENAME_EXCHANGE
    if result == 0:
        return True
    error = ctypes.get_errno()
    if error in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP, errno.ENOTSUP}:
        return False
    raise OSError(error, os.strerror(error), str(right))


@contextmanager
def transaction(input_path: Path, output_path: Path):
    target = Path(output_path).absolute()
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise ValueError('Output path cannot contain symbolic links')
    target = target.resolve()
    source = Path(input_path).resolve()
    if target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError('Output and source must be separate; source images are immutable')
    input_id = hashlib.sha256(os.fsencode(str(source))).hexdigest()
    target.parent.mkdir(parents=True, exist_ok=True)
    with _output_lock(target):
        work = None
        backup = None
        committed = False
        try:
            _validate_output(target, input_id)
            work = Path(tempfile.mkdtemp(prefix=f'.{target.name}.work-', dir=target.parent))
            (work / '.gitignore').write_text('*\n', encoding='utf-8')
            stage = work / 'result'
            stage.mkdir()
            (stage / '.gitignore').write_text('*\n', encoding='utf-8')
            yield stage
            if not stage.is_dir() or stage.is_symlink():
                raise ValueError('Pipeline output staging directory was replaced')
            files, directories = _inventory(stage)
            if MARKER in files:
                raise ValueError('Pipeline output uses the reserved ownership marker name')
            (stage / MARKER).write_text(json.dumps({'tool': 'agriscan-workflow', 'input_id': input_id,
                                                   'files': sorted(files), 'directories': sorted(directories)}), encoding='utf-8')
            # Reject a foreign file added while the potentially long job ran.
            _validate_output(target, input_id)
            if not target.exists() or not _exchange_directories(stage, target):
                backup = work / 'previous'
                try:
                    if target.exists():
                        target.rename(backup)
                    stage.rename(target)
                except BaseException as exc:
                    if backup.exists():
                        if target.exists() or target.is_symlink():
                            raise RuntimeError(f'Output path changed during replacement; prior result is preserved at {backup}') from exc
                        try:
                            backup.rename(target)
                        except BaseException as rollback_exc:
                            raise RuntimeError(f'Output replacement failed; prior result is preserved at {backup}') from rollback_exc
                    raise exc
            committed = True
        finally:
            # If rollback itself failed, retain the only surviving previous copy.
            if work is not None and (backup is None or not backup.exists() or committed):
                shutil.rmtree(work)
