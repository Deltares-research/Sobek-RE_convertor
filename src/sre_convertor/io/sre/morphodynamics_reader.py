from __future__ import annotations

from pathlib import Path
import statistics

from ...models import MorphodynamicsSummary
from .records import load_records


def read_morphodynamics_summary(input_dir: Path) -> tuple[MorphodynamicsSummary, list[str]]:
    warnings: list[str] = []

    mpin_records = load_records(input_dir, "DEFICN", {"MPIN"})
    sbst_records = load_records(input_dir, "DEFSUB", {"SBST"})

    branch_ids = {
        record.attrs.get("ci", "")
        for record in mpin_records
        if record.attrs.get("ci") and record.attrs.get("ci") != "-1"
    }
    has_morphology_switch = any(record.attrs.get("md") == "1" for record in sbst_records)
    grain_size_samples = _extract_grain_size_samples(mpin_records)
    representative_d50_m = statistics.median(grain_size_samples) if grain_size_samples else None
    sediment_fractions = _derive_sediment_fractions(grain_size_samples)
    branch_samples = _extract_branch_grain_size_samples(mpin_records)
    branch_composition = _compute_branch_composition(branch_samples, sediment_fractions)

    if branch_ids and not has_morphology_switch:
        warnings.append("MPIN grain-size initialization found, but DEFSUB does not indicate active morphology switch.")

    summary = MorphodynamicsSummary(
        branch_count_with_grainsize=len(branch_ids),
        has_morphology_switch=has_morphology_switch,
        representative_d50_m=representative_d50_m,
        sediment_fractions_d50_m=sediment_fractions,
        grain_size_sample_count=len(grain_size_samples),
        branch_composition=branch_composition,
    )
    return summary, warnings


def _extract_grain_size_samples(mpin_records: list) -> list[float]:
    d50_values: list[float] = []
    for record in mpin_records:
        raw = record.attrs.get("c5")
        if raw is None:
            raw = ""
        value = _to_grainsize(raw)
        if value is not None:
            d50_values.append(value)

        for table in record.tables:
            for row in table:
                sample = _sample_from_row(row)
                if sample is not None:
                    d50_values.append(sample)

    return d50_values


def _extract_branch_grain_size_samples(mpin_records: list) -> dict[str, list[float]]:
    per_branch: dict[str, list[float]] = {}
    for record in mpin_records:
        branch_id = record.attrs.get("ci")
        if not branch_id or branch_id == "-1":
            continue

        values: list[float] = []
        attr_value = _to_grainsize(record.attrs.get("c5", ""))
        if attr_value is not None:
            values.append(attr_value)

        for table in record.tables:
            for row in table:
                sample = _sample_from_row(row)
                if sample is not None:
                    values.append(sample)

        if values:
            per_branch[branch_id] = values

    return per_branch


def _sample_from_row(row: tuple[str, ...]) -> float | None:
    if len(row) < 2:
        return None

    candidates = [_to_grainsize(token) for token in row[1:]]
    clean = [value for value in candidates if value is not None]
    if not clean:
        return None

    # MPIN rows contain multiple grain-size descriptors; use the smallest
    # valid class-scale value as a stable D50 proxy.
    return min(clean)


def _to_grainsize(raw: str) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None

    if value <= 0.0:
        return None
    if value >= 1.0e8:
        return None
    # Grain diameters in meters; filter physically implausible outliers.
    if value > 0.5:
        return None
    return value


def _derive_sediment_fractions(samples: list[float]) -> tuple[float, ...]:
    if not samples:
        return tuple()

    sorted_values = sorted(samples)
    percentiles = (5.0, 20.0, 35.0, 50.0, 65.0, 80.0, 95.0)
    candidates = [_percentile(sorted_values, p) for p in percentiles]

    unique: list[float] = []
    for value in candidates:
        rounded = round(value, 7)
        if rounded <= 0.0:
            continue
        if unique and abs(unique[-1] - rounded) < 1e-7:
            continue
        unique.append(rounded)

    if not unique:
        unique = [round(statistics.median(sorted_values), 7)]

    return tuple(unique)


def _compute_branch_composition(
    branch_samples: dict[str, list[float]],
    fractions: tuple[float, ...],
) -> tuple[tuple[str, tuple[float, ...]], ...]:
    if not branch_samples or not fractions:
        return tuple()

    composition: list[tuple[str, tuple[float, ...]]] = []
    for branch_id in sorted(branch_samples.keys()):
        samples = branch_samples[branch_id]
        counts = [0 for _ in fractions]
        for sample in samples:
            idx = min(range(len(fractions)), key=lambda i: abs(fractions[i] - sample))
            counts[idx] += 1

        total = sum(counts)
        if total <= 0:
            continue
        weights = tuple(count / total for count in counts)
        composition.append((branch_id, weights))

    return tuple(composition)


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]

    rank = (len(sorted_values) - 1) * percentile / 100.0
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    weight = rank - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight
