from __future__ import annotations

from enum import Enum

from detector_scenario_tool.domain.scenario import (
    ScenarioDocument,
    SendMessageStep,
)
from detector_scenario_tool.validation.diagnostics import Diagnostic, Severity


class NaMode(str, Enum):
    STANDBY = "standby"  # режим 1
    ERASE = "erase"  # режим 2
    TEST = "test"  # режим 3
    OBSERVATION = "observation"  # режим 4
    DATA_OUTPUT = "data_output"  # режим 5
    EMERGENCY = "emergency"  # режим 6
    POWER_OFF = "power_off"  # режим 7


MODE_LABELS: dict[NaMode, str] = {
    NaMode.STANDBY: "дежурный режим",
    NaMode.ERASE: "режим стирания ППЗУ",
    NaMode.TEST: "режим тестирования ППЗУ",
    NaMode.OBSERVATION: "режим наблюдений",
    NaMode.DATA_OUTPUT: "режим вывода данных",
    NaMode.EMERGENCY: "аварийный режим",
    NaMode.POWER_OFF: "режим выключения",
}

# MSG_ID -> допустимость по режимам 1..7
# Основано на таблице 5.2.10 протокола.
ALLOWED_KU_BY_MODE: dict[NaMode, set[int]] = {
    NaMode.STANDBY: {
        0x0000, 0x0001, 0x0002, 0x0003, 0x0006, 0x0007, 0x0008, 0x0009,
        0x000A, 0x000B,
    },
    NaMode.ERASE: {
        0x0001, 0x0005, 0x0006, 0x000B,
    },
    NaMode.TEST: {
        0x0001, 0x0005, 0x0006, 0x000B,
    },
    NaMode.OBSERVATION: {
        0x0000, 0x0001, 0x0004, 0x0005, 0x000B,
    },
    NaMode.DATA_OUTPUT: {
        0x0001, 0x0005, 0x000B,
    },
    NaMode.EMERGENCY: {
        0x0000, 0x0001, 0x0007, 0x0008, 0x000B, 0x000C,
    },
    NaMode.POWER_OFF: {
        0x0001,
    },
}

KT_ALLOWED_MODES: set[NaMode] = {
    NaMode.OBSERVATION,
}

TARGET_MODE_BY_KU: dict[int, NaMode] = {
    0x0003: NaMode.OBSERVATION,
    0x0006: NaMode.DATA_OUTPUT,
    0x0008: NaMode.ERASE,
    0x0009: NaMode.TEST,
    0x000B: NaMode.POWER_OFF,
}


def analyze_modes(document: ScenarioDocument) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    current_mode = NaMode.STANDBY

    for i, step in enumerate(document.steps):
        if not isinstance(step, SendMessageStep):
            continue

        if step.message is None or step.message.msg_id is None:
            continue

        category = step.message.category
        msg_id = step.message.msg_id

        if category == "KU":
            allowed = ALLOWED_KU_BY_MODE.get(current_mode, set())
            if msg_id not in allowed:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.WARNING,
                        step_index=i,
                        code="mode.ku_not_allowed",
                        message=(
                            f"КУ 0x{msg_id:04X} '{step.message.name}' "
                            f"недопустима в режиме '{MODE_LABELS[current_mode]}'."
                        ),
                    )
                )

            # Дополнительная явная проверка: переходы в 2/3/4/5 только из дежурного режима.
            if msg_id in (0x0003, 0x0006, 0x0008, 0x0009) and current_mode != NaMode.STANDBY:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.WARNING,
                        step_index=i,
                        code="mode.target_mode_requires_standby",
                        message=(
                            f"КУ 0x{msg_id:04X} '{step.message.name}' "
                            f"обычно должна запускаться из дежурного режима, "
                            f"а сейчас сценарий находится в режиме '{MODE_LABELS[current_mode]}'."
                        ),
                    )
                )

            current_mode = _apply_mode_transition(current_mode, msg_id)

        elif category == "KT":
            if current_mode not in KT_ALLOWED_MODES:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.WARNING,
                        step_index=i,
                        code="mode.kt_ignored",
                        message=(
                            f"КТ 0x{msg_id:04X} '{step.message.name}' "
                            f"в режиме '{MODE_LABELS[current_mode]}' игнорируется НА."
                        ),
                    )
                )

    return diagnostics


def _apply_mode_transition(current_mode: NaMode, msg_id: int) -> NaMode:
    # Явные переходы по КУ
    if msg_id == 0x0005:
        return NaMode.STANDBY

    if msg_id in TARGET_MODE_BY_KU:
        return TARGET_MODE_BY_KU[msg_id]

    if msg_id == 0x000C and current_mode == NaMode.EMERGENCY:
        # Сброс аварийного статуса из аварийного режима логически возвращает в режим 1.
        return NaMode.STANDBY

    return current_mode
