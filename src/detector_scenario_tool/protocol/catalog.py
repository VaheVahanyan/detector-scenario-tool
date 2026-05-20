from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MessageSpec:
    category: str  # KU / KT / TS
    msg_id: int
    name: str
    payload_length: int
    is_long: bool
    ack_expected: bool = False


class ProtocolCatalog:
    def __init__(self) -> None:
        self.messages: list[MessageSpec] = [
            MessageSpec("KU", 0x0000, "Запрос телеметрии", 6, False, True),
            MessageSpec("KU", 0x0001, "Запрос статуса", 6, False, True),
            MessageSpec("KU", 0x0002, "Предустановка времени", 6, False, True),
            MessageSpec("KU", 0x0003, "Включение режима наблюдений", 6, False, True),
            MessageSpec("KU", 0x0004, "Управление режимом наблюдений", 6, False, True),
            MessageSpec("KU", 0x0005, "Дежурный режим", 6, False, True),
            MessageSpec("KU", 0x0006, "Вывод данных", 6, False, True),
            MessageSpec("KU", 0x0007, "Задание настроек", 64, True, True),
            MessageSpec("KU", 0x0008, "Стирание ППЗУ", 6, False, True),
            MessageSpec("KU", 0x0009, "Тест ППЗУ", 6, False, True),
            MessageSpec("KU", 0x000A, "Запрос результатов теста ППЗУ", 6, False, True),
            MessageSpec("KU", 0x000B, "Выключение", 6, False, True),
            MessageSpec("KU", 0x000C, "Сброс аварийного статуса", 6, False, True),

            MessageSpec("KT", 0x0100, "Сверка времени", 6, False, False),
            MessageSpec("KT", 0x0101, "Параметры орбиты", 34, True, False),
            MessageSpec("KT", 0x0102, "Параметры ориентации", 22, True, False),
            MessageSpec("KT", 0x0103, "Геомагнитное поле", 18, True, False),

            MessageSpec("TS", 0x0200, "Статус", 6, False, False),
            MessageSpec("TS", 0x0201, "Квитанция", 6, False, False),
            MessageSpec("TS", 0x0202, "Телеметрия", 96, True, False),
            MessageSpec("TS", 0x0203, "Результаты теста ППЗУ", 6144, True, False),
        ]

    def get_by_category(self, category: str) -> list[MessageSpec]:
        return [m for m in self.messages if m.category == category]

    def get_ku_messages(self) -> list[MessageSpec]:
        return self.get_by_category("KU")

    def get_kt_messages(self) -> list[MessageSpec]:
        return self.get_by_category("KT")

    def get_ts_messages(self) -> list[MessageSpec]:
        return self.get_by_category("TS")

    def find(self, category: str, msg_id: int) -> MessageSpec | None:
        for message in self.messages:
            if message.category == category and message.msg_id == msg_id:
                return message
        return None
