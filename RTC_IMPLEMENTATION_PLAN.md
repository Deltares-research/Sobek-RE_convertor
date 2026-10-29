# SRE RTC to D-RTC implementation plan

## Goal and scope

Replace the current native SRE RTC conversion with a conversion whose D-RTC
rules, triggers, observations, and structure outputs preserve the source
model's behavior. Treat the SRE `CNTL` and `TRGR` records as the source of
truth; do not infer behavior from controller names.

The first implementation change must remove the existing native conversion
before adding its replacement. The RTC source is always the selected SRE
case; there is no user option to provide a separate RTC folder or package.
Keep an RTC activation switch only if it remains useful, but remove any
`rtc_source_dir` option. Do not change the hydrodynamic or morphodynamics
conversion as part of this work.

The current worktree already contains uncommitted morphodynamics changes,
including edits to [orchestrator.py](./src/sre_convertor/orchestrator.py),
[models.py](./src/sre_convertor/models.py), and
[test_conversion_e2e.py](./tests/test_conversion_e2e.py). Review and preserve
those changes when implementing overlapping edits; do not reset or overwrite
them.

## Implementation status

The old RTC-folder pass-through and native inventory path have been removed.
A typed parser now reads SRE controllers, trigger records, active trigger
slots, table roles, interpolation/periodicity flags, and structure links. The
compiler now emits D-RTC time-absolute schedules, hydraulic lookups, and
hydraulic-trigger rules for the supported source subset. Schedules are clipped
or extended to cover the effective runtime; the Driel, Amero, Hagestein, and
Driel Omloop controls in the bundled case are included. Unsupported controller
and trigger semantics still fail before an RTC package or DIMR component is
written.

The implementation intentionally maps source `<` conditions to D-RTC
`LessEqual`, initializes crest outputs to their maximum known crest, and reads
the initial gate height from the source structure's `gh` field. SRE
non-periodic table lookup clamps to its endpoint values; D-RTC lookup
`BLOCK` extrapolation also returns the endpoint values. The control figure is
linked from the README.

## Verified SRE behavior to preserve

The source case is in [data/sre_simulation](./data/sre_simulation). Its
controller and trigger definitions are in `DEFSTR.*`; its runtime interval is
2000-01-01 through 2150-12-31 in `DEFRUN.1`.

SRE controller and trigger types are independent:

| SRE field | Source meaning |
|---|---|
| `CNTL ct=0/1/2/3` | Time / Hydraulic / Interval / PID controller |
| `TRGR ty=0/1/2` | Time / Hydraulic / Both trigger |
| `TRGR` operation `0/1` | Source `<` / `>`; emitted as `LessEqual` / `Greater` |
| `CNTL ta` | Enables/disables the corresponding `gi` trigger slot |

Controller type is read from the encoded `ct` value, not inferred from the
name; “Driel PID” is encoded as `ct=1` (Hydraulic), not `ct=3` (PID). The
model's hydraulic triggers observe water level at SRE branch `99938`, chainage
`34000`.

| Structure | Hydraulic condition | Selected controller output |
|---|---|---|
| Driel (`ST_73326`) | `H <= 10` / `H > 10` | Hydraulic lookup / time schedule to crest level |
| Amero (`ST_78756`) | `H <= 11.4` / `H > 11.4` | Hydraulic lookup / time schedule to crest level |
| Hagestein (`ST_78758`) | `H <= 11.4` / `H > 11.4` | Hydraulic lookup / time schedule to crest level |
| Driel Omloop (`ST_99477`) | `H <= 10` / `H > 10` | Time schedule, gate height `0.5` / `0` |

The time-controller tables for Driel, Amero, and Hagestein end in 2000, 2019,
and 2019 respectively; the Driel Omloop tables run to 2150. Every `ct=0`
output table is emitted as a D-RTC `timeAbsolute` series covering the effective
runtime. Before/after-table values use the SRE non-periodic endpoint hold. The
model contains hydraulic-triggered rules and time-controller output tables;
that is not the same as a calendar-time trigger.

At an exact threshold, the conversion intentionally maps the source low-side
`<` rule to `<=`; equality selects the low-side rule, while the high-side `>`
rule remains strict.

## Ordered implementation

### 1. Remove the incorrect native RTC conversion and RTC-folder pass-through — completed

The obsolete native/inventory and RTC-folder copy paths were removed. RTC is
opt-in and is now generated only from the selected SRE case. The new compiler
fails before writing an RTC package or DIMR RTC component if it encounters
unsupported source behavior.

### 2. Define a typed SRE RTC intermediate model and parser — implemented for current input

Reintroduce native parsing as a new, independently tested implementation.
Keep raw source codes and normalized enum values together so diagnostics can
identify the source record and unsupported values cannot be silently
misclassified.

- Parse `CNTL`, `TRGR`, and structure-to-controller links from `DEFSTR.*`.
  Preserve record ID, name, source file/line where available, raw values,
  tables, controlled structure/parameter, observation location, and trigger
  slots.
