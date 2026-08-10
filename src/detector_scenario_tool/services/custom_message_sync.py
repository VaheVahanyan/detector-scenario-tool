"""Keeps the protocol registry in step with what a document says about messages.

A document may do three things to the catalogue: add messages of its own, replace built-in ones,
and hide built-in ones. All three are reversible, because the built-in definitions live in
`protocol/definitions` as code and are never written over — this class only remembers what it
changed so it can put the originals back.

The registry is process-wide, so switching documents has to undo the previous document's changes
as well as apply the new one's.
"""

from __future__ import annotations

from detector_scenario_tool.domain.custom_messages import CustomMessageSpec, to_message_def
from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.fields import MessageDef


class CustomMessageSync:
    def __init__(self) -> None:
        #: Keys this added that the catalogue did not have.
        self._added: set[tuple[str, int]] = set()
        #: Built-in definitions displaced by an override or a suppression, kept so they can be
        #: restored exactly.
        self._displaced: dict[tuple[str, int], MessageDef] = {}

    @property
    def registered_keys(self) -> set[tuple[str, int]]:
        return set(self._added) | set(self._displaced)

    def apply(
            self,
            specs: list[CustomMessageSpec],
            suppressed: list[tuple[str, int]] | None = None,
    ) -> list[CustomMessageSpec]:
        """Apply a document's message changes. Returns the definitions that were refused."""
        self.clear()

        rejected: list[CustomMessageSpec] = []

        for spec in specs:
            key = (spec.category, spec.msg_id)
            existing = registry.find(*key)

            if existing is not None and not existing.custom:
                if not spec.overrides_builtin:
                    # An accidental collision, as opposed to a deliberate replacement.
                    rejected.append(spec)
                    continue
                self._displaced.setdefault(key, existing)
            elif existing is None:
                self._added.add(key)

            registry.register(to_message_def(spec), replace=True)

        for key in suppressed or []:
            key = (key[0], key[1])
            existing = registry.find(*key)
            if existing is None or existing.custom:
                continue
            self._displaced.setdefault(key, existing)
            registry.unregister(*key)

        _refresh_dependents()
        return rejected

    def clear(self) -> None:
        """Put the catalogue back exactly as the specification defines it."""
        for category, msg_id in self._added:
            registry.unregister(category, msg_id)
        self._added.clear()

        for original in self._displaced.values():
            registry.register(original, replace=True)
        self._displaced.clear()

        _refresh_dependents()


def builtin_definition(category: str, msg_id: int) -> MessageDef | None:
    """The definition as the specification has it, whatever the document has done to it."""
    from detector_scenario_tool.protocol.definitions import ALL_MESSAGE_DEFS

    for spec in ALL_MESSAGE_DEFS:
        if spec.category == category and spec.msg_id == msg_id:
            return spec
    return None


def is_builtin(category: str, msg_id: int) -> bool:
    return builtin_definition(category, msg_id) is not None


def _refresh_dependents() -> None:
    """Anything caching a view of the registry has to be told."""
    from detector_scenario_tool.validation import mode_analyzer

    mode_analyzer.refresh()
