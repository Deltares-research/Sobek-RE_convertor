from __future__ import annotations

from pathlib import Path

from ...models import CrossSectionDefinition, CrossSectionLocation
from .records import load_records


def read_cross_sections(input_dir: Path) -> tuple[tuple[CrossSectionDefinition, ...], tuple[CrossSectionLocation, ...], list[str]]:
    warnings: list[str] = []

    all_crsn_records = load_records(input_dir, "DEFCRS", {"CRSN"})
    location_records = [record for record in all_crsn_records if "ci" in record.attrs and "lc" in record.attrs]
    definition_records = load_records(input_dir, "DEFCRS", {"CRDS"})
    relation_records = [
        record
        for record in all_crsn_records
        if "di" in record.attrs
    ]

    definitions_by_id: dict[str, CrossSectionDefinition] = {}
    for record in definition_records:
        definition_id = record.attrs.get("id")
        if not definition_id:
            continue

        table = record.tables[0] if record.tables else tuple()
        levels: list[float] = []
        total_widths: list[float] = []
        flow_widths: list[float] = []

        for row in table:
            if len(row) < 3:
                continue
            try:
                levels.append(float(row[0]))
                total_widths.append(float(row[1]))
                flow_widths.append(float(row[2]))
            except ValueError:
                continue

        if not levels:
            warnings.append(f"Cross-section definition {definition_id} has no valid tabulated rows.")
            continue

        definitions_by_id[definition_id] = CrossSectionDefinition(
            id=definition_id,
            name=record.attrs.get("nm", definition_id),
            levels=tuple(levels),
            flow_widths=tuple(flow_widths),
            total_widths=tuple(total_widths),
        )

    relation_by_cross_id: dict[str, tuple[str, float]] = {}
    for record in relation_records:
        cross_id = record.attrs.get("id")
        definition_id = record.attrs.get("di")
        if not cross_id or not definition_id:
            continue
        reference_level = _as_float(record.attrs.get("rl"), 0.0)
        relation_by_cross_id[cross_id] = (definition_id, reference_level)

    locations: list[CrossSectionLocation] = []
    for record in location_records:
        cross_id = record.attrs.get("id")
        if not cross_id:
            continue

        relation = relation_by_cross_id.get(cross_id)
        if relation is None:
            warnings.append(f"Cross-section location {cross_id} has no definition relation in DEFCRS.*.")
            continue

        definition_id, reference_level = relation
        if definition_id not in definitions_by_id:
            warnings.append(
                f"Cross-section location {cross_id} references unknown definition {definition_id}."
            )
            continue

        branch_id = record.attrs.get("ci")
        chainage = _as_float(record.attrs.get("lc"), None)
        if branch_id is None or chainage is None:
            warnings.append(f"Cross-section location {cross_id} is missing ci/lc fields.")
            continue

        locations.append(
            CrossSectionLocation(
                id=cross_id,
                name=record.attrs.get("nm", cross_id),
                branch_id=branch_id,
                chainage=chainage,
                definition_id=definition_id,
                reference_level=reference_level,
            )
        )

    definitions = tuple(definitions_by_id[key] for key in sorted(definitions_by_id.keys()))
    locations_sorted = tuple(sorted(locations, key=lambda item: (item.branch_id, item.chainage, item.id)))

    return definitions, locations_sorted, warnings


def _as_float(value: str | None, fallback: float | None) -> float | None:
    if value is None:
        return fallback
    try:
        return float(value)
    except ValueError:
        return fallback
