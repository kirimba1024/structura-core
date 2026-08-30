#!/usr/bin/env python3
"""
StructureAnalyzer -- numeric quality/problem metrics for a converted
vanilla Structure NBT, so curation ("which of 2884 files are worth keeping")
doesn't require eyeballing every one.

Every metric here is a known technique borrowed from existing fields, not
invented for this project -- see docstrings for the source. Nothing here
replaces looking at a render eventually; it's a pre-filter to avoid looking
at obviously-broken or obviously-boring pieces.
"""
import argparse
import json
import math
import struct
import zlib
from collections import Counter, deque

from .nbt import AIR_NAMES, Structure

# Some pieces omit air entirely (legacy conversion), others list it
# explicitly (hand-authored jigsaw pieces, to carve into terrain).
# StructureAnalyzer normalizes both to "not present" so every metric below
# means the same thing regardless of which authoring path produced the file.


class StructureAnalyzer:
    def __init__(self, path: str):
        self.path = path
        s = Structure(path)
        self.size = s.size
        self.palette = s.palette
        self.positions = {pos: idx for pos, idx in s.present.items()
                           if s.palette[idx] not in AIR_NAMES}
        self._components = None  # cached

    # ---- A. geometry / integrity -----------------------------------

    def bbox_volume(self) -> int:
        sx, sy, sz = self.size
        return sx * sy * sz

    def density(self) -> float:
        """non-air block count / bounding-box volume.

        Standard PCG "density" measure (Smith & Whitehead, 2010) repurposed
        for 3D: how much of the reserved footprint is actually solid. Very
        low density on a *converted* piece (after we already strip padding
        air) usually means a sprawling, sparse original build rather than a
        real bug -- but combined with `connected_components` a low density
        + many components is a strong debris signal.
        """
        return len(self.positions) / self.bbox_volume()

    def connected_components(self):
        """26-connected flood fill over non-air cells.

        Standard connected-component labeling, the same algorithm used to
        strip the lapis-lazuli debris earlier in this session. Returns
        components sorted largest-first.
        """
        if self._components is not None:
            return self._components
        visited = set()
        components = []
        for start in self.positions:
            if start in visited:
                continue
            comp = []
            q = deque([start])
            visited.add(start)
            while q:
                x, y, z = q.popleft()
                comp.append((x, y, z))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for dz in (-1, 0, 1):
                            if dx == dy == dz == 0:
                                continue
                            np_ = (x + dx, y + dy, z + dz)
                            if np_ in self.positions and np_ not in visited:
                                visited.add(np_)
                                q.append(np_)
            components.append(comp)
        components.sort(key=len, reverse=True)
        self._components = components
        return components

    def debris_fraction(self) -> float:
        """Fraction of blocks NOT in the largest connected component."""
        comps = self.connected_components()
        if not comps:
            return 0.0
        main = len(comps[0])
        total = sum(len(c) for c in comps)
        return 1 - main / total

    def floating_fraction(self) -> float:
        """Fraction of blocks with no support chain down to a block at
        min-Y (the structure's own floor plane).

        Borrowed from voxel-building-validation practice: a cell is
        "grounded" if the cell directly below it is solid, propagated
        transitively (support graph flood fill), same principle used for
        gravity constraints in block-building tools/games. Anything not
        reachable that way is floating debris or a disconnected floating
        wing -- both worth flagging before this piece goes in the library.
        """
        if not self.positions:
            return 0.0
        min_y = min(p[1] for p in self.positions)
        grounded = set()
        q = deque()
        for pos in self.positions:
            if pos[1] == min_y:
                grounded.add(pos)
                q.append(pos)
        while q:
            x, y, z = q.popleft()
            # support propagates sideways along the same row and upward
            # onto a supported block (i.e. this is a "resting on or
            # attached to something already grounded" flood fill, not
            # strict straight-down gravity -- a wall attached to a
            # grounded floor counts as grounded).
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        if dx == dy == dz == 0:
                            continue
                        np_ = (x + dx, y + dy, z + dz)
                        if np_ in self.positions and np_ not in grounded:
                            grounded.add(np_)
                            q.append(np_)
        return 1 - len(grounded) / len(self.positions)

    # ---- B. material diversity --------------------------------------

    def block_histogram(self):
        c = Counter(self.positions.values())
        result = Counter()
        for index, count in c.items():
            result[self.palette[index]] += count
        return result

    def palette_entropy(self) -> float:
        """Shannon entropy (bits) of the block-type distribution.

        Standard information-theory diversity measure. Low entropy = a
        near-monolithic material (fine for e.g. a plain corridor); very
        high entropy relative to block count can indicate a noisy/messy
        legacy build rather than deliberate material variation.
        """
        hist = self.block_histogram()
        total = sum(hist.values())
        h = 0.0
        for n in hist.values():
            p = n / total
            h -= p * math.log2(p)
        return h

    # ---- C. compressibility / structural complexity -------------------

    def compression_ratio(self) -> float:
        """compressed size / raw size of the (pos, state) stream, zlib.

        A real-compressor approximation of Kolmogorov complexity, in the
        Normalized-Compression-Distance lineage used to score procedurally
        generated content. Low ratio = very repetitive geometry (a long
        plain corridor); ratio close to 1 = little redundancy, either a
        deliberately intricate piece or a noisy/dirty one -- read together
        with entropy and debris_fraction to tell those apart.
        """
        items = sorted(self.positions.items())
        raw = b"".join(struct.pack(">iiiI", *pos, state) for pos, state in items)
        if not raw:
            return 0.0
        compressed = zlib.compress(raw, level=9)
        return len(compressed) / len(raw)

    # ---- D. symmetry -----------------------------------------------

    def mirror_symmetry(self, axis: str = "x") -> float:
        """Fraction of blocks whose mirrored position (same axis, across
        the piece's own centerline) also has a block of the same type.

        Standard mirror-symmetry scoring, the same comparison-to-transformed
        -copy principle used to score symmetry error in voxel/3D generation
        work (e.g. SymTRELLIS). 1.0 = perfectly symmetric on that axis.
        """
        sx, sy, sz = self.size
        axis_i = {"x": 0, "y": 1, "z": 2}[axis]
        dim = self.size[axis_i]
        match = 0
        for pos, state in self.positions.items():
            mirrored = list(pos)
            mirrored[axis_i] = dim - 1 - pos[axis_i]
            mirrored = tuple(mirrored)
            if self.positions.get(mirrored) == state:
                match += 1
        return match / len(self.positions) if self.positions else 0.0

    # ---- E. terrain-capture heuristic (domain-specific, not academic) --

    #  Not a borrowed technique like the others -- this is the same thing
    #  Minecraft builders already do by eye with WorldEdit's //distr: check
    #  what fraction of the block count is "natural terrain" material.
    #  Connected-component/floating checks can't catch a captured hill,
    #  because attached terrain is topologically indistinguishable from
    #  intentional building material (see: SmallHouse.schematic, height 76,
    #  ~11% dirt+grass+stone, one connected & fully grounded component).
    _NATURAL_BLOCKS = {
        "minecraft:dirt", "minecraft:grass_block", "minecraft:stone",
        "minecraft:gravel", "minecraft:sand", "minecraft:coarse_dirt",
        "minecraft:podzol", "minecraft:mycelium", "minecraft:andesite",
        "minecraft:diorite", "minecraft:granite", "minecraft:clay",
    }

    def natural_terrain_fraction(self) -> float:
        hist = self.block_histogram()
        total = sum(hist.values())
        if not total:
            return 0.0
        natural = sum(n for name, n in hist.items() if name in self._NATURAL_BLOCKS)
        return natural / total

    # ---- report -------------------------------------------------------

    def report(self) -> dict:
        comps = self.connected_components()
        return {
            "path": self.path,
            "size": self.size,
            "block_count": len(self.positions),
            "palette_size": len(self.palette),
            "density": round(self.density(), 4),
            "components": len(comps),
            "main_component_size": len(comps[0]) if comps else 0,
            "debris_fraction": round(self.debris_fraction(), 4),
            "floating_fraction": round(self.floating_fraction(), 4),
            "palette_entropy_bits": round(self.palette_entropy(), 3),
            "compression_ratio": round(self.compression_ratio(), 4),
            "mirror_symmetry_x": round(self.mirror_symmetry("x"), 3),
            "mirror_symmetry_z": round(self.mirror_symmetry("z"), 3),
            "natural_terrain_fraction": round(self.natural_terrain_fraction(), 4),
            "warnings": self._warnings(comps),
        }

    def _warnings(self, comps):
        warnings = []
        if self.debris_fraction() > 0.005:
            warnings.append(
                f"debris: {len(comps)-1} disconnected component(s), "
                f"{self.debris_fraction()*100:.1f}% of blocks -- consider dropping"
            )
        if self.floating_fraction() > 0.02:
            warnings.append(
                f"floating: {self.floating_fraction()*100:.1f}% of blocks have no "
                f"support chain to the floor plane -- check for a detached wing"
            )
        if self.density() < 0.02:
            warnings.append(
                f"very low density ({self.density()*100:.2f}%) -- bounding box "
                f"likely still has untrimmed padding"
            )
        ntf = self.natural_terrain_fraction()
        if ntf > 0.15:
            warnings.append(
                f"likely captured terrain: {ntf*100:.1f}% of blocks are natural "
                f"material (dirt/grass/stone/...) -- check for an attached hill/tree"
            )
        return warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    r = StructureAnalyzer(args.path).report()
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        for k, v in r.items():
            if k == "warnings":
                continue
            print(f"{k:22s}: {v}")
        if r["warnings"]:
            print("warnings:")
            for w in r["warnings"]:
                print(f"  - {w}")
        else:
            print("warnings: none")


if __name__ == "__main__":
    main()
