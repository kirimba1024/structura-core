import hashlib
import os
import stat
from pathlib import Path

from .nbt_io import atomic_write

PAGE_BYTES = 64 * 1024
MINIMUM_FILE_BYTES = 1024 * 1024


def _directory(backup):
    return Path(backup).parent.parent / 'backup-blobs'


def store(source, backup, expected, synchronize):
    folder = _directory(backup)
    folder.mkdir(exist_ok=True)
    pages, whole, size = [], hashlib.sha256(), 0
    with Path(source).open('rb') as stream:
        for data in iter(lambda: stream.read(PAGE_BYTES), b''):
            whole.update(data)
            size += len(data)
            key = hashlib.sha256(data).hexdigest()
            destination = folder / key
            if not destination.is_file() or hashlib.sha256(destination.read_bytes()).hexdigest() != key:
                atomic_write(destination, data)
                with destination.open('rb') as written:
                    os.fsync(written.fileno())
                if hashlib.sha256(destination.read_bytes()).hexdigest() != key:
                    raise OSError('Backup page verification failed')
            pages.append(key)
    if whole.hexdigest() != expected:
        raise ValueError('Prepared backup file changed')
    synchronize(folder)
    synchronize(folder.parent)
    return {'size': size, 'pages': pages, 'mode': stat.S_IMODE(Path(source).stat().st_mode)}


def validate(record):
    if not isinstance(record, dict):
        raise ValueError('Invalid backup content record')
    size, pages, mode = record.get('size'), record.get('pages'), record.get('mode')
    if type(size) is not int or size <= 0 or not isinstance(pages, list) or len(pages) != (size + PAGE_BYTES - 1) // PAGE_BYTES:
        raise ValueError('Invalid backup page count')
    if type(mode) is not int or not 0 <= mode <= 0o7777:
        raise ValueError('Invalid backup file permissions')
    if any(not isinstance(key, str) or len(key) != 64 or any(c not in '0123456789abcdef' for c in key) for key in pages):
        raise ValueError('Invalid backup page hash')


def blocks(backup, record):
    folder = _directory(backup)
    remaining = record['size']
    for key in record['pages']:
        path = folder / key
        with path.open('rb') as stream:
            data = stream.read(PAGE_BYTES + 1)
        if len(data) != min(remaining, PAGE_BYTES) or hashlib.sha256(data).hexdigest() != key:
            raise ValueError('Backup page no longer matches its hash')
        remaining -= len(data)
        yield data


def digest(backup, record):
    result = hashlib.sha256()
    for data in blocks(backup, record):
        result.update(data)
    return result.hexdigest()


def materialize(backup, record, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('wb') as stream:
        for data in blocks(backup, record):
            stream.write(data)
    destination.chmod(record['mode'])
