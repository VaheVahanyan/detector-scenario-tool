from __future__ import annotations

from detector_scenario_tool.ui.editors.data_output_payload_editor import DataOutputPayloadEditor
from detector_scenario_tool.ui.editors.erase_flash_payload_editor import EraseFlashPayloadEditor
from detector_scenario_tool.ui.editors.fixed_aa_payload_editor import FixedAaPayloadEditor
from detector_scenario_tool.ui.editors.geomagnetic_field_payload_editor import GeomagneticFieldPayloadEditor
from detector_scenario_tool.ui.editors.observation_control_payload_editor import ObservationControlPayloadEditor
from detector_scenario_tool.ui.editors.observation_enable_payload_editor import ObservationEnablePayloadEditor
from detector_scenario_tool.ui.editors.orbit_params_payload_editor import OrbitParamsPayloadEditor
from detector_scenario_tool.ui.editors.orientation_params_payload_editor import OrientationParamsPayloadEditor
from detector_scenario_tool.ui.editors.payload_editor_base import PayloadEditorBase
from detector_scenario_tool.ui.editors.set_time_payload_editor import SetTimePayloadEditor
from detector_scenario_tool.ui.editors.settings_payload_editor import SettingsPayloadEditor
from detector_scenario_tool.ui.editors.standby_mode_payload_editor import StandbyModePayloadEditor
from detector_scenario_tool.ui.editors.test_flash_payload_editor import TestFlashPayloadEditor
from detector_scenario_tool.ui.editors.test_results_request_payload_editor import TestResultsRequestPayloadEditor
from detector_scenario_tool.ui.editors.time_sync_payload_editor import TimeSyncPayloadEditor


def build_payload_editor_registry() -> dict[tuple[str, int], PayloadEditorBase]:
    return {
        ("KU", 0x0000): FixedAaPayloadEditor("telemetry_request"),
        ("KU", 0x0001): FixedAaPayloadEditor("status_request"),
        ("KU", 0x0002): SetTimePayloadEditor(),
        ("KU", 0x0003): ObservationEnablePayloadEditor(),
        ("KU", 0x0004): ObservationControlPayloadEditor(),
        ("KU", 0x0005): StandbyModePayloadEditor(),
        ("KU", 0x0006): DataOutputPayloadEditor(),
        ("KU", 0x0007): SettingsPayloadEditor(),
        ("KU", 0x0008): EraseFlashPayloadEditor(),
        ("KU", 0x0009): TestFlashPayloadEditor(),
        ("KU", 0x000A): TestResultsRequestPayloadEditor(),
        ("KU", 0x000B): FixedAaPayloadEditor("power_off"),
        ("KU", 0x000C): FixedAaPayloadEditor("reset_emergency_status"),
        ("KT", 0x0100): TimeSyncPayloadEditor(),
        ("KT", 0x0101): OrbitParamsPayloadEditor(),
        ("KT", 0x0102): OrientationParamsPayloadEditor(),
        ("KT", 0x0103): GeomagneticFieldPayloadEditor(),
    }