# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""src/ui — UI-пакет приложения im-human.

Реэкспортирует все публичные классы интерфейса для удобного импорта:
    from src.ui import MainWindow, SimulationWorker, ...

ВАЖНО: импорт этого пакета тянет PySide6 и pyqtgraph. Классы определяются
при импорте, но виджеты НЕ создаются — безопасно в headless-окружении без
QApplication (определение класса != создание QWidget).
"""
from __future__ import annotations

from src.ui.main_window import MainWindow
from src.ui.worker import SimulationWorker
from src.ui.human_panel import HumanPanel
from src.ui.time_controls import TimeControls
from src.ui.telemetry_dashboard import TelemetryDashboard
from src.ui.substance_manager import SubstanceManager
from src.ui.event_log import EventLog

__all__ = [
    "MainWindow",
    "SimulationWorker",
    "HumanPanel",
    "TimeControls",
    "TelemetryDashboard",
    "SubstanceManager",
    "EventLog",
]
