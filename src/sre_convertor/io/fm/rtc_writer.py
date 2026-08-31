from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import json
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from ...models import RuntimeSettings, SreRtcController, SreRtcSummary


@dataclass(frozen=True)
class RtcCouplingItem:
    source_name: str
    target_name: str


@dataclass(frozen=True)
class RtcCoupling:
    flow_to_rtc: tuple[RtcCouplingItem, ...]
    rtc_to_flow: tuple[RtcCouplingItem, ...]


def copy_rtc_package(source_dir: Path, target_dir: Path) -> tuple[Path, RtcCoupling]:
    if not source_dir.is_dir():
        raise FileNotFoundError(f"RTC source directory not found: {source_dir}")

    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(source_dir, target_dir)

    coupling = read_rtc_coupling(target_dir / "rtcDataConfig.xml")
    return target_dir, coupling


def write_sre_rtc_inventory(target_path: Path, summary: SreRtcSummary) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "controllers": [
            {
                "id": controller.id,
                "name": controller.name,
                "controllerType": controller.controller_type,
                "controlledParameter": controller.controlled_parameter,
                "controlledStructureId": controller.controlled_structure_id,
                "triggerIds": list(controller.trigger_ids),
                "observationBranchId": controller.observation_branch_id,
                "observationChainage": controller.observation_chainage,
                "parameters": dict(controller.parameters),
                "tables": [[list(row) for row in table] for table in controller.tables],
            }
            for controller in summary.controllers
        ],
        "triggers": [
            {
                "id": trigger.id,
                "name": trigger.name,
                "triggerType": trigger.trigger_type,
                "branchId": trigger.branch_id,
                "chainage": trigger.chainage,
                "tables": [[list(row) for row in table] for table in trigger.tables],
            }
            for trigger in summary.triggers
        ],
    }
    target_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target_path


def write_native_rtc_package(
    target_dir: Path,
    summary: SreRtcSummary,
    runtime: RuntimeSettings,
) -> tuple[Path, RtcCoupling, Path | None, list[str]]:
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    observation_names = _rtc_observation_names(summary)
    observation_path = None
    if observation_names:
        observation_path = write_rtc_observation_points(target_dir.parent / "dflowfm" / "ObservationPoints_rtc.ini", observation_names)

    (target_dir / "settings.json").write_text('{\n  "xmlDir": ".",\n  "schemaDir": "."\n}\n', encoding="utf-8")
    _copy_rtc_schema_files(target_dir, warnings)
    (target_dir / "rtcRuntimeConfig.xml").write_text(_native_runtime_config(runtime), encoding="utf-8")
    (target_dir / "rtcToolsConfig.xml").write_text(_native_tools_config(summary, observation_names, warnings), encoding="utf-8")
    (target_dir / "rtcDataConfig.xml").write_text(_native_data_config(summary, observation_names), encoding="utf-8")
    (target_dir / "statePI.xml").write_text(_state_pi_config(runtime), encoding="utf-8")
    (target_dir / "state_import.xml").write_text(_state_import_config(summary), encoding="utf-8")

    (target_dir / "state_export.xml").write_text(_state_import_config(summary), encoding="utf-8")
    coupling = read_rtc_coupling(target_dir / "rtcDataConfig.xml")
    return target_dir, coupling, observation_path, warnings


def write_rtc_observation_points(target_path: Path, observation_names: dict[tuple[str, float], str]) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[General]", "    fileVersion           = 2.00", "    fileType              = obsPoint", ""]
    for (branch_id, chainage), name in sorted(observation_names.items(), key=lambda item: item[1]):
        lines.extend(
            [
                "[ObservationPoint]",
                f"    name      = {name}",
                f"    branchId  = {branch_id}",
                f"    chainage  = {chainage:.3f}",
                "",
            ]
        )
    target_path.write_text("\n".join(lines), encoding="utf-8")
    return target_path


