import struct
from pathlib import Path


def read_chunk(directory, cx, cz):
    from amulet.level.formats.anvil_world.region import _decompress

    path = Path(directory) / f"r.{cx // 32}.{cz // 32}.mca"
    if not path.is_file():
        return None
    with path.open("rb") as stream:
        header = 4 * ((cx % 32) + 32 * (cz % 32))
        stream.seek(header)
        value = stream.read(4)
        if len(value) != 4:
            raise ValueError(f"Truncated region header: {path.name}")
        location = int.from_bytes(value, "big")
        if not location:
            return None
        sector, count = location >> 8, location & 255
        if sector < 2 or count == 0:
            raise ValueError(f"Invalid chunk location: {cx}, {cz}")
        stream.seek(sector * 4096)
        size = stream.read(4)
        if len(size) != 4:
            raise ValueError(f"Missing chunk data: {cx}, {cz}")
        length = struct.unpack(">I", size)[0]
        if not 1 <= length <= count * 4096 - 4:
            raise ValueError(f"Invalid chunk length: {cx}, {cz}")
        payload = stream.read(length)
        if len(payload) != length:
            raise ValueError(f"Truncated chunk: {cx}, {cz}")
        stream.seek(header)
        if stream.read(4) != value:
            raise ValueError("World changed during reading; refresh again")
    if payload[0] & 128:
        external = Path(directory) / f"c.{cx}.{cz}.mcc"
        with external.open("rb") as stream:
            data = stream.read(64 * 1024 * 1024 + 1)
        if len(data) > 64 * 1024 * 1024:
            raise ValueError("External chunk exceeds the read budget")
        payload = bytes([payload[0] & 127]) + data
    return _decompress(payload).compound
