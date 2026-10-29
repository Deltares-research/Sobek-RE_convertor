from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum
from pathlib import Path
import shlex


_SENTINEL = 1.0e9


class SreRtcControllerType(IntEnum):
    TIME = 0
    HYDRAULIC = 1
    INTERVAL = 2
    PID = 3


class SreRtcControlledParameter(IntEnum):
    CREST_LEVEL = 0
    CREST_WIDTH = 1
    GATE_HEIGHT = 2


class SreRtcTriggerType(IntEnum):
    TIME = 0
    HYDRAULIC = 1
    BOTH = 2


class SreRtcComparison(IntEnum):
    LESS_THAN = 0
    GREATER_THAN = 1


class SreRtcTableRole(str, Enum):
    TIME_CONTROLLER = "Time Controller"
    STEER_TABLE = "Steer Table"
    HYDRAULIC_CONTROLLER = "Hydraulic Controller"


@dataclass(frozen=True)
class SreRtcTableMetadata:
    role: SreRtcTableRole | None
    axis_labels: tuple[str, ...]
    interpolation_code: int | None
    periodicity_code: int | None


@dataclass(frozen=True)
class SreRtcTriggerSlot:
    index: int
    trigger_id: str | None
    active: bool


@dataclass(frozen=True)
class SreRtcController:
    id: str
    name: str
    type_code: int
    controller_type: SreRtcControllerType
    parameter_code: int
    controlled_parameter: SreRtcControlledParameter
    controlled_structure_id: str | None
    trigger_slots: tuple[SreRtcTriggerSlot, ...]
    observation_branch_id: str | None
    observation_chainage: float | None
    tables: tuple[tuple[tuple[str, ...], ...], ...]
    source_file: Path
    source_line: int
    raw_lines: tuple[str, ...]
    table_metadata: tuple[SreRtcTableMetadata, ...] = ()

    @property
    def active_trigger_ids(self) -> tuple[str, ...]:
        return tuple(
            slot.trigger_id
            for slot in self.trigger_slots
            if slot.active and slot.trigger_id is not None
        )


@dataclass(frozen=True)
class SreRtcTriggerCondition:
    time: datetime | None
    enable_code: int | None
    combination_code: int | None
    comparison: SreRtcComparison | None
    threshold: float | None
    raw_values: tuple[str, ...]


@dataclass(frozen=True)
class SreRtcTrigger:
    id: str
    name: str
    type_code: int
    trigger_type: SreRtcTriggerType
    branch_id: str | None
    chainage: float | None
    tables: tuple[tuple[tuple[str, ...], ...], ...]
    conditions: tuple[SreRtcTriggerCondition, ...]
    source_file: Path
    source_line: int
    raw_lines: tuple[str, ...]


@dataclass(frozen=True)
class SreRtcSummary:
    controllers: tuple[SreRtcController, ...] = ()
    triggers: tuple[SreRtcTrigger, ...] = ()


@dataclass(frozen=True)
class _SourceRecord:
    lines: tuple[str, ...]
    source_file: Path
    source_line: int


def read_sre_rtc(input_dir: Path) -> tuple[SreRtcSummary, list[str]]:
    structure_links = _read_controller_structure_links(input_dir)
    controller_records = _iter_records(input_dir, "CNTL")
    trigger_records = _iter_records(input_dir, "TRGR")
    controllers = tuple(
        _parse_controller(record, structure_links)
        for record in controller_records
        if _record_id(record) is not None
    )
    triggers = tuple(
        _parse_trigger(record)
        for record in trigger_records
        if _record_id(record) is not None
    )

    _ensure_unique((controller.id for controller in controllers), "controller")
    _ensure_unique((trigger.id for trigger in triggers), "trigger")
    trigger_ids = {trigger.id for trigger in triggers}
    for controller in controllers:
        missing = [trigger_id for trigger_id in controller.active_trigger_ids if trigger_id not in trigger_ids]
        if missing:
            raise ValueError(
                f"{_location(controller.source_file, controller.source_line)}: "
                f"controller {controller.id} references missing active trigger(s): {', '.join(missing)}."
            )

    warnings = []
    if not controllers and not triggers:
        warnings.append("No SRE RTC CNTL/TRGR records were found in DEFSTR.*.")
    return SreRtcSummary(controllers=controllers, triggers=triggers), warnings


