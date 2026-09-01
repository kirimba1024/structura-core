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

import numpy as np

from .nbt import AIR_NAMES, Structure


def _sparkline(counts, y0, y1, width=40):
    span = y1 - y0 + 1
    buckets = [0] * min(width, span)
    for y, n in counts.items():
        i = min(len(buckets) - 1, (y - y0) * len(buckets) // span)
        buckets[i] += n
    peak = max(buckets) or 1
    ramp = " ▁▂▃▄▅▆▇█"
    return "".join(ramp[round(b / peak * (len(ramp) - 1))] for b in buckets)

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
        self.air_positions = {pos for pos, idx in s.present.items()
                               if s.palette[idx] in AIR_NAMES}
        self._components = None  # cached
        self._rooms = None  # cached

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

    def terrain_profile(self):
        """Y-range and per-layer density of the natural-terrain material
        already in this piece (captured hill, authored yard mound, ...).
        natural_terrain_fraction is one ratio for the whole piece; this is
        where it sits and how it's distributed -- a thin scattered dusting
        reads very differently from one dense captured mass, same overall
        fraction."""
        natural_ys = [
            pos[1] for pos, idx in self.positions.items()
            if self.palette[idx] in self._NATURAL_BLOCKS
        ]
        if not natural_ys:
            return None
        y0, y1 = min(natural_ys), max(natural_ys)
        return {
            "min_y": y0,
            "max_y": y1,
            "span": y1 - y0 + 1,
            "block_count": len(natural_ys),
            "density_profile": _sparkline(Counter(natural_ys), y0, y1),
        }

    # ---- F. rooms / silhouette -- numeric stand-ins for "look at a
    #  picture", not academic citations, but each built on the same
    #  primitives (connected-component labeling, PCA) used elsewhere in
    #  this project and confirmed as the standard approach for exactly
    #  this via web research (2026-09-01): room segmentation from dilating
    #  a voxel occupancy grid until doorway apertures close, then labeling
    #  connected components, is literally how voxel indoor-map room
    #  detection is done in robotics/reconstruction work; PCA/SVD on a
    #  point cloud for a principal-axis oriented bounding box is the
    #  standard cheap elongation/orientation descriptor. -----------------

    def rooms(self):
        """Explicit-air cells (already interior-only -- see convert_legacy's
        exterior/interior split), 6-connected into individual enclosed
        rooms. Component count/sizes describe interior complexity without
        opening a render."""
        if self._rooms is not None:
            return self._rooms
        if not self.air_positions:
            self._rooms = []
            return self._rooms
        from scipy import ndimage

        positions = np.asarray(list(self.air_positions), dtype=np.int32)
        offset = positions.min(axis=0)
        local = positions - offset
        mask = np.zeros(tuple(local.max(axis=0) + 1), dtype=bool)
        mask[tuple(local.T)] = True
        labels, count = ndimage.label(mask, structure=ndimage.generate_binary_structure(3, 1))
        sizes = np.bincount(labels.ravel())[1:] if count else np.array([], dtype=int)
        self._rooms = sorted(sizes.tolist(), reverse=True)
        return self._rooms

    def footprint_elongation(self):
        """PCA on the XZ footprint of solid blocks: ratio of the major to
        minor principal-axis spread, and that major axis's angle off the
        X grid line. A Minecraft build is normally grid-aligned by
        construction -- an angle far from 0/90 degrees is itself a signal
        (diagonal roof detail, or a captured/rotated selection)."""
        if len(self.positions) < 2:
            return 1.0, 0.0
        pts = np.array([(p[0], p[2]) for p in self.positions], dtype=float)
        pts -= pts.mean(axis=0)
        cov = np.cov(pts.T)
        eigvals, eigvecs = np.linalg.eigh(cov)
        order = np.argsort(eigvals)[::-1]
        eigvals = np.clip(eigvals[order], 1e-9, None)
        major = eigvecs[:, order[0]]
        angle = math.degrees(math.atan2(major[1], major[0])) % 90.0
        return float(math.sqrt(eigvals[0] / eigvals[1])), round(angle, 1)

    def vertical_profile(self, width: int = 40) -> str:
        """One-line block-count-per-Y sparkline -- roof taper, multiple
        floors, or a floating outlier layer all show up as a shape in
        text, no render needed."""
        if not self.positions:
            return ""
        ys = [p[1] for p in self.positions]
        return _sparkline(Counter(ys), min(ys), max(ys), width)

    def floor_count(self) -> int:
        """Distinct horizontal density peaks in the Y-profile. A floor
        plate (floor planking, or the ceiling below the next room up)
        is a near-full-footprint slab, so it shows up as a local peak in
        blocks-per-Y separated by lower-density room-interior layers.
        scipy.signal.find_peaks is the standard 1D peak-detection
        primitive; a 15%-of-max prominence floor keeps window-band or
        trim ripples from counting as extra floors. Heuristic, not exact
        -- an open-plan atrium or a dome throws it off."""
        if not self.positions:
            return 0
        from scipy.signal import find_peaks

        ys = [p[1] for p in self.positions]
        y0, y1 = min(ys), max(ys)
        if y1 == y0:
            return 1
        counts = np.zeros(y1 - y0 + 1)
        for y, n in Counter(ys).items():
            counts[y - y0] = n
        peaks, _ = find_peaks(counts, prominence=counts.max() * 0.15, distance=2)
        return max(1, len(peaks))

    # ---- G. environment fit -- material-palette voting, the same
    #  technique natural_terrain_fraction already uses, just against
    #  different curated block sets. A guess to narrow human/AI attention,
    #  not a verdict -- e.g. this is the kind of signal that could have
    #  flagged davegr_house_cave's mismatch (heavy glass/wood, low stone)
    #  ahead of the live in-game rejection recorded in its notes. --------

    _WATER_BLOCKS = {
        "minecraft:prismarine", "minecraft:prismarine_bricks",
        "minecraft:dark_prismarine", "minecraft:sea_lantern",
        "minecraft:kelp", "minecraft:kelp_plant", "minecraft:conduit",
        "minecraft:tube_coral_block", "minecraft:brain_coral_block",
        "minecraft:sponge", "minecraft:wet_sponge",
    }
    _NETHER_BLOCKS = {
        "minecraft:netherrack", "minecraft:nether_bricks", "minecraft:blackstone",
        "minecraft:basalt", "minecraft:soul_sand", "minecraft:soul_soil",
        "minecraft:glowstone", "minecraft:magma_block", "minecraft:crimson_planks",
        "minecraft:warped_planks", "minecraft:nether_wart_block", "minecraft:shroomlight",
    }

    def environment_fit(self) -> dict:
        hist = self.block_histogram()
        total = sum(hist.values()) or 1
        water = sum(n for name, n in hist.items() if name in self._WATER_BLOCKS) / total
        nether = sum(n for name, n in hist.items() if name in self._NETHER_BLOCKS) / total
        glass = sum(n for name, n in hist.items() if "glass" in name) / total
        stone_family = sum(
            n for name, n in hist.items()
            if "stone" in name or "cobble" in name or "brick" in name
        ) / total
        return {
            "water_material_fraction": round(water, 4),
            "nether_material_fraction": round(nether, 4),
            "glass_fraction": round(glass, 4),
            "stone_family_fraction": round(stone_family, 4),
            "has_own_ground": self.natural_terrain_fraction() > 0.15,
            "cave_friendly_guess": stone_family > 0.5 and glass < 0.05,
        }

    # ---- report -------------------------------------------------------

    def report(self) -> dict:
        comps = self.connected_components()
        rooms = self.rooms()
        elongation, axis_angle = self.footprint_elongation()
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
            "room_count": len(rooms),
            "room_sizes": rooms[:8],
            "footprint_elongation": round(elongation, 2),
            "footprint_axis_deg": axis_angle,
            "floor_count": self.floor_count(),
            "vertical_profile": self.vertical_profile(),
            "terrain_profile": self.terrain_profile(),
            "environment_fit": self.environment_fit(),
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
