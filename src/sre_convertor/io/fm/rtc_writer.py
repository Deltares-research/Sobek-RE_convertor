from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import json
import math
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET
from typing import Protocol, TypeVar

from ...models import Branch, NetworkModel, Node, RuntimeSettings, Structure
from ..sre.rtc_reader import (
    SreRtcComparison,
    SreRtcController,
    SreRtcControllerType,
    SreRtcControlledParameter,
    SreRtcSummary,
    SreRtcTableMetadata,
    SreRtcTableRole,
    SreRtcTrigger,
    SreRtcTriggerCondition,
    SreRtcTriggerType,
)
from .dimr_writer import RtcCoupling, RtcCouplingItem


FEWS_NAMESPACE = "http://www.wldelft.nl/fews"
PI_NAMESPACE = "http://www.wldelft.nl/fews/PI"
OPENDA_NAMESPACE = "http://www.openda.org"
XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"
RTC_TIMESTEP_SECONDS = 600
OBSERVATION_FILE_NAME = "rtc_observations.xyn"
RTC_SCHEMA_DIRECTORY = Path(__file__).resolve().parents[4] / "data" / "fm" / "rtc"


class _Identified(Protocol):
    id: str


_IdentifiedT = TypeVar("_IdentifiedT", bound=_Identified)


class RtcConversionError(ValueError):
    pass


class _RuleKind(str, Enum):
    TIME_ABSOLUTE = "timeAbsolute"
    LOOKUP_TABLE = "lookupTable"


@dataclass(frozen=True)
class _Observation:
    branch_id: str
    chainage: float
    name: str
    series_id: str
    x: float
    y: float


@dataclass(frozen=True)
class _ControllerPlan:
    controller: SreRtcController
    structure: Structure
    trigger: SreRtcTrigger
    condition: SreRtcTriggerCondition
    observation: _Observation
    output_id: str
    rule_id: str
    status_id: str
    actuator_target: str
    actuator_quantity: str
    rule_kind: _RuleKind
    schedule_series_id: str | None = None
    schedule_rows: tuple[tuple[datetime, float], ...] = ()
    schedule_interpolation: str | None = None
    maximum_output: float | None = None
    lookup_rows: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class _OutputPlan:
    output_id: str
    structure: Structure
    actuator_quantity: str
    actuator_target: str
    initial_value: float
    controllers: tuple[_ControllerPlan, ...]


@dataclass(frozen=True)
class RtcCompilation:
    rtc_coupling: RtcCoupling
    observation_file_name: str
    observation_file_content: str
    file_contents: tuple[tuple[str, bytes], ...]
    timestep_seconds: int


