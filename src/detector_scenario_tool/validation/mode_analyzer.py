"""Mode tracking across a scenario.

The allowed-command matrix is not written out here any more: it comes from
`MessageDef.allowed_modes`, which is filled straight from the specification's validity table.

Limitation, unchanged from the previous implementation: long modes (`ERASE`, `TEST`, `DUMP`) end on
an internal completion event the scenario cannot see, so the model keeps the scenario in that mode
until an explicit `CMD_DUTY` / `CMD_SHUTDOWN`. Commands rejected only because of that assumption are
reported as warnings, never errors.
"""

from __future__ import annotations

from detector_scenario_tool.domain.scenario import ScenarioDocument, SendMessageStep
from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.modes import Mode
from detector_scenario_tool.validation.diagnostics import Diagnostic, Severity

#: Kept as a module-level view so tests and tooling can read the matrix without walking the
#: registry themselves.
ALLOWED_KU_BY_MODE: dict[Mode, set[int]] = {}
KT_ALLOWED_MODES: set[Mode] = set()


def _rebuild_matrices() -> None:
    ALLOWED_KU_BY_MODE.clear()
    for mode in Mode:
        ALLOWED_KU_BY_MODE[mode] = {
            spec.msg_id
            for spec in registry.by_category("KU")
            if mode in spec.allowed_modes
        }

    KT_ALLOWED_MODES.clear()
    for spec in registry.by_category("KT"):
        KT_ALLOWED_MODES.update(spec.allowed_modes)


_rebuild_matrices()


def refresh() -> None:
    """Re-read the registry, e.g. after a user-defined message was registered."""
    _rebuild_matrices()


def analyze_modes(document: ScenarioDocument) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    current_mode = Mode.DUTY

    for index, step in enumerate(document.steps):
        if not isinstance(step, SendMessageStep) or not step.enabled:
            continue
        if step.message is None or step.message.msg_id is None:
            continue

        spec = registry.find(step.message.category, step.message.msg_id)
        if spec is None:
            continue

        if current_mode not in spec.allowed_modes:
            diagnostics.append(
                _not_allowed_diagnostic(spec, index, current_mode)
            )
        else:
            current_mode = _apply_transition(current_mode, spec)

    return diagnostics


def _not_allowed_diagnostic(spec, index: int, mode: Mode) -> Diagnostic:
    if spec.category == "KT":
        # КТ are silently dropped by the НА — no acknowledgement comes back at all, so a
        # scenario that sends one outside OBSERVE simply loses the data.
        return Diagnostic(
            severity=Severity.WARNING,
            step_index=index,
            code="mode.kt_ignored",
            params={
                "msg": f"0x{spec.msg_id:04X}",
                "symbol": spec.symbol,
                "mode_key": mode.label_key,
            },
        )

    return Diagnostic(
        severity=Severity.ERROR,
        step_index=index,
        code="mode.ku_not_allowed",
        params={
            "msg": f"0x{spec.msg_id:04X}",
            "symbol": spec.symbol,
            "mode_key": mode.label_key,
        },
    )


def _apply_transition(current_mode: Mode, spec) -> Mode:
    if spec.changes_mode_to is not None:
        return spec.changes_mode_to

    if spec.symbol == "CMD_RESET_ALARM" and current_mode is Mode.ALARM:
        # §9.13: leaves ALARM only when MaskedAlarm ends up zero. A scenario cannot know the
        # hardware state, so assume the optimistic path — that is the case worth validating.
        return Mode.DUTY

    return current_mode


def mode_at_step(document: ScenarioDocument, step_index: int) -> Mode:
    """The mode the scenario is in when `step_index` executes."""
    current_mode = Mode.DUTY

    for index, step in enumerate(document.steps):
        if index >= step_index:
            break
        if not isinstance(step, SendMessageStep) or not step.enabled:
            continue
        if step.message is None or step.message.msg_id is None:
            continue

        spec = registry.find(step.message.category, step.message.msg_id)
        if spec is None or current_mode not in spec.allowed_modes:
            continue

        current_mode = _apply_transition(current_mode, spec)

    return current_mode
