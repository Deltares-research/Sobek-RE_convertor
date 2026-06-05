from __future__ import annotations

from pathlib import Path


def write_dimr_config(target_path: Path, mdu_relative_path: str) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)

    content = f"""<?xml version=\"1.0\" encoding=\"utf-8\"?>
<dimrConfig xmlns=\"http://schemas.deltares.nl/dimr\">
  <documentation>
    <fileVersion>1.2</fileVersion>
    <createdBy>sre_convertor</createdBy>
  </documentation>
  <control>
    <start name=\"DFlowFM\" />
  </control>
  <component name=\"DFlowFM\">
    <library>dflowfm</library>
    <workingDir>.</workingDir>
    <inputFile>{mdu_relative_path}</inputFile>
  </component>
</dimrConfig>
"""
    target_path.write_text(content, encoding="utf-8")
