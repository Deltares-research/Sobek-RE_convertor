from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET


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
