#!/usr/bin/env python3
"""
Diagnostic: for every door in a converted structure NBT, check whether the
cells immediately around it (both sides) are actually present as explicit
air blocks -- vs. simply absent (which means "untouched", i.e. real terrain
will show through there when placed in the world).
"""
import argparse

from .nbt import AIR_NAMES, Structure

FACING_VEC = {
    "north": (0, 0, -1), "south": (0, 0, 1),
    "east": (1, 0, 0), "west": (-1, 0, 0),
}


def find_doors(s):
    doors = []
    for pos, idx in s.present.items():
        name = s.palette[idx]
        if not name.endswith("_door"):
            continue
        comp = s.palette_raw[idx]
        props = comp.get("Properties")
        if props is None or "half" not in props or str(props["half"]) != "lower":
            continue
        if "facing" not in props:
            continue
        vec = FACING_VEC.get(str(props["facing"]))
        if vec is None:
            continue
        doors.append((pos, str(props["facing"]), vec))
    return doors


def check(path, steps=2):
    s = Structure(path)
    doors = find_doors(s)

    print(f"found {len(doors)} door(s)\n")

    def cell_status(pos):
        name = s.name_at(pos)
        if name is None:
            return "UNTOUCHED (real terrain will show through)"
        return "air (explicit)" if name in AIR_NAMES else f"solid: {name}"

    problems = 0
    for (x, y, z), facing, (dx, dy, dz) in doors:
        print(f"door at {(x, y, z)} facing {facing}")
        for label, sign in (("outward", 1), ("inward", -1)):
            for step in range(1, steps + 1):
                for dyy in (0, 1):
                    p = (x + dx * step * sign, y + dyy, z + dz * step * sign)
                    status = cell_status(p)
                    flag = "  <-- PROBLEM" if "UNTOUCHED" in status else ""
                    if flag:
                        problems += 1
                    print(f"    {label} step={step} y+{dyy}: {p} -> {status}{flag}")
        print()

    print(f"total problem cells (untouched where air was expected): {problems}")
    return problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--steps", type=int, default=2)
    args = parser.parse_args()
    if args.steps < 1:
        parser.error("--steps must be positive")
    check(args.path, args.steps)


if __name__ == "__main__":
    main()
