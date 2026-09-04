#!/usr/bin/env python3
"""Cheap proxies for the two mistakes builders name most often.

Not a beauty score. Beauty in a voxel world is partly honesty to the medium
and no number expresses that. What these catch is the short list of defects
that builders themselves write down -- the single cuboid, the flat wall, the
monotone or confetti palette, the floating block, the half-cut tree -- so a
human looks at fewer obviously-broken pieces.

Every figure has to be read beside the archetype. A bounding-box fill of
0.76 damns a house and is simply correct for a block of captured ground,
which is supposed to be solid. A metric applied across types measures type.
The dangerous failure of an automatic filter is confident rejection:
passing something mediocre costs one bad structure in a world, rejecting
something excellent loses it permanently, so read these generously.
"""
import argparse
import json
from collections import Counter

import numpy as np
from scipy import ndimage

from .nbt import AIR_NAMES, Structure

NATURAL_RUN_LIMIT = 7

# Calibrated against the archive rather than guessed. Across 235 pieces the
# largest coplanar vertical patch runs p10 0.010, median 0.056, p90 0.124 and
# never exceeds 0.20, so a threshold of 0.25 -- chosen before the scan --
# flagged nothing at all. 0.15 selects roughly the worst twentieth, which is
# what a prefilter is for.
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
    """The silhouette test, made arithmetic. A build should read as a black
    shape against a sunset; a single box does not."""
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
    """The most-cited beginner mistake: a flat single-block wall. Measured as
    the largest connected patch on any single vertical slice, which is the
    same operator used for flat plates on terrain."""
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
    """Terraforming guides put the limit at about seven blocks in a straight
    line on anything meant to look natural. Reported as the share of runs
    that exceed it, which is more useful than the maximum."""
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
    """The 60-30-10 split, as a histogram check. Roughly 60/30/10 passes;
    100/0/0 is monotone and twenty blocks at 5% each is confetti."""
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
    """Perceived brightness, Rec. 601. Value contrast is what makes a build
    read at distance; hue barely survives the trip."""
    red, green, blue = rgb[:3]
    return 0.299 * red + 0.587 * green + 0.114 * blue


def palette_colour(counts, colors):
    """Value spread and temperature, given a name-to-RGB table.

    Colour is the largest axis this module was missing and the easiest to
    get wrong architecturally: the real block colours live in the render
    library, which reads them out of the client jar, and analysis must not
    start depending on a renderer. So the table is passed in. Callers that
    have textures supply real colours; callers that do not simply skip this.

    Two numbers, both from builders' own advice. Value spread, because a
    palette with no light-to-dark range reads as a flat smear from any
    distance however varied it is up close. And warm share, because mixing
    warm and cool families with nothing between them is the clash guides
    name most often."""
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
    """Floating blocks and one-wide whiskers: both are things nobody builds
    on purpose and both are cheap to count."""
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
    """Defects that are ours to detect and not the author's fault: a canopy
    the selection cut in half, and material flush against a box wall."""
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


def flags(data):
    """The subset of the ugliness list that a number can honestly raise.
    Counts on the 235-piece archive are in the commit that added this."""
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
    parser = argparse.ArgumentParser(description=__doc__)
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
    print("  flags        " + ("none" if not raised else ""))
    for flag in raised:
        print(f"               - {flag}")


if __name__ == "__main__":
    main()