- Use explicit enums for the source values listed above. Never infer type from
  the name (for example, do not infer PID from “Driel PID”).
- Apply `ta` slot flags to the corresponding `gi` IDs. Retain disabled slots
  for diagnostics, but do not compile them as active trigger references.
- Validate identifiers, duplicate records, missing links, malformed table
  rows, sentinel values, and invalid/unknown enum codes. Surface actionable
  errors with record IDs; do not silently drop unsupported records.
- Parse the `Both` trigger's time and hydraulic components and its composition
  explicitly. Do not flatten it to a single condition without proving
  equivalent semantics.
- Keep SRE parsing separate from D-RTC XML generation so both can be tested
  without a running flow model.

### 3. Compile controller rules without changing their meaning — time and hydraulic subset implemented

Build a conversion layer from the typed SRE representation to D-RTC rules.
Use the D-RTC schema/runtime version matching the intended installed package.

| SRE controller | D-RTC representation | Required checks |
|---|---|---|
| Time (`ct=0`) | `timeAbsolute` with a PI time series covering the effective runtime | Preserve dated values and continuous interpolation; extend boundary values using SRE endpoint clamping |
| Hydraulic (`ct=1`) | `lookupTable` using the `Hydraulic Controller` TBLE role | Preserve axes and rows; map continuous interpolation to `LINEAR` and endpoint clamping to `BLOCK` |
| Interval (`ct=2`) | Equivalent interval rule or an explicitly composed rule | Confirm interval boundaries and transition behavior before mapping |
| PID (`ct=3`) | `pid` | Map setpoint, gains, sign, limits, initial state, and sampling semantics only when equivalent |

For the current case, the “Driel PID” record must compile as a hydraulic
lookup rule. Do not translate it into a PID rule. Do not use D-RTC `deadBand`
to emulate strict SRE triggers unless parity tests establish that its
state-retention semantics match SOBEK.

Validate controlled parameter support for every output. Crest-level and
gate-height controls require correct D-Flow FM structure-control exchange
items; do not omit gate-height controllers with only a warning. If a
controller cannot be represented faithfully, stop native package generation
with a specific diagnostic rather than emitting a partial package.

### 4. Compile trigger selection and controller activation — hydraulic subset implemented

- Map hydraulic SRE triggers to D-RTC standard conditions with the correct
  observed quantity and comparison (`LessEqual` for source `<`, `Greater` for
  source `>`).
- Map time triggers to calendar-time conditions only when the SRE trigger is
  actually `ty=0`. Map `ty=2` by explicitly composing its time and hydraulic
  components and preserving the source Boolean behavior.
- Preserve enabled trigger references and rule-to-trigger associations.
- Define and test the behavior when no trigger is true, when a threshold is
  exactly met, and when multiple triggers for one output are simultaneously
  true. Detect conflicting rules driving the same structure parameter before
  writing a runnable package.
- Ensure that each intended conditional rule is referenced by the correct
  trigger and that unconditional rules remain active only when the SRE model
  says they should.

### 5. Bind observations and actuator outputs to D-Flow FM — implemented

- Resolve each SRE branch/chainage to the corresponding converted FM branch
  and observation point. Validate the location and water-level quantity
  instead of relying on an assumed branch-name match.
- Generate or update `ObservationPoints.ini` entries and `rtcDataConfig.xml`
  imports using the D-RTC exchange-item names supported by the selected FM /
  RTC versions.
- Map each controlled SRE structure and parameter to the correct FM actuator
  exchange item, including crest level and gate height. Validate that the
  structure exists in the generated FM structure files and that the exchange
  item is writable.
- Keep the generated input/output mapping deterministic and report the SRE
  controller, FM structure, RTC rule, and exchange-item names for traceability.

### 6. Handle schedule coverage and runtime dates explicitly — implemented

- Derive the effective simulation start, stop, and reference date from the
  converted runtime; do not hard-code the source case's 2150 end date.
- Extend each absolute schedule to the effective runtime using SRE's verified
  continuous interpolation and first/last-value clamping outside its source
  bounds. Preserve all source knots inside the runtime.
- Emit the result as D-RTC `timeAbsolute` from a PI time series; do not
  simplify a bounded source table to an unconditional `constant` rule.
- Keep the default short conversion duration (`test_duration_seconds`) in
  mind: tests must distinguish a short smoke-test runtime from the full model
  interval and ensure generated schedules cover whichever interval is
  requested.

### 7. Generate and wire the D-RTC package through DIMR — package generation implemented; runtime check pending

- Generate `rtcToolsConfig.xml`, `rtcDataConfig.xml`, runtime/state
  configuration, and any required RTC files from validated rules, triggers,
  inputs, and outputs. Validate generated XML against the pinned D-RTC XSDs.
