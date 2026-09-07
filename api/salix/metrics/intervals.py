"""Interval arithmetic shared by the metrics engine.

Diarized speech overlaps -- people talk over each other -- so naive summation
double-counts. These helpers work on merged unions, which is what makes
`talk_ratio + silence` add up to the call duration instead of exceeding it.
"""

from __future__ import annotations

Interval = tuple[int, int]


def merge(intervals: list[Interval]) -> list[Interval]:
    """Merge overlapping/touching intervals into a sorted, disjoint set."""
    if not intervals:
        return []
    ordered = sorted((a, b) for a, b in intervals if b > a)
    if not ordered:
        return []
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def total(intervals: list[Interval]) -> int:
    """Total covered time of a set of intervals, counting overlap once."""
    return sum(end - start for start, end in merge(intervals))


def gaps(intervals: list[Interval], floor: int, ceiling: int) -> list[Interval]:
    """The uncovered stretches between `floor` and `ceiling`."""
    merged = merge(intervals)
    result: list[Interval] = []
    cursor = floor
    for start, end in merged:
        if start > cursor:
            result.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < ceiling:
        result.append((cursor, ceiling))
    return result


def overlap_ms(a: Interval, b: Interval) -> int:
    """Milliseconds shared by two intervals; 0 if they are disjoint."""
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def clipped_total(intervals: list[Interval], start: int, end: int) -> int:
    """Covered time within a window, counting overlap once."""
    window = (start, end)
    return sum(overlap_ms(iv, window) for iv in merge(intervals))
