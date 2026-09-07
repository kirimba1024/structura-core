"""One optional translation boundary, with operation-local caches and diagnostics."""

import warnings
from collections import Counter
from copy import deepcopy

from amulet_nbt import CompoundTag, IntTag, ListTag, NamedTag, StringTag

from .conversion_losses import ConversionWarning, _fields
from .nbt import Structure, _integer, _vector, parse_state
from .schematic import _list


class _Bridge:
    def __init__(self, platform, target_version):
        try:
            import PyMCTranslate
            from amulet.api.block import Block
            from amulet.api.block_entity import BlockEntity
        except ImportError as error:
            raise ModuleNotFoundError("Bedrock translation needs: pip install 'structura-core[bedrock]'", name="amulet") from error
        self.Block, self.BlockEntity = Block, BlockEntity
        self.manager = PyMCTranslate.new_translation_manager()
        version = _vector(target_version, "target_version")
        if version not in self.manager.version_numbers(platform):
            raise ValueError(f"translator has no exact {platform} schema {version}; choose a supported target_version")
        self.target = self.manager.get_version(platform, version)
        self.losses = Counter()
        self.versions = {}
        self.specs = {}
        self.cache = {}
        self.get_raw = None

    def version(self, platform, data_version):
        key = platform, data_version
        if key not in self.versions:
            data_version = _integer(data_version, f"{platform} block version")
            versions = [self.manager.get_version(platform, value) for value in self.manager.version_numbers(platform)]
            candidates = [value for value in versions if value.data_version <= data_version]
            if not candidates or data_version > max(value.data_version for value in versions):
                raise ValueError(f"translator does not cover {platform} DataVersion {data_version}")
            self.versions[key] = max(candidates, key=lambda value: value.data_version)
        return self.versions[key]

    def block(self, name, properties):
        namespace, base = name.split(":", 1)
        return self.Block(namespace, base, dict(properties))

    def specification(self, version, block):
        key = version.platform, version.version_number, block
        if key not in self.specs:
            try:
                spec = version.block.get_specification(block.namespace, block.base_name, force_blockstate=True)
            except KeyError as error:
                raise ValueError(f"no {version.platform} translation for {block.namespaced_name}") from error
            for name, value in block.properties.items():
                if name == "waterlogged" and version.platform == "java" and version.block.is_waterloggable(block.namespaced_name):
                    allowed = (StringTag("true"), StringTag("false"))
                else:
                    allowed = spec.valid_properties.get(name, ())
                if value not in allowed:
                    raise ValueError(f"unsupported {version.platform} block property {block.namespaced_name}[{name}={value}]")
            self.specs[key] = spec
        return self.specs[key]

    def entity(self, version, block, payload, position):
        if payload is None:
            return None
        spec = self.specification(version, block)
        if not spec.nbt_identifier:
            raise ValueError(f"block NBT has no translation for {block.namespaced_name}")
        return self.BlockEntity(*spec.nbt_identifier, *position, NamedTag(deepcopy(payload)))

    def unpack(self, version, block):
        self.specification(version, block)
        if version.platform == "java":
            if version.block.is_waterloggable(block.namespaced_name):
                properties = block.properties
                wet = properties.pop("waterlogged", StringTag("false")) == StringTag("true")
                block = self.block(block.namespaced_name, properties)
            else:
                wet = version.block.is_waterloggable(block.namespaced_name, True)
            if wet:
                return (block, self.Block.from_string_blockstate("minecraft:water[level=0]"))
        return (block,)

    def universal(self, position):
        layers, payload = self.get_raw(position)
        if not layers:
            self.losses["missing neighbouring cells interpreted as air"] += 1
            return self.Block("universal_minecraft", "air"), None
        cache_key = tuple((v.platform, v.version_number, block) for v, block in layers)
        if payload is None and cache_key in self.cache:
            return self.cache[cache_key], None
        result, entity, cacheable = [], None, payload is None
        for layer, (version, raw) in enumerate(layers):
            for sublayer, block in enumerate(self.unpack(version, raw)):
                nbt = self.entity(version, raw, payload, position) if layer == sublayer == 0 else None
                translated, translated_nbt, needed = version.block.to_universal(
                    block, nbt, force_blockstate=True, block_location=position)
                if needed:
                    cacheable = False

                    def neighbour(offset):
                        other = tuple(a + b for a, b in zip(position, offset))
                        entries, tag = self.get_raw(other)
                        if not entries:
                            self.losses["missing neighbouring cells interpreted as air"] += 1
                            return self.Block("minecraft", "air"), None
                        neighbour_version, neighbour_block = entries[0]
                        if neighbour_version.version_number != version.version_number:
                            raise ValueError("neighbour-dependent translation across mixed Bedrock schemas is unsupported")
                        return neighbour_block, self.entity(neighbour_version, neighbour_block, tag, other)

                    translated, translated_nbt, needed = version.block.to_universal(
                        block, nbt, force_blockstate=True, block_location=position, get_block_callback=neighbour)
                if needed:
                    self.losses["block translations still need unavailable context"] += 1
                if not isinstance(translated, self.Block) or translated.namespace != "universal_minecraft":
                    raise ValueError(f"block cannot be translated safely: {raw}")
                result.append(translated)
                if layer == sublayer == 0:
                    entity = translated_nbt
        joined = self.Block.join(result)
        if cacheable and entity is None:
            self.cache[cache_key] = joined
        return joined, entity

    def convert(self, position):
        universal, entity = self.universal(position)
        output, block_entity = [], None
        for index, layer in enumerate(universal.block_tuple):
            block, nbt, needed = self.target.block.from_universal(
                layer, entity if index == 0 else None, force_blockstate=True, block_location=position,
                get_block_callback=lambda offset: self.universal(tuple(a + b for a, b in zip(position, offset))))
            if not isinstance(block, self.Block) or block.namespace != "minecraft":
                raise ValueError(f"target cannot represent block {layer}; conversion to entities is unsupported")
            if needed:
                self.losses["target block translations need unavailable context"] += 1
            output.extend(block.block_tuple)
            if index == 0:
                block_entity = nbt
            restored, _, _ = self.target.block.to_universal(block, nbt, force_blockstate=True)
            if restored != layer:
                self.losses["block states do not survive a translation round trip"] += 1
        if self.target.platform == "java":
            first, extra = output[0], output[1:]
            properties = first.properties
            wet = bool(extra and extra[0].namespaced_name in {"minecraft:water", "minecraft:flowing_water"})
            if self.target.block.is_waterloggable(first.namespaced_name):
                properties["waterlogged"] = StringTag("true" if wet else "false")
                extra = extra[1:] if wet else extra
            elif wet and self.target.block.is_waterloggable(first.namespaced_name, True):
                extra = extra[1:]
            if extra:
                self.losses["secondary block layers omitted in Java"] += 1
            output = [self.block(first.namespaced_name, properties)]
        if len(output) > 2:
            raise ValueError("Bedrock supports at most two block layers")
        return output, block_entity

    def report(self, strict):
        if not self.losses:
            return
        message = "Bedrock conversion: " + "; ".join(f"{key} ({count})" for key, count in sorted(self.losses.items()))
        if strict:
            raise ValueError(message)
        warnings.warn(message, ConversionWarning, stacklevel=3)


