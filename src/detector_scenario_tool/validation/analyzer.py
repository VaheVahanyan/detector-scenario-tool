from __future__ import annotations

from detector_scenario_tool.domain.scenario import (
    ScenarioDocument,
    SendMessageStep,
    StepKind,
    WaitForTsStep,
    WaitTimeStep,
)
from detector_scenario_tool.validation.diagnostics import Diagnostic, Severity
from detector_scenario_tool.validation.mode_analyzer import analyze_modes


def analyze_scenario(document: ScenarioDocument) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    for i, step in enumerate(document.steps):
        if isinstance(step, SendMessageStep):
            if step.message is None or step.message.msg_id is None:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        step_index=i,
                        code="message.missing",
                        message="У шага отправки не выбрано сообщение.",
                    )
                )

            if step.kind == StepKind.SEND_KU:
                if step.ack_timeout_ms is None:
                    diagnostics.append(
                        Diagnostic(
                            severity=Severity.WARNING,
                            step_index=i,
                            code="ack.timeout_missing",
                            message="Для SEND_KU не задан ACK timeout.",
                        )
                    )

                if step.kind == StepKind.SEND_KU:
                    if _ku_requires_status_wait(step):
                        next_step = document.steps[i + 1] if i + 1 < len(document.steps) else None
                        next_next_step = document.steps[i + 2] if i + 2 < len(document.steps) else None

                        if not _has_expected_status_sequence(next_step, next_next_step):
                            diagnostics.append(
                                Diagnostic(
                                    severity=Severity.WARNING,
                                    step_index=i,
                                    code="status.wait_missing",
                                    message=(
                                        f"После KU 0x{step.message.msg_id:04X} '{step.message.name}' "
                                        f"нет ожидаемой последовательности WAIT_FOR_TS на ТС 'Статус' "
                                        f"(допустимо сразу или после шага квитанции)."
                                    ),
                                )
                            )

                next_step = document.steps[i + 1] if i + 1 < len(document.steps) else None
                if not _is_ack_wait_step(next_step):
                    diagnostics.append(
                        Diagnostic(
                            severity=Severity.WARNING,
                            step_index=i,
                            code="ack.wait_missing",
                            message="После SEND_KU нет следующего шага WAIT_FOR_TS на ТС 'Квитанция'.",
                        )
                    )
                else:
                    _validate_ack_wait_binding(
                        send_step=step,
                        wait_step=next_step,
                        step_index=i + 1,
                        diagnostics=diagnostics,
                    )

                if step.message and step.message.category == "KU" and step.message.msg_id == 0x0002:
                    _validate_set_time_payload(step, i, diagnostics)

                if step.message and step.message.category == "KU" and step.message.msg_id == 0x0003:
                    _validate_observation_enable_payload(step, i, diagnostics)

                if step.message and step.message.category == "KU" and step.message.msg_id == 0x0004:
                    _validate_observation_control_payload(step, i, diagnostics)

                if step.message and step.message.category == "KU" and step.message.msg_id == 0x0005:
                    _validate_standby_mode_payload(step, i, diagnostics)

                if step.message and step.message.category == "KU" and step.message.msg_id == 0x0006:
                    _validate_data_output_payload(step, i, diagnostics)

                if step.message and step.message.category == "KU" and step.message.msg_id == 0x0007:
                    _validate_settings_payload(step, i, diagnostics)

                if step.message and step.message.category == "KU" and step.message.msg_id == 0x0008:
                    _validate_erase_flash_payload(step, i, diagnostics)

                if step.message and step.message.category == "KU" and step.message.msg_id == 0x0009:
                    _validate_test_flash_payload(step, i, diagnostics)

                if step.message and step.message.category == "KU" and step.message.msg_id == 0x000A:
                    _validate_test_results_request_payload(step, i, diagnostics)

                if step.message and step.message.category == "KT" and step.message.msg_id == 0x0100:
                    _validate_kt_0100_payload(step, i, diagnostics)

                if step.message and step.message.category == "KT" and step.message.msg_id == 0x0101:
                    _validate_kt_0101_payload(step, i, diagnostics)

                if step.message and step.message.category == "KT" and step.message.msg_id == 0x0102:
                    _validate_kt_0102_payload(step, i, diagnostics)

                if step.message and step.message.category == "KT" and step.message.msg_id == 0x0103:
                    _validate_kt_0103_payload(step, i, diagnostics)

        elif isinstance(step, WaitTimeStep):
            if step.delay_ms <= 0:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.WARNING,
                        step_index=i,
                        code="wait_time.invalid",
                        message="WAIT_TIME имеет delay_ms <= 0.",
                    )
                )

        elif isinstance(step, WaitForTsStep):
            if step.expected is None or step.expected.msg_id is None:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        step_index=i,
                        code="wait_ts.target_missing",
                        message="У WAIT_FOR_TS не выбран ожидаемый ТС.",
                    )
                )

            if step.timeout_ms <= 0:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.WARNING,
                        step_index=i,
                        code="wait_ts.timeout_invalid",
                        message="WAIT_FOR_TS имеет timeout_ms <= 0.",
                    )
                )
            if step.expected is not None and step.expected.category == "TS" and step.expected.msg_id == 0x0201:
                if step.bind_to_previous_ku and step.ack_for_msg_id is None:
                    diagnostics.append(
                        Diagnostic(
                            severity=Severity.INFO,
                            step_index=i,
                            code="ack.bind_prev_ku_auto",
                            message="WAIT_FOR_TS привязан к предыдущей KU. MSG_ID будет логически браться из предыдущего шага.",
                        )
                    )

                if step.require_ack_ok and not step.bind_to_previous_ku and step.ack_for_msg_id is None:
                    diagnostics.append(
                        Diagnostic(
                            severity=Severity.WARNING,
                            step_index=i,
                            code="ack.require_ok_without_binding",
                            message="Требуется ACK accepted, но не задана привязка к предыдущей KU и не указан ACK for MSG_ID.",
                        )
                    )

    diagnostics.extend(analyze_modes(document))
    return diagnostics