def read_rtc_coupling(rtc_data_config_path: Path) -> RtcCoupling:
    if not rtc_data_config_path.exists():
        return RtcCoupling(flow_to_rtc=tuple(), rtc_to_flow=tuple())

    root = ET.fromstring(rtc_data_config_path.read_text(encoding="utf-8"))
    namespace = _namespace(root.tag)
    import_series = root.find(f"{{{namespace}}}importSeries") if namespace else root.find("importSeries")
    export_series = root.find(f"{{{namespace}}}exportSeries") if namespace else root.find("exportSeries")

    flow_to_rtc = _read_series_items(import_series, source_is_flow=True, namespace=namespace)
    rtc_to_flow = _read_series_items(export_series, source_is_flow=False, namespace=namespace)
    return RtcCoupling(flow_to_rtc=flow_to_rtc, rtc_to_flow=rtc_to_flow)


def _read_series_items(parent: ET.Element | None, *, source_is_flow: bool, namespace: str) -> tuple[RtcCouplingItem, ...]:
    if parent is None:
        return tuple()

    items: list[RtcCouplingItem] = []
    for time_series in parent.findall(_tag("timeSeries", namespace)):
        rtc_name = time_series.attrib.get("id", "")
        if source_is_flow and not rtc_name.startswith("[Input]"):
            continue
        if not source_is_flow and not rtc_name.startswith("[Output]"):
            continue

        exchange_item = time_series.find(_tag("OpenMIExchangeItem", namespace))
        if exchange_item is None:
            continue

        element = exchange_item.findtext(_tag("elementId", namespace), default="").strip()
        quantity = exchange_item.findtext(_tag("quantityId", namespace), default="").strip()
        flow_name = _fm_exchange_name(element, quantity)
        if not flow_name:
            continue

        if source_is_flow:
            items.append(RtcCouplingItem(source_name=flow_name, target_name=rtc_name))
        else:
            items.append(RtcCouplingItem(source_name=rtc_name, target_name=flow_name))

    return tuple(items)