def import_bedrock(document, target_version, strict):
    bridge = _Bridge("java", target_version)
    palette = {}
    used = {int(index) for layer in document.layers for index in layer if int(index) >= 0}
    for index in sorted(used):
        entry = document.states[index]
        if "version" not in entry or "states" not in entry:
            raise ValueError("translation requires versioned Bedrock block states (1.13 or newer)")
        palette[index] = (bridge.version("bedrock", int(entry["version"])),
                          bridge.block(str(entry["name"]), entry["states"]))

    def get_raw(position):
        x, y, z = (a - b for a, b in zip(position, document.origin))
        sx, sy, sz = document.size
        if not (0 <= x < sx and 0 <= y < sy and 0 <= z < sz):
            return [], None
        index = (x * sy + y) * sz + z
        layers = [palette[int(layer[index])] for layer in document.layers if int(layer[index]) >= 0]
        payload = document.position_data.get(str(index), {}).get("block_entity_data")
        return layers, payload

    bridge.get_raw = get_raw
    root = CompoundTag({"DataVersion": IntTag(bridge.target.data_version), "size": _list(document.size),
                        "palette": ListTag(), "blocks": ListTag(), "entities": ListTag()})
    states = {}
    sx, sy, sz = document.size
    for index in range(sx * sy * sz):
        if all(int(layer[index]) == -1 for layer in document.layers):
            continue
        x, remainder = divmod(index, sy * sz)
        y, z = divmod(remainder, sz)
        local = x, y, z
        position = tuple(a + b for a, b in zip(local, document.origin))
        blocks, entity = bridge.convert(position)
        state = blocks[0].blockstate
        if state not in states:
            states[state] = len(states)
            root["palette"].append(parse_state(state))
        record = CompoundTag({"pos": _list(local), "state": IntTag(states[state])})
        if entity is not None:
            record["nbt"] = deepcopy(entity.nbt.compound)
            record["nbt"]["id"] = StringTag(entity.namespaced_name)
            record["nbt"].update({axis: IntTag(value) for axis, value in zip("xyz", local)})
        root["blocks"].append(record)
    if document.entities:
        bridge.losses["ordinary entities omitted; translator has no entity database"] = len(document.entities)
    count = sum("block_entity_data" in value for value in document.position_data.values())
    if count:
        bridge.losses["block entity payloads translated; arbitrary NBT fidelity is not guaranteed"] = count
    if (_fields(document.root, ("format_version", "size", "structure_world_origin", "structure")) or
            _fields(document.structure, ("block_indices", "entities", "palette")) or
            _fields(document.structure["palette"], ("default",)) or
            _fields(document.palette, ("block_palette", "block_position_data")) or
            any(_fields(value, ("block_entity_data",)) for value in document.position_data.values()) or
            any(_fields(value, ("name", "states", "version")) for value in document.states)):
        bridge.losses["additional native Bedrock fields omitted"] = 1
    bridge.report(strict)
    result = Structure.from_root(root)
    result.source_origin = document.origin
    return result


