import json
import re

from amulet_nbt import ByteTag, CompoundTag, DoubleTag, IntTag, ListTag, StringTag

LEGACY_ENTITIES = {
    "painting": "minecraft:painting",
    "itemframe": "minecraft:item_frame",
    "glowitemframe": "minecraft:glow_item_frame",
}

LEGACY_ENTITY_ALIASES = {
    **LEGACY_ENTITIES,
    "areaeffectcloud": "minecraft:area_effect_cloud",
    "armorstand": "minecraft:armor_stand",
    "arrow": "minecraft:arrow",
    "blaze": "minecraft:blaze",
    "boat": "minecraft:boat",
    "item": "minecraft:item",
    "xporb": "minecraft:experience_orb",
    "egg": "minecraft:egg",
    "leashknot": "minecraft:leash_knot",
    "snowball": "minecraft:snowball",
    "fireball": "minecraft:fireball",
    "smallfireball": "minecraft:small_fireball",
    "enderpearl": "minecraft:ender_pearl",
    "eyeofendersignal": "minecraft:eye_of_ender",
    "potion": "minecraft:potion",
    "thrownpotion": "minecraft:potion",
    "xpbottle": "minecraft:experience_bottle",
    "witherskull": "minecraft:wither_skull",
    "tntprimed": "minecraft:tnt",
    "fallingsand": "minecraft:falling_block",
    "fireworksrocketentity": "minecraft:firework_rocket",
    "spectralarrow": "minecraft:spectral_arrow",
    "shulkerbullet": "minecraft:shulker_bullet",
    "dragonfireball": "minecraft:dragon_fireball",
    "endercrystal": "minecraft:end_crystal",
    "fishhook": "minecraft:fishing_bobber",
    "chicken": "minecraft:chicken",
    "sheep": "minecraft:sheep",
    "pig": "minecraft:pig",
    "cow": "minecraft:cow",
    "villager": "minecraft:villager",
    "bat": "minecraft:bat",
    "creeper": "minecraft:creeper",
    "skeleton": "minecraft:skeleton",
    "zombie": "minecraft:zombie",
    "rabbit": "minecraft:rabbit",
    "wolf": "minecraft:wolf",
    "spider": "minecraft:spider",
    "cavespider": "minecraft:cave_spider",
    "squid": "minecraft:squid",
    "slime": "minecraft:slime",
    "lavaslime": "minecraft:magma_cube",
    "silverfish": "minecraft:silverfish",
    "enderman": "minecraft:enderman",
    "endermite": "minecraft:endermite",
    "guardian": "minecraft:guardian",
    "elderguardian": "minecraft:elder_guardian",
    "ghast": "minecraft:ghast",
    "shulker": "minecraft:shulker",
    "giant": "minecraft:giant",
    "witch": "minecraft:witch",
    "witherboss": "minecraft:wither",
    "enderdragon": "minecraft:ender_dragon",
    "pigzombie": "minecraft:zombified_piglin",
    "husk": "minecraft:husk",
    "stray": "minecraft:stray",
    "witherskeleton": "minecraft:wither_skeleton",
    "zombievillager": "minecraft:zombie_villager",
    "skeletonhorse": "minecraft:skeleton_horse",
    "zombiehorse": "minecraft:zombie_horse",
    "evocationfangs": "minecraft:evoker_fangs",
    "evocationillager": "minecraft:evoker",
    "vindicationillager": "minecraft:vindicator",
    "illusionillager": "minecraft:illusioner",
    "vex": "minecraft:vex",
    "mushroomcow": "minecraft:mooshroom",
    "snowman": "minecraft:snow_golem",
    "polarbear": "minecraft:polar_bear",
    "llama": "minecraft:llama",
    "llamaspit": "minecraft:llama_spit",
    "parrot": "minecraft:parrot",
    "ozelot": "minecraft:ocelot",
    "entityhorse": "minecraft:horse",
    "villagergolem": "minecraft:iron_golem",
    "minecartrideable": "minecraft:minecart",
    "minecartchest": "minecraft:chest_minecart",
    "minecartfurnace": "minecraft:furnace_minecart",
    "minecarttnt": "minecraft:tnt_minecart",
    "minecarthopper": "minecraft:hopper_minecart",
    "minecartspawner": "minecraft:spawner_minecart",
    "minecartcommandblock": "minecraft:command_block_minecart",
}


def _legacy_tile_text(root):
    """Sign text keyed by the schematic's own coordinates.

    Amulet translates a legacy sign into the modern shape -- front_text,
    back_text, is_waxed -- and leaves its messages empty, so the container
    arrives and the words do not. The original Text1..Text4 are still in the
    file, so they are read from it directly rather than reconstructed.
    """
    found = {}
    root = _schematic_root(root)
    blocks = root.get("Blocks") if isinstance(root.get("Blocks"), CompoundTag) else root
    entries = root.get("TileEntities") or blocks.get("BlockEntities") or []
    for entry in entries:
        lines = [str(entry.get(f"Text{i}", "")) for i in range(1, 5)]
        if not any(line.strip() for line in lines):
            continue
        try:
            pos = tuple(int(str(entry[axis])) for axis in ("x", "y", "z"))
        except KeyError:
            continue
        found[pos] = lines
    return found


