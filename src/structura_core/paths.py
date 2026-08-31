"""Shared helpers for carving decorative block paths between two points --
used by house_port.py's yard network and dome_port.py's underwater room."""
AIR = "minecraft:air"


def hash3(x, y, z, salt):
    return (x * 73856093 ^ y * 19349663 ^ z * 83492791 ^ salt) & 0xff


def line_cells(a, b):
    x0, z0 = a
    x1, z1 = b
    dx, dz = abs(x1 - x0), abs(z1 - z0)
    sx = 1 if x1 > x0 else -1
    sz = 1 if z1 > z0 else -1
    err = dx - dz
    x, z = x0, z0
    cells = []
    while True:
        cells.append((x, z))
        if x == x1 and z == z1:
            break
        e2 = 2 * err
        if e2 > -dz:
            err -= dz
            x += sx
        if e2 < dx:
            err += dx
            z += sz
    return cells


def jittered_route(hub_xz, target_xz, bounds, salt, index):
    mx = (hub_xz[0] + target_xz[0]) // 2 + (hash3(index, 1, 1, salt) % 7 - 3)
    mz = (hub_xz[1] + target_xz[1]) // 2 + (hash3(index, 2, 2, salt) % 7 - 3)
    mx = max(0, min(bounds[0] - 1, mx))
    mz = max(0, min(bounds[1] - 1, mz))
    return line_cells(hub_xz, (mx, mz)) + line_cells((mx, mz), target_xz)


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
