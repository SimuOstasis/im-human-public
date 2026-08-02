#!/usr/bin/env python
# Copyright © 2026 Vladimir Bazhin <info@simuostasis.com>
#
# Licensed under the Apache License, Version 2.0.
# http://www.apache.org/licenses/LICENSE-2.0

"""Разовый calibration/benchmark-скрипт: замер времени кадра UI дашборда (PERF-02/PERF-03).

НЕ импортируется НИ ОДНИМ модулем под src/ — это benchmark-time-only утилита, её
единственный НАМЕРЕННЫЙ побочный эффект — печать чисел и, опционально, снимков окна
дашборда. Приложение никогда не запускает и не знает об этом скрипте.

ВАЖНО (G-17-1, UAT фазы 17): скрипт создаёт настоящий `MainWindow`, который читает и
пишет ОБЩИЕ QSettings("im-human", "simulator") реального приложения (geometry/dockstate,
main_window.py D-06). Без изоляции последний прогон бенчмарка перезаписывал бы это
состояние (доки «Управление временем»/«Журнал событий» скрыты под замер) и оно
«утекало» бы в следующий обычный запуск приложения — кнопки управления/скорости
казались бы пропавшими. `run_single()` оборачивает жизненный цикл окна в
`_isolate_app_settings()`, которая снимает и точно восстанавливает эти два ключа —
реальные настройки приложения гарантированно не меняются этим скриптом.

────────────────────────────────────────────────────────────────────────────
ТРЕБОВАНИЕ К ОКРУЖЕНИЮ (обязательно, не опционально)
────────────────────────────────────────────────────────────────────────────
Скрипт ОБЯЗАН запускаться на реальном сеансе рабочего стола Windows, БЕЗ
переопределения `QT_QPA_PLATFORM` (обычный режим этого репозитория для тестов
под pytest, см. `src/tests/test_benchmark.py`). Под `offscreen`-платформой
контекст OpenGL пустой (`context=None`), PyQtGraph перехватывает и логирует
исключение отрисовки в `paintEvent` вместо того, чтобы упасть
(`pyqtgraph/debug.py`'s `printExc`), и конфигурация `opengl` выглядит
подозрительно быстрой без всякой реальной отрисовки — цифры получаются
бессмысленными (`17-RESEARCH.md` Pitfall 1, воспроизведено эмпирически). Первое,
что делает скрипт, ДО импорта чего-либо из PySide6, — проверка этой переменной
окружения (см. `_platform_guard()` ниже); при непустом значении скрипт
завершается ненулевым кодом с объяснением, не пытаясь окружение исправить.

────────────────────────────────────────────────────────────────────────────
МЕТОДОЛОГИЯ (D-05/D-06/D-07, 17-CONTEXT.md)
────────────────────────────────────────────────────────────────────────────
D-05: метрика сравнения "до/после" — время выполнения ОДНОГО вызова
      `TelemetryDashboard.update()`, в миллисекундах, через `time.perf_counter()`.
      Не FPS-счётчик и не CPU% (отклонены D-05 как менее прямые). Важно
      (`17-RESEARCH.md` Pitfall 3): выше `update()` уже стоят два независимых
      троттлинга (эмиссия worker'а ≤20/с, рендер-гейт MainWindow 200мс/5fps) —
      замер обязательно формулируется как "стоимость на вызов update()", а не
      "стоимость на тик симуляции".

D-06: два сценария, оба на реальной симуляции:
      1. "wide" — худший случай, все 24 плота видны одновременно, скорость x1000.
      2. "typical" — типичный случай, видно 6-12 плотов (обычный размер окна),
         скорости x100 и x1000.

D-07: три конфигурации:
      - "baseline" — software-рендер БЕЗ viewport-фильтра (поведение ДО PERF-01,
        воспроизводится подменой метода дашборда в этом скрипте, репозиторный код
        НЕ откатывается).
      - "visible" — текущее поведение репозитория (viewport-culling из PERF-01,
        `TelemetryDashboard._visible_row_range()`).
      - "opengl" — visible + `pg.setConfigOption("useOpenGL", True)`.

Запуск (одиночный прогон, читаемый вывод):
    venv\\Scripts\\python.exe scripts/benchmark_ui_frame_time.py \\
        --config visible --scenario typical --speed 100 --duration 15

Запуск (одиночный прогон, JSON-строка для сборки в матрицу):
    venv\\Scripts\\python.exe scripts/benchmark_ui_frame_time.py \\
        --config opengl --scenario wide --speed 1000 --duration 15 --json

Запуск (полная матрица D-06 × D-07, 9 прогонов, markdown-отчёт):
    venv\\Scripts\\python.exe scripts/benchmark_ui_frame_time.py --all --duration 15
    (путь по умолчанию для --out:
     .planning/phases/17-ui-performance-stabilization/17-benchmark-raw.md)

Requirements: PERF-02, PERF-03 (17-CONTEXT.md, 17-03-PLAN.md)
"""
from __future__ import annotations