def _is_ack_wait_step(step) -> bool:
    if not isinstance(step, WaitForTsStep):
        return False
    if step.expected is None:
        return False
    return step.expected.category == "TS" and step.expected.msg_id == 0x0201


def _validate_ack_wait_binding(
        send_step: SendMessageStep,
        wait_step: WaitForTsStep,
        step_index: int,
        diagnostics: list[Diagnostic],
) -> None:
    if wait_step.expected is None or wait_step.expected.msg_id != 0x0201:
        return

    expected_msg_id = send_step.message.msg_id if send_step.message is not None else None

    if wait_step.bind_to_previous_ku:
        if expected_msg_id is None:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    step_index=step_index,
                    code="ack.bind_prev_ku_without_msg",
                    message="WAIT_FOR_TS привязан к предыдущей KU, но у предыдущего SEND_KU нет MSG_ID.",
                )
            )
        elif wait_step.ack_for_msg_id is not None and wait_step.ack_for_msg_id != expected_msg_id:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    step_index=step_index,
                    code="ack.bind_prev_ku_mismatch",
                    message="ACK for MSG_ID не совпадает с MSG_ID предыдущей KU.",
                )
            )

    if wait_step.ack_for_msg_id is not None and expected_msg_id is not None:
        if wait_step.ack_for_msg_id != expected_msg_id:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    step_index=step_index,
                    code="ack.msg_id_mismatch",
                    message="WAIT_FOR_TS ожидает квитанцию не на ту KU, которая стоит перед ним.",
                )
            )


