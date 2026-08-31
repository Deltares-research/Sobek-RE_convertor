from __future__ import annotations

from pathlib import Path

from ...models import BoundaryCondition, LateralDischarge, NetworkModel, TimeSeriesPoint
from .records import RawRecord, load_records


def read_conditions(
    input_dir: Path,
    network: NetworkModel,
) -> tuple[tuple[BoundaryCondition, ...], tuple[LateralDischarge, ...], list[str]]:
    warnings: list[str] = []

    node_name_by_id = {node.id: (node.name or node.id) for node in network.nodes}

    records = load_records(input_dir, "DEFCND", {"FLBO", "FLBR", "FLNO", "FLNX", "FLBX", "FLDI"})

    boundary_locations: dict[str, tuple[str, str]] = {}
    lateral_locations: dict[str, tuple[str, float, str]] = {}
    boundary_series_records: dict[str, RawRecord] = {}
    lateral_series_records: dict[str, RawRecord] = {}

    for record in records:
        if record.key == "FLBO" and "ci" in record.attrs and "id" in record.attrs:
            boundary_locations[record.attrs["id"]] = (
                record.attrs["ci"],
                record.attrs.get("nm", record.attrs["id"]),
            )

        if record.key in {"FLBR", "FLBX"} and "ci" in record.attrs and "lc" in record.attrs and "id" in record.attrs:
            chainage = _as_float(record.attrs.get("lc"))
            if chainage is not None:
                lateral_locations[record.attrs["id"]] = (
                    record.attrs["ci"],
                    chainage,
                    record.attrs.get("nm", record.attrs["id"]),
                )

        if record.key == "FLBO" and record.tables:
            boundary_series_records[record.attrs.get("id", "")] = record

        if record.key == "FLBR" and record.tables:
            lateral_series_records[record.attrs.get("id", "")] = record

    boundaries: list[BoundaryCondition] = []
    for boundary_id, (node_id, boundary_name) in sorted(boundary_locations.items()):
        node_name = node_name_by_id.get(node_id)
        if node_name is None:
            warnings.append(f"Boundary {boundary_id} references unknown node {node_id}.")
            continue

        series_record = boundary_series_records.get(boundary_id)
        series = _parse_timeseries(series_record) if series_record is not None else tuple()

        quantity = "dischargebnd"
        if series_record is not None:
            if "h_" in series_record.attrs or series_record.attrs.get("ty") == "0":
                quantity = "waterlevelbnd"

        boundaries.append(
            BoundaryCondition(
                id=boundary_id,
                name=boundary_name,
                node_id=node_id,
                node_name=node_name,
                quantity=quantity,
                series=series,
            )
        )

    laterals: list[LateralDischarge] = []
    for lateral_id, (branch_id, chainage, lateral_name) in sorted(lateral_locations.items()):
        series_record = lateral_series_records.get(lateral_id)
        series = _parse_timeseries(series_record) if series_record is not None else tuple()

        if not series:
            series = (
                TimeSeriesPoint(time="1900/01/01;00:00:00", value=0.0),
                TimeSeriesPoint(time="1900/01/02;00:00:00", value=0.0),
            )

        laterals.append(
            LateralDischarge(
                id=lateral_id,
                name=lateral_name,
                branch_id=branch_id,
                chainage=chainage,
                series=series,
            )
        )

    return tuple(boundaries), tuple(laterals), warnings


def _parse_timeseries(record: RawRecord | None) -> tuple[TimeSeriesPoint, ...]:
    if record is None or not record.tables:
        return tuple()

    rows = record.tables[0]
    series: list[TimeSeriesPoint] = []
    for row in rows:
        if len(row) < 2:
            continue
        value = _as_float(row[1])
        if value is None:
            continue
        series.append(TimeSeriesPoint(time=row[0], value=value))
    return tuple(series)


def _as_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
