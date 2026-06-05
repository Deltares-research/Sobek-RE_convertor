from __future__ import annotations

from pathlib import Path

from .models import ConversionOptions, ConversionReport
from .orchestrator import convert_network_case


def convert_network(
    input_dir: str | Path,
    output_dir: str | Path,
    model_name: str = "sre2fm_network",
) -> ConversionReport:
    """Convert only the SRE network into a minimal FM schematization."""
    options = ConversionOptions(model_name=model_name)
    return convert_network_case(Path(input_dir), Path(output_dir), options)
