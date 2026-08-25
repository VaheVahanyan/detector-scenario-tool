"""Resolving the few messages the application reasons about by name.

`protocol/well_known.py` exists because the specification has renumbered the catalogue twice and
each time the acknowledgement's identifier was spelled out in a handful of unrelated layers. The
last test in this file is the one that matters: it fails if a new literal creeps back in.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from detector_scenario_tool.protocol import registry, well_known

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "detector_scenario_tool"

#: Every identifier the catalogue currently holds. Comparing against these in application code is
#: what `well_known` exists to replace.
CATALOGUE_IDS = {spec.msg_id for spec in registry.all_messages()}

#: Files that legitimately name identifiers: the definitions themselves, the migration tables that
#: translate between revisions, and this test.
ALLOWED = {
    "protocol/definitions/control_commands.py",
    "protocol/definitions/telemetry_commands.py",
    "protocol/definitions/telemetry_messages.py",
    "storage/migration.py",
}


class TestResolution:
    @pytest.mark.parametrize(
        "symbol",
        [well_known.ACK, well_known.STATUS, well_known.TELEMETRY,
         well_known.TEST_RESULT, well_known.VERSION,
         well_known.SET_DEST_ID, well_known.SET_DEVICE_ID],
    )
    def test_every_symbol_resolves(self, symbol):
        spec = well_known.definition(symbol)
        assert spec is not None, symbol
        assert spec.symbol == symbol
        assert well_known.msg_id(symbol) == spec.msg_id

    def test_matching_needs_the_right_category(self):
        ack = well_known.definition(well_known.ACK)
        assert well_known.is_ack("TS", ack.msg_id)
        assert not well_known.is_ack("KU", ack.msg_id)

    def test_a_missing_identifier_is_not_a_match(self):
        assert not well_known.is_ack("TS", None)
        assert not well_known.is_status("TS", 0x0FFF)

    def test_a_v2_identifier_is_not_a_match(self):
        """The whole point: 0201h was the acknowledgement and no longer is."""
        assert not well_known.is_ack("TS", 0x0201)

    def test_the_address_commands_are_told_apart(self):
        dest = registry.by_symbol("CMD_SET_DEST_ID")
        device = registry.by_symbol("CMD_SET_DEVICE_ID")

        assert well_known.is_address_command("KU", dest.msg_id) == well_known.SET_DEST_ID
        assert well_known.is_address_command("KU", device.msg_id) == well_known.SET_DEVICE_ID
        assert well_known.is_address_command("KU", registry.by_symbol("CMD_ERASE").msg_id) is None

    def test_a_hidden_message_degrades_instead_of_raising(self, monkeypatch):
        """A scenario may hide a catalogue message. That must not crash the runner mid-run."""
        ack = registry.by_symbol(well_known.ACK)
        registry.unregister(ack.category, ack.msg_id)
        try:
            assert well_known.definition(well_known.ACK) is None
            assert well_known.msg_id(well_known.ACK) is None
            assert well_known.is_ack("TS", ack.msg_id) is False
        finally:
            registry.register(ack, replace=True)


def test_no_module_compares_a_message_id_to_a_literal():
    """The guard. A literal identifier in application code is a renumbering waiting to break.

    This is not hypothetical bookkeeping: `domain/timeline.py` still compared against `0x0201`
    after the v2.1 renumbering, because no test covered that tooltip. Nothing failed, and the
    acknowledgement tooltip silently stopped appearing.
    """
    offenders = []

    for path in sorted(SRC.rglob("*.py")):
        relative = path.relative_to(SRC).as_posix()
        if relative in ALLOWED:
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
                continue

            names = _attribute_names(node.left)
            if not any(name.endswith("msg_id") for name in names):
                continue

            for operand in node.comparators:
                if (
                    isinstance(operand, ast.Constant)
                    and isinstance(operand.value, int)
                    and operand.value in CATALOGUE_IDS
                ):
                    offenders.append(f"{relative}:{node.lineno} compares to 0x{operand.value:04X}")

    assert not offenders, (
        "use protocol/well_known.py instead of a literal identifier:\n  "
        + "\n  ".join(offenders)
    )


def _attribute_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Attribute):
        return [node.attr]
    if isinstance(node, ast.Name):
        return [node.id]
    return []