def _validate_set_time_payload(
        step: SendMessageStep,
        step_index: int,
        diagnostics: list[Diagnostic],
) -> None:
    board_time_ms = step.payload.get("board_time_ms")
    board_time_s = step.payload.get("board_time_s")

    if board_time_ms is None:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.set_time.board_time_ms_missing",
                message="Для 'Предустановка времени' не задано поле board_time_ms.",
            )
        )
    elif not (0 <= int(board_time_ms) <= 65535):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="ku.set_time.board_time_ms_range",
                message="Поле board_time_ms должно быть в диапазоне 0..65535.",
            )
        )

    if board_time_s is None:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.set_time.board_time_s_missing",
                message="Для 'Предустановка времени' не задано поле board_time_s.",
            )
        )
    elif not (0 <= int(board_time_s) <= 0xFFFFFFFF):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="ku.set_time.board_time_s_range",
                message="Поле board_time_s должно быть в диапазоне 0..4294967295.",
            )
        )


def _validate_observation_enable_payload(
        step: SendMessageStep,
        step_index: int,
        diagnostics: list[Diagnostic],
) -> None:
    selected_nand_bank = step.payload.get("selected_nand_bank")
    ped_power_enabled = bool(step.payload.get("ped_power_enabled", False))
    ped_low_power = bool(step.payload.get("ped_low_power", False))
    ped_event_registration = bool(step.payload.get("ped_event_registration", False))
    event_format_mode = int(step.payload.get("event_format_mode", 0))
    event_count_mode = int(step.payload.get("event_count_mode", 0))
    spectrum_mode = int(step.payload.get("spectrum_mode", 0))
    histogram_cells = int(step.payload.get("histogram_cells", 0))
    particle_threshold = int(step.payload.get("particle_threshold", 0))

    if selected_nand_bank not in ("nand1", "nand2"):
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.obs_enable.bank_missing",
                message="Для 'Включение режима наблюдений' не выбран корректный банк NAND.",
            )
        )

    if not ped_power_enabled and ped_low_power:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.obs_enable.ped_low_power_ignored",
                message="PED low power включён, но PED power выключен. Этот флаг выглядит бессмысленно.",
            )
        )

    if not ped_power_enabled and ped_event_registration:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.obs_enable.ped_event_registration_ignored",
                message="PED event registration включён, но PED power выключен. Этот флаг выглядит бессмысленно.",
            )
        )

    if ped_power_enabled and ped_low_power and ped_event_registration:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.obs_enable.ped_event_registration_suspect",
                message="PED event registration включён одновременно с PED low power. По протоколу это подозрительная комбинация.",
            )
        )

    if event_format_mode == 0 and event_count_mode != 0:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.obs_enable.event_count_unused",
                message="Event count mode задан, хотя event format mode = 0. Это выглядит бессмысленно.",
            )
        )

    if spectrum_mode == 0 and histogram_cells != 0:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.obs_enable.histogram_unused_no_spectrum",
                message="Histogram cells заданы, хотя spectrum mode = 0. Это выглядит бессмысленно.",
            )
        )

    if spectrum_mode != 1 and histogram_cells != 0:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.obs_enable.histogram_only_for_spectrum1",
                message="Histogram cells заданы не для Spectrum-1. По протоколу это подозрительная комбинация.",
            )
        )

    if not (0 <= particle_threshold <= 15):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="ku.obs_enable.particle_threshold_range",
                message="Particle threshold должен быть в диапазоне 0..15.",
            )
        )


