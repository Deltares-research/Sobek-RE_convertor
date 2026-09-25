from __future__ import annotations

from pathlib import Path

from ...models import SreCaseModel
from .records import RawRecord, load_records


def collect_value_read_details(input_dir: Path, case: SreCaseModel) -> tuple[str, ...]:
    records = _load_all_records(input_dir)
    details: list[str] = []

    for node in case.network.nodes:
        record = _find_record(records, "NODE", node.id)
        details.append(
            f"NODE id={node.id!r} name={node.name!r} x={node.x:g} y={node.y:g} {_source(record)}"
        )
    for branch in case.network.branches:
        record = _find_record(records, "BRCH", branch.id)
        details.append(
            f"BRCH id={branch.id!r} name={branch.name!r} from={branch.from_node_id!r} "
            f"to={branch.to_node_id!r} length={branch.length:g} {_source(record)}"
        )

    for definition in case.cross_section_definitions:
        record = _find_record(records, "CRDS", definition.id)
        level_summary = (
            f"levels_count={len(definition.levels)} "
            f"levels_min={min(definition.levels):g} levels_max={max(definition.levels):g}"
            if definition.levels
            else "levels_count=0 levels_min=empty levels_max=empty"
        )
        details.append(
            f"cross-section definition id={definition.id!r} name={definition.name!r} "
            f"{level_summary} {_source(record)}"
        )
    for location in case.cross_section_locations:
        record = _find_record(records, "CRSN", location.id)
        details.append(
            f"cross-section location id={location.id!r} name={location.name!r} "
            f"branch={location.branch_id!r} chainage={location.chainage:g} definition={location.definition_id!r} "
            f"reference_level={location.reference_level:g} {_source(record)}"
        )

    for boundary in case.boundaries:
        record = _find_record(records, "FLBO", boundary.id)
        details.append(_series_detail("boundary", boundary.id, boundary.name, boundary.series, record, f"node={boundary.node_id!r} quantity={boundary.quantity}"))
    for lateral in case.laterals:
        record = _find_record(records, "FLBR", lateral.id) or _find_record(records, "FLBX", lateral.id)
        details.append(_series_detail("lateral", lateral.id, lateral.name, lateral.series, record, f"branch={lateral.branch_id!r} chainage={lateral.chainage:g}"))

    for roughness in case.roughness:
        record = _find_record(records, "BDFR", roughness.branch_id, attribute="ci")
        details.append(
            f"roughness branch={roughness.branch_id!r} type={roughness.friction_type!r} value={roughness.value:g} {_source(record)}"
        )
    for initial in case.initial_conditions:
        record = _find_record(records, "FLIN", initial.branch_id, attribute="ci")
        details.append(
            f"initial condition branch={initial.branch_id!r} chainage={initial.chainage:g} water_level={initial.water_level:g} {_source(record)}"
        )
    for structure in case.structures:
        record = _find_record(records, "STRU", structure.id)
        details.append(
            f"structure id={structure.id!r} name={structure.name!r} type={structure.structure_type!r} "
            f"branch={structure.branch_id!r} chainage={structure.chainage:g} crest_level={structure.crest_level:g} "
            f"crest_width={structure.crest_width:g} {_source(record)}"
        )

    details.append(
        f"runtime refdate={case.runtime.refdate.isoformat()} tstart={case.runtime.tstart_seconds} "
        f"tstop={case.runtime.tstop_seconds} {_source(_first_record(records, "FLTM"))}"
    )
    morph = case.morphodynamics
    details.append(
        f"morphodynamics morphology_switch={morph.has_morphology_switch} branches_with_grainsize={morph.branch_count_with_grainsize} "
        f"grain_samples={morph.grain_size_sample_count} d50={morph.representative_d50_m} "
        f"sediment_fractions={_values(morph.sediment_fractions_d50_m)} {_source(_first_record(records, "MPIN", "SBST", "TRNS"))}"
    )
    for controller in case.rtc.controllers:
        record = _find_record(records, "CONT", controller.id)
        details.append(
            f"RTC controller id={controller.id!r} name={controller.name!r} type={controller.controller_type!r} "
            f"parameter={controller.controlled_parameter!r} triggers={controller.trigger_ids} {_source(record)}"
        )
    for trigger in case.rtc.triggers:
        record = _find_record(records, "TRIG", trigger.id)
        details.append(
            f"RTC trigger id={trigger.id!r} name={trigger.name!r} type={trigger.trigger_type!r} "
            f"branch={trigger.branch_id!r} chainage={trigger.chainage} {_source(record)}"
        )

    return tuple(details)


def _load_all_records(input_dir: Path) -> list[RawRecord]:
    families = {
        "DEFTOP": {"NODE", "BRCH"}, "DEFGRD": {"GRID"}, "DEFCRS": {"CRSN", "CRDS"},
        "DEFCND": {"FLBO", "FLBR", "FLBX", "FLDI", "FLNO", "FLNX"}, "DEFRUN": {"FLTM"},
        "DEFFRC": {"BDFR"}, "DEFICN": {"FLIN", "MPIN"}, "DEFSUB": {"SBST"},
        "DEFTRN": {"TRNS"}, "DEFSTR": {"STRU", "STCM", "STDS"},
    }
    return [record for stem, keys in families.items() for record in load_records(input_dir, stem, keys)]


def _find_record(records: list[RawRecord], key: str, value: str, attribute: str = "id") -> RawRecord | None:
    return next((record for record in records if record.key == key and record.attrs.get(attribute) == value), None)


def _first_record(records: list[RawRecord], *keys: str) -> RawRecord | None:
    return next((record for record in records if record.key in keys), None)


def _source(record: RawRecord | None) -> str:
    if record is None:
        return "source=not matched"
    return f"source={record.source_file.name} lines={record.source_line_start}-{record.source_line_end}"


def _values(values: tuple[float, ...]) -> str:
    return "[" + ", ".join(f"{value:g}" for value in values) + "]"


def _series_detail(kind: str, identifier: str, name: str, series: tuple, record: RawRecord | None, location: str) -> str:
    if series:
        time_start = series[0].time
        time_end = series[-1].time
        minimum = min(point.value for point in series)
        maximum = max(point.value for point in series)
        summary = (
            f"time_start={time_start!r} time_end={time_end!r} "
            f"minimum={minimum:g} maximum={maximum:g}"
        )
    else:
        summary = "time_start=empty time_end=empty minimum=empty maximum=empty"
    return f"{kind} id={identifier!r} name={name!r} {location} {summary} {_source(record)}"