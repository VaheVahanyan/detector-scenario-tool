from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from detector_scenario_tool.app import settings as app_settings
from detector_scenario_tool.i18n import set_language, tr
from detector_scenario_tool.ui.main_window import MainWindow


def main() -> int:
    set_language(app_settings.load_language())

    app = QApplication(sys.argv)
    app.setApplicationName(tr("app.title"))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