def compile_sre_rtc(
    summary: SreRtcSummary,
    network: NetworkModel,
    structures: tuple[Structure, ...],
    runtime: RuntimeSettings,
    *,
    timestep_seconds: int = RTC_TIMESTEP_SECONDS,
) -> RtcCompilation:
    _rtc_schema_files()
    errors: list[str] = []
    if not summary.controllers:
        errors.append("No SRE CNTL records were found; there are no controls to compile.")

    if timestep_seconds <= 0:
        errors.append(f"RTC timestep must be positive, got {timestep_seconds}.")
    elif (
        runtime.tstop_seconds <= runtime.tstart_seconds
        or runtime.tstart_seconds % timestep_seconds != 0
        or runtime.tstop_seconds % timestep_seconds != 0
    ):
        errors.append(
            "The runtime start/stop interval must be positive and aligned to the "
            f"{timestep_seconds}s RTC timestep."
        )

    runtime_start = runtime.refdate + timedelta(seconds=runtime.tstart_seconds)
    runtime_stop = runtime.refdate + timedelta(seconds=runtime.tstop_seconds)
    branch_by_id = _unique_by_id(network.branches, "branch", errors)
    node_by_id = _unique_by_id(network.nodes, "node", errors)
    structure_by_id = _unique_by_id(structures, "structure", errors)
    triggers_by_id = {trigger.id: trigger for trigger in summary.triggers}

    candidates: list[_ControllerPlan] = []
    observations: dict[str, _Observation] = {}

    for controller in sorted(summary.controllers, key=lambda item: item.id):
        structure_id = controller.controlled_structure_id
        structure = structure_by_id.get(structure_id or "")
        if structure is None:
            errors.append(
                f"Controller {controller.id} is not linked to a converted structure "
                f"(SRE link: {structure_id or 'missing'})."
            )
            continue

        actuator = _actuator_target(controller, structure, errors)
        if actuator is None:
            continue
        actuator_target, actuator_quantity, parameter_name = actuator
        output_id = f"output_{_safe_identifier(structure.id)}_{parameter_name}"

        if (
            controller.controlled_parameter is SreRtcControlledParameter.CREST_LEVEL
            and (
                not math.isfinite(structure.crest_level)
                or abs(structure.crest_level) >= 1.0e9
            )
        ):
            errors.append(
                f"Controller {controller.id} targets structure {structure.id} whose "
                "initial crest level is invalid for RTC state."
            )

        if (
            controller.controlled_parameter is SreRtcControlledParameter.GATE_HEIGHT
            and (
                structure.gate_height is None
                or not math.isfinite(structure.gate_height)
                or abs(structure.gate_height) >= 1.0e9
            )
        ):
            errors.append(
                f"Controller {controller.id} targets structure {structure.id} whose "
                "initial gate height is unavailable for RTC state."
            )

        active_trigger_ids = controller.active_trigger_ids
        if len(active_trigger_ids) != 1:
            errors.append(
                f"Controller {controller.id} has {len(active_trigger_ids)} active trigger "
                "slots; only one active trigger per controller is currently supported."
            )
            continue

        trigger = triggers_by_id.get(active_trigger_ids[0])
        if trigger is None:
            errors.append(
                f"Controller {controller.id} references missing trigger {active_trigger_ids[0]}."
            )
            continue

        observation = _resolve_observation(
            controller,
            trigger,
            branch_by_id,
            node_by_id,
            errors,
        )
        if observation is None:
            continue
        observations[observation.series_id] = observation

        if trigger.trigger_type is not SreRtcTriggerType.HYDRAULIC:
            errors.append(
                f"Trigger {trigger.id} for controller {controller.id} has unsupported "
                f"trigger type {trigger.trigger_type.name}; only hydraulic triggers are supported."
            )
            continue
        if len(trigger.conditions) != 1:
            errors.append(
                f"Hydraulic trigger {trigger.id} has {len(trigger.conditions)} condition rows; "
                "only a single strict comparison is supported."
            )
            continue

        condition = trigger.conditions[0]
        if condition.comparison is None or condition.threshold is None:
            errors.append(
                f"Hydraulic trigger {trigger.id} has no supported comparison/threshold."
            )
            continue
        if condition.enable_code is not None or condition.combination_code is not None:
            errors.append(
                f"Hydraulic trigger {trigger.id} uses on/off or and/or flags whose "
                "combination semantics have not been verified."
            )
            continue

        rule_kind: _RuleKind | None = None
        schedule_rows: tuple[tuple[datetime, float], ...] = ()
        schedule_interpolation: str | None = None
        maximum_output: float | None = None
        lookup_rows: tuple[tuple[float, float], ...] = ()
        if controller.controller_type is SreRtcControllerType.TIME:
            schedule_rows, schedule_interpolation, maximum_output = _compile_time_schedule(
                controller,
                runtime_start,
                runtime_stop,
                errors,
            )
            if schedule_rows:
                rule_kind = _RuleKind.TIME_ABSOLUTE
        elif controller.controller_type is SreRtcControllerType.HYDRAULIC:
            lookup_rows = _parse_hydraulic_table(controller, errors)
            if lookup_rows:
                rule_kind = _RuleKind.LOOKUP_TABLE
        else:
            errors.append(
                f"Controller {controller.id} has unsupported controller type "
                f"{controller.controller_type.name} (ct={controller.type_code})."
            )
            continue

        if rule_kind is None:
            continue

        candidates.append(
            _ControllerPlan(
                controller=controller,
                structure=structure,
                trigger=trigger,
                condition=condition,
                observation=observation,
                output_id=output_id,
                rule_id=f"rule_controller_{_safe_identifier(controller.id)}",
                status_id=(
                    f"status_controller_{_safe_identifier(controller.id)}_"
                    f"trigger_{_safe_identifier(trigger.id)}"
                ),
                actuator_target=actuator_target,
                actuator_quantity=actuator_quantity,
                rule_kind=rule_kind,
                schedule_series_id=(
                    f"time_schedule_controller_{_safe_identifier(controller.id)}"
                    if schedule_rows
                    else None
                ),
                schedule_rows=schedule_rows,
                schedule_interpolation=schedule_interpolation,
                maximum_output=maximum_output,
                lookup_rows=lookup_rows,
            )
        )

    _check_trigger_groups(candidates, errors)

    if errors:
        unique_errors = tuple(dict.fromkeys(errors))
        raise RtcConversionError(
            "SRE RTC cannot be converted faithfully; no RTC package was written:\n"
            + "\n".join(f"- {error}" for error in unique_errors)
        )

    output_plans = _group_outputs(candidates)
    ordered_observations = tuple(
        observations[key] for key in sorted(observations)
    )
    file_contents = _build_rtc_files(
        output_plans,
        ordered_observations,
        runtime_start,
        runtime_stop,
        timestep_seconds,
    )
    observation_file_content = "".join(
        f"{observation.x:.3f} {observation.y:.3f} {observation.name}\n"
        for observation in ordered_observations
    )
    coupling = RtcCoupling(
        flow_to_rtc=tuple(
            RtcCouplingItem(
                source_name=f"observations/{observation.name}/water_level",
                target_name=observation.series_id,
            )
            for observation in ordered_observations
        ),
        rtc_to_flow=tuple(
            RtcCouplingItem(
                source_name=output.output_id,
                target_name=output.actuator_target,
            )
            for output in output_plans
        ),
    )
    return RtcCompilation(
        rtc_coupling=coupling,
        observation_file_name=OBSERVATION_FILE_NAME,
        observation_file_content=observation_file_content,
        file_contents=file_contents,
        timestep_seconds=timestep_seconds,
    )


def write_sre_rtc_package(
    compilation: RtcCompilation,
    rtc_directory: Path,
    dflowfm_directory: Path,
) -> list[Path]:
    schema_files = _rtc_schema_files()
    created_files: list[Path] = []

    for relative_path, content in compilation.file_contents:
        target_path = rtc_directory / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)
        created_files.append(target_path)

    schema_directory = rtc_directory / "xsd_dir"
    schema_directory.mkdir(parents=True, exist_ok=True)
    for schema_path in schema_files:
        target_path = schema_directory / schema_path.name
        shutil.copy2(schema_path, target_path)
        created_files.append(target_path)

    observation_path = dflowfm_directory / compilation.observation_file_name
    observation_path.parent.mkdir(parents=True, exist_ok=True)
    observation_path.write_text(compilation.observation_file_content, encoding="utf-8")
    created_files.append(observation_path)
    return created_files


