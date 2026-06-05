from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ConversionContext:
    input_dir: Path
    output_dir: Path
    model_name: str


class ConverterPlugin(Protocol):
    name: str

    def run(self, context: ConversionContext) -> None:
        ...
