from amulet_nbt import CompoundTag, StringTag

from .blockstates import parse_state, state_key


COMPASS = ("north", "east", "south", "west")
SPATIAL = {"facing", "axis", "rotation", "shape", "hinge", "type", "orientation", "half", "face", "attachment", *COMPASS, "up", "down"}


def transform_state(state, transform, *, defaults=None, allowed=None):
    raw = parse_state(state)
    name = str(raw["Name"])
    original = {key: str(value) for key, value in raw.get("Properties", {}).items()}
    defaults = defaults or {}
    horizontal = transform.horizontal()
    if horizontal is None:
        if transform.direction('up') == 'down':
            return _upside_down_state(state, transform, defaults, allowed or {})
        return _vertical_state(raw, transform, defaults, allowed or {})
    turns, flip = horizontal
    directions = {name: transform.direction(name) for name in COMPASS}
    props = {key: str(value) for key, value in defaults.items() if key in SPATIAL}
    props.update(original)
    mapped = {}
    for key, value in props.items():
        if key == "facing":
            value = directions.get(value, value)
        elif key == "axis" and turns % 2:
            value = {"x": "z", "z": "x"}.get(value, value)
        elif key == "rotation":
            angle = int(value)
            if not 0 <= angle < 16:
                raise ValueError(f"Unsupported block rotation: {name}")
            angle = -angle if flip == "x" else 8 - angle if flip == "z" else angle
            value = str((angle + turns * 4) % 16)
        elif key == "orientation":
            value = "_".join(directions.get(part, part) for part in value.split("_"))
        elif key == "shape":
            parts = value.split("_")
            if len(parts) == 2 and parts[1] in COMPASS:
                parts = [directions.get(part, part) for part in parts]
                if parts[0] != "ascending":
                    parts.sort(key=("north", "south", "east", "west").index)
                value = "_".join(parts)
            elif flip and value in ("inner_left", "inner_right", "outer_left", "outer_right"):
                stem, side = value.rsplit("_", 1)
                value = stem + "_" + ("right" if side == "left" else "left")
        elif flip and key in ("hinge", "type"):
            value = {"left": "right", "right": "left"}.get(value, value)
        target = directions.get(key, key)
        if key in original or value != str(defaults.get(target, "")):
            mapped[target] = StringTag(value)
    raw.pop("Properties", None)
    if mapped:
        raw["Properties"] = CompoundTag(mapped)
    return state_key(raw)


def _upside_down_state(state, transform, defaults, allowed):
    from .grid_transform import GridTransform

    horizontal = GridTransform.operation(flip='y').compose(transform)
    raw = parse_state(transform_state(state, horizontal, defaults=defaults, allowed=allowed))
    original = {key: str(value) for key, value in raw.get('Properties', {}).items()}
    props = {key: str(value) for key, value in defaults.items() if key in SPATIAL}
    props.update(original)
    horizontal_only = ('facing' in props and not {'up', 'down'} <= set(map(str, allowed.get('facing', ())))
                       and not {'half', 'face', 'attachment'} & props.keys())
    if horizontal_only or 'rotation' in props or props.get('half') in ('upper', 'lower') or 'shape' in props and props['shape'] not in ('straight', 'inner_left', 'inner_right', 'outer_left', 'outer_right'):
        raise ValueError(f"Cannot mirror vertically: {raw['Name']}. Minecraft has no supported upside-down orientation.")
    swaps = {'up': 'down', 'down': 'up', 'top': 'bottom', 'bottom': 'top', 'floor': 'ceiling', 'ceiling': 'floor'}
    mapped = {}
    for key, value in props.items():
        target = swaps.get(key, key)
        if key in ('half', 'type', 'facing', 'face', 'attachment'):
            value = swaps.get(value, value)
        elif key == 'orientation':
            value = '_'.join(swaps.get(part, part) for part in value.split('_'))
        if key in SPATIAL and (target not in allowed or value not in set(map(str, allowed[target]))):
            raise ValueError(f"Cannot represent transformed {raw['Name']}: {target}={value}")
        if key in original or value != str(defaults.get(target, '')):
            mapped[target] = StringTag(value)
    raw.pop('Properties', None)
    if mapped:
        raw['Properties'] = CompoundTag(mapped)
    return state_key(raw)


def _vertical_state(raw, transform, defaults, allowed):
    name = str(raw["Name"])
    original = {key: str(value) for key, value in raw.get("Properties", {}).items()}
    props = {key: str(value) for key, value in defaults.items() if key in SPATIAL}
    props.update(original)
    spatial = props.keys() & SPATIAL
    supported = {"axis", "facing", "orientation", "up", "down", *COMPASS}
    if spatial - supported or "facing" in spatial and not {"up", "down"} <= set(map(str, allowed.get("facing", ()))):
        raise ValueError(f"Cannot tilt or mirror vertically: {name}. Minecraft has no supported orientation for this block.")
    mapped = {}
    for key, value in props.items():
        target = transform.direction(key) if key in ("up", "down", *COMPASS) else key
        if key == "axis":
            vector = transform.vector(tuple(int(axis == value) for axis in "xyz"))
            value = "xyz"[next(i for i, component in enumerate(vector) if component)]
        elif key == "facing":
            value = transform.direction(value)
        elif key == "orientation":
            value = "_".join(transform.direction(part) for part in value.split("_"))
        if key in spatial and (target not in allowed or value not in set(map(str, allowed[target]))):
            raise ValueError(f"Cannot represent transformed {name}: {target}={value}")
        if key in original or value != str(defaults.get(target, "")):
            mapped[target] = StringTag(value)
    raw.pop("Properties", None)
    if mapped:
        raw["Properties"] = CompoundTag(mapped)
    return state_key(raw)