def _read_controller_structure_links(input_dir: Path) -> dict[str, str]:
    links: dict[str, str] = {}
    for record in _iter_records(input_dir, "STRU"):
        tokens = _header_tokens(record)
        structure_id = _value_after(tokens, "id")
        if structure_id is None:
            continue
        for controller_id in _values_after(tokens, "cj", 4):
            if controller_id in ("", "-1"):
                continue
            structure_id_with_prefix = f"ST_{structure_id}"
            existing = links.get(controller_id)
            if existing is not None and existing != structure_id_with_prefix:
                raise ValueError(
                    f"{_location(record.source_file, record.source_line)}: "
                    f"controller {controller_id} is linked to multiple structures."
                )
            links[controller_id] = structure_id_with_prefix
    return links


def _parse_controller(record: _SourceRecord, structure_links: dict[str, str]) -> SreRtcController:
    tokens = _header_tokens(record)
    controller_id = _required_value(tokens, "id", record)
    type_code = _required_int(tokens, "ct", record)
    parameter_code = _required_int(tokens, "ca", record)
    try:
        controller_type = SreRtcControllerType(type_code)
    except ValueError as exc:
        raise ValueError(
            f"{_location(record.source_file, record.source_line)}: "
            f"controller {controller_id} has unknown ct code {type_code}."
        ) from exc
    try:
        controlled_parameter = SreRtcControlledParameter(parameter_code)
    except ValueError as exc:
        raise ValueError(
            f"{_location(record.source_file, record.source_line)}: "
            f"controller {controller_id} has unknown ca code {parameter_code}."
        ) from exc

    trigger_ids = _values_after(tokens, "gi", 4)
    active_codes = _values_after(tokens, "ta", 4)
    if len(trigger_ids) != 4 or len(active_codes) != 4:
        raise ValueError(
            f"{_location(record.source_file, record.source_line)}: "
            f"controller {controller_id} must define four gi/ta trigger slots."
        )

    slots: list[SreRtcTriggerSlot] = []
    for index, (trigger_id, active_code) in enumerate(zip(trigger_ids, active_codes)):
        if active_code not in {"0", "1"}:
            raise ValueError(
                f"{_location(record.source_file, record.source_line)}: "
                f"controller {controller_id} has invalid ta flag {active_code!r} in slot {index + 1}."
            )
        normalized_id = None if trigger_id == "-1" else trigger_id
        active = active_code == "1"
        if active and normalized_id is None:
            raise ValueError(
                f"{_location(record.source_file, record.source_line)}: "
                f"controller {controller_id} enables empty gi slot {index + 1}."
            )
        slots.append(SreRtcTriggerSlot(index=index, trigger_id=normalized_id, active=active))

    branch_ids = _values_after(tokens, "cb", 5)
    chainage_values = _values_after(tokens, "cl", 5)
    observation_branch_id: str | None = None
    observation_chainage: float | None = None
    for branch_id, raw_chainage in zip(branch_ids, chainage_values):
        chainage = _optional_float(
            raw_chainage,
            record,
            f"controller {controller_id} observation chainage",
        )
        if branch_id not in {"", "-1"} and chainage is not None:
            observation_branch_id = branch_id
            observation_chainage = chainage
            break

    tables = _parse_tables(record)
    table_metadata = _parse_table_metadata(record)
    if len(table_metadata) != len(tables):
        raise ValueError(
            f"{_location(record.source_file, record.source_line)}: "
            f"controller {controller_id} has {len(tables)} TBLE tables but "
            f"{len(table_metadata)} table metadata blocks."
        )

    return SreRtcController(
        id=controller_id,
        name=_value_after(tokens, "nm") or controller_id,
        type_code=type_code,
        controller_type=controller_type,
        parameter_code=parameter_code,
        controlled_parameter=controlled_parameter,
        controlled_structure_id=structure_links.get(controller_id),
        trigger_slots=tuple(slots),
        observation_branch_id=observation_branch_id,
        observation_chainage=observation_chainage,
        tables=tables,
        source_file=record.source_file,
        source_line=record.source_line,
        raw_lines=record.lines,
        table_metadata=table_metadata,
    )


