"""Shared helpers for carving decorative block paths between two points --
used by house_port.py's yard network and dome_port.py's underwater room."""
import numpy as np

from .nbt import AIR_NAMES

AIR = "minecraft:air"


def wall_mask(src, y_lo, y_hi, size_xz, min_run=3):
    """A column counts as a real wall only if it's solid for min_run
    consecutive layers somewhere in [y_lo, y_hi] -- tall enough that a
    fence post, flower bed or garden border (1-2 blocks) doesn't qualify,
    but an actual multi-block wall does. Paths are free to run over any
    other authored ground/yard content, not just Structura's own pod.
    size_xz is the (X, Z) footprint shape."""
    height = y_hi - y_lo + 1
    layers = np.zeros((height, size_xz[0], size_xz[1]), dtype=bool)
    for (x, y, z), index in src.present.items():
        if y_lo <= y <= y_hi and src.palette[index] not in AIR_NAMES:
            layers[y - y_lo, x, z] = True
    run = np.zeros(size_xz, dtype=int)
    best = np.zeros(size_xz, dtype=int)
    for grid in layers:
        run = np.where(grid, run + 1, 0)
        best = np.maximum(best, run)
    return best >= min_run


def hash3(x, y, z, salt):
    return (x * 73856093 ^ y * 19349663 ^ z * 83492791 ^ salt) & 0xff


def straight_cells(a, b):
    ax, az = a
    bx, bz = b
    cells = []
    if ax == bx:
        step = 1 if bz >= az else -1
        for z in range(az, bz + step, step):
            cells.append((ax, z))
    else:
        step = 1 if bx >= ax else -1
        for x in range(ax, bx + step, step):
            cells.append((x, az))
    return cells


def orthogonal_legs(a, b, salt, index):
    ax, az = a
    bx, bz = b
    corner = (bx, az) if hash3(ax, az, index, salt) % 2 else (ax, bz)
    return straight_cells(a, corner) + straight_cells(corner, b)


def jittered_route(hub_xz, target_xz, bounds, salt, index):
    mx = (hub_xz[0] + target_xz[0]) // 2 + (hash3(index, 1, 1, salt) % 7 - 3)
    mz = (hub_xz[1] + target_xz[1]) // 2 + (hash3(index, 2, 2, salt) % 7 - 3)
    mx = max(0, min(bounds[0] - 1, mx))
    mz = max(0, min(bounds[1] - 1, mz))
    midpoint = (mx, mz)
    return (
        orthogonal_legs(hub_xz, midpoint, salt, index)
        + orthogonal_legs(midpoint, target_xz, salt, index + 1000)
    )


def merge_cells(merged, cells):
    for pos, state in cells:
        current = merged.get(pos)
        if current is None or current == state:
            merged[pos] = state
        elif current == AIR:
            merged[pos] = state
        # else: keep the existing solid state -- a solid block always wins
        # over air, so two crossing paths never eat a hole in each other's
        # floor.