def _validate_observation_control_payload(
        step: SendMessageStep,
        step_index: int,
        diagnostics: list[Diagnostic],
) -> None:
    ped_power_enabled = bool(step.payload.get("ped_power_enabled", False))
    ped_low_power = bool(step.payload.get("ped_low_power", False))
    ped_event_registration = bool(step.payload.get("ped_event_registration", False))

    event_format_mode = int(step.payload.get("event_format_mode", 0))
    event_count_mode = int(step.payload.get("event_count_mode", 0))
    spectrum_mode = int(step.payload.get("spectrum_mode", 0))
    histogram_cells = int(step.payload.get("histogram_cells", 0))

    if not ped_power_enabled and ped_low_power:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.obs_control.ped_low_power_ignored",
                message="PED low power включён, но PED power выключен. Этот флаг выглядит бессмысленно.",
            )
        )

    if not ped_power_enabled and ped_event_registration:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.obs_control.ped_event_registration_ignored",
                message="PED event registration включён, но PED power выключен. Этот флаг выглядит бессмысленно.",
            )
        )

    if ped_power_enabled and ped_low_power and ped_event_registration:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.obs_control.ped_event_registration_suspect",
                message="PED event registration включён одновременно с PED low power. По протоколу это подозрительная комбинация.",
            )
        )

    if event_format_mode == 0 and event_count_mode != 0:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.obs_control.event_count_unused",
                message="Event count mode задан, хотя event format mode = 0. Это выглядит бессмысленно.",
            )
        )

    if spectrum_mode == 0 and histogram_cells != 0:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.obs_control.histogram_unused_no_spectrum",
                message="Histogram cells заданы, хотя spectrum mode = 0. Это выглядит бессмысленно.",
            )
        )

    if spectrum_mode != 1 and histogram_cells != 0:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.obs_control.histogram_only_for_spectrum1",
                message="Histogram cells заданы не для Spectrum-1. По протоколу это подозрительная комбинация.",
            )
        )


def _validate_standby_mode_payload(
        step: SendMessageStep,
        step_index: int,
        diagnostics: list[Diagnostic],
) -> None:
    selected_nand_bank = step.payload.get("selected_nand_bank")
    ped_power_enabled = bool(step.payload.get("ped_power_enabled", False))
    ped_low_power = bool(step.payload.get("ped_low_power", False))

    if selected_nand_bank not in ("nand1", "nand2"):
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.standby.bank_missing",
                message="Для 'Дежурный режим' не выбран корректный банк NAND.",
            )
        )

    if not ped_power_enabled and ped_low_power:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.standby.ped_low_power_ignored",
                message="PED low power включён, но PED power выключен. Этот флаг выглядит бессмысленно.",
            )
        )


def _validate_data_output_payload(
        step: SendMessageStep,
        step_index: int,
        diagnostics: list[Diagnostic],
) -> None:
    selected_nand_bank = step.payload.get("selected_nand_bank")
    output_interface = step.payload.get("output_interface")
    output_type = step.payload.get("output_type")
    requested_packet_count = int(step.payload.get("requested_packet_count", 0))

    if selected_nand_bank not in ("nand1", "nand2"):
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.data_output.bank_missing",
                message="Для 'Вывод данных' не выбран корректный банк NAND.",
            )
        )

    if output_interface not in ("usb", "can"):
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.data_output.interface_missing",
                message="Для 'Вывод данных' не выбран корректный интерфейс вывода.",
            )
        )

    if output_type not in ("requested_count", "accumulated"):
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.data_output.type_missing",
                message="Для 'Вывод данных' не выбран корректный тип вывода.",
            )
        )

    if requested_packet_count < 0:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="ku.data_output.requested_packet_count_negative",
                message="Requested packet count не может быть отрицательным.",
            )
        )

    if output_type == "accumulated" and requested_packet_count != 0:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.data_output.requested_packet_count_ignored",
                message="Requested packet count задан, хотя output type = accumulated. По протоколу это поле тогда игнорируется.",
            )
        )


