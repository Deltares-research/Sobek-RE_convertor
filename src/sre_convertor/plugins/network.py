from __future__ import annotations

from pathlib import Path

from ..api import convert_network


class NetworkConverterPlugin:
    name = "network"

    def run(self, context_input_dir: Path, context_output_dir: Path, model_name: str) -> None:
        convert_network(context_input_dir, context_output_dir, model_name=model_name)
