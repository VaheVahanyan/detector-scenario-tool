"""Catalogue view over the message registry.

`MessageSpec` used to be the source of truth and carried a hard-coded Russian name. It is now a
thin adapter over `MessageDef` so the rest of the UI keeps working, with `name` resolved through
the translation layer on every access — that is what makes message names follow the language
switch.
"""

from __future__ import annotations

from dataclasses import dataclass

from detector_scenario_tool.i18n import tr
from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.fields import AckBehaviour, MessageDef


@dataclass(frozen=True)
class MessageSpec:
    definition: MessageDef

    @property
    def category(self) -> str:
        return self.definition.category

    @property
    def msg_id(self) -> int:
        return self.definition.msg_id

    @property
    def symbol(self) -> str:
        return self.definition.symbol

    @property
    def name_key(self) -> str:
        return self.definition.name_key

    @property
    def name(self) -> str:
        # A user-defined name is not a translation key.
        return self.definition.custom_name or tr(self.definition.name_key)

    @property
    def is_custom(self) -> bool:
        return self.definition.custom

    @property
    def payload_length(self) -> int:
        return self.definition.length

    @property
    def is_long(self) -> bool:
        return self.definition.is_long

    @property
    def ack_expected(self) -> bool:
        return self.definition.ack is not AckBehaviour.NONE

    @property
    def hex_id(self) -> str:
        return f"0x{self.msg_id:04X}"

    def label(self) -> str:
        return f"{self.hex_id} {self.name}"


class ProtocolCatalog:
    """Read-only façade over `protocol.registry`."""

    @property
    def messages(self) -> list[MessageSpec]:
        return [MessageSpec(spec) for spec in registry.all_messages()]

    def get_by_category(self, category: str) -> list[MessageSpec]:
        return [MessageSpec(spec) for spec in registry.by_category(category)]

    def get_ku_messages(self) -> list[MessageSpec]:
        return self.get_by_category("KU")

    def get_kt_messages(self) -> list[MessageSpec]:
        return self.get_by_category("KT")

    def get_ts_messages(self) -> list[MessageSpec]:
        return self.get_by_category("TS")

    def find(self, category: str, msg_id: int) -> MessageSpec | None:
        spec = registry.find(category, msg_id)
        return None if spec is None else MessageSpec(spec)

    def find_by_symbol(self, symbol: str) -> MessageSpec | None:
        spec = registry.by_symbol(symbol)
        return None if spec is None else MessageSpec(spec)
