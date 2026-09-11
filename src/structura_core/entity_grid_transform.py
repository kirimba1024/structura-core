from copy import deepcopy
from math import atan2, cos, degrees, floor, radians, sin

from amulet_nbt import DoubleTag, FloatTag, IntTag, ListTag, StringTag

from .entity_positions import HANGING_ENTITIES


DIRECTIONS = ("down", "up", "north", "south", "west", "east")
HORIZONTAL = ("south", "west", "north", "east")
ANCHORS = ("TileX", "TileY", "TileZ")


def transform_entity(record, size, transform):
    result = deepcopy(record)
    def point(values):
        return ListTag([DoubleTag(v) for v in transform.point(tuple(float(v) for v in values), size)])
    result["pos"] = point(record["pos"])
    block = transform.point(tuple(int(v) for v in record["blockPos"]), size, cell=True)
    result["blockPos"] = ListTag([IntTag(v) for v in block])
    pending = [result["nbt"]]
    while pending:
        payload = pending.pop()
        pending.extend(payload.get("Passengers", ()))
        if "Pos" in payload:
            payload["Pos"] = point(payload["Pos"])
        if "Motion" in payload:
            payload["Motion"] = ListTag([DoubleTag(v) for v in transform.vector(tuple(float(v) for v in payload["Motion"]))])
        if "Rotation" in payload:
            yaw, pitch = (radians(float(v)) for v in payload["Rotation"])
            vx, vy, vz = transform.vector((-sin(yaw) * cos(pitch), -sin(pitch), cos(yaw) * cos(pitch)))
            rotation = degrees(atan2(-vx, vz)) % 360, degrees(atan2(-vy, (vx * vx + vz * vz) ** 0.5))
            payload["Rotation"] = ListTag([FloatTag(round(v, 7)) for v in rotation])
        if str(payload.get("id", "")) in HANGING_ENTITIES:
            if all(key in payload for key in ANCHORS):
                anchor = transform.point(tuple(int(payload[key]) for key in ANCHORS), size, cell=True)
                payload.update({key: IntTag(v) for key, v in zip(ANCHORS, anchor)})
            for key in ("facing", "Facing", "Direction"):
                if key not in payload:
                    continue
                value = payload[key]
                names = DIRECTIONS if key == "Facing" else HORIZONTAL
                direction = str(value) if isinstance(value, StringTag) else names[int(value) % len(names)]
                direction = transform.direction(direction)
                if direction not in names or str(payload.get("id", "")) == "minecraft:painting" and direction in ("up", "down"):
                    raise ValueError("This hanging entity cannot face the transformed direction")
                payload[key] = StringTag(direction) if isinstance(value, StringTag) else type(value)(names.index(direction))
    if str(result["nbt"].get("id", "")) not in HANGING_ENTITIES:
        result["blockPos"] = ListTag([IntTag(floor(float(v))) for v in result["pos"]])
    return result
