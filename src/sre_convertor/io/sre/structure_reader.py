from __future__ import annotations

from pathlib import Path
import shlex

from ...models import Structure
from .records import RawRecord, load_records


def read_structures(input_dir: Path) -> tuple[tuple[Structure, ...], list[str]]:
    warnings: list[str] = []

    records = load_records(input_dir, "DEFSTR", {"STRU", "STCM", "STDS"})

    location_by_id: dict[str, RawRecord] = {}
    compound_location_by_id: dict[str, RawRecord] = {}
    structure_to_compound_id = _read_structure_to_compound_links(input_dir)
    definition_link_by_id: dict[str, str] = {}
    definition_by_id: dict[str, RawRecord] = {}

    for record in records:
        if record.key == "STRU" and "dd" not in record.attrs and "ci" in record.attrs and "lc" in record.attrs:
            structure_id = record.attrs.get("id")
            if structure_id:
                location_by_id[structure_id] = record
        elif record.key == "STCM":
            compound_id = record.attrs.get("id")
            if not compound_id:
                continue
            if "ci" in record.attrs and "lc" in record.attrs:
                compound_location_by_id[compound_id] = record
        elif record.key == "STRU" and "dd" in record.attrs:
            structure_id = record.attrs.get("id")
            if structure_id:
                definition_link_by_id[structure_id] = record.attrs["dd"]
        elif record.key == "STDS":
            definition_id = record.attrs.get("id")
            if definition_id:
                definition_by_id[definition_id] = record

    structures: list[Structure] = []
    for structure_id, location_record in sorted(location_by_id.items()):
        definition_id = definition_link_by_id.get(structure_id)
        if not definition_id:
            warnings.append(f"Structure {structure_id} has no linked definition id in DEFSTR.*.")
            continue

        definition_record = definition_by_id.get(definition_id)
        if definition_record is None:
            warnings.append(f"Structure {structure_id} references missing STDS definition {definition_id}.")
            continue

        branch_id = location_record.attrs.get("ci", "")
        chainage = _as_float(location_record.attrs.get("lc"), 0.0)

        if branch_id == "-1":
            mapped = _match_compound_location(
                structure_id,
                location_record,
                structure_to_compound_id,
                compound_location_by_id,
            )
            if mapped is None:
                warnings.append(
                    f"Structure {structure_id} has no direct branch location and could not be matched to STCM location."
                )
                continue
            branch_id, chainage = mapped

        structure_type = _map_structure_type(definition_record)
        crest_level = _first_valid_float(definition_record, ["zs", "cl", "z1"], default=0.0)
        crest_width = _first_valid_float(definition_record, ["cw", "w1", "wl", "wr"], default=1.0)

        gate_opening_width = None
        gate_lower_edge_level = None
        if structure_type == "orifice":
            gate_opening_width = _first_valid_float(definition_record, ["wl", "w1", "cw"], default=crest_width)
            gate_lower_edge_level = _first_valid_float(definition_record, ["zs", "z1", "cl"], default=crest_level)

        structures.append(
            Structure(
                id=f"ST_{structure_id}",
                name=location_record.attrs.get("nm", structure_id),
                branch_id=branch_id,
                chainage=chainage,
                structure_type=structure_type,
                crest_level=crest_level,
                crest_width=crest_width,
                gate_opening_width=gate_opening_width,
                gate_lower_edge_level=gate_lower_edge_level,
            )
        )

    return tuple(structures), warnings


def _match_compound_location(
    structure_id: str,
    location_record: RawRecord,
    structure_to_compound_id: dict[str, str],
    compound_location_by_id: dict[str, RawRecord],
) -> tuple[str, float] | None:
    compound_id = structure_to_compound_id.get(structure_id)
    if compound_id:
        compound_record = compound_location_by_id.get(compound_id)
        if compound_record is not None:
            branch_id = compound_record.attrs.get("ci")
            chainage = _as_float(compound_record.attrs.get("lc"), None)
            if branch_id and chainage is not None:
                return branch_id, chainage

    # Fallback heuristic if explicit compound membership was unavailable.
    location_name = location_record.attrs.get("nm", "").lower()
    for candidate in compound_location_by_id.values():
        candidate_name = candidate.attrs.get("nm", "").lower()
        if not candidate_name:
            continue
        if candidate_name.split()[0] in location_name:
            branch_id = candidate.attrs.get("ci")
            chainage = _as_float(candidate.attrs.get("lc"), None)
            if branch_id and chainage is not None:
                return branch_id, chainage
    return None


def _map_structure_type(definition_record: RawRecord) -> str:
    ty = definition_record.attrs.get("ty")
    if ty == "2":
        return "orifice"
    return "weir"


def _first_valid_float(record: RawRecord, keys: list[str], default: float) -> float:
    for key in keys:
        value = _as_float(record.attrs.get(key), None)
        if value is not None and value < 1.0e9:
            return value
    return default


def _as_float(value: str | None, default: float | None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _read_structure_to_compound_links(input_dir: Path) -> dict[str, str]:
    links: dict[str, str] = {}

    for path in sorted(input_dir.glob("DEFSTR.*")):
        if not path.is_file():
            continue

        current_compound_id: str | None = None
        in_dlst = False

        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line:
                continue

            tokens = shlex.split(line)
            if not tokens:
                continue

            key = tokens[0].upper()
            if key == "STCM":
                current_compound_id = None
                for idx in range(1, len(tokens) - 1):
                    if tokens[idx].lower() == "id":
                        current_compound_id = tokens[idx + 1].strip("'")
                        break
                in_dlst = False
                continue

            if key == "DLST":
                in_dlst = not in_dlst
                continue

            if not in_dlst or not current_compound_id:
                continue

            for token in tokens:
                member_id = token.strip("'")
                if member_id and member_id != "-1":
                    links[member_id] = current_compound_id

    return links