def export_bedrock(src, target_version, strict):
    bridge = _Bridge("bedrock", target_version)
    version = bridge.version("java", src.data_version)
    palette = [bridge.block(str(entry["Name"]), entry.get("Properties", {})) for entry in src.palette_raw]

    def get_raw(position):
        index = src.present.get(position)
        if index is None:
            return [], None
        return [(version, palette[index])], src.block_nbt.get(position)

    bridge.get_raw = get_raw
    volume = src.size[0] * src.size[1] * src.size[2]
    layers = [[-1] * volume for _ in range(2)]
    states, entries, position_data = {}, ListTag(), CompoundTag()
    for position, index in src.present.items():
        if src.palette[index] == "minecraft:structure_void":
            continue
        blocks, entity = bridge.convert(position)
        x, y, z = position
        offset = (x * src.size[1] + y) * src.size[2] + z
        for layer, block in enumerate(blocks):
            if block not in states:
                states[block] = len(states)
                entries.append(CompoundTag({"name": StringTag(block.namespaced_name),
                                            "states": CompoundTag(block.properties),
                                            "version": IntTag(bridge.target.data_version)}))
            layers[layer][offset] = states[block]
        if entity is not None:
            payload = deepcopy(entity.nbt.compound)
            payload["id"] = StringTag(entity.base_name)
            payload.update({axis: IntTag(value) for axis, value in zip("xyz", position)})
            position_data[str(offset)] = CompoundTag({"block_entity_data": payload})
    if src.entities:
        bridge.losses["ordinary entities omitted; translator has no entity database"] = len(src.entities)
    if src.block_nbt:
        bridge.losses["block entity payloads translated; arbitrary NBT fidelity is not guaranteed"] = len(src.block_nbt)
    bridge.report(strict)
    return CompoundTag({"format_version": IntTag(1), "size": _list(src.size), "structure_world_origin": _list((0, 0, 0)),
                        "structure": CompoundTag({"block_indices": ListTag([_list(layer) for layer in layers]),
                                                  "entities": ListTag(), "palette": CompoundTag({"default": CompoundTag({
                                                      "block_palette": entries, "block_position_data": position_data})})})})
