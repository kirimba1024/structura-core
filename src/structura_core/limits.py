"""Allocation limits shared by native structure formats."""

DEFAULT_MAX_BLOCKS = 2_000_000


def check_volume(volume, limit):
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("max_blocks must be a positive integer")
    if volume > limit:
        raise ValueError(f"structure contains {volume:,} cells; max_blocks is {limit:,}")