def _active_controller_table(
    controller: SreRtcController,
    role: SreRtcTableRole,
    errors: list[str],
) -> tuple[tuple[tuple[str, ...], ...], SreRtcTableMetadata] | None:
    if len(controller.tables) != len(controller.table_metadata):
        errors.append(
            f"Controller {controller.id} has {len(controller.tables)} TBLE tables but "
            f"{len(controller.table_metadata)} table metadata blocks."
        )
        return None

    matches = [
        (table, metadata)
        for table, metadata in zip(controller.tables, controller.table_metadata)
        if metadata.role is role
    ]
    if len(matches) != 1:
        roles = ", ".join(
            metadata.role.value if metadata.role is not None else "unknown"
            for metadata in controller.table_metadata
        )
        errors.append(
            f"Controller {controller.id} has {len(matches)} {role.value!r} tables "
            f"(table roles: {roles or 'none'}); exactly one active table is required."
        )
        return None

    table, metadata = matches[0]
    if metadata.interpolation_code != 0:
        errors.append(
            f"Controller {controller.id} {role.value} table uses unsupported "
            f"PDIN interpolation code {metadata.interpolation_code!r}; "
            "only SRE continuous interpolation (code 0) is supported."
        )
        return None
    if metadata.periodicity_code != 0:
        errors.append(
            f"Controller {controller.id} {role.value} table uses unsupported "
            f"PDIN periodicity code {metadata.periodicity_code!r}; "
            "only non-periodic tables (code 0) are supported."
        )
        return None
    if len(metadata.axis_labels) != 2:
        errors.append(
            f"Controller {controller.id} {role.value} table has axis labels "
            f"{metadata.axis_labels!r}; exactly two axes are required."
        )
        return None
    return table, metadata


def _compile_time_schedule(
    controller: SreRtcController,
    runtime_start: datetime,
    runtime_stop: datetime,
    errors: list[str],
) -> tuple[tuple[tuple[datetime, float], ...], str | None, float | None]:
    active_table = _active_controller_table(
        controller,
        SreRtcTableRole.TIME_CONTROLLER,
        errors,
    )
    if active_table is None:
        return (), None, None
    rows, metadata = active_table
    if metadata.axis_labels[0].casefold() != "time":
        errors.append(
            f"Time controller {controller.id} active table has unexpected time axis "
            f"{metadata.axis_labels[0]!r}."
        )
        return (), None, None
    expected_output_axis = (
        "crest level"
        if controller.controlled_parameter is SreRtcControlledParameter.CREST_LEVEL
        else "gate height"
    )
    if expected_output_axis not in metadata.axis_labels[1].casefold():
        errors.append(
            f"Time controller {controller.id} active table has unexpected output axis "
            f"{metadata.axis_labels[1]!r}; expected {expected_output_axis}."
        )
        return (), None, None

    if not rows:
        errors.append(f"Time controller {controller.id} has no schedule rows.")
        return (), None, None

    parsed_rows: list[tuple[datetime, float]] = []
    for row_index, row in enumerate(rows, start=1):
        if len(row) != 2:
            errors.append(
                f"Time controller {controller.id} schedule row {row_index} has "
                f"{len(row)} values; expected date and value."
            )
            return (), None, None
        try:
            timestamp = datetime.strptime(row[0], "%Y/%m/%d;%H:%M:%S")
            value = float(row[1])
        except ValueError:
            errors.append(
                f"Time controller {controller.id} has an invalid schedule row "
                f"{row_index}: {row!r}."
            )
            return (), None, None
        if not math.isfinite(value) or abs(value) >= 1.0e9:
            errors.append(
                f"Time controller {controller.id} schedule row {row_index} has "
                f"invalid/sentinel value {row[1]!r}."
            )
            return (), None, None
        if parsed_rows and timestamp <= parsed_rows[-1][0]:
            errors.append(
                f"Time controller {controller.id} schedule dates are not strictly "
                "increasing."
            )
            return (), None, None
        parsed_rows.append((timestamp, value))

    if runtime_stop <= runtime_start:
        errors.append(
            f"Time controller {controller.id} cannot cover non-positive runtime "
            f"{runtime_start.isoformat(sep=' ')} to {runtime_stop.isoformat(sep=' ')}."
        )
        return (), None, None

    schedule_rows = [
        (runtime_start, _schedule_value(parsed_rows, runtime_start)),
        *(
            row
            for row in parsed_rows
            if runtime_start < row[0] < runtime_stop
        ),
        (runtime_stop, _schedule_value(parsed_rows, runtime_stop)),
    ]
    return tuple(schedule_rows), "LINEAR", max(value for _, value in parsed_rows)


def _schedule_value(
    rows: list[tuple[datetime, float]],
    timestamp: datetime,
) -> float:
    if timestamp <= rows[0][0]:
        return rows[0][1]
    if timestamp >= rows[-1][0]:
        return rows[-1][1]

    for (left_time, left_value), (right_time, right_value) in zip(rows, rows[1:]):
        if left_time <= timestamp <= right_time:
            fraction = (timestamp - left_time).total_seconds() / (
                right_time - left_time
            ).total_seconds()
            return left_value + (right_value - left_value) * fraction
    raise ValueError(f"Unable to interpolate controller schedule at {timestamp!r}.")


