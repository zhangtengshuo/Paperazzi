"""Reference Publication Year Spectroscopy for Graph Analytics.

This canonical implementation treats absent counts in neighboring calendar years as
zero observations when computing the local median baseline. Omitting zero years would
artificially raise the baseline around sparse historical peaks.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import statistics
from typing import Any

from .snapshot import GraphSnapshot


def rpys(
    snapshot: GraphSnapshot,
    *,
    baseline_radius: int = 2,
    top_peaks: int = 20,
) -> dict[str, Any]:
    year_counts: Counter[int] = Counter()
    refs_by_year: dict[int, Counter[str]] = defaultdict(Counter)
    labels: dict[str, str] = {}
    for refs in snapshot.references.values():
        for ref in refs:
            if ref.cited_year is None:
                continue
            year_counts[ref.cited_year] += 1
            refs_by_year[ref.cited_year][ref.reference_key] += 1
            labels.setdefault(ref.reference_key, ref.raw_reference)

    if not year_counts:
        return {
            "series": [],
            "peaks": [],
            "baseline_radius": baseline_radius,
            "input_quality": snapshot.input_quality,
            "quality_warning": "RPYS has no cited-reference years in this snapshot.",
        }

    first_year = min(year_counts)
    last_year = max(year_counts)
    series: list[dict[str, Any]] = []
    for year in range(first_year, last_year + 1):
        neighbors = [
            year_counts[y]
            for y in range(year - baseline_radius, year + baseline_radius + 1)
            if y != year
        ]
        baseline = statistics.median(neighbors) if neighbors else 0.0
        count = int(year_counts[year])
        deviation = float(count - baseline)
        series.append(
            {
                "year": year,
                "reference_count": count,
                "local_baseline": baseline,
                "deviation": deviation,
            }
        )

    ranked = sorted(
        series,
        key=lambda row: (-row["deviation"], -row["reference_count"], row["year"]),
    )
    peaks: list[dict[str, Any]] = []
    for row in ranked:
        if len(peaks) >= top_peaks:
            break
        if row["deviation"] <= 0:
            continue
        year = int(row["year"])
        peaks.append(
            {
                **row,
                "top_references": [
                    {
                        "reference_key": key,
                        "cited_count": count,
                        "raw_reference": labels.get(key),
                    }
                    for key, count in refs_by_year[year].most_common(10)
                ],
            }
        )

    return {
        "series": series,
        "peaks": peaks,
        "baseline_radius": baseline_radius,
        "input_quality": snapshot.input_quality,
        "quality_warning": (
            "RPYS uses observed local WoS cited references. Missing/partial CR can "
            "lower counts but cannot create citation evidence. Neighboring zero-count "
            "calendar years are retained in the local baseline."
        ),
    }


__all__ = ["rpys"]
