# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""
src/main.py — точка входа приложения im-human.

Устанавливает переменные среды ДО импорта Qt, создаёт QApplication,
загружает и применяет тёмную тему из dark.qss, создаёт MainWindow и
запускает главный цикл событий.

Импорт MainWindow выполняется внутри main() ПОСЛЕ создания QApplication —
это предотвращает преждевременную инициализацию Qt-виджетов на уровне модуля.

Requirements: UI-11, UI-12 / D-14, D-16 (CONTEXT.md Phase 6)
"""

import os
import sys
from pathlib import Path

# Добавляем корень проекта в sys.path, чтобы `from src.*` работало
# независимо от того, как запускается скрипт (python src/main.py или python -m src.main)
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Устанавливаем переменные среды ДО любого импорта Qt
os.environ.setdefault("PYTHONIOENCODING", "utf-8")          # D-23: стабильная работа в PowerShell cp1251
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")    # D-18: избегаем deadlock sentence-transformers


def main() -> None:
    """
    Точка входа приложения.

    Порядок инициализации:
    1. QApplication (должен быть создан первым)
    2. Загрузка и применение тёмной темы dark.qss (D-14)
    3. Auto-detect OpenGL для pyqtgraph (D-02)
    4. Создание и отображение MainWindow
    5. Запуск главного цикла событий
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("im-human")
    app.setOrganizationName("im-human")
    app.setApplicationDisplayName("im-human — Симулятор биологической модели")

    # Загрузить и применить тёмную тему (D-14, UI-11)
    qss_path = Path(__file__).parent / "ui" / "styles" / "dark.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
    else:
        print(
            f"[WARNING] dark.qss not found at {qss_path} — default Qt theme will be used",
            file=sys.stderr,
        )

    # Auto-detect OpenGL для pyqtgraph (D-02: опциональная зависимость)
    try:
        import OpenGL  # noqa: F401
        import pyqtgraph as pg
        pg.setConfigOption("useOpenGL", True)
    except ImportError:
        # PyOpenGL не установлен — используем Qt-backend (приемлемо для MVP)
        pass

    # Импорт MainWindow ПОСЛЕ создания QApplication (избегаем преждевременной инициализации Qt)
    from src.ui.main_window import MainWindow  # noqa: E402

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