def _parse_trigger(record: _SourceRecord) -> SreRtcTrigger:
    tokens = _header_tokens(record)
    trigger_id = _required_value(tokens, "id", record)
    type_code = _required_int(tokens, "ty", record)
    try:
        trigger_type = SreRtcTriggerType(type_code)
    except ValueError as exc:
        raise ValueError(
            f"{_location(record.source_file, record.source_line)}: "
            f"trigger {trigger_id} has unknown ty code {type_code}."
        ) from exc

    branch_id = _value_after(tokens, "tb")
    if branch_id in {"", "-1"}:
        branch_id = None
    chainage = _optional_float(
        _value_after(tokens, "tl"),
        record,
        f"trigger {trigger_id} chainage",
    )
    tables = _parse_tables(record)
    conditions = tuple(_parse_trigger_condition(row, record, trigger_id) for table in tables for row in table)
    return SreRtcTrigger(
        id=trigger_id,
        name=_value_after(tokens, "nm") or trigger_id,
        type_code=type_code,
        trigger_type=trigger_type,
        branch_id=branch_id,
        chainage=chainage,
        tables=tables,
        conditions=conditions,
        source_file=record.source_file,
        source_line=record.source_line,
        raw_lines=record.lines,
    )


def _parse_trigger_condition(
    row: tuple[str, ...],
    record: _SourceRecord,
    trigger_id: str,
) -> SreRtcTriggerCondition:
    if not row:
        raise ValueError(
            f"{_location(record.source_file, record.source_line)}: trigger {trigger_id} has an empty condition row."
        )
    condition_time = _parse_time(row[0], record, trigger_id)
    enable_code = _optional_int(row[1], record, trigger_id, "on/off") if len(row) > 1 else None
    combination_code = _optional_int(row[2], record, trigger_id, "and/or") if len(row) > 2 else None
    comparison_code = _optional_int(row[3], record, trigger_id, "operation") if len(row) > 3 else None
    threshold = (
        _optional_float(row[4], record, f"trigger {trigger_id} threshold")
        if len(row) > 4
        else None
    )

    comparison = None
    if comparison_code is not None:
        try:
            comparison = SreRtcComparison(comparison_code)
        except ValueError as exc:
            raise ValueError(
                f"{_location(record.source_file, record.source_line)}: "
                f"trigger {trigger_id} has unknown operation code {comparison_code}."
            ) from exc

    return SreRtcTriggerCondition(
        time=condition_time,
        enable_code=enable_code,
        combination_code=combination_code,
        comparison=comparison,
        threshold=threshold,
        raw_values=row,
    )


def _iter_records(input_dir: Path, key: str) -> tuple[_SourceRecord, ...]:
    records: list[_SourceRecord] = []
    for path in sorted(input_dir.glob("DEFSTR.*")):
        if not path.is_file():
            continue
        current: list[str] = []
        current_start = 0
        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            first = shlex.split(line)[0]
            if first == key:
                if current:
                    records.append(_SourceRecord(tuple(current), path, current_start))
                current = [line]
                current_start = line_number
            elif current and first == key.lower():
                records.append(_SourceRecord(tuple(current), path, current_start))
                current = []
                current_start = 0
            elif current:
                current.append(line)
        if current:
            records.append(_SourceRecord(tuple(current), path, current_start))
    return tuple(records)


def _parse_tables(record: _SourceRecord) -> tuple[tuple[tuple[str, ...], ...], ...]:
    tables: list[tuple[tuple[str, ...], ...]] = []
    current: list[tuple[str, ...]] | None = None
    for line in record.lines:
        tokens = shlex.split(line)
        row_tokens: list[str] = []
        for token in tokens:
            if token == "TBLE":
                if current is not None:
                    raise ValueError(
                        f"{_location(record.source_file, record.source_line)}: nested TBLE in source record."
                    )
                current = []
            elif token.lower() == "tble":
                if current is None:
                    continue
                if row_tokens:
                    current.append(tuple(row_tokens))
                    row_tokens = []
                tables.append(tuple(current))
                current = None
            elif current is not None and token != "<":
                row_tokens.append(token)
            elif current is not None and token == "<":
                if row_tokens:
                    current.append(tuple(row_tokens))
                    row_tokens = []
        if current is not None and row_tokens:
            current.append(tuple(row_tokens))
    if current is not None:
        tables.append(tuple(current))
    return tuple(table for table in tables if table)


def _parse_table_metadata(
    record: _SourceRecord,
) -> tuple[SreRtcTableMetadata, ...]:
    tables: list[SreRtcTableMetadata] = []
    prefix_tokens: list[str] = []
    in_table = False

    for line in record.lines:
        for token in shlex.split(line):
            if token == "TBLE":
                if in_table:
                    raise ValueError(
                        f"{_location(record.source_file, record.source_line)}: "
                        "nested TBLE in controller record."
                    )
                tables.append(_table_metadata_from_prefix(prefix_tokens, record))
                prefix_tokens = []
                in_table = True
            elif token.lower() == "tble":
                in_table = False
                prefix_tokens = []
            elif not in_table:
                prefix_tokens.append(token)

    return tuple(tables)


