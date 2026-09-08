import re
from collections.abc import Mapping
from copy import deepcopy

from amulet_nbt import CompoundTag, StringTag

AIR_NAMES = frozenset({"minecraft:air", "minecraft:cave_air", "minecraft:void_air"})

_RESOURCE_LOCATION = re.compile(r"[a-z0-9_.-]+:[a-z0-9_./-]+\Z")


def state_key(entry: Mapping) -> str:
    """Return a stable ``namespace:block[prop=value,...]`` palette key."""
    name = str(entry["Name"])
    properties = entry.get("Properties")
    if not properties:
        return name
    values = ",".join(f"{key}={value}" for key, value in sorted(properties.items()))
    return f"{name}[{values}]"


def parse_state(value: str) -> CompoundTag:
    """Parse the compact state syntax accepted by generation helpers."""
    if not isinstance(value, str):
        raise ValueError(f"block state must be a string, got {value!r}")
    name, properties = value, None
    if "[" in value:
        if not value.endswith("]"):
            raise ValueError(f"invalid block state: {value!r}")
        name, raw = value[:-1].split("[", 1)
        parsed = {}
        for pair in raw.split(","):
            if not pair or "=" not in pair:
                raise ValueError(f"invalid block state property: {value!r}")
            key, item = pair.split("=", 1)
            if (not key or not item or key in parsed
                    or any(c in key + item for c in "[]=, \t\r\n")):
                raise ValueError(f"invalid block state property: {value!r}")
            parsed[key] = StringTag(item)
        properties = CompoundTag(parsed)
    if not _RESOURCE_LOCATION.fullmatch(name):
        raise ValueError(f"block state needs a valid namespace and name: {value!r}")
    entry = CompoundTag({"Name": StringTag(name)})
    if properties:
        entry["Properties"] = properties
    return entry


def validate_palette(palette, label):
    for entry in palette:
        if not isinstance(entry, CompoundTag) or not isinstance(entry.get("Name"), StringTag):
            raise ValueError(f"invalid palette entry in {label}")
        properties = entry.get("Properties")
        if properties is not None and (not isinstance(properties, CompoundTag)
                or any(not isinstance(v, StringTag) for v in properties.values())):
            raise ValueError(f"invalid palette properties in {label}")
        parse_state(state_key(entry))


FAMILIES = {
    "stairs": {"facing", "half", "shape", "waterlogged"},
    "slab": {"type", "waterlogged"},
    "trapdoor": {"facing", "half", "open", "powered", "waterlogged"},
    "door": {"facing", "half", "hinge", "open", "powered"},
    "fence_gate": {"facing", "in_wall", "open", "powered"},
    "fence": {"north", "east", "south", "west", "waterlogged"},
    "wall": {"north", "east", "south", "west", "up", "waterlogged"},
    "log": {"axis"}, "wood": {"axis"}, "stem": {"axis"}, "hyphae": {"axis"},
    "leaves": {"distance", "persistent", "waterlogged"},
    "button": {"face", "facing", "powered"},
}


def _family(name):
    return next((family for family in FAMILIES if name.endswith("_" + family)), None)


def replace_material(source, target):
    old, new = parse_state(source), parse_state(target)
    old_name, new_name = str(old["Name"]), str(new["Name"])
    props = old.get("Properties", {})
    if old_name == new_name:
        retained = deepcopy(dict(props))
    else:
        family = _family(old_name)
        allowed = FAMILIES[family] if (family and family == _family(new_name)
                  and old_name.startswith("minecraft:") and new_name.startswith("minecraft:")) else set()
        retained = {key: deepcopy(value) for key, value in props.items() if key in allowed}
    retained.update(new.get("Properties", {}))
    if retained:
        new["Properties"] = CompoundTag(retained)
    return state_key(new)