def _parse_hydraulic_table(
    controller: SreRtcController,
    errors: list[str],
) -> tuple[tuple[float, float], ...]:
    active_table = _active_controller_table(
        controller,
        SreRtcTableRole.HYDRAULIC_CONTROLLER,
        errors,
    )
    if active_table is None:
        return ()
    rows, metadata = active_table
    expected_output_axis = (
        "crest level"
        if controller.controlled_parameter is SreRtcControlledParameter.CREST_LEVEL
        else "gate height"
    )
    if (
        "water level" not in metadata.axis_labels[0].casefold()
        or expected_output_axis not in metadata.axis_labels[1].casefold()
    ):
        errors.append(
            f"Hydraulic controller {controller.id} active table has unexpected axes "
            f"{metadata.axis_labels!r}; expected water level and {expected_output_axis}."
        )
        return ()
    if len(rows) < 2:
        errors.append(
            f"Hydraulic controller {controller.id} lookup table has fewer than two rows."
        )
        return ()

    parsed_rows: list[tuple[float, float]] = []
    for row_index, row in enumerate(rows, start=1):
        if len(row) != 2:
            errors.append(
                f"Hydraulic controller {controller.id} lookup row {row_index} has "
                f"{len(row)} values; expected two numeric values."
            )
            return ()
        try:
            x_value, y_value = float(row[0]), float(row[1])
        except ValueError:
            errors.append(
                f"Hydraulic controller {controller.id} has a non-numeric lookup row "
                f"{row_index}: {row!r}."
            )
            return ()
        if (
            not math.isfinite(x_value)
            or not math.isfinite(y_value)
            or abs(x_value) >= 1.0e9
            or abs(y_value) >= 1.0e9
        ):
            errors.append(
                f"Hydraulic controller {controller.id} lookup row {row_index} "
                "contains an invalid/sentinel value."
            )
            return ()
        if parsed_rows and x_value <= parsed_rows[-1][0]:
            errors.append(
                f"Hydraulic controller {controller.id} lookup x values are not "
                "strictly increasing."
            )
            return ()
        parsed_rows.append((x_value, y_value))
    return tuple(parsed_rows)


def _check_trigger_groups(
    candidates: list[_ControllerPlan],
    errors: list[str],
) -> None:
    groups: dict[str, list[_ControllerPlan]] = {}
    for candidate in candidates:
        groups.setdefault(candidate.output_id, []).append(candidate)

    for output_id, group in sorted(groups.items()):
        if len(group) < 2:
            continue
        ordered = sorted(group, key=lambda item: item.controller.id)
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                if left.observation.series_id != right.observation.series_id:
                    errors.append(
                        f"Controllers {left.controller.id} and {right.controller.id} "
                        f"drive {output_id} from different observations; trigger overlap "
                        "cannot be resolved."
                    )
                    continue
                _check_condition_pair(left, right, errors)


def _check_condition_pair(
    left: _ControllerPlan,
    right: _ControllerPlan,
    errors: list[str],
) -> None:
    left_condition = left.condition
    right_condition = right.condition
    if left_condition.comparison is right_condition.comparison:
        errors.append(
            f"Controllers {left.controller.id} and {right.controller.id} drive the same "
            "structure parameter with overlapping same-direction triggers."
        )
        return

    less = (
        (left, left_condition)
        if left_condition.comparison is SreRtcComparison.LESS_THAN
        else (right, right_condition)
    )
    greater = (
        (left, left_condition)
        if left_condition.comparison is SreRtcComparison.GREATER_THAN
        else (right, right_condition)
    )
    less_threshold = less[1].threshold
    greater_threshold = greater[1].threshold
    if less_threshold is None or greater_threshold is None:
        return
    if greater_threshold < less_threshold:
        errors.append(
            f"Controllers {less[0].controller.id} and {greater[0].controller.id} have "
            f"overlapping conditions H <= {_format_number(less_threshold)} and "
            f"H > {_format_number(greater_threshold)} for the same output."
        )
    elif greater_threshold > less_threshold:
        errors.append(
            f"Controllers {less[0].controller.id} and {greater[0].controller.id} leave "
            f"the interval {_format_number(less_threshold)} < H <= "
            f"{_format_number(greater_threshold)} without a selected rule."
        )


def _actuator_target(
    controller: SreRtcController,
    structure: Structure,
    errors: list[str],
) -> tuple[str, str, str] | None:
    if not structure.name:
        errors.append(
            f"Controller {controller.id} targets structure {structure.id} with no "
            "D-Flow FM structure name."
        )
        return None
    if controller.controlled_parameter is SreRtcControlledParameter.CREST_LEVEL:
        if structure.structure_type not in {"weir", "orifice"}:
            errors.append(
                f"Controller {controller.id} controls crest level on unsupported "
                f"structure type {structure.structure_type!r} ({structure.id})."
            )
            return None
        group = "weirs" if structure.structure_type == "weir" else "orifices"
        return (
            f"{group}/{structure.name}/crestlevel",
            "crestlevel",
            "crest_level",
        )
    if controller.controlled_parameter is SreRtcControlledParameter.GATE_HEIGHT:
        if structure.structure_type != "orifice":
            errors.append(
                f"Controller {controller.id} controls gate height on unsupported "
                f"structure type {structure.structure_type!r} ({structure.id})."
            )
            return None
        return (
            f"orifices/{structure.name}/gateheight",
            "gateheight",
            "gate_height",
        )
    errors.append(
        f"Controller {controller.id} controls unsupported parameter "
        f"{controller.controlled_parameter.name}."
    )
    return None