import argparse
import json as jsonlib
import os
import statistics
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve()
_PROJECT_ROOT = _SCRIPT_PATH.parent.parent

# Три конфигурации D-07, в порядке отчёта.
_CONFIGS = ("baseline", "visible", "opengl")

# Матрица D-06 x D-07: (сценарий, множитель скорости, конфигурации).
_MATRIX_RUNS: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    ("wide", 1000, _CONFIGS),
    ("typical", 100, _CONFIGS),
    ("typical", 1000, _CONFIGS),
)

# Эмпирически откалиброванный на этой машине размер окна для сценария "typical"
# (D-06: 6-12 видимых плотов). При window=(1400, 480) с скрытыми доками
# «Управление временем»/«Журнал событий» реально видны ровно 3 строки сетки
# (12 плотов) — стабильно в диапазоне окон высотой 433-540px (запас с обеих
# сторон от границ перехода 12<->16 плотов), проверено живым замером геометрии
# на этой машине (17-03-SUMMARY.md). Портируемость на другую машину/DPI не
# гарантируется — на этот случай скрипт САМ проверяет достигнутый сценарий
# (см. `_assert_scenario`) и завершается ошибкой, а не тихо пишет не тот
# сценарий.
_TYPICAL_WINDOW_SIZE = (1400, 480)

_GL_VENDOR = 0x1F00
_GL_RENDERER = 0x1F01


def _platform_guard() -> None:
    """Первое, что делает скрипт, ДО импорта чего-либо из PySide6 (T-17-07).

    Отказывается работать под `QT_QPA_PLATFORM=offscreen` (или любым другим
    непустым значением) — см. докстринг модуля, раздел «ТРЕБОВАНИЕ К
    ОКРУЖЕНИЮ». Не пытается «исправить» окружение самостоятельно.
    """
    qpa = os.environ.get("QT_QPA_PLATFORM", "").strip()
    if qpa:
        print(
            f"ОШИБКА: переменная окружения QT_QPA_PLATFORM={qpa!r} выставлена.\n"
            "Замер времени кадра UI ОБЯЗАН идти на реальном экране: под offscreen "
            "контекст OpenGL пустой (context=None), PyQtGraph перехватывает и "
            "логирует исключение отрисовки в paintEvent вместо того, чтобы упасть "
            "(pyqtgraph/debug.py printExc), и конфигурация useOpenGL=True "
            "выглядит подозрительно быстрой без всякой реальной отрисовки — "
            "цифры получатся бессмысленными (17-RESEARCH.md Pitfall 1).\n"
            "Снимите переменную окружения (unset QT_QPA_PLATFORM в bash / "
            "Remove-Item Env:QT_QPA_PLATFORM в PowerShell) и запустите на "
            "реальном сеансе рабочего стола Windows.",
            file=sys.stderr,
        )
        sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────
# Одиночный прогон
# ─────────────────────────────────────────────────────────────────────────


