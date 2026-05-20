from __future__ import annotations

from typing import Iterable

_CURRENT_LANGUAGE = "ru"

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "ru": {
        "app.title": "Detector Scenario Tool",

        "menu.file": "Файл",
        "menu.edit": "Правка",
        "menu.language": "Язык",

        "language.ru": "Русский",
        "language.en": "English",

        "action.new": "Новый",
        "action.open": "Открыть...",
        "action.save": "Сохранить",
        "action.save_as": "Сохранить как...",
        "action.export_packed_json": "Экспорт packed JSON...",
        "action.import_logs": "Импорт логов...",

        "action.add_ku": "Добавить КУ",
        "action.add_kt": "Добавить КТ",
        "action.add_wait": "Добавить ожидание",
        "action.add_wait_ts": "Добавить ожидание ТС",

        "action.delete_step": "Удалить шаг",
        "action.move_step_up": "Переместить шаг вверх",
        "action.move_step_down": "Переместить шаг вниз",
        "action.duplicate_step": "Дублировать шаг",
        "action.move_step_to_top": "Переместить шаг в начало",
        "action.move_step_to_bottom": "Переместить шаг в конец",

        "button.add_ku": "+ КУ",
        "button.add_kt": "+ КТ",
        "button.add_wait": "+ Ожидание",
        "button.add_wait_ts": "+ ТС",

        "tab.logs": "Логи",
        "tab.warnings": "Предупреждения",

        "timeline.detector_to_board": "Детектор → Борт",
        "timeline.board_to_detector": "Борт → Детектор",
        "timeline.time_ms": "Время, мс",
        "timeline.zoom_hint": "Ctrl+Колесо",

        "logs.import": "Импорт логов",
        "logs.clear": "Очистить логи",
        "logs.port1": "Порт 1",
        "logs.port2": "Порт 2",
        "logs.baud": "Скорость",
        "logs.start_live": "Старт live",
        "logs.stop_live": "Стоп live",
        "logs.pause": "Пауза",
        "logs.resume": "Продолжить",
        "logs.auto_scroll": "Автопрокрутка",
        "logs.save_session": "Сохранять live-сессию",
        "logs.save_session_path_placeholder": "Путь к файлу сессии...",
        "logs.browse": "Обзор...",
        "logs.live_stopped": "Live: остановлен",
        "logs.no_logs_loaded": "Логи не загружены.",

        "logs.filter.dir.all": "Все направления",
        "logs.filter.dir.tx": "TX",
        "logs.filter.dir.rx": "RX",
        "logs.filter.category.all": "Все категории",
        "logs.filter.source.all": "Все источники",
        "logs.filter.problems_only": "Только проблемы",
        "logs.filter.reset": "Сбросить фильтры",

        "logs.column.time": "Время",
        "logs.column.source": "Источник",
        "logs.column.direction": "Направление",
        "logs.column.message": "Сообщение",
        "logs.column.summary": "Кратко",
        "logs.column.payload_hex": "Данные HEX",

        "scenario.column.index": "#",
        "scenario.column.enabled": "Вкл",
        "scenario.column.kind": "Тип",
        "scenario.column.message_target": "Сообщение / Цель",
        "scenario.column.timeout": "Таймаут",
        "scenario.column.comment": "Комментарий",

        "warnings.column.severity": "Серьёзность",
        "warnings.column.step": "Шаг",
        "warnings.column.code": "Код",
        "warnings.column.message": "Сообщение",

        "severity.error": "Ошибка",
        "severity.warning": "Предупреждение",
        "severity.info": "Инфо",

        "status.live_prefix": "Live: {text}",
        "status.live_error_prefix": "Ошибка live: {text}",

        "summary.execution": (
            "Текущий шаг: {current} | "
            "Первое расхождение: {mismatch} | "
            "Сопоставлено шагов: {matched_steps}/{total_steps} | "
            "Несопоставлено шагов: {unmatched_steps} | "
            "Сопоставлено логов: {matched_logs}/{total_logs} | "
            "Лишних логов: {unmatched_logs}"
        ),
        "summary.current.none": "нет",
        "summary.current.step": "#{step}",
        "summary.mismatch.none": "нет",
        "summary.mismatch.step": "шаг #{step}",

        "scenario.step.send": "Отправка {category}",
        "scenario.step.wait_ts": "Ожидание ТС",
        "scenario.step.wait": "Ожидание",
        "scenario.step.comment": "Комментарий",
        "scenario.step.ms": "{value} мс",

        "execution.no_message_selected": "Для шага не выбрано сообщение.",
        "execution.no_expected_ts": "Для WAIT_FOR_TS не выбрано ожидаемое ТС.",
        "execution.wait_not_matched": "WAIT_TIME шаг #{step} не сопоставляется с логами.",
        "execution.current_first_live": "Текущий шаг #{step}: ожидание первого live-события протокола.",
        "execution.current_blocked_here": "Текущий шаг #{step}: выполнение остановилось здесь после предыдущего рассинхрона.",
        "execution.pending_not_reached": "Шаг #{step} ещё не был достигнут.",
        "execution.pending_blocked": "Шаг #{step} ещё не достигнут, потому что выполнение остановилось раньше.",

        "execution.current_waiting_send": "Текущий шаг #{step}: ожидание {direction} {category} 0x{msg_id:04X}.",
        "execution.current_waiting_ts": "Текущий WAIT_FOR_TS шаг #{step}: ожидание {direction} {category} 0x{msg_id:04X}.",

        "execution.matched_send": "Шаг #{step} сопоставлен с логом #{log_row}: {direction} {category} 0x{msg_id:04X}, источник={source}, время={time} мс.",
        "execution.matched_wait_ts": "WAIT_FOR_TS шаг #{step} сопоставлен с логом #{log_row}: {direction} {category} 0x{msg_id:04X}, источник={source}, время={time} мс.",
        "execution.matched_to_step": "Сопоставлено со сценарием: шаг #{step}, {category} 0x{msg_id:04X}.",
        "execution.matched_to_wait_ts": "Сопоставлено со сценарием: шаг #{step}, WAIT_FOR_TS {category} 0x{msg_id:04X}.",

        "execution.source_unusual_step": "Шаг #{step} сопоставлен с логом #{log_row}, но источник выглядит подозрительно: {source}; ожидался один из {expected}.",
        "execution.source_unusual_log": "Лог сопоставлен со сценарием для шага #{step}, но источник выглядит подозрительно.",

        "execution.first_mismatch": "Первое расхождение на шаге #{step}: ожидалось {direction} {category} 0x{msg_id:04X}, но следующий несопоставленный лог #{log_row}: {got_direction} {got_category} 0x{got_msg_id:04X} от {source} в {time} мс.",
        "execution.extra_before_step": "Лишний лог перед шагом #{step}: лог #{log_row} = {direction} {category} 0x{msg_id:04X} от {source} в {time} мс.",
        "execution.unmatched_log": "Лог #{log_row} лишний: {direction} {category} 0x{msg_id:04X}, источник={source}, время={time} мс.",

        "log.direction.tx": "TX",
        "log.direction.rx": "RX",
        "log.source.empty": "-",

        "live.status.stopped": "остановлен",
        "live.status.no_ports": "не выбраны порты",
        "live.status.starting": "запуск...",
        "live.status.nothing_to_pause": "нечего ставить на паузу",
        "live.status.nothing_to_resume": "нечего продолжать",
        "live.status.paused": "пауза",
        "live.status.resumed": "продолжено",
        "live.status.session_save_enabled_no_path": "сохранение live-сессии включено, но путь к файлу пуст",
        "live.status.saving_session": "сохранение сессии в {path}",
        "live.status.save_error": "ошибка сохранения: {error}",

        "serial.status.connected": "подключено: {port} @ {baudrate}",
        "serial.status.disconnected": "отключено: {port}",
        "serial.status.paused": "пауза: {port}",
        "serial.status.resumed": "продолжено: {port}",
        "serial.status.reconnecting": "переподключение: {port}",

        "serial.error.pyserial_missing": "pyserial не установлен. Установи: pip install pyserial",
        "serial.error.open_failed": "не удалось открыть {port}: {error}",
        "serial.error.read_failed": "{port}: ошибка чтения: {error}",

        "action.export_generated_c": "Сгенерировать C код",
        "dialog.export_generated_c": "Экспорт C кода",
        "dialog.export_failed_title": "Ошибка экспорта",

        "inspector.empty": "Шаг не выбран",

        "inspector.group.common": "Общее",
        "inspector.group.message": "Сообщение",
        "inspector.group.payload": "Payload",
        "inspector.group.packed_preview": "Packed preview",
        "inspector.group.wait_time": "Ожидание времени",
        "inspector.group.wait_for_ts": "Ожидание ТС",

        "inspector.field.title": "Название",
        "inspector.field.enabled": "Включено",
        "inspector.field.comment": "Комментарий",
        "inspector.field.message": "Сообщение",
        "inspector.field.ack_policy": "ACK policy",
        "inspector.field.ack_timeout_ms": "ACK timeout, мс",
        "inspector.field.pack_status": "Статус pack",
        "inspector.field.expected_length": "Ожидаемая длина",
        "inspector.field.actual_length": "Фактическая длина",
        "inspector.field.hex": "HEX",
        "inspector.field.delay_ms": "Задержка, мс",
        "inspector.field.expected_ts": "Ожидаемое ТС",
        "inspector.field.timeout_ms": "Таймаут, мс",
        "inspector.field.bind_to_previous_ku": "Привязать к предыдущему КУ",
        "inspector.field.ack_for_msg_id": "ACK для MSG_ID",
        "inspector.field.require_ack_accepted": "Требовать ACK accepted",

        "inspector.ack.none": "None",
        "inspector.ack.expect": "Expect ACK",
        "inspector.ack.optional": "Optional ACK",

        "inspector.payload.no_specialized_editor": "Для этого сообщения пока нет специализированного редактора payload.",
        "inspector.pack.no_message_selected": "Сообщение не выбрано",
        "inspector.pack.ok": "OK",
        "inspector.pack.length_mismatch": "Несовпадение длины",
        "inspector.pack.error": "Ошибка: {error}",

        "payload.fixed.title.telemetry_request": "Запрос телеметрии",
        "payload.fixed.title.status_request": "Запрос статуса",
        "payload.fixed.title.power_off": "Выключение",
        "payload.fixed.title.reset_emergency_status": "Сброс аварийного статуса",
        "payload.fixed.info": "Payload фиксированный: AA AA AA AA AA AA",

        "payload.set_time.board_time_ms": "Бортовое время, мс",
        "payload.set_time.board_time_s": "Бортовое время, с",

        "payload.obs_enable.bank": "Выбранный банк NAND",
        "payload.obs_enable.ped_power": "Питание ПЕД включено",
        "payload.obs_enable.ped_low_power": "Пониженное питание ПЕД",
        "payload.obs_enable.ped_event_registration": "Регистрация событий ПЕД",
        "payload.obs_enable.event_format": "Режим формата событий",
        "payload.obs_enable.event_count": "Режим счёта событий",
        "payload.obs_enable.spectrum_mode": "Режим спектра",
        "payload.obs_enable.hist_cells": "Ячейки гистограммы",
        "payload.obs_enable.particle_threshold": "Порог частиц",

        "payload.obs_control.ped_power": "Питание ПЕД включено",
        "payload.obs_control.ped_low_power": "Пониженное питание ПЕД",
        "payload.obs_control.ped_event_registration": "Регистрация событий ПЕД",
        "payload.obs_control.event_format": "Режим формата событий",
        "payload.obs_control.event_count": "Режим счёта событий",
        "payload.obs_control.spectrum_mode": "Режим спектра",
        "payload.obs_control.hist_cells": "Ячейки гистограммы",

        "payload.standby.bank": "Выбранный банк NAND",
        "payload.standby.nand_power": "Питание NAND включено",
        "payload.standby.ped_power": "Питание ПЕД включено",
        "payload.standby.ped_low_power": "Пониженное питание ПЕД",

        "payload.option.bank.nand1": "NAND1",
        "payload.option.bank.nand2": "NAND2",

        "payload.option.event_format.0": "0 - не формировать",
        "payload.option.event_format.1": "1 - формировать всегда",
        "payload.option.event_format.2": "2 - вне внутреннего РП",
        "payload.option.event_format.3": "3 - вне внутреннего и внешнего РП",
        "payload.option.event_format.3_short": "3 - вне РП",
        "payload.option.event_format.4": "4 - только если n(AC1) < n(AC1)max",

        "payload.option.event_count.0": "0 - не используется",
        "payload.option.event_count.1": "1 - Nmax=1",
        "payload.option.event_count.2": "2 - Nmax=10",
        "payload.option.event_count.3": "3 - Nmax=20",
        "payload.option.event_count.4": "4 - Nmax=50",
        "payload.option.event_count.5": "5 - Nmax=100",

        "payload.option.spectrum_mode.0": "0 - без спектра",
        "payload.option.spectrum_mode.1": "1 - Спектр-1",
        "payload.option.spectrum_mode.2": "2 - Спектр-2",

        "payload.option.hist_cells.0": "0 - не используется",
        "payload.option.hist_cells.1": "1 - 256",
        "payload.option.hist_cells.2": "2 - 512",
        "payload.option.hist_cells.3": "3 - 1024",
        "payload.option.hist_cells.4": "4 - 2048",

        "payload.data_output.bank": "Выбранный банк NAND",
        "payload.data_output.keep_power": "Сохранить питание после выдачи",
        "payload.data_output.output_interface": "Интерфейс выдачи",
        "payload.data_output.output_type": "Тип выдачи",
        "payload.data_output.requested_packet_count": "Запрошенное число пакетов",

        "payload.erase_flash.bank": "Выбранный банк NAND",
        "payload.erase_flash.keep_power": "Сохранить питание NAND после стирания",

        "payload.test_flash.bank": "Выбранный банк NAND",
        "payload.test_flash.keep_power": "Сохранить питание NAND после теста",

        "payload.test_results.bank": "Выбранный банк NAND",

        "payload.time_sync.board_time_ms": "Бортовое время, мс",
        "payload.time_sync.board_time_s": "Бортовое время, с",
        "payload.time_sync.board_time_s_placeholder": "0 .. 4294967295",

        "payload.option.output_interface.usb": "USB",
        "payload.option.output_interface.can": "CAN",

        "payload.option.output_type.requested_count": "Запрошенное число пакетов",
        "payload.option.output_type.accumulated": "Накопленные данные",

        "payload.settings.group.control": "Управляющее слово",
        "payload.settings.group.temp": "Температурные пределы",
        "payload.settings.group.power": "Пределы напряжения / тока",
        "payload.settings.group.radiation": "Пороги радиации",
        "payload.settings.group.rtc": "Начальное RTC",
        "payload.settings.group.misc": "Сессия / счётчики / маска аварий",

        "payload.settings.write_session_id": "Записать session id",
        "payload.settings.write_nand1_packet_count": "Записать число пакетов NAND1",
        "payload.settings.write_nand2_packet_count": "Записать число пакетов NAND2",
        "payload.settings.write_nand1_erase_count": "Записать число стираний NAND1",
        "payload.settings.write_nand2_erase_count": "Записать число стираний NAND2",
        "payload.settings.write_nand1_test_count": "Записать число тестов NAND1",
        "payload.settings.write_nand2_test_count": "Записать число тестов NAND2",

        "payload.settings.min_mc_temp": "Мин. температура МК",
        "payload.settings.max_mc_temp": "Макс. температура МК",
        "payload.settings.min_pu_temp": "Мин. температура ПУ",
        "payload.settings.max_pu_temp": "Макс. температура ПУ",
        "payload.settings.min_ped_temp": "Мин. температура ПЭД",
        "payload.settings.max_ped_temp": "Макс. температура ПЭД",
        "payload.settings.min_bd_temp": "Мин. температура блока детектора",
        "payload.settings.max_bd_temp": "Макс. температура блока детектора",

        "payload.settings.min_pu_voltage": "Мин. напряжение ПУ",
        "payload.settings.max_pu_voltage": "Макс. напряжение ПУ",
        "payload.settings.min_pu_current": "Мин. ток ПУ",
        "payload.settings.max_pu_current": "Макс. ток ПУ",
        "payload.settings.min_ped_voltage": "Мин. напряжение ПЭД",
        "payload.settings.max_ped_voltage": "Макс. напряжение ПЭД",
        "payload.settings.min_ped_current": "Мин. ток ПЭД",
        "payload.settings.max_ped_current": "Макс. ток ПЭД",

        "payload.settings.outer_radiation_lmin": "Внешняя радиация Lmin",
        "payload.settings.outer_radiation_lmax": "Внешняя радиация Lmax",
        "payload.settings.inner_radiation_bmin": "Внутренняя радиация Bmin",
        "payload.settings.ac1_max_count": "Макс. счёт AC1",

        "payload.settings.initial_rtc": "Начальное RTC",
        "payload.settings.session_id": "Session id",
        "payload.settings.nand1_packet_count": "Число пакетов NAND1",
        "payload.settings.nand2_packet_count": "Число пакетов NAND2",
        "payload.settings.nand1_erase_count": "Число стираний NAND1",
        "payload.settings.nand2_erase_count": "Число стираний NAND2",
        "payload.settings.nand1_test_count": "Число тестов NAND1",
        "payload.settings.nand2_test_count": "Число тестов NAND2",
        "payload.settings.alarm_mask": "Маска аварий",

        "payload.orbit.group.time": "Время измерения",
        "payload.orbit.group.coords": "Координаты",
        "payload.orbit.group.velocity": "Скорость",
        "payload.orbit.group.misc": "Дополнительно",

        "payload.orbit.time_ms": "Время, мс",
        "payload.orbit.time_s": "Время, с",
        "payload.orbit.x": "X",
        "payload.orbit.y": "Y",
        "payload.orbit.z": "Z",
        "payload.orbit.vx": "Vx",
        "payload.orbit.vy": "Vy",
        "payload.orbit.vz": "Vz",
        "payload.orbit.l_shell": "L-shell",
        "payload.orbit.b_field": "B-field",
        "payload.orbit.i32_placeholder": "-2147483648 .. 2147483647",

        "payload.orientation.group.time": "Время измерения",
        "payload.orientation.group.quaternion": "Кватернион",
        "payload.orientation.time_ms": "Время, мс",
        "payload.orientation.time_s": "Время, с",
        "payload.orientation.q0": "q0",
        "payload.orientation.q1": "q1",
        "payload.orientation.q2": "q2",
        "payload.orientation.q3": "q3",

        "payload.geomagnetic.group.time": "Время измерения",
        "payload.geomagnetic.group.vector": "Вектор геомагнитного поля",
        "payload.geomagnetic.time_ms": "Время, мс",
        "payload.geomagnetic.time_s": "Время, с",
        "payload.geomagnetic.bx": "Bx",
        "payload.geomagnetic.by": "By",
        "payload.geomagnetic.bz": "Bz",

        "action.add_expected_response": "Добавить ожидаемый ответ",
        "button.add_expected_response": "+ Ожидаемый ответ",
        "dialog.no_expected_response_title": "Нет ожидаемого ответа",
        "dialog.no_expected_response_text": "Для выбранной команды пока не задан автоматически ожидаемый ответ.",
        "dialog.expected_response_invalid_title": "Невозможно вставить ответ",
        "dialog.expected_response_invalid_text": "Выбери шаг отправки KU или KT.",
        "dialog.expected_response_exists_title": "Ответ уже существует",
        "dialog.expected_response_exists_text": "Следующий шаг уже является ожиданием ответа и выглядит подходящим.",

        "inspector.group.retry": "Повторы / ACK",
        "inspector.field.retry_attempts": "Количество попыток",
        "inspector.field.retry_delay_ms": "Задержка между повторами, мс",
        "inspector.field.retry_on_timeout": "Повторять при таймауте",
        "inspector.field.retry_on_reject": "Повторять при reject",
    },
    "en": {
        "app.title": "Detector Scenario Tool",

        "menu.file": "File",
        "menu.edit": "Edit",
        "menu.language": "Language",

        "language.ru": "Русский",
        "language.en": "English",

        "action.new": "New",
        "action.open": "Open...",
        "action.save": "Save",
        "action.save_as": "Save As...",
        "action.export_packed_json": "Export packed JSON...",
        "action.import_logs": "Import logs...",

        "action.add_ku": "Add KU",
        "action.add_kt": "Add KT",
        "action.add_wait": "Add Wait",
        "action.add_wait_ts": "Add Wait TS",

        "action.delete_step": "Delete step",
        "action.move_step_up": "Move step up",
        "action.move_step_down": "Move step down",
        "action.duplicate_step": "Duplicate step",
        "action.move_step_to_top": "Move step to top",
        "action.move_step_to_bottom": "Move step to bottom",

        "button.add_ku": "+ KU",
        "button.add_kt": "+ KT",
        "button.add_wait": "+ Wait",
        "button.add_wait_ts": "+ TS",

        "tab.logs": "Logs",
        "tab.warnings": "Warnings",

        "timeline.detector_to_board": "Detector → Board",
        "timeline.board_to_detector": "Board → Detector",
        "timeline.time_ms": "Time, ms",
        "timeline.zoom_hint": "Ctrl+Wheel",

        "logs.import": "Import logs",
        "logs.clear": "Clear logs",
        "logs.port1": "Port 1",
        "logs.port2": "Port 2",
        "logs.baud": "Baud",
        "logs.start_live": "Start live",
        "logs.stop_live": "Stop live",
        "logs.pause": "Pause",
        "logs.resume": "Resume",
        "logs.auto_scroll": "Auto-scroll",
        "logs.save_session": "Save live session",
        "logs.save_session_path_placeholder": "Session file path...",
        "logs.browse": "Browse...",
        "logs.live_stopped": "Live: stopped",
        "logs.no_logs_loaded": "No logs loaded.",

        "logs.filter.dir.all": "All directions",
        "logs.filter.dir.tx": "TX",
        "logs.filter.dir.rx": "RX",
        "logs.filter.category.all": "All categories",
        "logs.filter.source.all": "All sources",
        "logs.filter.problems_only": "Problems only",
        "logs.filter.reset": "Reset filters",

        "logs.column.time": "Time",
        "logs.column.source": "Src",
        "logs.column.direction": "Dir",
        "logs.column.message": "Message",
        "logs.column.summary": "Summary",
        "logs.column.payload_hex": "Payload hex",

        "scenario.column.index": "#",
        "scenario.column.enabled": "Enabled",
        "scenario.column.kind": "Kind",
        "scenario.column.message_target": "Message / Target",
        "scenario.column.timeout": "Timeout",
        "scenario.column.comment": "Comment",

        "warnings.column.severity": "Severity",
        "warnings.column.step": "Step",
        "warnings.column.code": "Code",
        "warnings.column.message": "Message",

        "severity.error": "Error",
        "severity.warning": "Warning",
        "severity.info": "Info",

        "status.live_prefix": "Live: {text}",
        "status.live_error_prefix": "Live error: {text}",

        "summary.execution": (
            "Current step: {current} | "
            "First mismatch: {mismatch} | "
            "Steps matched: {matched_steps}/{total_steps} | "
            "Unmatched steps: {unmatched_steps} | "
            "Logs matched: {matched_logs}/{total_logs} | "
            "Unmatched logs: {unmatched_logs}"
        ),
        "summary.current.none": "none",
        "summary.current.step": "#{step}",
        "summary.mismatch.none": "none",
        "summary.mismatch.step": "step #{step}",
        "scenario.step.send": "Send {category}",
        "scenario.step.wait_ts": "Wait for TS",
        "scenario.step.wait": "Wait",
        "scenario.step.comment": "Comment",
        "scenario.step.ms": "{value} ms",

        "execution.no_message_selected": "Step has no message selected.",
        "execution.no_expected_ts": "WAIT_FOR_TS has no expected TS selected.",
        "execution.wait_not_matched": "WAIT_TIME step #{step} is not matched to logs.",
        "execution.current_first_live": "Current step #{step}: waiting for first live protocol event.",
        "execution.current_blocked_here": "Current step #{step}: execution is paused here after a previous mismatch.",
        "execution.pending_not_reached": "Step #{step} has not been reached yet.",
        "execution.pending_blocked": "Step #{step} has not been reached because execution is blocked earlier.",

        "execution.current_waiting_send": "Current step #{step}: waiting for {direction} {category} 0x{msg_id:04X}.",
        "execution.current_waiting_ts": "Current WAIT_FOR_TS step #{step}: waiting for {direction} {category} 0x{msg_id:04X}.",

        "execution.matched_send": "Matched step #{step} with log row #{log_row}: {direction} {category} 0x{msg_id:04X}, source={source}, time={time} ms.",
        "execution.matched_wait_ts": "Matched WAIT_FOR_TS step #{step} with log row #{log_row}: {direction} {category} 0x{msg_id:04X}, source={source}, time={time} ms.",
        "execution.matched_to_step": "Matched to scenario step #{step}: {category} 0x{msg_id:04X}.",
        "execution.matched_to_wait_ts": "Matched to scenario step #{step}: WAIT_FOR_TS {category} 0x{msg_id:04X}.",

        "execution.source_unusual_step": "Matched step #{step} with log row #{log_row}, but source looks unusual: {source}; expected one of {expected}.",
        "execution.source_unusual_log": "Matched to scenario step #{step}, but source looks unusual.",

        "execution.first_mismatch": "First mismatch at step #{step}: expected {direction} {category} 0x{msg_id:04X}, but next unmatched log row #{log_row} is {got_direction} {got_category} 0x{got_msg_id:04X} from {source} at {time} ms.",
        "execution.extra_before_step": "Unexpected extra log before step #{step}: log row #{log_row} = {direction} {category} 0x{msg_id:04X} from {source} at {time} ms.",
        "execution.unmatched_log": "Log row #{log_row} is unmatched: {direction} {category} 0x{msg_id:04X}, source={source}, time={time} ms.",

        "log.direction.tx": "TX",
        "log.direction.rx": "RX",
        "log.source.empty": "-",

        "live.status.stopped": "stopped",
        "live.status.no_ports": "no ports selected",
        "live.status.starting": "starting...",
        "live.status.nothing_to_pause": "nothing to pause",
        "live.status.nothing_to_resume": "nothing to resume",
        "live.status.paused": "paused",
        "live.status.resumed": "resumed",
        "live.status.session_save_enabled_no_path": "session save enabled, but file path is empty",
        "live.status.saving_session": "saving session to {path}",
        "live.status.save_error": "save error: {error}",

        "serial.status.connected": "connected: {port} @ {baudrate}",
        "serial.status.disconnected": "disconnected: {port}",
        "serial.status.paused": "paused: {port}",
        "serial.status.resumed": "resumed: {port}",
        "serial.status.reconnecting": "reconnecting: {port}",

        "serial.error.pyserial_missing": "pyserial is not installed. Install it with: pip install pyserial",
        "serial.error.open_failed": "failed to open {port}: {error}",
        "serial.error.read_failed": "{port}: read error: {error}",

        "action.export_generated_c": "Export generated C...",
        "dialog.export_generated_c": "Export generated C",
        "dialog.export_failed_title": "Export failed",

        "inspector.empty": "No step selected",

        "inspector.group.common": "Common",
        "inspector.group.message": "Message",
        "inspector.group.payload": "Payload",
        "inspector.group.packed_preview": "Packed preview",
        "inspector.group.wait_time": "Wait time",
        "inspector.group.wait_for_ts": "Wait for TS",

        "inspector.field.title": "Title",
        "inspector.field.enabled": "Enabled",
        "inspector.field.comment": "Comment",
        "inspector.field.message": "Message",
        "inspector.field.ack_policy": "ACK policy",
        "inspector.field.ack_timeout_ms": "ACK timeout ms",
        "inspector.field.pack_status": "Pack status",
        "inspector.field.expected_length": "Expected length",
        "inspector.field.actual_length": "Actual length",
        "inspector.field.hex": "Hex",
        "inspector.field.delay_ms": "Delay ms",
        "inspector.field.expected_ts": "Expected TS",
        "inspector.field.timeout_ms": "Timeout ms",
        "inspector.field.bind_to_previous_ku": "Bind to previous KU",
        "inspector.field.ack_for_msg_id": "ACK for MSG_ID",
        "inspector.field.require_ack_accepted": "Require ACK accepted",

        "inspector.ack.none": "None",
        "inspector.ack.expect": "Expect ACK",
        "inspector.ack.optional": "Optional ACK",

        "inspector.payload.no_specialized_editor": "No specialized payload editor for this message yet.",
        "inspector.pack.no_message_selected": "No message selected",
        "inspector.pack.ok": "OK",
        "inspector.pack.length_mismatch": "Length mismatch",
        "inspector.pack.error": "Error: {error}",

        "payload.fixed.title.telemetry_request": "Telemetry request",
        "payload.fixed.title.status_request": "Status request",
        "payload.fixed.title.power_off": "Power off",
        "payload.fixed.title.reset_emergency_status": "Reset emergency status",
        "payload.fixed.info": "Payload is fixed: AA AA AA AA AA AA",

        "payload.set_time.board_time_ms": "Board time ms",
        "payload.set_time.board_time_s": "Board time s",

        "payload.obs_enable.bank": "Selected NAND bank",
        "payload.obs_enable.ped_power": "PED power enabled",
        "payload.obs_enable.ped_low_power": "PED low power",
        "payload.obs_enable.ped_event_registration": "PED event registration",
        "payload.obs_enable.event_format": "Event format mode",
        "payload.obs_enable.event_count": "Event count mode",
        "payload.obs_enable.spectrum_mode": "Spectrum mode",
        "payload.obs_enable.hist_cells": "Histogram cells",
        "payload.obs_enable.particle_threshold": "Particle threshold",

        "payload.obs_control.ped_power": "PED power enabled",
        "payload.obs_control.ped_low_power": "PED low power",
        "payload.obs_control.ped_event_registration": "PED event registration",
        "payload.obs_control.event_format": "Event format mode",
        "payload.obs_control.event_count": "Event count mode",
        "payload.obs_control.spectrum_mode": "Spectrum mode",
        "payload.obs_control.hist_cells": "Histogram cells",

        "payload.standby.bank": "Selected NAND bank",
        "payload.standby.nand_power": "NAND power enabled",
        "payload.standby.ped_power": "PED power enabled",
        "payload.standby.ped_low_power": "PED low power",

        "payload.option.bank.nand1": "NAND1",
        "payload.option.bank.nand2": "NAND2",

        "payload.option.event_format.0": "0 - do not generate",
        "payload.option.event_format.1": "1 - always generate",
        "payload.option.event_format.2": "2 - outside inner RP",
        "payload.option.event_format.3": "3 - outside inner and outer RP",
        "payload.option.event_format.3_short": "3 - outside RP",
        "payload.option.event_format.4": "4 - only if n(AC1) < n(AC1)max",

        "payload.option.event_count.0": "0 - not used",
        "payload.option.event_count.1": "1 - Nmax=1",
        "payload.option.event_count.2": "2 - Nmax=10",
        "payload.option.event_count.3": "3 - Nmax=20",
        "payload.option.event_count.4": "4 - Nmax=50",
        "payload.option.event_count.5": "5 - Nmax=100",

        "payload.option.spectrum_mode.0": "0 - no spectrum",
        "payload.option.spectrum_mode.1": "1 - Spectrum-1",
        "payload.option.spectrum_mode.2": "2 - Spectrum-2",

        "payload.option.hist_cells.0": "0 - not used",
        "payload.option.hist_cells.1": "1 - 256",
        "payload.option.hist_cells.2": "2 - 512",
        "payload.option.hist_cells.3": "3 - 1024",
        "payload.option.hist_cells.4": "4 - 2048",

        "payload.data_output.bank": "Selected NAND bank",
        "payload.data_output.keep_power": "Keep power after output",
        "payload.data_output.output_interface": "Output interface",
        "payload.data_output.output_type": "Output type",
        "payload.data_output.requested_packet_count": "Requested packet count",

        "payload.erase_flash.bank": "Selected NAND bank",
        "payload.erase_flash.keep_power": "Keep NAND power after erase",

        "payload.test_flash.bank": "Selected NAND bank",
        "payload.test_flash.keep_power": "Keep NAND power after test",

        "payload.test_results.bank": "Selected NAND bank",

        "payload.time_sync.board_time_ms": "Board time ms",
        "payload.time_sync.board_time_s": "Board time s",
        "payload.time_sync.board_time_s_placeholder": "0 .. 4294967295",

        "payload.option.output_interface.usb": "USB",
        "payload.option.output_interface.can": "CAN",

        "payload.option.output_type.requested_count": "Requested packet count",
        "payload.option.output_type.accumulated": "Accumulated data",

        "payload.settings.group.control": "Control word",
        "payload.settings.group.temp": "Temperature limits",
        "payload.settings.group.power": "Voltage / current limits",
        "payload.settings.group.radiation": "Radiation thresholds",
        "payload.settings.group.rtc": "Initial RTC",
        "payload.settings.group.misc": "Session / counters / alarm mask",

        "payload.settings.write_session_id": "Write session id",
        "payload.settings.write_nand1_packet_count": "Write NAND1 packet count",
        "payload.settings.write_nand2_packet_count": "Write NAND2 packet count",
        "payload.settings.write_nand1_erase_count": "Write NAND1 erase count",
        "payload.settings.write_nand2_erase_count": "Write NAND2 erase count",
        "payload.settings.write_nand1_test_count": "Write NAND1 test count",
        "payload.settings.write_nand2_test_count": "Write NAND2 test count",

        "payload.settings.min_mc_temp": "Min MCU temp",
        "payload.settings.max_mc_temp": "Max MCU temp",
        "payload.settings.min_pu_temp": "Min PU temp",
        "payload.settings.max_pu_temp": "Max PU temp",
        "payload.settings.min_ped_temp": "Min PED temp",
        "payload.settings.max_ped_temp": "Max PED temp",
        "payload.settings.min_bd_temp": "Min detector block temp",
        "payload.settings.max_bd_temp": "Max detector block temp",

        "payload.settings.min_pu_voltage": "Min PU voltage",
        "payload.settings.max_pu_voltage": "Max PU voltage",
        "payload.settings.min_pu_current": "Min PU current",
        "payload.settings.max_pu_current": "Max PU current",
        "payload.settings.min_ped_voltage": "Min PED voltage",
        "payload.settings.max_ped_voltage": "Max PED voltage",
        "payload.settings.min_ped_current": "Min PED current",
        "payload.settings.max_ped_current": "Max PED current",

        "payload.settings.outer_radiation_lmin": "Outer radiation Lmin",
        "payload.settings.outer_radiation_lmax": "Outer radiation Lmax",
        "payload.settings.inner_radiation_bmin": "Inner radiation Bmin",
        "payload.settings.ac1_max_count": "AC1 max count",

        "payload.settings.initial_rtc": "Initial RTC",
        "payload.settings.session_id": "Session id",
        "payload.settings.nand1_packet_count": "NAND1 packet count",
        "payload.settings.nand2_packet_count": "NAND2 packet count",
        "payload.settings.nand1_erase_count": "NAND1 erase count",
        "payload.settings.nand2_erase_count": "NAND2 erase count",
        "payload.settings.nand1_test_count": "NAND1 test count",
        "payload.settings.nand2_test_count": "NAND2 test count",
        "payload.settings.alarm_mask": "Alarm mask",

        "payload.orbit.group.time": "Measurement time",
        "payload.orbit.group.coords": "Coordinates",
        "payload.orbit.group.velocity": "Velocity",
        "payload.orbit.group.misc": "Orbit extras",

        "payload.orbit.time_ms": "Time ms",
        "payload.orbit.time_s": "Time s",
        "payload.orbit.x": "X",
        "payload.orbit.y": "Y",
        "payload.orbit.z": "Z",
        "payload.orbit.vx": "Vx",
        "payload.orbit.vy": "Vy",
        "payload.orbit.vz": "Vz",
        "payload.orbit.l_shell": "L-shell",
        "payload.orbit.b_field": "B-field",
        "payload.orbit.i32_placeholder": "-2147483648 .. 2147483647",

        "payload.orientation.group.time": "Measurement time",
        "payload.orientation.group.quaternion": "Quaternion",
        "payload.orientation.time_ms": "Time ms",
        "payload.orientation.time_s": "Time s",
        "payload.orientation.q0": "q0",
        "payload.orientation.q1": "q1",
        "payload.orientation.q2": "q2",
        "payload.orientation.q3": "q3",

        "payload.geomagnetic.group.time": "Measurement time",
        "payload.geomagnetic.group.vector": "Geomagnetic field vector",
        "payload.geomagnetic.time_ms": "Time ms",
        "payload.geomagnetic.time_s": "Time s",
        "payload.geomagnetic.bx": "Bx",
        "payload.geomagnetic.by": "By",
        "payload.geomagnetic.bz": "Bz",

        "action.add_expected_response": "Add expected response",
        "button.add_expected_response": "+ Expected response",
        "dialog.no_expected_response_title": "No expected response",
        "dialog.no_expected_response_text": "No automatic expected response is defined yet for the selected command.",
        "dialog.expected_response_invalid_title": "Cannot insert response",
        "dialog.expected_response_invalid_text": "Select a KU or KT send step.",
        "dialog.expected_response_exists_title": "Response already exists",
        "dialog.expected_response_exists_text": "The next step is already a response wait and looks compatible.",

        "inspector.group.retry": "Retry / ACK",
        "inspector.field.retry_attempts": "Attempt count",
        "inspector.field.retry_delay_ms": "Retry delay ms",
        "inspector.field.retry_on_timeout": "Retry on timeout",
        "inspector.field.retry_on_reject": "Retry on reject",
    },
}


def get_language() -> str:
    return _CURRENT_LANGUAGE


def set_language(language: str) -> None:
    global _CURRENT_LANGUAGE
    if language not in _TRANSLATIONS:
        raise ValueError(f"Unsupported language: {language}")
    _CURRENT_LANGUAGE = language


def available_languages() -> Iterable[str]:
    return _TRANSLATIONS.keys()


def tr(key: str, **kwargs) -> str:
    text = _TRANSLATIONS.get(_CURRENT_LANGUAGE, {}).get(key)
    if text is None:
        text = _TRANSLATIONS["en"].get(key, key)
    return text.format(**kwargs) if kwargs else text