def _resolve_observation(
    controller: SreRtcController,
    trigger: SreRtcTrigger,
    branches: dict[str, Branch],
    nodes: dict[str, Node],
    errors: list[str],
) -> _Observation | None:
    branch_id = trigger.branch_id or controller.observation_branch_id
    chainage = trigger.chainage
    if chainage is None:
        chainage = controller.observation_chainage
    if branch_id is None or chainage is None:
        errors.append(
            f"Controller {controller.id} / trigger {trigger.id} has no complete "
            "hydraulic observation location."
        )
        return None
    if (
        trigger.branch_id is not None
        and controller.observation_branch_id is not None
        and trigger.branch_id != controller.observation_branch_id
    ):
        errors.append(
            f"Controller {controller.id} observation branch "
            f"{controller.observation_branch_id} differs from trigger {trigger.id} "
            f"branch {trigger.branch_id}."
        )
        return None
    if (
        trigger.chainage is not None
        and controller.observation_chainage is not None
        and not math.isclose(
            trigger.chainage,
            controller.observation_chainage,
            rel_tol=0.0,
            abs_tol=1.0e-6,
        )
    ):
        errors.append(
            f"Controller {controller.id} observation chainage "
            f"{_format_number(controller.observation_chainage)} differs from trigger "
            f"{trigger.id} chainage {_format_number(trigger.chainage)}."
        )
        return None

    branch = branches.get(branch_id)
    if branch is None:
        errors.append(
            f"Controller {controller.id} observation references unknown branch {branch_id}."
        )
        return None
    if not math.isfinite(chainage) or chainage < 0 or chainage > branch.length:
        errors.append(
            f"Controller {controller.id} observation chainage {_format_number(chainage)} "
            f"is outside branch {branch_id} length {_format_number(branch.length)}."
        )
        return None

    start_node = nodes.get(branch.from_node_id)
    end_node = nodes.get(branch.to_node_id)
    if start_node is None or end_node is None:
        errors.append(
            f"Controller {controller.id} observation branch {branch_id} has a missing "
            "network endpoint."
        )
        return None
    fraction = 0.0 if branch.length == 0 else chainage / branch.length
    x = start_node.x + (end_node.x - start_node.x) * fraction
    y = start_node.y + (end_node.y - start_node.y) * fraction
    safe_branch = _safe_identifier(branch_id)
    safe_chainage = _safe_identifier(_format_number(chainage))
    name = f"rtc_obs_b{safe_branch}_s{safe_chainage}"
    return _Observation(
        branch_id=branch_id,
        chainage=chainage,
        name=name,
        series_id=f"input_{name}_water_level",
        x=x,
        y=y,
    )


def _unique_by_id(
    items: tuple[_IdentifiedT, ...],
    item_kind: str,
    errors: list[str],
) -> dict[str, _IdentifiedT]:
    result: dict[str, _IdentifiedT] = {}
    for item in items:
        item_id = getattr(item, "id")
        if item_id in result:
            errors.append(f"Duplicate {item_kind} id {item_id!r} prevents RTC mapping.")
        else:
            result[item_id] = item
    return result


def _group_outputs(candidates: list[_ControllerPlan]) -> tuple[_OutputPlan, ...]:
    grouped: dict[str, list[_ControllerPlan]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.output_id, []).append(candidate)

    outputs: list[_OutputPlan] = []
    for output_id, controllers in sorted(grouped.items()):
        first = controllers[0]
        if (
            first.controller.controlled_parameter
            is SreRtcControlledParameter.CREST_LEVEL
        ):
            initial_values = [first.structure.crest_level]
            for controller in controllers:
                initial_values.extend(
                    value for _, value in controller.lookup_rows
                )
                if controller.maximum_output is not None:
                    initial_values.append(controller.maximum_output)
            initial_value = max(initial_values)
        else:
            initial_value = first.structure.gate_height
            if initial_value is None:
                raise ValueError(
                    f"Controlled gate-height output {output_id} has no initial value."
                )
        outputs.append(
            _OutputPlan(
                output_id=output_id,
                structure=first.structure,
                actuator_quantity=first.actuator_quantity,
                actuator_target=first.actuator_target,
                initial_value=initial_value,
                controllers=tuple(
                    sorted(controllers, key=lambda item: item.controller.id)
                ),
            )
        )
    return tuple(outputs)


def _build_rtc_files(
    outputs: tuple[_OutputPlan, ...],
    observations: tuple[_Observation, ...],
    runtime_start: datetime,
    runtime_stop: datetime,
    timestep_seconds: int,
) -> tuple[tuple[str, bytes], ...]:
    tools_config = _build_tools_config(outputs)
    data_config = _build_data_config(outputs, observations)
    runtime_config = _build_runtime_config(
        runtime_start,
        runtime_stop,
        timestep_seconds,
    )
    state_pi = _build_state_pi(runtime_start)
    state_import = _build_state_import(outputs)
    settings = json.dumps(
        {"xmlDir": "xml_dir", "schemaDir": "xsd_dir"},
        indent=2,
    ).encode("utf-8") + b"\n"
    file_contents = [
        ("settings.json", settings),
        ("xml_dir/rtcToolsConfig.xml", tools_config),
        ("xml_dir/rtcDataConfig.xml", data_config),
        ("xml_dir/rtcRuntimeConfig.xml", runtime_config),
        ("xml_dir/statePI.xml", state_pi),
        ("xml_dir/state_import.xml", state_import),
    ]
    if _time_schedule_controllers(outputs):
        file_contents.insert(
            3,
            ("xml_dir/time_schedule_import.xml", _build_time_schedule_import(outputs)),
        )
    return tuple(file_contents)


