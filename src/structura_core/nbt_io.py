import gzip
import os
import stat
import zlib
from io import BytesIO
from os import PathLike
from pathlib import Path
from typing import Union
from uuid import uuid4

from amulet_nbt import (
    CompoundTag,
    NamedTag,
    NBTLoadError,
    load as load_nbt,
    utf8_escape_decoder,
    utf8_escape_encoder,
)

from .limits import DEFAULT_MAX_NBT_BYTES
from .snbt_reader import load_snbt

PathInput = Union[str, PathLike[str]]


def _check_byte_limit(limit):
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("max_nbt_bytes must be a positive integer")


def _bounded_read(stream, limit):
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"NBT data exceeds max_nbt_bytes={limit:,}")
    return data


def read_root(data: bytes, *, max_nbt_bytes: int = DEFAULT_MAX_NBT_BYTES,
              little_endian: bool = False) -> CompoundTag:
    _check_byte_limit(max_nbt_bytes)
    if len(data) > max_nbt_bytes:
        raise ValueError(f"NBT input exceeds max_nbt_bytes={max_nbt_bytes:,}")
    if data.startswith(b"\x1f\x8b"):
        try:
            with gzip.GzipFile(fileobj=BytesIO(data)) as stream:
                data = _bounded_read(stream, max_nbt_bytes)
        except (gzip.BadGzipFile, EOFError, zlib.error) as error:
            raise ValueError("invalid gzip-compressed NBT") from error
    try:
        options = {"string_decoder": utf8_escape_decoder} if little_endian else {}
        return load_nbt(data, compressed=False, little_endian=little_endian, **options).compound
    except (NBTLoadError, EOFError, TypeError) as error:
        raise ValueError(f"invalid NBT: {error}") from error


def load_root(path: PathInput, *, max_nbt_bytes: int = DEFAULT_MAX_NBT_BYTES,
              little_endian: bool = False) -> CompoundTag:
    _check_byte_limit(max_nbt_bytes)
    with Path(path).open("rb") as stream:
        data = _bounded_read(stream, max_nbt_bytes)
    if Path(path).suffix.lower() == ".snbt":
        try:
            text = data.decode("utf-8").strip()
            root = load_snbt(text)
        except (ValueError, UnicodeError, RecursionError) as error:
            raise ValueError(f"invalid SNBT: {error}") from error
        if not isinstance(root, CompoundTag):
            raise ValueError("SNBT root must be a compound")
        return root
    return read_root(data, max_nbt_bytes=max_nbt_bytes, little_endian=little_endian)


def write_root(root: CompoundTag, path: PathInput, compressed: bool = True, *, name: str = "",
               little_endian: bool = False) -> None:
    """Atomically write NBT, with reproducible gzip bytes when compressed."""
    if Path(path).suffix.lower() == ".snbt":
        data = (root.to_snbt(indent=2) + "\n").encode("utf-8")
    else:
        options = {"string_encoder": utf8_escape_encoder} if little_endian else {}
        data = NamedTag(root, name).save_to(compressed=False, little_endian=little_endian, **options)
    if compressed and Path(path).suffix.lower() != ".snbt":
        output = BytesIO()
        with gzip.GzipFile(fileobj=output, mode="wb", compresslevel=6, mtime=0) as stream:
            stream.write(data)
        data = output.getvalue()
    atomic_write(path, data)


def atomic_write(path: PathInput, data: bytes) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        temporary = destination.parent / f".{destination.name}.{uuid4().hex}"
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        if destination.exists():
            temporary.chmod(stat.S_IMODE(destination.stat().st_mode))
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