def _table_metadata_from_prefix(
    tokens: list[str],
    record: _SourceRecord,
) -> SreRtcTableMetadata:
    role = next(
        (
            SreRtcTableRole(token)
            for token in reversed(tokens)
            if token in {item.value for item in SreRtcTableRole}
        ),
        None,
    )

    axis_labels: tuple[str, ...] = ()
    for index, token in enumerate(tokens):
        if token != "CLTT":
            continue
        end = next(
            (
                stop
                for stop in range(index + 1, len(tokens))
                if tokens[stop] == "cltt"
            ),
            len(tokens),
        )
        axis_labels = tuple(tokens[index + 1 : end])

    pdin_index = next(
        (
            index
            for index in range(len(tokens) - 1, -1, -1)
            if tokens[index] == "PDIN"
        ),
        None,
    )
    interpolation_code: int | None = None
    periodicity_code: int | None = None
    if pdin_index is not None:
        try:
            interpolation_code = int(tokens[pdin_index + 1])
            periodicity_code = int(tokens[pdin_index + 2])
        except (IndexError, ValueError) as exc:
            raise ValueError(
                f"{_location(record.source_file, record.source_line)}: "
                "controller table has invalid PDIN interpolation/periodicity flags."
            ) from exc

    return SreRtcTableMetadata(
        role=role,
        axis_labels=axis_labels,
        interpolation_code=interpolation_code,
        periodicity_code=periodicity_code,
    )


def _header_tokens(record: _SourceRecord) -> list[str]:
    return shlex.split(record.lines[0])


def _record_id(record: _SourceRecord) -> str | None:
    return _value_after(_header_tokens(record), "id")


def _value_after(tokens: list[str], key: str) -> str | None:
    key_lower = key.lower()
    for index, token in enumerate(tokens[:-1]):
        if token.lower() == key_lower:
            return tokens[index + 1]
    return None


def _values_after(tokens: list[str], key: str, count: int) -> tuple[str, ...]:
    key_lower = key.lower()
    for index, token in enumerate(tokens[:-1]):
        if token.lower() == key_lower:
            return tuple(tokens[index + 1 : index + 1 + count])
    return ()


def _required_value(tokens: list[str], key: str, record: _SourceRecord) -> str:
    value = _value_after(tokens, key)
    if value is None or value == "":
        raise ValueError(f"{_location(record.source_file, record.source_line)}: missing {key} value.")
    return value


def _required_int(tokens: list[str], key: str, record: _SourceRecord) -> int:
    value = _required_value(tokens, key, record)
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(
            f"{_location(record.source_file, record.source_line)}: invalid {key} code {value!r}."
        ) from exc


def _optional_int(value: str, record: _SourceRecord, trigger_id: str, field: str) -> int | None:
    if value in {"", "-1"}:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(
            f"{_location(record.source_file, record.source_line)}: "
            f"trigger {trigger_id} has invalid {field} code {value!r}."
        ) from exc


def _optional_float(value: str | None, record: _SourceRecord, description: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except ValueError as exc:
        raise ValueError(
            f"{_location(record.source_file, record.source_line)}: invalid {description} {value!r}."
        ) from exc
    return None if abs(result) >= _SENTINEL else result


def _parse_time(value: str, record: _SourceRecord, trigger_id: str) -> datetime | None:
    if value in {"", "-1"}:
        return None
    try:
        return datetime.strptime(value, "%Y/%m/%d;%H:%M:%S")
    except ValueError as exc:
        raise ValueError(
            f"{_location(record.source_file, record.source_line)}: "
            f"trigger {trigger_id} has invalid date/time {value!r}."
        ) from exc


def _ensure_unique(ids: Iterable[str], record_type: str) -> None:
    values = tuple(ids)
    if len(values) != len(set(values)):
        duplicates = sorted({value for value in values if values.count(value) > 1})
        raise ValueError(f"Duplicate SRE RTC {record_type} id(s): {', '.join(duplicates)}.")


def _location(source_file: Path, source_line: int) -> str:
    return f"{source_file.name}:{source_line}"
