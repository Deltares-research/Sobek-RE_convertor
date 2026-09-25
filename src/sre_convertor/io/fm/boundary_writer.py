from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ...models import BoundaryCondition, LateralDischarge, RuntimeSettings, TimeSeriesPoint


def write_boundary_conditions(
    boundaries: tuple[BoundaryCondition, ...],
    runtime: RuntimeSettings,
    target_path: Path,
) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)

    ref = runtime.refdate.strftime("%Y-%m-%d 00:00:00")
    lines: list[str] = [
        "[General]",
        "    fileVersion           = 1.01",
        "    fileType              = boundConds",
        "",
    ]

    for boundary in boundaries:
        lines.extend(
            [
                "[forcing]",
                f"    name                  = {boundary.node_name}",
                "    function              = timeseries",
                "    time-interpolation    = linear",
                "    quantity              = time",
                f"    unit                  = minutes since {ref}",
                f"    quantity              = {boundary.quantity}",
                f"    unit                  = {_quantity_unit(boundary.quantity)}",
            ]
        )

        points = boundary.series
        if not points:
            points = (
                TimeSeriesPoint(time="1900/01/01;00:00:00", value=0.0),
                TimeSeriesPoint(time="1900/01/02;00:00:00", value=0.0),
            )

        for idx, point in enumerate(points):
            minutes = _minutes_since_ref(point.time, runtime.refdate)
            if minutes is None:
                minutes = idx
            lines.append(f"{minutes}\t{point.value:.6f}")

        lines.append("")

    target_path.write_text("\n".join(lines), encoding="utf-8")


def write_external_forcing_file(
    boundaries: tuple[BoundaryCondition, ...],
    laterals: tuple[LateralDischarge, ...],
    target_path: Path,
    data_path_prefix: str = "",
    branch_names: dict[str, str] | None = None,
) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        "[General]",
        "fileVersion = 2.00",
        "fileType    = extForce",
        "",
    ]

    prefix = data_path_prefix.strip()
    if prefix and not prefix.endswith("/"):
        prefix = f"{prefix}/"

    branch_names = branch_names or {}

    for boundary in boundaries:
        lines.extend(
            [
                "[boundary]",
                f"quantity    = {boundary.quantity}",
                f"nodeId      = {boundary.node_id}",
                f"forcingfile = {prefix}BoundaryConditions.bc",
                "",
            ]
        )

    for lateral in laterals:
        lines.extend(
            [
                "[lateral]",
                f"id                    = {lateral.name}",
                f"branchid              = {branch_names.get(lateral.branch_id, lateral.branch_id)}",
                f"chainage              = {lateral.chainage:.3f}",
                f"discharge             = {prefix}{lateral.name}.bc",
                "",
            ]
        )

    target_path.write_text("\n".join(lines), encoding="utf-8")


def write_lateral_bc_files(
    laterals: tuple[LateralDischarge, ...],
    runtime: RuntimeSettings,
    target_dir: Path,
) -> list[Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    ref = runtime.refdate.strftime("%Y-%m-%d 00:00:00")
    for lateral in laterals:
        path = target_dir / f"{lateral.name}.bc"
        lines: list[str] = [
            "[General]",
            "    fileVersion           = 1.01",
            "    fileType              = boundConds",
            "",
            "[forcing]",
            f"    name                  = {lateral.name}",
            "    function              = timeseries",
            "    time-interpolation    = linear",
            "    quantity              = time",
            f"    unit                  = minutes since {ref}",
            "    quantity              = lateral_discharge",
            "    unit                  = m3/s",
        ]

        series = _normalize_lateral_series(lateral.series, runtime)
        for minutes, value in series:
            lines.append(f"{minutes}\t{value:.6f}")

        lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")
        created.append(path)

    return created


def _normalize_lateral_series(
    series: tuple[TimeSeriesPoint, ...],
    runtime: RuntimeSettings,
) -> list[tuple[int, float]]:
    runtime_end_minutes = max(1, int(runtime.tstop_seconds / 60))
    required_last_minute = runtime_end_minutes + 1

    normalized: list[tuple[int, float]] = []
    for idx, point in enumerate(series):
        minutes = _minutes_since_ref(point.time, runtime.refdate)
        if minutes is None:
            minutes = idx
        normalized.append((minutes, point.value))

    if not normalized:
        return [(0, 0.0), (required_last_minute, 0.0)]

    monotonic: list[tuple[int, float]] = []
    for minutes, value in normalized:
        if monotonic and minutes <= monotonic[-1][0]:
            minutes = monotonic[-1][0] + 1
        monotonic.append((minutes, value))

    if len(monotonic) == 1:
        only_minute, only_value = monotonic[0]
        end_minute = max(only_minute + 1, required_last_minute)
        monotonic.append((end_minute, only_value))
        return monotonic

    if monotonic[-1][0] <= runtime_end_minutes:
        monotonic.append((required_last_minute, monotonic[-1][1]))

    return monotonic


def _minutes_since_ref(time_str: str, refdate: datetime) -> int | None:
    try:
        moment = datetime.strptime(time_str, "%Y/%m/%d;%H:%M:%S")
    except ValueError:
        return None

    minutes = int((moment - refdate).total_seconds() / 60)
    return max(0, minutes)


def _quantity_unit(quantity: str) -> str:
    if quantity == "waterlevelbnd":
        return "m"
    return "m3/s"