def _validate_settings_payload(
        step: SendMessageStep,
        step_index: int,
        diagnostics: list[Diagnostic],
) -> None:
    min_mc_temp = int(step.payload.get("min_mc_temp", 0))
    max_mc_temp = int(step.payload.get("max_mc_temp", 0))
    min_pu_temp = int(step.payload.get("min_pu_temp", 0))
    max_pu_temp = int(step.payload.get("max_pu_temp", 0))
    min_ped_temp = int(step.payload.get("min_ped_temp", 0))
    max_ped_temp = int(step.payload.get("max_ped_temp", 0))
    min_bd_temp = int(step.payload.get("min_bd_temp", 0))
    max_bd_temp = int(step.payload.get("max_bd_temp", 0))

    min_pu_voltage = int(step.payload.get("min_pu_voltage", 0))
    max_pu_voltage = int(step.payload.get("max_pu_voltage", 0))
    min_pu_current = int(step.payload.get("min_pu_current", 0))
    max_pu_current = int(step.payload.get("max_pu_current", 0))
    min_ped_voltage = int(step.payload.get("min_ped_voltage", 0))
    max_ped_voltage = int(step.payload.get("max_ped_voltage", 0))
    min_ped_current = int(step.payload.get("min_ped_current", 0))
    max_ped_current = int(step.payload.get("max_ped_current", 0))

    outer_radiation_lmin = int(step.payload.get("outer_radiation_lmin", 0))
    outer_radiation_lmax = int(step.payload.get("outer_radiation_lmax", 0))
    inner_radiation_bmin = int(step.payload.get("inner_radiation_bmin", 0))
    ac1_max_count = int(step.payload.get("ac1_max_count", 0))
    initial_rtc = int(step.payload.get("initial_rtc", 0))

    session_id = int(step.payload.get("session_id", 0))
    nand1_packet_count = int(step.payload.get("nand1_packet_count", 0))
    nand2_packet_count = int(step.payload.get("nand2_packet_count", 0))
    nand1_erase_count = int(step.payload.get("nand1_erase_count", 0))
    nand2_erase_count = int(step.payload.get("nand2_erase_count", 0))
    nand1_test_count = int(step.payload.get("nand1_test_count", 0))
    nand2_test_count = int(step.payload.get("nand2_test_count", 0))
    alarm_mask = int(step.payload.get("alarm_mask", 0))

    if min_mc_temp > max_mc_temp:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.settings.mc_temp_range",
                message="Min MCU temp больше Max MCU temp.",
            )
        )

    if min_pu_temp > max_pu_temp:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.settings.pu_temp_range",
                message="Min PU temp больше Max PU temp.",
            )
        )

    if min_ped_temp > max_ped_temp:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.settings.ped_temp_range",
                message="Min PED temp больше Max PED temp.",
            )
        )

    if min_bd_temp > max_bd_temp:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.settings.bd_temp_range",
                message="Min detector block temp больше Max detector block temp.",
            )
        )

    if min_pu_voltage > max_pu_voltage:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.settings.pu_voltage_range",
                message="Min PU voltage больше Max PU voltage.",
            )
        )

    if min_pu_current > max_pu_current:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.settings.pu_current_range",
                message="Min PU current больше Max PU current.",
            )
        )

    if min_ped_voltage > max_ped_voltage:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.settings.ped_voltage_range",
                message="Min PED voltage больше Max PED voltage.",
            )
        )

    if min_ped_current > max_ped_current:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.settings.ped_current_range",
                message="Min PED current больше Max PED current.",
            )
        )

    if outer_radiation_lmin > outer_radiation_lmax:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.settings.outer_radiation_range",
                message="Outer radiation Lmin больше Outer radiation Lmax.",
            )
        )

    if not (0 <= initial_rtc <= 0xFFFFFFFF):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="ku.settings.initial_rtc_range",
                message="Initial RTC должен быть в диапазоне 0..4294967295.",
            )
        )

    if ac1_max_count < 0:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="ku.settings.ac1_max_count_range",
                message="AC1 max count не может быть отрицательным.",
            )
        )

    if not (0 <= session_id <= 65535):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="ku.settings.session_id_range",
                message="Session id должен быть в диапазоне 0..65535.",
            )
        )

    if not (0 <= nand1_packet_count <= 16777215):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="ku.settings.nand1_packet_count_range",
                message="NAND1 packet count должен быть в диапазоне 0..16777215.",
            )
        )

    if not (0 <= nand2_packet_count <= 16777215):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="ku.settings.nand2_packet_count_range",
                message="NAND2 packet count должен быть в диапазоне 0..16777215.",
            )
        )

    for value, code, title in [
        (nand1_erase_count, "ku.settings.nand1_erase_count_range", "NAND1 erase count"),
        (nand2_erase_count, "ku.settings.nand2_erase_count_range", "NAND2 erase count"),
        (nand1_test_count, "ku.settings.nand1_test_count_range", "NAND1 test count"),
        (nand2_test_count, "ku.settings.nand2_test_count_range", "NAND2 test count"),
        (alarm_mask, "ku.settings.alarm_mask_range", "Alarm mask"),
    ]:
        if not (0 <= value <= 65535):
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    step_index=step_index,
                    code=code,
                    message=f"{title} должен быть в диапазоне 0..65535.",
                )
            )


