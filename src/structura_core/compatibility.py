from dataclasses import dataclass

from .version import DATA_VERSION


MIN_WORLD_WRITE_VERSION = 2844
MAX_WORLD_WRITE_VERSION = DATA_VERSION


def world_write_reason(data_version):
    if data_version < MIN_WORLD_WRITE_VERSION:
        return "World writing requires Java 1.18 or newer"
    if data_version > MAX_WORLD_WRITE_VERSION:
        return f"World DataVersion {data_version} is view-only; writing is supported through {MAX_WORLD_WRITE_VERSION}"
    return ""


def transfer_reason(source_version, target_version):
    if source_version <= 0 or target_version <= 0:
        return "Cannot paste without known source and destination DataVersion values"
    if source_version != target_version:
        return (f"Cannot paste DataVersion {source_version} into {target_version}. "
                "Use a verified version conversion before importing this copy.")
    return ""


@dataclass(frozen=True)
class SourceCapabilities:
    format: str
    data_version: int
    read_blocks: bool
    read_entities: bool
    edit: bool
    export_selection: bool
    save: bool
    reason: str = ""


def source_capabilities(format, data_version, *, schema=None):
    if format == "world":
        reason = world_write_reason(data_version)
    elif format == ".schem" and schema == 1:
        reason = "Sponge v1 is view-only; export selection to NBT before editing"
    elif format in (".litematic", ".mcstructure"):
        reason = "This format is view-only; export selection to NBT before editing"
    elif format not in (".nbt", ".snbt", ".schem", ".schematic"):
        return SourceCapabilities(format, data_version, False, False, False, False, False, "Unsupported source format")
    else:
        reason = ""
    return SourceCapabilities(format, data_version, True, True, not reason, True, not reason, reason)
