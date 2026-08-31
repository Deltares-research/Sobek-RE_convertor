# Sobek-RE_convertor

Tool for converting Sobek-RE models into Delft3D FM 1D models.

## Current status

The first whole-tool implementation phase is available:


- Scope: end-to-end case conversion pipeline with a stable runnable baseline.
- Input: SRE case folder with records in `DEFTOP.*`, `DEFGRD.*`, `DEFCRS.*`, `DEFCND.*`, `DEFSTR.*`, `DEFRUN.*`, `DEFFRC.*`, `DEFICN.*`, `DEFSUB.*`.
- Grid: branch mesh density is taken from `DEFGRD.*` (`GRID` tables) when available.
- Output: FM schematization in output directory with:
	- `dimr_config.xml`
	- `dflowfm/<model_name>.mdu`
	- `dflowfm/<model_name>_net.nc`
	- `dflowfm/<model_name>.ext`
	- `dflowfm/BoundaryConditions.bc`
	- `dflowfm/initialFields.ini`
	- `dflowfm/InitialWaterDepth.ini`
	- `dflowfm/Structures.ini`
	- `dflowfm/roughness-Main.ini`
	- `output/run_dimr.bat`

Additional files that are generated for inspection and optional activation:

	- `dflowfm/CrossSectionDefinitions.ini` (active by default)
	- `dflowfm/CrossSectionLocations.ini` (active by default)

## Progress tracker

Done:

- Topology conversion (`DEFTOP.*`) and branch discretization from `DEFGRD.*`.
- Cross-section definitions/locations conversion (`DEFCRS.*`).
- Boundary and lateral conversion (`DEFCND.*`) including runtime-safe series handling.
- Structure conversion (`DEFSTR.*`) with STCM/DLST location linking.
- Runtime parsing and short-run clamp (`DEFRUN.*`).
- Roughness conversion first pass (`DEFFRC.*`): branch-level representative Chezy values are written to `roughness-Main.ini`.
- Initial conditions first pass (`DEFICN.*`): FLIN branch water levels are parsed and used to derive initial water depth default.
- Structure warning audit from FM `.dia` output.

In progress:

- Morphodynamics first pass:
	- Source readiness detection is implemented (`DEFICN.*` MPIN + `DEFSUB.*` morphology switch).
	- Optional MDU sediment block activation is available via `activate_morphodynamics=True`.
	- Base `mor.mor` and `sed.sed` are generated from converted source summary values.
	- `sed.sed` now contains multiple derived sediment fractions (D50 classes) from MPIN grain-size samples.
	- Branch-aware composition export is generated in `mor.composition.ini` for traceability.
	- Still simplified: advanced transport options and direct FM underlayer initialization wiring are pending.

Not done yet:

- Full morphodynamics/sediment parameter transfer from SRE to FM file set.
- RTC coupling transfer and controller behavior parity.
- Initial conditions beyond first-pass global depth proxy (for example detailed branch/profile fields where needed).
- Roughness profile transfer at full spatial detail (currently reduced to representative branch value).
- Stronger runtime acceptance criterion: "simulation advanced and produced expected history/map outputs", beyond initial output marker presence.

## Architecture

The package is API-first and modular:

- `sre_convertor.api`: public entrypoints.
- `sre_convertor.io.sre`: Sobek-RE readers/parsers.
- `sre_convertor.io.fm`: Delft3D FM writers.
- `sre_convertor.orchestrator`: conversion pipeline and validation.
- `sre_convertor.plugins`: extension points for future conversion modules.

## Quick start

Install in editable mode with test dependencies:

```bash
pip install -e .[dev]
```

Call from Python:

```python
from sre_convertor import convert_network

report = convert_network(
		input_dir="data/sre_simulation",
		output_dir="build/fm_output",
		model_name="converted_network",
)

print(report)
```

Full case conversion:

```python
from sre_convertor import convert_case

report = convert_case(
		input_dir="data/sre_simulation",
		output_dir="build/fm_output",
		model_name="converted_case",
)

print(report)
```

Use a shorter runtime for testing:

```python
from sre_convertor import convert_case

report = convert_case(
		input_dir="data/sre_simulation",
		output_dir="build/fm_output",
		model_name="converted_case",
		test_duration_seconds=1800,
)
```

Disable cross-sections in MDU (optional fallback):

```python
from sre_convertor import convert_case

report = convert_case(
		input_dir="data/sre_simulation",
		output_dir="build/fm_output",
		model_name="converted_case",
		activate_cross_sections=False,
)
```

Enable first-pass morphodynamics block in MDU (experimental):

```python
from sre_convertor import convert_case

report = convert_case(
		input_dir="data/sre_simulation",
		output_dir="build/fm_output",
		model_name="converted_case",
		activate_morphodynamics=True,
)
```

Runtime success validation:

```python
from sre_convertor import run_and_validate_conversion, validate_conversion_success

# Option 1: validate after a separate/manual run of output/run_dimr.bat
result = validate_conversion_success(output_dir="output", model_name="sre2fm_case")
print(result.success, result.message)

# Option 2: execute output/run_dimr.bat and then validate automatically
result = run_and_validate_conversion(output_dir="output", model_name="sre2fm_case")
print(result.success, result.message)
```

Current success criterion for this project phase:

- Conversion is considered successful when the generated `.dia` file contains:
	`** INFO   : Done writing initial output to file(s).`

Run tests:

```bash
pytest
```