def _build_tools_config(outputs: tuple[_OutputPlan, ...]) -> bytes:
    root = _xml_root(
        FEWS_NAMESPACE,
        "rtcToolsConfig",
        "../xsd_dir/rtcToolsConfig.xsd",
    )
    rules = ET.SubElement(root, _tag(FEWS_NAMESPACE, "rules"))
    for output in outputs:
        for controller in output.controllers:
            rule = ET.SubElement(rules, _tag(FEWS_NAMESPACE, "rule"))
            if controller.rule_kind is _RuleKind.TIME_ABSOLUTE:
                _append_time_absolute_rule(rule, controller)
            else:
                _append_lookup_rule(rule, controller)

    triggers = ET.SubElement(root, _tag(FEWS_NAMESPACE, "triggers"))
    for output in outputs:
        if not output.controllers:
            continue
        trigger_wrapper = ET.SubElement(triggers, _tag(FEWS_NAMESPACE, "trigger"))
        _append_standard_trigger(trigger_wrapper, output.controllers, 0)
    return _serialize_xml(root, FEWS_NAMESPACE)


def _build_time_schedule_import(outputs: tuple[_OutputPlan, ...]) -> bytes:
    root = _xml_root(
        PI_NAMESPACE,
        "TimeSeries",
        "../xsd_dir/pi_timeseries.xsd",
        {"version": "1.2"},
    )
    ET.SubElement(root, _tag(PI_NAMESPACE, "timeZone")).text = "0.0"
    for controller in _time_schedule_controllers(outputs):
        if not controller.schedule_rows or controller.schedule_series_id is None:
            continue
        series = ET.SubElement(root, _tag(PI_NAMESPACE, "series"))
        header = ET.SubElement(series, _tag(PI_NAMESPACE, "header"))
        ET.SubElement(header, _tag(PI_NAMESPACE, "type")).text = "instantaneous"
        ET.SubElement(header, _tag(PI_NAMESPACE, "locationId")).text = (
            controller.schedule_series_id
        )
        ET.SubElement(header, _tag(PI_NAMESPACE, "parameterId")).text = "value"
        ET.SubElement(
            header,
            _tag(PI_NAMESPACE, "timeStep"),
            {"unit": "nonequidistant"},
        )
        ET.SubElement(header, _tag(PI_NAMESPACE, "startDate"), _date_time_attributes(
            controller.schedule_rows[0][0]
        ))
        ET.SubElement(header, _tag(PI_NAMESPACE, "endDate"), _date_time_attributes(
            controller.schedule_rows[-1][0]
        ))
        ET.SubElement(header, _tag(PI_NAMESPACE, "missVal")).text = "-9999.0"
        ET.SubElement(header, _tag(PI_NAMESPACE, "longName")).text = (
            controller.controller.name
        )
        ET.SubElement(header, _tag(PI_NAMESPACE, "units")).text = "m"
        for timestamp, value in controller.schedule_rows:
            ET.SubElement(
                series,
                _tag(PI_NAMESPACE, "event"),
                {
                    **_date_time_attributes(timestamp),
                    "value": _format_number(value),
                },
            )
    return _serialize_xml(root, PI_NAMESPACE)


def _time_schedule_controllers(
    outputs: tuple[_OutputPlan, ...],
) -> tuple[_ControllerPlan, ...]:
    return tuple(
        controller
        for output in outputs
        for controller in output.controllers
        if controller.rule_kind is _RuleKind.TIME_ABSOLUTE
    )


def _date_time_attributes(timestamp: datetime) -> dict[str, str]:
    return {
        "date": timestamp.strftime("%Y-%m-%d"),
        "time": timestamp.strftime("%H:%M:%S"),
    }


def _append_time_absolute_rule(
    parent: ET.Element,
    controller: _ControllerPlan,
) -> None:
    assert controller.schedule_series_id is not None
    rule = ET.SubElement(
        parent,
        _tag(FEWS_NAMESPACE, "timeAbsolute"),
        {"id": controller.rule_id, "name": controller.controller.name},
    )
    input_node = ET.SubElement(rule, _tag(FEWS_NAMESPACE, "input"))
    ET.SubElement(input_node, _tag(FEWS_NAMESPACE, "x")).text = (
        controller.schedule_series_id
    )
    output = ET.SubElement(rule, _tag(FEWS_NAMESPACE, "output"))
    ET.SubElement(output, _tag(FEWS_NAMESPACE, "y")).text = controller.output_id


def _append_lookup_rule(parent: ET.Element, controller: _ControllerPlan) -> None:
    rule = ET.SubElement(
        parent,
        _tag(FEWS_NAMESPACE, "lookupTable"),
        {"id": controller.rule_id, "name": controller.controller.name},
    )
    table = ET.SubElement(rule, _tag(FEWS_NAMESPACE, "table"))
    for x_value, y_value in controller.lookup_rows:
        ET.SubElement(
            table,
            _tag(FEWS_NAMESPACE, "record"),
            {"x": _format_number(x_value), "y": _format_number(y_value)},
        )
    ET.SubElement(rule, _tag(FEWS_NAMESPACE, "interpolationOption")).text = "LINEAR"
    ET.SubElement(rule, _tag(FEWS_NAMESPACE, "extrapolationOption")).text = "BLOCK"
    input_node = ET.SubElement(rule, _tag(FEWS_NAMESPACE, "input"))
    input_series = ET.SubElement(
        input_node,
        _tag(FEWS_NAMESPACE, "x"),
        {"ref": "IMPLICIT"},
    )
    input_series.text = controller.observation.series_id
    output_node = ET.SubElement(rule, _tag(FEWS_NAMESPACE, "output"))
    ET.SubElement(output_node, _tag(FEWS_NAMESPACE, "y")).text = controller.output_id


