from __future__ import annotations

from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape

from .rtc_writer import RtcCoupling, RtcCouplingItem


def write_dimr_config(
    target_path: Path,
    mdu_relative_path: str,
    include_rtc: bool = False,
    rtc_coupling: RtcCoupling | None = None,
    start_time: int = 0,
    stop_time: int = 86400,
    rtc_timestep: int = 600,
) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)

    control_block = """
  <control>
    <start name="DFlowFM" />
  </control>
"""
    rtc_components = ""
    if include_rtc:
        flow_to_rtc_items = _format_coupler_items(rtc_coupling.flow_to_rtc if rtc_coupling else tuple())
        rtc_to_flow_items = _format_coupler_items(rtc_coupling.rtc_to_flow if rtc_coupling else tuple())
        control_block = f"""
  <control>
    <parallel>
      <startGroup>
        <time>{start_time} {rtc_timestep} {stop_time}</time>
        <coupler name="flowfm_to_rtc" />
        <start name="RTC" />
        <coupler name="rtc_to_flowfm" />
      </startGroup>
      <start name="DFlowFM" />
    </parallel>
  </control>
"""
        rtc_components = f"""
  <component name="RTC">
    <library>FBCTools_BMI</library>
    <workingDir>rtc</workingDir>
    <inputFile>.</inputFile>
  </component>
  <coupler name="rtc_to_flowfm">
    <sourceComponent>RTC</sourceComponent>
    <targetComponent>DFlowFM</targetComponent>
{rtc_to_flow_items}
    <logger>
      <workingDir>.</workingDir>
      <outputFile>rtc_to_flowfm.nc</outputFile>
    </logger>
  </coupler>
  <coupler name="flowfm_to_rtc">
    <sourceComponent>DFlowFM</sourceComponent>
    <targetComponent>RTC</targetComponent>
{flow_to_rtc_items}
    <logger>
      <workingDir>.</workingDir>
      <outputFile>flowfm_to_rtc.nc</outputFile>
    </logger>
  </coupler>
"""

    content = f"""<?xml version="1.0" encoding="utf-8"?>
<dimrConfig xmlns="http://schemas.deltares.nl/dimrConfig" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://schemas.deltares.nl/dimrConfig http://content.oss.deltares.nl/schemas/dimr-1.2.xsd">
  <documentation>
    <fileVersion>1.0</fileVersion>
    <createdBy>sre_convertor</createdBy>
  </documentation>
{control_block}
  <component name="DFlowFM">
    <library>dflowfm</library>
    <workingDir>dflowfm</workingDir>
    <inputFile>{Path(mdu_relative_path).name}</inputFile>
  </component>
{rtc_components}
</dimrConfig>
"""
    target_path.write_text(content, encoding="utf-8")


def _format_coupler_items(items: Iterable[RtcCouplingItem]) -> str:
    lines: list[str] = []
    for item in items:
        lines.extend(
            [
                "    <item>",
                f"      <sourceName>{escape(item.source_name)}</sourceName>",
                f"      <targetName>{escape(item.target_name)}</targetName>",
                "    </item>",
            ]
        )
    return "\n".join(lines)
