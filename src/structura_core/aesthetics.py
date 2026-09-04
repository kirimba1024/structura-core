#!/usr/bin/env python3
import argparse
import json
from collections import Counter

import numpy as np
from scipy import ndimage

from .nbt import AIR_NAMES, Structure

NATURAL_RUN_LIMIT = 7

FLAT_WALL_LIMIT = 0.15
BOX_FILL_LIMIT = 0.7
BOX_LEVEL_LIMIT = 4


def solid_mask(structure):
    width, height, depth = structure.size
    solid = np.zeros((width, height, depth), dtype=bool)
    for (x, y, z), index in structure.present.items():
        if structure.palette[index] not in AIR_NAMES:
            solid[x, y, z] = True
    return solid


def silhouette(solid):
    occupied = np.argwhere(solid)
    if not occupied.size:
        return dict(bbox_fill=0.0, top_levels=0, aspect=0.0)
    lo, hi = occupied.min(axis=0), occupied.max(axis=0)
    core = solid[lo[0]:hi[0] + 1, lo[1]:hi[1] + 1, lo[2]:hi[2] + 1]
    footprint = core.any(axis=1)
    top = np.where(
        footprint, core.shape[1] - 1 - np.argmax(core[:, ::-1, :], axis=1), -1,
    )
    span = hi - lo + 1
    return dict(
        bbox_fill=round(float(core.sum() / core.size), 3),
        top_levels=int(len(np.unique(top[footprint]))),
        aspect=round(float(max(span[0], span[2]) / max(min(span[0], span[2]), 1)), 2),
    )


def flat_wall(solid):
    largest = 0
    for axis in (0, 2):
        for index in range(solid.shape[axis]):
            plane = solid[index] if axis == 0 else solid[:, :, index]
            if plane.sum() < 16:
                continue
            labels, count = ndimage.label(plane)
            if count:
                largest = max(largest, int(ndimage.sum(plane, labels, range(1, count + 1)).max()))
    return round(largest / max(int(solid.sum()), 1), 3)


def longest_straight_run(solid):
    footprint = solid.any(axis=1)
    if not footprint.any():
        return dict(run_p95=0.0, run_max=0, over_limit=0.0)
    top = np.where(
        footprint, solid.shape[1] - 1 - np.argmax(solid[:, ::-1, :], axis=1), -1,
    )
    runs = []
    for heights, mask in ((top, footprint), (top.T, footprint.T)):
        for row in range(heights.shape[0]):
            length = 1
            for column in range(1, heights.shape[1]):
                same = (mask[row, column] and mask[row, column - 1]
                        and heights[row, column] == heights[row, column - 1])
                if same:
                    length += 1
                else:
                    if length > 1:
                        runs.append(length)
                    length = 1
            if length > 1:
                runs.append(length)
    lengths = np.array(runs) if runs else np.array([0])
    return dict(
        run_p95=round(float(np.percentile(lengths, 95)), 1),
        run_max=int(lengths.max()),
        over_limit=round(float((lengths > NATURAL_RUN_LIMIT).mean()), 3),
    )


def block_counts(structure):
    counts = Counter()
    for index in structure.present.values():
        name = structure.palette[index]
        if name not in AIR_NAMES:
            counts[name] += 1
    return counts


def palette_balance(structure):
    counts = block_counts(structure)
    total = max(sum(counts.values()), 1)
    shares = [count / total for _, count in counts.most_common(3)]
    shares += [0.0] * (3 - len(shares))
    return dict(
        distinct=len(counts),
        top_three=[round(share, 3) for share in shares],
        dominance=round(shares[0], 3),
    )


def luminance(rgb):
    red, green, blue = rgb[:3]
    return 0.299 * red + 0.587 * green + 0.114 * blue


def palette_colour(counts, colors):
    weighted = [(count, colors[name]) for name, count in counts.items()
                if name in colors]
    if not weighted:
        return None
    total = sum(count for count, _ in weighted)
    values = np.array([luminance(rgb) for _, rgb in weighted])
    weights = np.array([count for count, _ in weighted], dtype=float) / total
    order = np.argsort(values)
    sorted_values, sorted_weights = values[order], weights[order]
    cumulative = np.cumsum(sorted_weights)
    low = float(sorted_values[np.searchsorted(cumulative, 0.10)])
    high = float(sorted_values[min(np.searchsorted(cumulative, 0.90),
                                   len(sorted_values) - 1)])
    warm = sum(weight for weight, (_, rgb) in zip(weights, weighted)
               if rgb[0] > rgb[2])
    return dict(
        covered=round(total / max(sum(counts.values()), 1), 3),
        value_mean=round(float((values * weights).sum()), 1),
        value_spread=round(float(np.sqrt((weights * (values - (values * weights).sum()) ** 2).sum())), 1),
        value_range=round(high - low, 1),
        warm_share=round(float(warm), 3),
    )


