"""Compatibility imports for structures and NBT serialization."""

from .nbt_io import (
    PathInput as PathInput,
    _bounded_read as _bounded_read,
    _check_byte_limit as _check_byte_limit,
    _check_snbt_end as _check_snbt_end,
    atomic_write as atomic_write,
    load_root as load_root,
    read_root as read_root,
    write_root as write_root,
)
from .structure import (
    _RESOURCE_LOCATION as _RESOURCE_LOCATION,
    AIR_NAMES as AIR_NAMES,
    Position as Position,
    State as State,
    Structure as Structure,
    _integer as _integer,
    _validate_palette as _validate_palette,
    _vector as _vector,
    parse_state as parse_state,
    state_key as state_key,
)
from .structure_writer import (
    save_structure as save_structure,
)
