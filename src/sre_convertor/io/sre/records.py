from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex


@dataclass(frozen=True)
class RawRecord:
    key: str
    attrs: dict[str, str]
    tables: tuple[tuple[tuple[str, ...], ...], ...]
    source_file: Path


def normalize_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value


def list_family_files(input_dir: Path, stem: str) -> list[Path]:
    files = sorted(p for p in input_dir.glob(f"{stem}.*") if p.is_file())
    return files


def load_records(input_dir: Path, stem: str, keys: set[str]) -> list[RawRecord]:
    records: list[RawRecord] = []
    for path in list_family_files(input_dir, stem):
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        records.extend(_parse_file_records(lines, path, keys))
    return records


def _parse_file_records(lines: list[str], source_file: Path, keys: set[str]) -> list[RawRecord]:
    grouped_lines: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        token = stripped.split(maxsplit=1)[0].upper()
        if token in keys:
            if current:
                grouped_lines.append(current)
            current = [stripped]
        elif current:
            current.append(stripped)

    if current:
        grouped_lines.append(current)

    return [_parse_record(chunk, source_file) for chunk in grouped_lines]


def _parse_record(lines: list[str], source_file: Path) -> RawRecord:
    first_tokens = _split_tokens(lines[0])
    key = first_tokens[0].upper()

    attrs: dict[str, str] = {}
    tables: list[tuple[tuple[str, ...], ...]] = []
    current_table: list[tuple[str, ...]] | None = None

    for line_idx, line in enumerate(lines):
        tokens = _split_tokens(line)
        if not tokens:
            continue

        if current_table is not None:
            if tokens[0].lower() == "tble":
                tables.append(tuple(current_table))
                current_table = None
                # parse potential attributes after tble on same line
                if len(tokens) > 1:
                    _consume_attributes(tokens[1:], attrs)
                continue

            filtered = tuple(normalize_value(t) for t in tokens if t != "<")
            if filtered:
                current_table.append(filtered)
            continue

        start = 1 if line_idx == 0 else 0
        payload = tokens[start:]
        i = 0
        while i < len(payload):
            token = payload[i]
            if token.upper() == "TBLE":
                current_table = []
                i += 1
                continue

            if i + 1 >= len(payload):
                break

            key_token = payload[i].lower()
            value_token = normalize_value(payload[i + 1])
            attrs[key_token] = value_token
            i += 2

    if current_table is not None:
        tables.append(tuple(current_table))

    return RawRecord(key=key, attrs=attrs, tables=tuple(tables), source_file=source_file)


def _split_tokens(line: str) -> list[str]:
    return shlex.split(line)


def _consume_attributes(tokens: list[str], attrs: dict[str, str]) -> None:
    i = 0
    while i + 1 < len(tokens):
        attrs[tokens[i].lower()] = normalize_value(tokens[i + 1])
        i += 2