- Construct RTC coupling items from the SRE-derived observations and actuator
  outputs. Retain or refactor the DIMR coupler writer for the generated
  package, but do not support copying or parsing a user-supplied RTC package.
- Configure DIMR bidirectional couplers for FM observations to RTC and RTC
  commands to FM structures. Confirm the component/library names and exchange
  item identifiers against the target runtime, not only the repository sample.
- Make the RTC step, DIMR coupling step, FM step, start/stop times, and
  reference date mutually consistent. Reject invalid timing combinations
  before writing the package.
- Ensure output files are listed in the conversion report and that enabling
  RTC does not add the RTC component when generation or package validation
  fails.

### 8. Document the supported behavior and limitations — updated

Update [README.md](./README.md) to describe the SRE-only RTC source, the
supported SRE controller/trigger types, unsupported semantics, required
D-RTC/DIMR runtime versions, and how to enable conversion. State that users
cannot provide a separate RTC folder. Document the threshold-equality mapping
and schedule-coverage policy. Remove claims that are not backed by runtime
validation.

- Create a figure describing the SRE case's RTC controls, stored in the
  project's documentation assets and linked from the README. Show the shared
  water-level observation (branch `99938`, chainage `34000`), each structure's
  threshold conditions, which time or hydraulic controller is selected, and
  the controlled crest/gate-height output. Distinguish trigger conditions from
  time-controller value schedules, and show that equality selects the
  low-side rule after the `<` to `<=` mapping. Base the figure on the parsed
  SRE records, not on controller names.

## Validation plan

### Unit and golden tests

- Parse the SRE fixture and assert the exact enum values, controller/structure
  links, active `ta`/`gi` slots, observations, tables, and trigger thresholds.
- Assert that `ty=1` is hydraulic, `ct=1` is hydraulic, and a name containing
  “PID” does not change the encoded controller type.
- Test `ty=0/1/2`, `ct=0/1/2/3`, unknown codes, missing IDs, malformed tables,
  duplicate IDs, disabled trigger slots, and missing references.
- Test each generated rule independently: absolute schedules, hydraulic
  lookup values and interpolation, interval semantics, and PID
  parameter mapping where supported.
- Test strict threshold conditions immediately below, exactly at, and
  immediately above 10 and 11.4, verifying that equality selects the
  `LessEqual` low-side rule.
- Test schedule start/end boundaries and endpoint clamping before/after each
  source table.
- Validate the current case's lookup rows and outputs against the values in
  `DEFSTR.4` / `DEFSTR.5`, including Driel Omloop gate heights.

### Conversion and integration tests

- Test SRE-derived conversion with RTC enabled and the SRE fixture. Assert
  generated files, valid schemas, exact imports and exports, and no unsupported
  controller silently omitted.
- Test that there is no public folder/package input option. Test no-RTC
  conversion and the explicit warning/error path when RTC is requested but
  the SRE input is missing or its control set cannot be converted faithfully.
- Test a short DIMR/FM/RTC run with the actual supported runtime and inspect
  logs and coupler outputs. XML parsing alone is not evidence that the D-RTC
  package executes.
- Where SRE results are available, compare controller selection and output
  against the same water-level input series. Include threshold crossings,
  exact equality, schedule endpoints, and the full requested runtime.

## Completion criteria

- The old native reader/writer/fallback and stale documentation/tests are
  removed before the replacement is introduced; the separate RTC-folder
  option and package-copy path are removed as well.
- RTC is generated only from SRE input, and the generated package is wired
  through DIMR without a supplied-package fallback.
- Every supported SRE controller and trigger is compiled from source codes
  and active slots, not names or assumptions.
- All source outputs, observations, runtime dates, and trigger boundaries are
  represented or rejected explicitly; there is no silent approximation.
- A figure documenting the SRE RTC controls is included in the project
  documentation and linked from the README.
- Generated configuration validates against the intended D-RTC schemas and
  completes a DIMR/FM/D-RTC runtime smoke test.
- Focused RTC tests and the existing relevant conversion tests pass.

## References

- SRE case inputs: [DEFSTR.2](./data/sre_simulation/DEFSTR.2),
  [DEFSTR.4](./data/sre_simulation/DEFSTR.4),
  [DEFSTR.5](./data/sre_simulation/DEFSTR.5), and
  [DEFRUN.1](./data/sre_simulation/DEFRUN.1).
- [D-RTC User Manual](https://content.oss.deltares.nl/delft3d/D-Real_Time_Control_User_Manual.pdf).
- [D-Flow FM User Manual](./data/fm_manuals/D-Flow_FM_User_Manual_1D2D.pdf)
  and [DIMR User Manual](./data/fm_manuals/DIMR_User_Manual.pdf).
- D-RTC configuration schema:
  [rtcToolsConfig.xsd](https://github.com/Deltares/Delft3D/blob/e025e7875536d32506deba93d9d5a0254044310d/src/engines_gpl/fbc/packages/FBCTools/xsd/rtcToolsConfig.xsd).