def _append_standard_trigger(
    parent: ET.Element,
    controllers: tuple[_ControllerPlan, ...],
    index: int,
) -> None:
    controller = controllers[index]
    trigger = ET.SubElement(
        parent,
        _tag(FEWS_NAMESPACE, "standard"),
        {
            "id": (
                f"trigger_{_safe_identifier(controller.controller.id)}_"
                f"{_safe_identifier(controller.trigger.id)}"
            )
        },
    )
    condition = ET.SubElement(trigger, _tag(FEWS_NAMESPACE, "condition"))
    x1_series = ET.SubElement(
        condition,
        _tag(FEWS_NAMESPACE, "x1Series"),
        {"ref": "EXPLICIT"},
    )
    x1_series.text = controller.observation.series_id
    operator = (
        "LessEqual"
        if controller.condition.comparison is SreRtcComparison.LESS_THAN
        else "Greater"
    )
    ET.SubElement(condition, _tag(FEWS_NAMESPACE, "relationalOperator")).text = operator
    assert controller.condition.threshold is not None
    ET.SubElement(condition, _tag(FEWS_NAMESPACE, "x2Value")).text = _format_number(
        controller.condition.threshold
    )

    true_branch = ET.SubElement(trigger, _tag(FEWS_NAMESPACE, "true"))
    true_trigger = ET.SubElement(true_branch, _tag(FEWS_NAMESPACE, "trigger"))
    ET.SubElement(true_trigger, _tag(FEWS_NAMESPACE, "ruleReference")).text = (
        controller.rule_id
    )

    if index + 1 < len(controllers):
        false_branch = ET.SubElement(trigger, _tag(FEWS_NAMESPACE, "false"))
        false_trigger = ET.SubElement(false_branch, _tag(FEWS_NAMESPACE, "trigger"))
        _append_standard_trigger(false_trigger, controllers, index + 1)

    output = ET.SubElement(trigger, _tag(FEWS_NAMESPACE, "output"))
    ET.SubElement(output, _tag(FEWS_NAMESPACE, "status")).text = controller.status_id


def _build_data_config(
    outputs: tuple[_OutputPlan, ...],
    observations: tuple[_Observation, ...],
) -> bytes:
    root = _xml_root(
        FEWS_NAMESPACE,
        "rtcDataConfig",
        "../xsd_dir/rtcDataConfig.xsd",
    )
    import_series = ET.SubElement(root, _tag(FEWS_NAMESPACE, "importSeries"))
    schedule_controllers = _time_schedule_controllers(outputs)
    if schedule_controllers:
        import_pi_file = ET.SubElement(
            import_series,
            _tag(FEWS_NAMESPACE, "PITimeSeriesFile"),
        )
        ET.SubElement(
            import_pi_file,
            _tag(FEWS_NAMESPACE, "timeSeriesFile"),
        ).text = "time_schedule_import.xml"
        ET.SubElement(
            import_pi_file,
            _tag(FEWS_NAMESPACE, "useBinFile"),
        ).text = "false"
        for controller in schedule_controllers:
            assert controller.schedule_series_id is not None
            time_series = ET.SubElement(
                import_series,
                _tag(FEWS_NAMESPACE, "timeSeries"),
                {"id": controller.schedule_series_id},
            )
            pi_time_series = ET.SubElement(
                time_series,
                _tag(FEWS_NAMESPACE, "PITimeSeries"),
            )
            ET.SubElement(
                pi_time_series,
                _tag(FEWS_NAMESPACE, "locationId"),
            ).text = controller.schedule_series_id
            ET.SubElement(
                pi_time_series,
                _tag(FEWS_NAMESPACE, "parameterId"),
            ).text = "value"
            ET.SubElement(pi_time_series, _tag(FEWS_NAMESPACE, "unit")).text = "m"
            ET.SubElement(
                pi_time_series,
                _tag(FEWS_NAMESPACE, "interpolationOption"),
            ).text = controller.schedule_interpolation or "LINEAR"
            ET.SubElement(
                pi_time_series,
                _tag(FEWS_NAMESPACE, "extrapolationOption"),
            ).text = "BLOCK"

    for observation in observations:
        time_series = ET.SubElement(
            import_series,
            _tag(FEWS_NAMESPACE, "timeSeries"),
            {"id": observation.series_id},
        )
        exchange_item = ET.SubElement(
            time_series,
            _tag(FEWS_NAMESPACE, "OpenMIExchangeItem"),
        )
        ET.SubElement(exchange_item, _tag(FEWS_NAMESPACE, "elementId")).text = (
            observation.name
        )
        ET.SubElement(exchange_item, _tag(FEWS_NAMESPACE, "quantityId")).text = (
            "water_level"
        )
        ET.SubElement(exchange_item, _tag(FEWS_NAMESPACE, "unit")).text = "m"

    export_series = ET.SubElement(root, _tag(FEWS_NAMESPACE, "exportSeries"))
    ET.SubElement(
        export_series,
        _tag(FEWS_NAMESPACE, "CSVTimeSeriesFile"),
        {"decimalSeparator": ".", "delimiter": ",", "adjointOutput": "false"},
    )
    pi_file = ET.SubElement(export_series, _tag(FEWS_NAMESPACE, "PITimeSeriesFile"))
    ET.SubElement(pi_file, _tag(FEWS_NAMESPACE, "timeSeriesFile")).text = (
        "timeseries_export.xml"
    )
    ET.SubElement(pi_file, _tag(FEWS_NAMESPACE, "useBinFile")).text = "false"

    for output in outputs:
        time_series = ET.SubElement(
            export_series,
            _tag(FEWS_NAMESPACE, "timeSeries"),
            {"id": output.output_id},
        )
        exchange_item = ET.SubElement(
            time_series,
            _tag(FEWS_NAMESPACE, "OpenMIExchangeItem"),
        )
        ET.SubElement(exchange_item, _tag(FEWS_NAMESPACE, "elementId")).text = (
            output.structure.name
        )
        ET.SubElement(exchange_item, _tag(FEWS_NAMESPACE, "quantityId")).text = (
            output.actuator_quantity
        )
        ET.SubElement(exchange_item, _tag(FEWS_NAMESPACE, "unit")).text = "m"
        for controller in output.controllers:
            ET.SubElement(
                export_series,
                _tag(FEWS_NAMESPACE, "timeSeries"),
                {"id": controller.status_id},
            )
    return _serialize_xml(root, FEWS_NAMESPACE)