def construction_tells(solid):
    supported = np.zeros_like(solid)
    supported[:, 1:, :] = solid[:, :-1, :]
    rows = np.arange(solid.shape[1])[None, :, None]
    floating = int((solid & ~supported & (rows > 0)).sum())
    footprint = solid.any(axis=1).astype(np.int8)
    neighbours = ndimage.convolve(footprint, np.ones((3, 3), np.int8), mode="constant")
    whiskers = int((footprint.astype(bool) & (neighbours - footprint < 3)).sum())
    labels, count = ndimage.label(solid)
    sizes = ndimage.sum(solid, labels, range(1, count + 1)) if count else np.array([0])
    return dict(
        floating=floating,
        floating_share=round(floating / max(int(solid.sum()), 1), 4),
        whisker_columns=whiskers,
        debris_components=int((sizes < 8).sum()),
        largest_share=round(float(sizes.max() / max(int(solid.sum()), 1)), 4),
    )


def capture_tells(structure, solid):
    leaves = logs = 0
    for index in structure.present.values():
        name = structure.palette[index]
        if name.endswith("_leaves"):
            leaves += 1
        elif name.endswith("_log") or name.endswith("_stem"):
            logs += 1
    faces = dict(
        x0=float(solid[0].mean()), x1=float(solid[-1].mean()),
        z0=float(solid[:, :, 0].mean()), z1=float(solid[:, :, -1].mean()),
        ylo=float(solid[:, 0, :].mean()), yhi=float(solid[:, -1, :].mean()),
    )
    return dict(
        leaves=leaves, logs=logs,
        orphan_canopy=bool(leaves > 40 and logs * 12 < leaves),
        faces={key: round(value, 3) for key, value in faces.items()},
        cut_faces=int(sum(1 for value in faces.values() if value > 0.15)),
    )


HINT_CONFIDENCE = {
    "debris": 0.9,
    "orphan canopy": 0.9,
    "scattered": 0.8,
    "flat wall": 0.5,
    "no value spread": 0.4,
    "confetti palette": 0.4,
    "box-like": 0.3,
    "monotone palette": 0.3,
}


def review_score(data):
    return round(sum(HINT_CONFIDENCE.get(hint.split(":")[0], 0.5)
                     for hint in flags(data)), 2)


def flags(data):
    silhouette_data, palette, construction, capture = (
        data["silhouette"], data["palette"], data["construction"], data["capture"])
    raised = []
    if (silhouette_data["bbox_fill"] > BOX_FILL_LIMIT
            and silhouette_data["top_levels"] <= BOX_LEVEL_LIMIT):
        raised.append("box-like: fills its bounding box with almost no roofline")
    colour = data.get("colour")
    if colour and colour["covered"] > 0.5 and colour["value_range"] < 30:
        raised.append("no value spread: reads as a flat smear at distance")
    if data["flat_wall"] > FLAT_WALL_LIMIT:
        raised.append("flat wall: too much mass on one vertical slice")
    if palette["dominance"] > 0.8:
        raised.append("monotone palette: one block is most of the build")
    if palette["distinct"] > 60 and palette["dominance"] < 0.25:
        raised.append("confetti palette: many blocks, none dominant")
    if capture["orphan_canopy"]:
        raised.append("orphan canopy: leaves the selection cut away from their logs")
    if construction["debris_components"] > 40:
        raised.append("debris: many tiny disconnected components")
    if construction["largest_share"] < 0.5:
        raised.append("scattered: most of the mass is off the main body")
    return raised


def report(path, colors=None):
    structure = Structure(path)
    solid = solid_mask(structure)
    return dict(
        name=str(path), size=list(structure.size), blocks=int(solid.sum()),
        silhouette=silhouette(solid),
        flat_wall=flat_wall(solid),
        terrain=longest_straight_run(solid),
        palette=palette_balance(structure),
        construction=construction_tells(solid),
        capture=capture_tells(structure, solid),
        colour=palette_colour(block_counts(structure), colors) if colors else None,
    )


def report_with_flags(path):
    data = report(path)
    data["flags"] = flags(data)
    return data


def main():
    parser = argparse.ArgumentParser(
        description="beauty heuristics: what to look at first, never what to reject",
    )
    parser.add_argument("path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    data = report(args.path)
    if args.json:
        print(json.dumps(data, indent=2))
        return
    sil, cons, cap = data["silhouette"], data["construction"], data["capture"]
    print(f"{data['name']}  {data['size']}  {data['blocks']} blocks")
    print(f"  silhouette   bbox fill {sil['bbox_fill']:.3f}  top levels {sil['top_levels']}  aspect {sil['aspect']}")
    print(f"  flat wall    largest coplanar patch {data['flat_wall']:.3f} of mass")
    print(f"  terrain      runs p95 {data['terrain']['run_p95']} max {data['terrain']['run_max']} "
          f"over {NATURAL_RUN_LIMIT}: {100 * data['terrain']['over_limit']:.1f}%")
    print(f"  palette      {data['palette']['distinct']} blocks, top three {data['palette']['top_three']}")
    print(f"  construction floating {cons['floating']} ({100 * cons['floating_share']:.1f}%), "
          f"whisker columns {cons['whisker_columns']}, debris {cons['debris_components']}")
    print(f"  capture      {cap['cut_faces']} box faces touched, orphan canopy: {cap['orphan_canopy']}")
    raised = flags(data)
    print(f"  review       score {review_score(data):.2f} "
          f"({'nothing to look at' if not raised else str(len(raised)) + ' hint(s)'})")
    for flag in raised:
        print(f"               - {flag}")


if __name__ == "__main__":
    main()
