def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    for start, end in intervals:
        if start > end:
            raise ValueError(f"invalid interval: {(start, end)!r}")
    merged: list[tuple[int, int]] = []
    for start, end in sorted((s, e) for s, e in intervals):
        if merged and start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def covered_points(intervals: list[tuple[int, int]]) -> int:
    return sum(end - start + 1 for start, end in merge_intervals(intervals))