def _validate_erase_flash_payload(
        step: SendMessageStep,
        step_index: int,
        diagnostics: list[Diagnostic],
) -> None:
    selected_nand_bank = step.payload.get("selected_nand_bank")

    if selected_nand_bank not in ("nand1", "nand2"):
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.erase_flash.bank_missing",
                message="Для 'Стирание ППЗУ' не выбран корректный банк NAND.",
            )
        )


def _validate_test_flash_payload(
        step: SendMessageStep,
        step_index: int,
        diagnostics: list[Diagnostic],
) -> None:
    selected_nand_bank = step.payload.get("selected_nand_bank")

    if selected_nand_bank not in ("nand1", "nand2"):
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.test_flash.bank_missing",
                message="Для 'Тест ППЗУ' не выбран корректный банк NAND.",
            )
        )


def _validate_test_results_request_payload(
        step: SendMessageStep,
        step_index: int,
        diagnostics: list[Diagnostic],
) -> None:
    selected_nand_bank = step.payload.get("selected_nand_bank")

    if selected_nand_bank not in ("nand1", "nand2"):
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                step_index=step_index,
                code="ku.test_results_request.bank_missing",
                message="Для 'Запрос результатов теста ППЗУ' не выбран корректный банк NAND.",
            )
        )


def _validate_kt_0100_payload(
        step: SendMessageStep,
        step_index: int,
        diagnostics: list[Diagnostic],
) -> None:
    board_time_ms = int(step.payload.get("board_time_ms", 0))
    board_time_s = int(step.payload.get("board_time_s", 0))

    if not (0 <= board_time_ms <= 65535):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="kt.0100.board_time_ms_range",
                message="board_time_ms должен быть в диапазоне 0..65535.",
            )
        )

    if not (0 <= board_time_s <= 0xFFFFFFFF):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="kt.0100.board_time_s_range",
                message="board_time_s должен быть в диапазоне 0..4294967295.",
            )
        )


def _validate_kt_0101_payload(
        step: SendMessageStep,
        step_index: int,
        diagnostics: list[Diagnostic],
) -> None:
    measurement_time_ms = int(step.payload.get("measurement_time_ms", 0))
    measurement_time_s = int(step.payload.get("measurement_time_s", 0))

    x = int(step.payload.get("x", 0))
    y = int(step.payload.get("y", 0))
    z = int(step.payload.get("z", 0))

    vx = int(step.payload.get("vx", 0))
    vy = int(step.payload.get("vy", 0))
    vz = int(step.payload.get("vz", 0))

    l_shell = int(step.payload.get("l_shell", 0))
    b_field = int(step.payload.get("b_field", 0))

    if not (0 <= measurement_time_ms <= 65535):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="kt.0101.measurement_time_ms_range",
                message="measurement_time_ms должен быть в диапазоне 0..65535.",
            )
        )

    if not (0 <= measurement_time_s <= 0xFFFFFFFF):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="kt.0101.measurement_time_s_range",
                message="measurement_time_s должен быть в диапазоне 0..4294967295.",
            )
        )

    for value, code, title in [
        (x, "kt.0101.x_range", "x"),
        (y, "kt.0101.y_range", "y"),
        (z, "kt.0101.z_range", "z"),
        (vx, "kt.0101.vx_range", "vx"),
        (vy, "kt.0101.vy_range", "vy"),
        (vz, "kt.0101.vz_range", "vz"),
    ]:
        if not (-0x80000000 <= value <= 0x7FFFFFFF):
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    step_index=step_index,
                    code=code,
                    message=f"{title} должен быть в диапазоне -2147483648..2147483647.",
                )
            )

    if not (0 <= l_shell <= 65535):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="kt.0101.l_shell_range",
                message="l_shell должен быть в диапазоне 0..65535.",
            )
        )

    if not (0 <= b_field <= 65535):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="kt.0101.b_field_range",
                message="b_field должен быть в диапазоне 0..65535.",
            )
        )