def _schematic_root(root):
    """Return the payload compound used by classic and Sponge schematics."""
    nested = root.get("Schematic")
    return nested if isinstance(nested, CompoundTag) else root


def _entity_data(entry):
    """Merge Sponge's outer placement record with its Data/Extra payload."""
    merged = CompoundTag(
        {key: value for key, value in entry.items() if key not in ("Data", "Extra")}
    )
    for key in ("Data", "Extra"):
        extra = entry.get(key)
        if isinstance(extra, CompoundTag):
            merged.update(extra)
    return merged


def _structure_entity(position, payload):
    exact = payload.get("exact", False)
    pos = tuple(float(value) for value in position)
    placed = pos if exact else tuple(value + 0.5 for value in pos)
    nbt = CompoundTag(dict(payload.get("nbt", {}).items()))
    nbt["id"] = StringTag(payload["id"])
    nbt["Pos"] = ListTag([DoubleTag(value) for value in placed])
    if "facing" in payload:
        nbt["Facing"] = ByteTag(payload["facing"])
    if "variant" in payload:
        nbt["variant"] = StringTag(payload["variant"])
    if not exact:
        for axis, value in zip(("TileX", "TileY", "TileZ"), pos):
            nbt[axis] = IntTag(int(value))
    return CompoundTag(
        {
            "pos": ListTag([DoubleTag(value) for value in placed]),
            "blockPos": ListTag([IntTag(int(value // 1)) for value in pos]),
            "nbt": nbt,
        }
    )


def _legacy_entities(root, preserve_all=False):
    """Entities selected for conversion, with exact positions for non-hangers.

    World generation keeps its conservative decorations-only default. Render
    conversion opts into every entity so a preview can show what the source
    actually contains without changing the datapack policy.
    """
    found = []
    root = _schematic_root(root)
    for entry in root.get("Entities") or []:
        data = _entity_data(entry)
        identifier = str(data.get("id") or data.get("Id") or "")
        namespace, separator, legacy = identifier.partition(":")
        if not separator:
            legacy, namespace = namespace, ""
        key = legacy.replace("_", "").lower()
        kind = (LEGACY_ENTITY_ALIASES if preserve_all else LEGACY_ENTITIES).get(key)
        custom = bool(namespace and namespace != "minecraft")
        if custom:
            kind = identifier if preserve_all else None
        if kind is None and preserve_all and legacy:
            snake = re.sub(r"(?<!^)(?=[A-Z])", "_", legacy).replace(".", "_").lower()
            kind = f"minecraft:{snake}"
        if kind is None:
            continue
        hanging = not custom and key in LEGACY_ENTITIES
        if hanging:
            try:
                pos = tuple(
                    int(str(data[axis])) for axis in ("TileX", "TileY", "TileZ")
                )
            except KeyError:
                try:
                    pos = tuple(float(str(value)) for value in entry["Pos"])
                except (KeyError, TypeError, ValueError):
                    continue
        else:
            try:
                pos = tuple(float(str(value)) for value in entry["Pos"])
            except (KeyError, TypeError, ValueError):
                try:
                    pos = tuple(float(str(value)) for value in data["Pos"])
                except (KeyError, TypeError, ValueError):
                    continue
        payload = {"id": kind, "exact": not hanging}
        if preserve_all:
            payload["nbt"] = data
        if "Facing" in data:
            payload["facing"] = int(str(data["Facing"])) % 6
        elif "Direction" in data:
            old_facing = int(str(data["Direction"])) % 4
            payload["facing"] = (3, 4, 2, 5)[old_facing]
        if "Motive" in data:
            name = str(data["Motive"]).split(":")[-1]
            payload["variant"] = (
                "minecraft:" + re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
            )
        found.append((pos, payload))
    return found


def _text_component(message):
    try:
        component = json.loads(message)
    except ValueError:
        return {"text": message}
    return component if isinstance(component, (str, dict, list)) else {"text": message}


def _has_text(component):
    if isinstance(component, str):
        return bool(component.strip())
    if isinstance(component, list):
        return any(_has_text(item) for item in component)
    if isinstance(component, dict):
        return (
            _has_text(component.get("text", ""))
            or _has_text(component.get("extra", []))
            or any(key in component for key in ("translate", "selector", "score", "keybind", "nbt"))
        )
    return bool(component)


def restore_sign_text(blocks, legacy_text, origin):
    ox, oy, oz = origin
    shifted_text = {
        (x - ox, y - oy, z - oz): lines
        for (x, y, z), lines in legacy_text.items()
    }
    restored = 0
    for pos, _idx, entry_nbt in blocks:
        lines = shifted_text.get(pos)
        if lines is None or entry_nbt is None or "front_text" not in entry_nbt:
            continue
        front = entry_nbt["front_text"]
        existing = [str(m) for m in front.get("messages", [])]
        if any(_has_text(_text_component(message)) for message in existing):
            continue
        front["messages"] = ListTag([StringTag(json.dumps(_text_component(line))) for line in lines])
        restored += 1
    return restored
