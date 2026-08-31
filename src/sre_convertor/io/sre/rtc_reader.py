from __future__ import annotations

from pathlib import Path
import shlex

from ...models import SreRtcController, SreRtcSummary, SreRtcTrigger


_SENTINEL = 1.0e9


def read_sre_rtc(input_dir: Path) -> tuple[SreRtcSummary, list[str]]:
    warnings: list[str] = []
    controller_to_structure = _read_controller_structure_links(input_dir)
    controllers: list[SreRtcController] = []
    triggers: list[SreRtcTrigger] = []

    for lines in _iter_records(input_dir, "CNTL"):
        controller = _parse_controller(lines, controller_to_structure)
        if controller is not None:
            controllers.append(controller)

    for lines in _iter_records(input_dir, "TRGR"):
        trigger = _parse_trigger(lines)
        if trigger is not None:
            triggers.append(trigger)

    trigger_ids = {trigger.id for trigger in triggers}
    for controller in controllers:
        missing = [trigger_id for trigger_id in controller.trigger_ids if trigger_id not in trigger_ids]
        if missing:
            warnings.append(f"Controller {controller.id} references missing trigger(s): {', '.join(missing)}.")

    return SreRtcSummary(controllers=tuple(controllers), triggers=tuple(triggers)), warnings


def _iter_records(input_dir: Path, key: str) -> list[list[str]]:
    records: list[list[str]] = []
    current: list[str] = []
    key_upper = key.upper()

    for path in sorted(input_dir.glob("DEFSTR.*")):
        if not path.is_file():
            continue
        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            first = line.split(maxsplit=1)[0].upper()
            if first == key_upper:
                if current:
                    records.append(current)
                current = [line]
                continue
            if current:
                current.append(line)
                if first == key_upper.lower():
                    records.append(current)
                    current = []
        if current:
            records.append(current)
            current = []

    return records


def _read_controller_structure_links(input_dir: Path) -> dict[str, str]:
    links: dict[str, str] = {}
    for lines in _iter_records(input_dir, "STRU"):
        header_tokens = shlex.split(lines[0])
        structure_id = _scalar_after(header_tokens, "id")
        controller_ids = _values_after(header_tokens, "cj", 4)
        if not structure_id:
            continue
        for controller_id in controller_ids:
            if controller_id and controller_id != "-1":
                links[controller_id] = f"ST_{structure_id}"
    return links


def _parse_controller(lines: list[str], controller_to_structure: dict[str, str]) -> SreRtcController | None:
    tokens = shlex.split(lines[0])
    all_tokens = [token for line in lines for token in shlex.split(line)]
    controller_id = _scalar_after(tokens, "id")
    if not controller_id:
        return None

    branch_ids = tuple(value for value in _values_after(tokens, "cb", 5) if value != "-1")
    chainages = tuple(_as_float(value) for value in _values_after(tokens, "cl", 5))
    chainages = tuple(value for value in chainages if value is not None and value < _SENTINEL)
    parameters = _interesting_parameters(
        all_tokens,
        ("ct", "ca", "cf", "mc", "sp", "ui", "ua", "u0", "pf", "if", "df", "va", "si"),
    )

    return SreRtcController(
        id=controller_id,
        name=_scalar_after(tokens, "nm") or controller_id,
        controller_type=_controller_type(tokens, lines),
        controlled_parameter=_controlled_parameter(_scalar_after(tokens, "ca")),
        controlled_structure_id=controller_to_structure.get(controller_id),
        trigger_ids=tuple(value for value in _values_after(tokens, "gi", 4) if value != "-1"),
        observation_branch_id=branch_ids[0] if branch_ids else None,
        observation_chainage=chainages[0] if chainages else None,
        parameters=parameters,
        tables=_extract_tables(lines),
    )


def _parse_trigger(lines: list[str]) -> SreRtcTrigger | None:
    tokens = shlex.split(lines[0])
    trigger_id = _scalar_after(tokens, "id")
    if not trigger_id:
        return None

    chainage = _as_float(_scalar_after(tokens, "tl") or "")
    if chainage is not None and chainage >= _SENTINEL:
        chainage = None

    return SreRtcTrigger(
        id=trigger_id,
        name=_scalar_after(tokens, "nm") or trigger_id,
        trigger_type=_trigger_type(_scalar_after(tokens, "ty")),
        branch_id=_none_if_missing(_scalar_after(tokens, "tb")),
        chainage=chainage,
        tables=_extract_tables(lines),
    )


def _scalar_after(tokens: list[str], key: str) -> str | None:
    key_lower = key.lower()
    for idx, token in enumerate(tokens[:-1]):
        if token.lower() == key_lower:
            return tokens[idx + 1]
    return None


def _values_after(tokens: list[str], key: str, count: int) -> tuple[str, ...]:
    key_lower = key.lower()
    for idx, token in enumerate(tokens[:-1]):
        if token.lower() == key_lower:
            return tuple(tokens[idx + 1 : idx + 1 + count])
    return tuple()


def _interesting_parameters(tokens: list[str], keys: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    values: list[tuple[str, str]] = []
    for key in keys:
        value = _scalar_after(tokens, key)
        if value is not None and value != "-1" and value != "9.9999e+009":
            values.append((key.upper(), value))
    return tuple(values)


def _extract_tables(lines: list[str]) -> tuple[tuple[tuple[str, ...], ...], ...]:
    tables: list[tuple[tuple[str, ...], ...]] = []
    current: list[tuple[str, ...]] | None = None

    for line in lines:
        tokens = shlex.split(line)
        idx = 0
        while idx < len(tokens):
            token = tokens[idx]
            if token == "TBLE":
                current = []
                idx += 1
                continue
            if token.lower() == "tble":
                if current is not None:
                    tables.append(tuple(current))
                    current = None
                idx += 1
                continue
            if token == "<":
                idx += 1
                continue
            if current is not None:
                row: list[str] = []
                while idx < len(tokens) and tokens[idx] != "<" and tokens[idx].lower() != "tble":
                    row.append(tokens[idx])
                    idx += 1
                if row:
                    current.append(tuple(row))
                else:
                    idx += 1
                continue
            idx += 1

    return tuple(table for table in tables if table)


def _controller_type(tokens: list[str], lines: list[str]) -> str:
    joined = " ".join(lines).lower()
    if "pid" in (_scalar_after(tokens, "nm") or "").lower():
        return "pid"
    if "hydraulic controller" in joined:
        return "hydraulic"
    if "time controller" in joined:
        return "time"
    code = _scalar_after(tokens, "ct")
    if code == "0":
        return "time"
    if code == "1":
        return "hydraulic"
    return "unknown"


def _controlled_parameter(code: str | None) -> str:
    return {"0": "crest_level", "1": "crest_width", "2": "gate_height"}.get(code or "", "unknown")


def _trigger_type(code: str | None) -> str:
    return {"1": "time", "2": "hydraulic", "3": "both"}.get(code or "", "unknown")


def _none_if_missing(value: str | None) -> str | None:
    if value is None or value == "-1":
        return None
    return value


def _as_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None