def _validate_kt_0102_payload(
        step: SendMessageStep,
        step_index: int,
        diagnostics: list[Diagnostic],
) -> None:
    measurement_time_ms = int(step.payload.get("measurement_time_ms", 0))
    measurement_time_s = int(step.payload.get("measurement_time_s", 0))

    q0 = int(step.payload.get("q0", 0))
    q1 = int(step.payload.get("q1", 0))
    q2 = int(step.payload.get("q2", 0))
    q3 = int(step.payload.get("q3", 0))

    if not (0 <= measurement_time_ms <= 65535):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="kt.0102.measurement_time_ms_range",
                message="measurement_time_ms должен быть в диапазоне 0..65535.",
            )
        )

    if not (0 <= measurement_time_s <= 0xFFFFFFFF):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="kt.0102.measurement_time_s_range",
                message="measurement_time_s должен быть в диапазоне 0..4294967295.",
            )
        )

    for value, code, title in [
        (q0, "kt.0102.q0_range", "q0"),
        (q1, "kt.0102.q1_range", "q1"),
        (q2, "kt.0102.q2_range", "q2"),
        (q3, "kt.0102.q3_range", "q3"),
    ]:
        if not (-0x80000000 <= value <= 0x7FFFFFFF):
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    step_index=step_index,
                    code=code,
                    message=f"{title} должен быть в диапазоне -2147483648..2147483647.",
                )
            )


def _validate_kt_0103_payload(
        step: SendMessageStep,
        step_index: int,
        diagnostics: list[Diagnostic],
) -> None:
    measurement_time_ms = int(step.payload.get("measurement_time_ms", 0))
    measurement_time_s = int(step.payload.get("measurement_time_s", 0))

    bx = int(step.payload.get("bx", 0))
    by = int(step.payload.get("by", 0))
    bz = int(step.payload.get("bz", 0))

    if not (0 <= measurement_time_ms <= 65535):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="kt.0103.measurement_time_ms_range",
                message="measurement_time_ms должен быть в диапазоне 0..65535.",
            )
        )

    if not (0 <= measurement_time_s <= 0xFFFFFFFF):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                step_index=step_index,
                code="kt.0103.measurement_time_s_range",
                message="measurement_time_s должен быть в диапазоне 0..4294967295.",
            )
        )

    for value, code, title in [
        (bx, "kt.0103.bx_range", "bx"),
        (by, "kt.0103.by_range", "by"),
        (bz, "kt.0103.bz_range", "bz"),
    ]:
        if not (-0x80000000 <= value <= 0x7FFFFFFF):
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    step_index=step_index,
                    code=code,
                    message=f"{title} должен быть в диапазоне -2147483648..2147483647.",
                )
            )


def _ku_requires_status_wait(step: SendMessageStep) -> bool:
    if step.message is None or step.message.category != "KU" or step.message.msg_id is None:
        return False

    return step.message.msg_id in {
        0x0003,  # Включение режима наблюдений
        0x0005,  # Дежурный режим
        0x0006,  # Вывод данных
        0x0008,  # Стирание ППЗУ
        0x0009,  # Тест ППЗУ
        0x000B,  # Выключение
        0x000C,  # Сброс аварийного статуса
    }


def _is_status_wait_step(step) -> bool:
    if not isinstance(step, WaitForTsStep):
        return False
    if step.expected is None:
        return False
    return step.expected.category == "TS" and step.expected.msg_id == 0x0200

def _has_expected_status_sequence(step1, step2) -> bool:
    if _is_status_wait_step(step1):
        return True

    if _is_ack_wait_step(step1) and _is_status_wait_step(step2):
        return True

    return False