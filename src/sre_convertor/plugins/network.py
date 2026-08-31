from __future__ import annotations

from ..api import convert_network
from .base import ConversionContext


class NetworkConverterPlugin:
    name = "network"

    def run(self, context: ConversionContext) -> None:
        convert_network(context.input_dir, context.output_dir, model_name=context.model_name)