def _build_runtime_config(
    runtime_start: datetime,
    runtime_stop: datetime,
    timestep_seconds: int,
) -> bytes:
    root = _xml_root(
        FEWS_NAMESPACE,
        "rtcRuntimeConfig",
        "../xsd_dir/rtcRuntimeConfig.xsd",
    )
    period = ET.SubElement(root, _tag(FEWS_NAMESPACE, "period"))
    user_defined = ET.SubElement(period, _tag(FEWS_NAMESPACE, "userDefined"))
    for name, value in (("startDate", runtime_start), ("endDate", runtime_stop)):
        ET.SubElement(
            user_defined,
            _tag(FEWS_NAMESPACE, name),
            {
                "date": value.strftime("%Y-%m-%d"),
                "time": value.strftime("%H:%M:%S"),
            },
        )
    ET.SubElement(
        user_defined,
        _tag(FEWS_NAMESPACE, "timeStep"),
        {"unit": "second", "multiplier": str(timestep_seconds), "divider": "1"},
    )
    mode = ET.SubElement(root, _tag(FEWS_NAMESPACE, "mode"))
    simulation = ET.SubElement(mode, _tag(FEWS_NAMESPACE, "simulation"))
    ET.SubElement(simulation, _tag(FEWS_NAMESPACE, "limitedMemory")).text = "true"
    return _serialize_xml(root, FEWS_NAMESPACE)


def _build_state_pi(runtime_start: datetime) -> bytes:
    root = _xml_root(
        PI_NAMESPACE,
        "State",
        "../xsd_dir/pi_state.xsd",
        {"version": "1.2"},
    )
    ET.SubElement(root, _tag(PI_NAMESPACE, "stateId")).text = "initial"
    ET.SubElement(root, _tag(PI_NAMESPACE, "timeZone")).text = "0.0"
    ET.SubElement(
        root,
        _tag(PI_NAMESPACE, "dateTime"),
        {
            "date": runtime_start.strftime("%Y-%m-%d"),
            "time": runtime_start.strftime("%H:%M:%S"),
        },
    )
    state_location = ET.SubElement(
        root,
        _tag(PI_NAMESPACE, "stateLoc"),
        {"type": "file"},
    )
    ET.SubElement(state_location, _tag(PI_NAMESPACE, "readLocation")).text = (
        "state_import.xml"
    )
    ET.SubElement(state_location, _tag(PI_NAMESPACE, "writeLocation")).text = (
        "state_export.xml"
    )
    return _serialize_xml(root, PI_NAMESPACE)


def _build_state_import(outputs: tuple[_OutputPlan, ...]) -> bytes:
    root = _xml_root(
        OPENDA_NAMESPACE,
        "treeVectorFile",
        "../xsd_dir/treeVector.xsd",
    )
    tree_vector = ET.SubElement(root, _tag(OPENDA_NAMESPACE, "treeVector"))
    for output in outputs:
        leaf = ET.SubElement(
            tree_vector,
            _tag(OPENDA_NAMESPACE, "treeVectorLeaf"),
            {"id": output.output_id},
        )
        ET.SubElement(leaf, _tag(OPENDA_NAMESPACE, "vector")).text = _format_number(
            output.initial_value
        )
    return _serialize_xml(root, OPENDA_NAMESPACE)


def _xml_root(
    namespace: str,
    name: str,
    schema_path: str,
    attributes: dict[str, str] | None = None,
) -> ET.Element:
    root_attributes = {
        _tag(XSI_NAMESPACE, "schemaLocation"): f"{namespace} {schema_path}"
    }
    if attributes:
        root_attributes.update(attributes)
    return ET.Element(_tag(namespace, name), root_attributes)


def _serialize_xml(root: ET.Element, default_namespace: str) -> bytes:
    ET.register_namespace("", default_namespace)
    ET.register_namespace("xsi", XSI_NAMESPACE)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _rtc_schema_files() -> tuple[Path, ...]:
    if not RTC_SCHEMA_DIRECTORY.is_dir():
        raise FileNotFoundError(
            f"D-RTC schema directory was not found: {RTC_SCHEMA_DIRECTORY}"
        )
    schema_files = tuple(sorted(RTC_SCHEMA_DIRECTORY.glob("*.xsd")))
    if not schema_files:
        raise FileNotFoundError(
            f"No D-RTC XSD files were found in {RTC_SCHEMA_DIRECTORY}."
        )
    return schema_files


def _safe_identifier(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return safe or "unnamed"


def _format_number(value: float) -> str:
    return format(value, ".15g")


def _tag(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"