def _namespace(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return ""


def _tag(name: str, namespace: str) -> str:
    return f"{{{namespace}}}{name}" if namespace else name


def _fm_exchange_name(element_id: str, quantity_id: str) -> str | None:
    quantity = quantity_id.lower()
    if "crest level" in quantity:
        return f"weirs/{element_id}/CrestLevel"
    if "water level" in quantity:
        return f"observations/{element_id}/water_level"
    return None


def _copy_rtc_schema_files(target_dir: Path, warnings: list[str]) -> None:
    schema_dir = Path(__file__).resolve().parents[4] / "data" / "fm" / "rtc"
    if not schema_dir.is_dir():
        warnings.append("Could not copy RTC schema files because data/fm/rtc was not found.")
        return

    for schema_path in schema_dir.glob("*.xsd"):
        shutil.copy2(schema_path, target_dir / schema_path.name)


def _rtc_observation_names(summary: SreRtcSummary) -> dict[tuple[str, float], str]:
        names: dict[tuple[str, float], str] = {}
        for controller in summary.controllers:
                if controller.observation_branch_id is None or controller.observation_chainage is None:
                        continue
                key = (controller.observation_branch_id, controller.observation_chainage)
                names.setdefault(key, f"SRE_RTC_{controller.observation_branch_id}_{controller.observation_chainage:g}")
        return names


def _native_runtime_config(runtime: RuntimeSettings) -> str:
        start = runtime.refdate + timedelta(seconds=runtime.tstart_seconds)
        stop = runtime.refdate + timedelta(seconds=runtime.tstop_seconds)
        return f"""<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<rtcRuntimeConfig xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:rtc="http://www.wldelft.nl/fews" xmlns="http://www.wldelft.nl/fews">
    <period>
        <userDefined>
            <startDate date="{start:%Y-%m-%d}" time="{start:%H:%M:%S}" />
            <endDate date="{stop:%Y-%m-%d}" time="{stop:%H:%M:%S}" />
            <timeStep unit="minute" multiplier="10" divider="1" />
        </userDefined>
    </period>
    <mode>
        <simulation>
            <limitedMemory>true</limitedMemory>
        </simulation>
    </mode>
</rtcRuntimeConfig>
"""


def _native_tools_config(
    summary: SreRtcSummary,
    observation_names: dict[tuple[str, float], str],
    warnings: list[str],
) -> str:
    rules: list[str] = []
    for controller in _selected_output_controllers(summary, warnings):
        output_id = _controller_output_id(controller)
        if output_id is None:
            warnings.append(f"Controller {controller.id} controls unsupported parameter {controller.controlled_parameter}.")
            continue

        if controller.controller_type == "time" and controller.tables:
            rules.append(_time_relative_rule(controller, output_id))
            continue

        table = _numeric_xy_table(controller)
        input_id = _controller_input_id(controller, observation_names)
        if table and input_id:
            rules.append(_lookup_rule(controller, input_id, output_id, table))
        else:
            warnings.append(f"Controller {controller.id} was inventoried but could not be synthesized as a D-RTC rule.")

    rules_text = "\n".join(f"    <rule>\n{rule}\n    </rule>" for rule in rules)
    return f"""<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<rtcToolsConfig xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:rtc="http://www.wldelft.nl/fews" xmlns="http://www.wldelft.nl/fews">
    <general>
        <description>SRE native controller conversion</description>
        <poolRoutingScheme>Theta</poolRoutingScheme>
        <theta>0.5</theta>
    </general>
    <rules>
{rules_text}
    </rules>
</rtcToolsConfig>
"""


def _native_data_config(summary: SreRtcSummary, observation_names: dict[tuple[str, float], str]) -> str:
    import_items: list[str] = []
    for observation_name in observation_names.values():
        import_items.append(_time_series_xml(f"[Input]{observation_name}/Water level (op)", observation_name, "Water level (op)"))

    export_items: list[str] = []
    for controller in _selected_output_controllers(summary, []):
        output_id = _controller_output_id(controller)
        if output_id is None or controller.controlled_structure_id is None:
            continue
        export_items.append(_time_series_xml(output_id, controller.controlled_structure_id, "Crest level (s)"))

    return f"""<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<rtcDataConfig xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:rtc="http://www.wldelft.nl/fews" xmlns="http://www.wldelft.nl/fews">
    <importSeries>
{''.join(import_items)}  </importSeries>
    <exportSeries>
        <CSVTimeSeriesFile decimalSeparator="." delimiter="," adjointOutput="false"></CSVTimeSeriesFile>
        <PITimeSeriesFile>
            <timeSeriesFile>timeseries_export.xml</timeSeriesFile>
            <useBinFile>false</useBinFile>
        </PITimeSeriesFile>
{''.join(export_items)}  </exportSeries>
</rtcDataConfig>
"""


def _state_pi_config(runtime: RuntimeSettings) -> str:
    start = runtime.refdate + timedelta(seconds=runtime.tstart_seconds)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<State xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.wldelft.nl/fews/PI" version="1.2">
    <stateId>warm</stateId>
    <timeZone>0.0</timeZone>
    <dateTime date="{start:%Y-%m-%d}" time="{start:%H:%M:%S}"/>
    <stateLoc type="file">
        <readLocation>state_import.xml</readLocation>
        <writeLocation>state_export.xml</writeLocation>
    </stateLoc>
</State>
"""


def _state_import_config(summary: SreRtcSummary) -> str:
    leaves = []
    for controller in _selected_output_controllers(summary, []):
        output_id = _controller_output_id(controller)
        if output_id is None:
            continue
        leaves.append(f"    <treeVectorLeaf id=\"{escape(output_id)}\">\n      <vector>{_initial_controller_value(controller):g}</vector>\n    </treeVectorLeaf>\n")
    return f"""<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<treeVectorFile xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="http://www.openda.org">
    <treeVector>
{''.join(leaves)}  </treeVector>
</treeVectorFile>
"""


def _controller_output_id(controller: SreRtcController) -> str | None:
    if controller.controlled_structure_id is None or controller.controlled_parameter != "crest_level":
        return None
    return f"[Output]{controller.controlled_structure_id}/Crest level (s)"


def _selected_output_controllers(summary: SreRtcSummary, warnings: list[str]) -> tuple[SreRtcController, ...]:
    priority = {"pid": 0, "hydraulic": 1, "time": 2}
    selected: dict[str, SreRtcController] = {}
    for controller in sorted(summary.controllers, key=lambda item: priority.get(item.controller_type, 9)):
        output_id = _controller_output_id(controller)
        if output_id is None:
            warnings.append(f"Controller {controller.id} controls unsupported parameter {controller.controlled_parameter}.")
            continue
        if output_id in selected:
            warnings.append(
                f"Controller {controller.id} was skipped because controller {selected[output_id].id} "
                f"already controls {output_id}."
            )
            continue
        selected[output_id] = controller
    return tuple(selected.values())


def _controller_input_id(controller: SreRtcController, observation_names: dict[tuple[str, float], str]) -> str | None:
        if controller.observation_branch_id is None or controller.observation_chainage is None:
                return None
        observation_name = observation_names.get((controller.observation_branch_id, controller.observation_chainage))
        if observation_name is None:
                return None
        return f"[Input]{observation_name}/Water level (op)"


def _time_relative_rule(controller: SreRtcController, output_id: str) -> str:
        rows = _time_controller_rows(controller)
        records = "".join(f"          <record time=\"{time:g}\" value=\"{value:g}\" />\n" for time, value in rows)
        return f"""      <timeRelative id="[RelativeTimeRule]SRE/{escape(controller.name)}">
                <mode>RETAINVALUEWHENINACTIVE</mode>
                <valueOption>ABSOLUTE</valueOption>
                <maximumPeriod>0</maximumPeriod>
                <interpolationOption>LINEAR</interpolationOption>
                <controlTable>
{records}        </controlTable>
                <output>
                    <y>{escape(output_id)}</y>
                </output>
            </timeRelative>"""


def _lookup_rule(controller: SreRtcController, input_id: str, output_id: str, rows: tuple[tuple[float, float], ...]) -> str:
        records = "".join(f"          <record x=\"{x:g}\" y=\"{y:g}\" />\n" for x, y in rows)
        return f"""      <lookupTable id="[LookupSignal]SRE/{escape(controller.name)}">
                <table>
{records}        </table>
                <interpolationOption>LINEAR</interpolationOption>
                <extrapolationOption>BLOCK</extrapolationOption>
                <input>
                    <x ref="EXPLICIT">{escape(input_id)}</x>
                </input>
                <output>
                    <y>{escape(output_id)}</y>
                </output>
            </lookupTable>"""


def _time_series_xml(series_id: str, element_id: str, quantity_id: str) -> str:
        return f"""    <timeSeries id="{escape(series_id)}">
            <OpenMIExchangeItem>
                <elementId>{escape(element_id)}</elementId>
                <quantityId>{escape(quantity_id)}</quantityId>
                <unit>m</unit>
            </OpenMIExchangeItem>
        </timeSeries>
"""


def _time_controller_rows(controller: SreRtcController) -> tuple[tuple[float, float], ...]:
        table = controller.tables[0] if controller.tables else tuple()
        values = [_as_float(row[1]) for row in table if len(row) >= 2 and _as_float(row[1]) is not None]
        if not values:
                return ((0.0, 0.0),)
        if len(set(values)) == 1:
                return ((0.0, values[0]), (3600.0, values[0]))
        return tuple((float(idx * 3600), value) for idx, value in enumerate(values))


def _numeric_xy_table(controller: SreRtcController) -> tuple[tuple[float, float], ...]:
        for table in controller.tables:
                rows: list[tuple[float, float]] = []
                for row in table:
                        if len(row) < 2:
                                continue
                        x = _as_float(row[0])
                        y = _as_float(row[1])
                        if x is None or y is None:
                                rows = []
                                break
                        rows.append((x, y))
                if rows:
                        return tuple(rows)
        return tuple()


def _initial_controller_value(controller: SreRtcController) -> float:
        rows = _numeric_xy_table(controller) or _time_controller_rows(controller)
        return rows[0][1] if rows else 0.0


def _as_float(value: str) -> float | None:
        try:
                return float(value)
        except ValueError:
                return None
