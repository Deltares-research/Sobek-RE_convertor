from __future__ import annotations

from pathlib import Path

def write_dimr_config(target_path: Path, mdu_relative_path: str, include_rtc: bool = False) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)

    control_block = """
  <control>
    <start name=\"DFlowFM\" />
  </control>
"""
    rtc_components = ""
    if include_rtc:
        control_block = """
  <control>
    <parallel>
      <startGroup>
        <time>0 600 86400</time>
        <coupler name=\"flowfm_to_rtc\" />
        <start name=\"RTC\" />
        <coupler name=\"rtc_to_flowfm\" />
      </startGroup>
      <start name=\"DFlowFM\" />
    </parallel>
  </control>
"""
        rtc_components = """
  <component name=\"RTC\">
    <library>FBCTools_BMI</library>
    <workingDir>rtc</workingDir>
    <inputFile>.</inputFile>
  </component>
  <coupler name=\"rtc_to_flowfm\">
    <sourceComponent>RTC</sourceComponent>
    <targetComponent>DFlowFM</targetComponent>
  </coupler>
  <coupler name=\"flowfm_to_rtc\">
    <sourceComponent>DFlowFM</sourceComponent>
    <targetComponent>RTC</targetComponent>
  </coupler>
"""

    content = f"""<?xml version=\"1.0\" encoding=\"utf-8\"?>
<dimrConfig xmlns=\"http://schemas.deltares.nl/dimrConfig\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xsi:schemaLocation=\"http://schemas.deltares.nl/dimrConfig http://content.oss.deltares.nl/schemas/dimr-1.2.xsd\">
  <documentation>
    <fileVersion>1.0</fileVersion>
    <createdBy>sre_convertor</createdBy>
  </documentation>
{control_block}
  <component name=\"DFlowFM\">
    <library>dflowfm</library>
    <workingDir>dflowfm</workingDir>
    <inputFile>{Path(mdu_relative_path).name}</inputFile>
  </component>
{rtc_components}
</dimrConfig>
"""
    target_path.write_text(content, encoding="utf-8")