def _percentile(values: list[float], pct: float) -> float:
    """95-й процентиль без numpy (единственная новая зависимость — стандартная
    библиотека `statistics`, уже используемая ниже для mean/median)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - k) + ordered[hi] * (k - lo)


def _prepare_window_for_scenario(window, scenario: str) -> None:
    """Подготовить геометрию окна под сценарий D-06.

    Доки «Управление временем» и «Журнал событий» скрываются в ОБОИХ
    сценариях, чтобы отдать телеметрии максимум вертикального места и убрать
    лишнюю переменную из геометрии — скрытие QDockWidget не отключает
    сигналы/слоты нижележащего виджета (TimeControls остаётся живым, его
    сигналы по-прежнему доходят до Worker'а), так что запуск симуляции через
    `time_controls.start_requested.emit(None)` работает как обычно, даже пока
    панель управления временем физически не показана.
    """
    from PySide6.QtWidgets import QApplication

    qapp = QApplication.instance()

    window._time_dock.hide()
    window._event_log_dock.hide()

    # Всегда СНАЧАЛА showNormal(): MainWindow.closeEvent безусловно
    # сохраняет geometry/dockstate в QSettings ("im-human"/"simulator") при
    # закрытии окна (T-06-13, main_window.py) — предыдущий прогон ЭТОГО
    # скрипта мог закрыться в состоянии showMaximized() и сохранить его.
    # MainWindow.__init__ восстанавливает это состояние через
    # restoreGeometry() ДО того, как этот метод успевает вызваться — а Qt
    # тихо игнорирует resize() на уже смаксимизированном окне (действует
    # только на "нормальную" геометрию, которая применится лишь после выхода
    # из maximized). Без явного showNormal() здесь сценарий "typical" мог бы
    # унаследовать maximized-геометрию от предыдущего "wide"-прогона и молча
    # показать все 24 плота вместо 6-12 — обнаружено живым прогоном на этой
    # машине (17-03-SUMMARY.md), не гипотетический риск.
    window.showNormal()
    qapp.processEvents()

    if scenario == "wide":
        window.showMaximized()
    else:  # "typical"
        w, h = _TYPICAL_WINDOW_SIZE
        window.resize(w, h)
        window.show()

    window._telemetry_dock.raise_()
    for _ in range(5):
        qapp.processEvents()


def _measure_actual_visible_rows(dashboard) -> tuple[int, int, int]:
    """Независимое вычисление РЕАЛЬНО видимых строк сетки (без буфера ±2).

    Дублирует геометрический расчёт `TelemetryDashboard._visible_row_range()`
    сознательно, а не вызывает его напрямую: в конфигурации `baseline` этот
    метод экземпляра подменён (см. `_patch_baseline_full_range`) и вернул бы
    полный диапазон, что сделало бы проверку достигнутого сценария
    бессмысленной для этой конфигурации. Здесь — БЕЗ буфера ±2 строки (в
    отличие от дашборда) и БЕЗ fallback на полный диапазон при нулевой
    геометрии, потому что это утверждение факта, а не рабочий гейт рендера.

    Returns:
        (first_row, last_row, num_visible_plots) — индексы первой/последней
        реально видимой строки (либо (-1, -1) если ничего не видно) и число
        реально видимых плотов (по `dashboard._plot_row`).
    """
    scroll = dashboard._scroll
    grid = dashboard._grid
    scroll_y = scroll.verticalScrollBar().value()
    viewport_h = scroll.viewport().height()
    visible_top, visible_bottom = scroll_y, scroll_y + viewport_h

    visible_rows: set[int] = set()
    for row in range(grid.rowCount()):
        item = grid.itemAtPosition(row, 0)
        if item is None:
            continue
        w = item.widget()
        row_top, row_bottom = w.y(), w.y() + w.height()
        if row_bottom > visible_top and row_top < visible_bottom:
            visible_rows.add(row)

    num_visible_plots = sum(1 for r in dashboard._plot_row.values() if r in visible_rows)
    if not visible_rows:
        return (-1, -1, 0)
    return (min(visible_rows), max(visible_rows), num_visible_plots)


def _assert_scenario(
    scenario: str, dashboard, first_row: int, last_row: int, visible_plots: int
) -> None:
    """Утвердить достигнутый сценарий D-06, а не предположить его (T-17-09).

    Ненулевой код выхода с диагностикой при несоответствии — «почти подходит»
    не принимается.
    """
    last_grid_row = dashboard._grid.rowCount() - 1
    if scenario == "wide":
        if first_row != 0 or last_row != last_grid_row:
            print(
                f"ОШИБКА: широкий сценарий (D-06) требует, чтобы были видны ВСЕ "
                f"строки сетки (0..{last_grid_row}), а реально видны строки "
                f"{first_row}..{last_row} ({visible_plots} плотов). Измените "
                "геометрию окна (maximise/скрытые доки) в _prepare_window_for_scenario.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:  # "typical"
        if not (6 <= visible_plots <= 12):
            print(
                f"ОШИБКА: типичный сценарий (D-06) требует 6-12 видимых плотов, "
                f"реально видно {visible_plots} (строки {first_row}..{last_row}). "
                f"Скорректируйте _TYPICAL_WINDOW_SIZE.",
                file=sys.stderr,
            )
            sys.exit(1)


def _patch_baseline_full_range(dashboard) -> None:
    """Воспроизвести поведение ДО PERF-01 (D-07 baseline) без отката кода.

    Подменяет `_visible_row_range()` У ЭТОГО ЭКЗЕМПЛЯРА (не у класса) на
    функцию, возвращающую полный диапазон строк — от нуля до последнего
    индекса строки сетки. Это в точности прежнее поведение: гейт видимости
    в `update()` всегда пропускает, `setData()` вызывается для всех 24
    кодов на каждый `update()`.
    """
    last_row = dashboard._grid.rowCount() - 1
    dashboard._visible_row_range = lambda: (0, last_row)


def _instrument_dashboard(dashboard) -> dict:
    """Обернуть `update()` и `setData()` инструментацией (D-05).

    Возвращает изменяемый словарь-накопитель, который наполняется по мере
    прогона реального цикла событий Qt (`app.exec()` в `_run_event_loop`).
    """
    stats: dict = {"update_ms": [], "setdata_calls": [], "error": None}

    orig_update = dashboard.update
    setdata_counter = {"n": 0}

    for code, curve in dashboard._curves.items():
        orig_set_data = curve.setData

        def _wrap_set_data(*args, _orig=orig_set_data, **kwargs):
            setdata_counter["n"] += 1
            return _orig(*args, **kwargs)

        curve.setData = _wrap_set_data

    def _wrapped_update(biomarker_values):
        setdata_counter["n"] = 0
        try:
            t0 = time.perf_counter()
            orig_update(biomarker_values)
            t1 = time.perf_counter()
        except Exception as exc:  # noqa: BLE001 - benchmark harness, see docstring
            # Исключение внутри измерительного окна -> нефальшивый провал
            # прогона (не печатать частичные числа как валидный результат) —
            # запомнить причину и прервать цикл событий немедленно.
            stats["error"] = f"{type(exc).__name__}: {exc}"
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.quit()
            return
        stats["update_ms"].append((t1 - t0) * 1000.0)
        stats["setdata_calls"].append(setdata_counter["n"])

    dashboard.update = _wrapped_update
    return stats


def _run_event_loop(window, speed: int, duration: float) -> None:
    """Запустить симуляцию через реальные сигналы и держать реальный цикл
    событий Qt заданное время (не заменять его ручной петлёй processEvents —
    иначе отрисовка не будет соответствовать реальному приложению)."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    window.time_controls.speed_changed.emit(speed)
    window.time_controls.start_requested.emit(None)
    QTimer.singleShot(max(1, int(duration * 1000)), app.quit)
    app.exec()


def _get_gl_renderer_string(dashboard) -> str:
    """Строка вендора/рендерера GPU, если доступна через Qt без сторонних
    зависимостей (17-RESEARCH.md Open Question 2). Best-effort: пустая
    строка, если контекста GL нет (software-конфигурации) или его не удалось
    прочитать — это диагностическая добавка к отчёту, а не критичный путь."""
    try:
        first_plot = next(iter(dashboard._plots.values()))
        viewport = first_plot.viewport()
        context = getattr(viewport, "context", None)
        if context is None:
            return ""
        ctx = viewport.context()
        if ctx is None:
            return ""
        fn = ctx.functions()
        vendor = fn.glGetString(_GL_VENDOR)
        renderer = fn.glGetString(_GL_RENDERER)
        if isinstance(vendor, bytes):
            vendor = vendor.decode(errors="replace")
        if isinstance(renderer, bytes):
            renderer = renderer.decode(errors="replace")
        if renderer:
            return f"{vendor} / {renderer}"
    except Exception:  # noqa: BLE001 - best-effort diagnostic, see docstring
        pass
    return ""


def _take_screenshot(window, path: Path) -> None:
    """Снять снимок ИМЕННО с экрана (screen.grabWindow + winId), не через
    отрисовку виджета QPainter'ом — последнее не покажет разницы GL-
    конфигурации (17-UI-SPEC.md «OpenGL toggle — visual parity contract»).

    Перед снимком окно однократно сворачивается и восстанавливается
    (`_nudge_compositor_repaint`). Без этого `grabWindow()` на этой машине
    (виртуальный дисплей VMware + удалённый сеанс) стабильно возвращает
    полностью чёрный кадр после того, как через окно прошёл вложенный
    `app.exec()` (ровно то, что делает `_run_event_loop` перед каждым
    снимком) — воспроизведено даже для тривиального `QWidget` без единого
    вызова PyQtGraph/OpenGL, то есть это не баг GL-рендера, а протухание
    композитного буфера DWM после вложенного цикла событий. Тот же символ на
    экране, тот же `winId()` — просто устаревшая поверхность. Цикл
    свернуть/восстановить принудительно пересобирает поверхность у DWM.
    """
    from PySide6.QtWidgets import QApplication

    _nudge_compositor_repaint(window)

    screen = QApplication.primaryScreen()
    pixmap = screen.grabWindow(window.winId())
    path.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(str(path))


def _nudge_compositor_repaint(window) -> None:
    """Свернуть и восстановить окно, чтобы принудительно заставить DWM
    пересобрать композитную поверхность перед `grabWindow()` (см.
    docstring `_take_screenshot`). Живо проверено на этой машине: без этого
    шага снимок для baseline/visible/opengl конфигураций в сценарии `wide`
    выходил полностью чёрным (RGB 0,0,0 на каждый сэмплированный пиксель) —
    не GL-специфично, воспроизведено даже на тривиальном `QWidget`."""
    from PySide6.QtWidgets import QApplication
    import time

    app = QApplication.instance()
    was_maximized = window.isMaximized()
    window.showMinimized()
    app.processEvents()
    time.sleep(0.3)
    if was_maximized:
        window.showMaximized()
    else:
        window.showNormal()
    app.processEvents()
    time.sleep(0.3)
    app.processEvents()


def _compute_stats(
    config: str,
    scenario: str,
    speed: int,
    stats: dict,
    first_row: int,
    last_row: int,
    visible_plots: int,
    dashboard,
    pg_module,
) -> dict:
    import PySide6

    times = stats["update_ms"]
    setdata_calls = stats["setdata_calls"]
    n = len(times)

    # WR-08 (17-REVIEW.md): _get_gl_renderer_string guards the equivalent
    # next(iter(...)) with a broad except (best-effort diagnostic), but this
    # call site had none — an empty dashboard._plots (e.g. corrupted/missing
    # biomarkers.json, which TelemetryDashboard itself handles gracefully)
    # would crash run_single() with a raw StopIteration instead of the clean,
    # diagnostic-rich failure path (_assert_scenario, _platform_guard, etc.)
    # the rest of this script is designed to produce.
    if not dashboard._plots:
        print("ОШИБКА: TelemetryDashboard не создал ни одного плота (biomarkers.json?).", file=sys.stderr)
        sys.exit(1)

    first_plot = next(iter(dashboard._plots.values()))
    viewport_class = type(first_plot.viewport()).__name__

    return {
        "config": config,
        "scenario": scenario,
        "speed": speed,
        "samples": n,
        "mean_ms": round(statistics.mean(times), 3) if times else 0.0,
        "median_ms": round(statistics.median(times), 3) if times else 0.0,
        "p95_ms": round(_percentile(times, 95), 3),
        "max_ms": round(max(times), 3) if times else 0.0,
        "avg_setdata_per_update": round(statistics.mean(setdata_calls), 2) if setdata_calls else 0.0,
        "visible_rows": [first_row, last_row],
        "visible_plots": visible_plots,
        "viewport_class": viewport_class,
        "pyqtgraph_version": pg_module.__version__,
        "pyside6_version": PySide6.__version__,
        "gl_renderer": _get_gl_renderer_string(dashboard),
    }


def _shutdown_window(window) -> None:
    """Остановить рабочий поток симуляции и закрыть окно так же, как это
    делают существующие тесты UI (src/tests/test_benchmark.py
    test_worker_throughput_benchmark) — shutdown() (не on_stop()!) реально
    завершает run()'s while-цикл перед quit()/wait(), иначе процесс может
    остаться висеть на QThread.wait()."""
    from PySide6.QtWidgets import QApplication

    # WR-06 (17-REVIEW.md): a single bare `except Exception: pass` around all
    # three steps meant a failure in worker.shutdown() skipped thread.quit()/
    # wait() entirely, risking a live QThread surviving into window.close()
    # and — since run_matrix() spawns each matrix cell as its own subprocess —
    # a hang blocking the whole --all run instead of failing fast/diagnosably.
    try:
        window._worker.shutdown()
    except Exception as exc:  # noqa: BLE001 - teardown must not mask the real result/error
        print(f"[warn] worker.shutdown() failed during teardown: {exc}", file=sys.stderr)
    try:
        window._thread.quit()
        if not window._thread.wait(10000):
            print("[warn] worker thread did not stop within 10s", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - teardown must not mask the real result/error
        print(f"[warn] thread teardown failed: {exc}", file=sys.stderr)
    window.close()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


@contextmanager
def _isolate_app_settings():
    """Снять и восстановить реальные QSettings("im-human", "simulator") приложения.

    Баг (обнаружен в UAT фазы 17, G-17-1): `MainWindow` использует ЕДИНЫЙ,
    жёстко заданный ключ реестра `QSettings("im-human", "simulator")`
    (main_window.py, D-06) — тот же самый, что использует настоящее
    production-приложение. `_prepare_window_for_scenario()` намеренно скрывает
    доки «Управление временем»/«Журнал событий» (см. её docstring), а
    `_shutdown_window()` вызывает `window.close()`, чей `closeEvent`
    БЕЗУСЛОВНО сохраняет текущую (урезанную под замер) geometry/dockstate в
    этот общий ключ. Следующий обычный запуск приложения читает то же самое
    состояние и остаётся без видимых кнопок управления/переключения скоростей
    — не баг UI-кода, а побочный эффект бенчмарка на чужие, не-benchmark'овые
    настройки. Этот менеджер контекста снимает снимок `mainwindow/geometry` и
    `mainwindow/dockstate` ДО создания окна и принудительно восстанавливает
    (или удаляет, если их не было) их точные исходные значения ПОСЛЕ, в
    finally — независимо от исхода прогона.
    """
    from PySide6.QtCore import QSettings

    settings = QSettings("im-human", "simulator")
    had_geometry = settings.contains("mainwindow/geometry")
    had_dockstate = settings.contains("mainwindow/dockstate")
    saved_geometry = settings.value("mainwindow/geometry") if had_geometry else None
    saved_dockstate = settings.value("mainwindow/dockstate") if had_dockstate else None
    try:
        yield
    finally:
        settings = QSettings("im-human", "simulator")
        if had_geometry:
            settings.setValue("mainwindow/geometry", saved_geometry)
        else:
            settings.remove("mainwindow/geometry")
        if had_dockstate:
            settings.setValue("mainwindow/dockstate", saved_dockstate)
        else:
            settings.remove("mainwindow/dockstate")
        settings.sync()


def run_single(
    config: str, scenario: str, speed: int, duration: float, shot: Path | None
) -> dict:
    """Выполнить один прогон: одна конфигурация (D-07) × один сценарий (D-06).

    При исключении внутри измерительного окна — пробрасывает его дальше
    (обрабатывается в `main()`, завершение ненулевым кодом, без печати
    частичных чисел как валидного результата).
    """
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    qss_path = _PROJECT_ROOT / "src" / "ui" / "styles" / "dark.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    import pyqtgraph as pg

    # ТОЛЬКО для opengl, ДО импорта MainWindow — после создания виджетов флаг
    # уже не подействует (17-RESEARCH.md, D-07).
    if config == "opengl":
        pg.setConfigOption("useOpenGL", True)

    from src.ui.main_window import MainWindow  # noqa: E402 - см. main.py, тот же порядок

    with _isolate_app_settings():
        window = MainWindow()
        try:
            _prepare_window_for_scenario(window, scenario)

            dashboard = window.telemetry
            if config == "baseline":
                _patch_baseline_full_range(dashboard)

            first_row, last_row, visible_plots = _measure_actual_visible_rows(dashboard)
            _assert_scenario(scenario, dashboard, first_row, last_row, visible_plots)

            stats = _instrument_dashboard(dashboard)
            _run_event_loop(window, speed, duration)

            if stats["error"] is not None:
                raise RuntimeError(f"Исключение внутри измерительного окна: {stats['error']}")

            result = _compute_stats(
                config, scenario, speed, stats, first_row, last_row, visible_plots, dashboard, pg
            )

            if shot is not None:
                _take_screenshot(window, shot)
                result["screenshot"] = str(shot)

            return result
        finally:
            _shutdown_window(window)


def _print_human(result: dict) -> None:
    print(f"config={result['config']} scenario={result['scenario']} speed=x{result['speed']}")
    print(f"  выборок (update() вызовов): {result['samples']}")
    print(
        f"  время на вызов update(): "
        f"mean={result['mean_ms']}мс median={result['median_ms']}мс "
        f"p95={result['p95_ms']}мс max={result['max_ms']}мс"
    )
    print(f"  среднее число setData() на update(): {result['avg_setdata_per_update']}")
    print(
        f"  реально видимые строки: {result['visible_rows']} "
        f"({result['visible_plots']} плотов)"
    )
    print(f"  viewport-класс: {result['viewport_class']}")
    print(f"  pyqtgraph={result['pyqtgraph_version']} PySide6={result['pyside6_version']}")
    if result.get("gl_renderer"):
        print(f"  GPU renderer: {result['gl_renderer']}")
    if result.get("screenshot"):
        print(f"  снимок: {result['screenshot']}")


# ─────────────────────────────────────────────────────────────────────────
# Режим полной матрицы (--all)
# ─────────────────────────────────────────────────────────────────────────


def _relative_shot_path(shot_path: Path) -> str:
    """Путь снимка относительно корня репозитория (T-17-10) — либо только
    имя файла, если снимок оказался вне репозитория (например, смоук-прогон
    в системный временный каталог), чтобы никогда не напечатать абсолютный
    локальный путь."""
    try:
        return str(shot_path.resolve().relative_to(_PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return shot_path.name


def _render_markdown_report(rows: list[dict], duration: float, shots: dict[str, Path]) -> str:
    date_str = datetime.now().strftime("%Y-%m-%d")
    pg_version = rows[0]["pyqtgraph_version"] if rows else "?"
    pyside_version = rows[0]["pyside6_version"] if rows else "?"

    lines: list[str] = []
    lines.append("# UI Frame Time Benchmark — raw results")
    lines.append("")
    lines.append(
        "Разовый воспроизводимый замер времени кадра UI (PERF-02/PERF-03), сгенерирован "
        "`scripts/benchmark_ui_frame_time.py --all`. Метрика — время выполнения ОДНОГО "
        "вызова `TelemetryDashboard.update()` в мс (D-05), не время на тик симуляции."
    )
    lines.append("")
    lines.append("## Окружение")
    lines.append(f"- pyqtgraph: {pg_version}")
    lines.append(f"- PySide6: {pyside_version}")
    lines.append(f"- Дата прогона: {date_str}")
    lines.append(f"- Измерительное окно на прогон (--duration): {duration} с")
    for config in _CONFIGS:
        matching = [r for r in rows if r["config"] == config]
        if not matching:
            continue
        r = matching[0]
        renderer_suffix = f", GPU: {r['gl_renderer']}" if r.get("gl_renderer") else ""
        lines.append(f"- Viewport-класс ({config}): {r['viewport_class']}{renderer_suffix}")
    for label, shot_path in shots.items():
        lines.append(f"- Снимок ({label}): {_relative_shot_path(shot_path)}")
    lines.append("")
    lines.append("## Результаты")
    lines.append("")
    lines.append(
        "| Сценарий | Скорость | Конфигурация | Выборок | Среднее на update(), мс | "
        "Медиана, мс | P95, мс | Максимум, мс | Ср. setData()/update() | Видимых плотов |"
    )
    lines.append(
        "|----------|----------|--------------|---------|--------------------------|"
        "-------------|---------|--------------|--------------------------|-----------------|"
    )
    for r in rows:
        lines.append(
            f"| {r['scenario']} | x{r['speed']} | {r['config']} | {r['samples']} | "
            f"{r['mean_ms']:.3f} | {r['median_ms']:.3f} | {r['p95_ms']:.3f} | "
            f"{r['max_ms']:.3f} | {r['avg_setdata_per_update']:.2f} | {r['visible_plots']} |"
        )
    lines.append("")
    return "\n".join(lines)


def run_matrix(args: argparse.Namespace) -> int:
    """Прогнать все 9 комбинаций D-06 × D-07 отдельными дочерними процессами
    (T-17-08: обязательно отдельными — флаг GPU-рендера в pyqtgraph действует
    только до создания виджетов, переключать конфигурации внутри одного
    процесса нельзя) и собрать markdown-отчёт. Частичная матрица НЕ выдаётся
    за полную: любой проваленный дочерний прогон -> ненулевой код выхода,
    без подстановки пропусков."""
    _platform_guard()

    rows: list[dict] = []
    shots: dict[str, Path] = {}
    failures: list[str] = []

    for scenario, speed, configs in _MATRIX_RUNS:
        for config in configs:
            label = f"{config}/{scenario}/x{speed}"
            cmd = [
                sys.executable,
                str(_SCRIPT_PATH),
                "--config", config,
                "--scenario", scenario,
                "--speed", str(speed),
                "--duration", str(args.duration),
                "--json",
            ]
            shot_path: Path | None = None
            if scenario == "wide":
                shot_path = args.out.parent / f"shot_{scenario}_x{speed}_{config}.png"
                cmd += ["--shot", str(shot_path)]

            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                print(f"ОШИБКА: прогон {label} завершился кодом {proc.returncode}:", file=sys.stderr)
                print(proc.stderr, file=sys.stderr)
                failures.append(label)
                continue

            try:
                # --json печатает ровно одну строку JSON — последняя непустая
                # строка stdout, устойчиво к любым сторонним print() до неё.
                json_line = [ln for ln in proc.stdout.splitlines() if ln.strip()][-1]
                row = jsonlib.loads(json_line)
            except (jsonlib.JSONDecodeError, IndexError) as exc:
                print(f"ОШИБКА: не удалось разобрать JSON-вывод прогона {label}: {exc}", file=sys.stderr)
                print(proc.stdout, file=sys.stderr)
                failures.append(label)
                continue

            rows.append(row)
            if shot_path is not None:
                shots[label] = shot_path

    if failures:
        print(
            f"ОШИБКА: {len(failures)} из {sum(len(c) for _, _, c in _MATRIX_RUNS)} прогонов "
            f"провалились ({', '.join(failures)}) — частичная матрица не выдаётся за полную.",
            file=sys.stderr,
        )
        return 1

    report = _render_markdown_report(rows, args.duration, shots)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(report)
    return 0


# ─────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Разовый замер времени кадра UI TelemetryDashboard (PERF-02/PERF-03). "
            "ОБЯЗАН запускаться на реальном экране, не под QT_QPA_PLATFORM=offscreen."
        )
    )
    parser.add_argument("--config", choices=("baseline", "visible", "opengl"), default=None)
    parser.add_argument("--scenario", choices=("wide", "typical"), default=None)
    parser.add_argument("--speed", type=int, default=100, help="Множитель скорости симуляции")
    parser.add_argument(
        "--duration", type=float, default=15.0, help="Длительность измерительного окна, секунд"
    )
    parser.add_argument("--shot", type=Path, default=None, help="Путь для снимка окна дашборда")
    parser.add_argument("--json", action="store_true", help="Печатать результат одной строкой JSON")
    parser.add_argument("--all", action="store_true", help="Прогнать полную матрицу D-06 x D-07 (9 прогонов)")
    parser.add_argument(
        "--out",
        type=Path,
        # WR-04 (17-REVIEW.md): relative Path resolves against the process's
        # CWD at invocation time, not the script's location — anchor on
        # _PROJECT_ROOT (already used elsewhere, e.g. the sys.path insertion)
        # so --all from any directory writes to the real repo location
        # instead of silently creating a stray tree wherever it was invoked.
        default=_PROJECT_ROOT / ".planning/phases/17-ui-performance-stabilization/17-benchmark-raw.md",
        help="Путь результирующего markdown-файла в режиме --all",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    if args.all:
        return run_matrix(args)

    if args.config is None or args.scenario is None:
        print(
            "ОШИБКА: --config и --scenario обязательны в одиночном режиме "
            "(или используйте --all для полной матрицы).",
            file=sys.stderr,
        )
        return 2

    _platform_guard()

    try:
        result = run_single(args.config, args.scenario, args.speed, args.duration, args.shot)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - top-level: любое исключение -> ненулевой код, без частичных чисел
        print(f"ОШИБКА: прогон завершился исключением: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(jsonlib.dumps(result))
    else:
        _print_human(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
