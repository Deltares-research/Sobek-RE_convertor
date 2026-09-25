from __future__ import annotations

from pathlib import Path

from ...models import SreCaseModel
from .records import RawRecord, load_records


def collect_value_read_details(input_dir: Path, case: SreCaseModel) -> tuple[str, ...]:
    records = _load_all_records(input_dir)
    details: list[str] = []

    for node in case.network.nodes:
        record = _find_record(records, "NODE", node.id)
        details.append(_detail("Node", (f"id={node.id!r}", f"name={node.name!r}", f"x={node.x:g}", f"y={node.y:g}", _source(record))))
    for branch in case.network.branches:
        record = _find_record(records, "BRCH", branch.id)
        details.append(_detail("Branch", (f"id={branch.id!r}", f"name={branch.name!r}", f"from={branch.from_node_id!r}", f"to={branch.to_node_id!r}", f"length={branch.length:g}", _source(record))))

    for definition in case.cross_section_definitions:
        record = _find_record(records, "CRDS", definition.id)
        level_summary = (
            f"levels_count={len(definition.levels)} "
            f"levels_min={min(definition.levels):g} levels_max={max(definition.levels):g}"
            if definition.levels
            else "levels_count=0 levels_min=empty levels_max=empty"
        )
        details.append(_detail("Cross-section definition", (f"id={definition.id!r}", f"name={definition.name!r}", *level_summary.split(), f"main_channel_width={definition.main_width:g}", f"floodplain_1_width={definition.fp1_width:g}", f"floodplain_2_width={definition.fp2_width:g}", _source(record))))
    for location in case.cross_section_locations:
        record = _find_record(records, "CRSN", location.id)
        details.append(_detail("Cross-section location", (f"id={location.id!r}", f"name={location.name!r}", f"branch={location.branch_id!r}", f"chainage={location.chainage:g}", f"definition={location.definition_id!r}", f"reference_level={location.reference_level:g}", _source(record))))

    for boundary in case.boundaries:
        record = _find_series_record(records, {"FLBO"}, boundary.id)
        details.append(
            _series_detail(
                "boundary",
                boundary.id,
                boundary.name,
                boundary.series,
                record,
                (
                    f"node={boundary.node_id!r}",
                    f"node_name={boundary.node_name!r}",
                    f"quantity={boundary.quantity}",
                ),
            )
        )
    for lateral in case.laterals:
        record = _find_series_record(records, {"FLBR"}, lateral.id) or _find_series_record(records, {"FLBX"}, lateral.id)
        details.append(
            _series_detail(
                "lateral",
                lateral.id,
                lateral.name,
                lateral.series,
                record,
                (f"branch={lateral.branch_id!r}", f"chainage={lateral.chainage:g}"),
            )
        )

    for roughness in case.roughness:
        record = _find_record(records, "BDFR", roughness.branch_id, attribute="ci")
        for section_name, chainages, values in roughness.section_profiles:
            for chainage, value in zip(chainages, values):
                details.append(_detail("Roughness", (f"branch={roughness.branch_id!r}", f"section={section_name!r}", f"type={roughness.friction_type!r}", f"chainage={chainage:g}", f"value={value:g}", _source(record))))
    for initial in case.initial_conditions:
        record = _find_record(records, "FLIN", initial.branch_id, attribute="ci")
        details.append(_detail("Initial condition", (f"branch={initial.branch_id!r}", f"chainage={initial.chainage:g}", f"water_level={initial.water_level:g}", _source(record))))
    for structure in case.structures:
        record = _find_record(records, "STRU", structure.id)
        details.append(_detail("Structure", (f"id={structure.id!r}", f"name={structure.name!r}", f"type={structure.structure_type!r}", f"branch={structure.branch_id!r}", f"chainage={structure.chainage:g}", f"crest_level={structure.crest_level:g}", f"crest_width={structure.crest_width:g}", _source(record))))

    details.append(_detail("Runtime", (f"refdate={case.runtime.refdate.isoformat()}", f"tstart={case.runtime.tstart_seconds}", f"tstop={case.runtime.tstop_seconds}", _source(_first_record(records, "FLTM")))))
    morph = case.morphodynamics
    details.append(_detail("Morphodynamics", (f"morphology_switch={morph.has_morphology_switch}", f"branches_with_grainsize={morph.branch_count_with_grainsize}", f"grain_samples={morph.grain_size_sample_count}", f"d50={morph.representative_d50_m}", f"sediment_fractions={_values(morph.sediment_fractions_d50_m)}", _source(_first_record(records, "MPIN", "SBST", "TRNS")))))
    for controller in case.rtc.controllers:
        record = _find_record(records, "CONT", controller.id)
        details.append(_detail("RTC controller", (f"id={controller.id!r}", f"name={controller.name!r}", f"type={controller.controller_type!r}", f"parameter={controller.controlled_parameter!r}", f"triggers={controller.trigger_ids}", _source(record))))
    for trigger in case.rtc.triggers:
        record = _find_record(records, "TRIG", trigger.id)
        details.append(_detail("RTC trigger", (f"id={trigger.id!r}", f"name={trigger.name!r}", f"type={trigger.trigger_type!r}", f"branch={trigger.branch_id!r}", f"chainage={trigger.chainage}", _source(record))))

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


def _find_series_record(records: list[RawRecord], keys: set[str], value: str) -> RawRecord | None:
    return next(
        (
            record
            for record in records
            if record.key in keys and record.attrs.get("id") == value and record.tables
        ),
        None,
    )


def _first_record(records: list[RawRecord], *keys: str) -> RawRecord | None:
    return next((record for record in records if record.key in keys), None)


def _source(record: RawRecord | None) -> str:
    if record is None:
        return "source=not matched"
    return f"source={record.source_file.name} lines={record.source_line_start}-{record.source_line_end}"


def _values(values: tuple[float, ...]) -> str:
    return "[" + ", ".join(f"{value:g}" for value in values) + "]"


def _series_detail(
    kind: str,
    identifier: str,
    name: str,
    series: tuple,
    record: RawRecord | None,
    location_fields: tuple[str, ...],
) -> str:
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
    fields = (
        f"id={identifier!r}",
        f"name={name!r}",
        *location_fields,
        *summary.split(),
        _source(record),
    )
    return _detail(kind.capitalize(), fields)


def _detail(title: str, fields: tuple[str, ...]) -> str:
    return "\n".join([title, *(f"  {field}" for field in fields)])