"""
tray_manager.py
================

Fase 4 — Minimize to tray

Provides:
    * FloatingArcReactor       — a small (80×80) frameless, always-on-top
                                 draggable Qt widget that displays a stylised
                                 arc reactor "J" icon.  It re-opens the main
                                 HUD on left-click.
    * TrayManager              — a `pystray` background icon (Windows/Linux)
                                 with left-click toggle mute and right-click
                                 menu: "Mostra" / "Esci".

Both objects are owned by ``MainWindow``.  When the user issues the voice
command "minimizzati" / "nasconditi", or presses the "–" HUD button, the
main window is hidden, the waveform repaint is paused, the camera preview
is throttled to 1 fps and this floating icon + tray icon are shown.

On "mostrati" / "torna" (voice) or via the floating icon / tray menu the
main window is restored and every animation resumes.

Left-click on the tray icon toggles microphone mute: icon turns red while
muted, back to cyan on unmute. This mirrors the F4 / on-screen mute button.

The module keeps every heavy import lazy so it costs almost nothing when
the tray is never opened.
"""

from __future__ import annotations

import math
import threading
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPointF
from PyQt6.QtGui import (
    QBrush, QColor, QConicalGradient, QPainter, QPen, QRadialGradient,
)
from PyQt6.QtWidgets import QWidget


# ----------------------------------------------------------------------
# Floating draggable arc-reactor icon
# ----------------------------------------------------------------------
class FloatingArcReactor(QWidget):
    """Small always-on-top draggable icon shown when the HUD is minimized."""

    #: emitted with no args → user requested the main window back
    restore_requested = pyqtSignal()

    _SIZE = 84  # px

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(self._SIZE, self._SIZE)
        self.setToolTip("JARVIS — click to restore")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # animation
        self._angle = 0.0
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._tick)
        self._tmr.start(40)

        # drag state
        self._drag_offset: Optional[QPointF] = None
        self._pressed_pos: Optional[QPointF] = None
        self._is_dragging = False

    # ------- animation -------
    def _tick(self) -> None:
        self._angle = (self._angle + 3.0) % 360.0
        self.update()

    # ------- painting -------
    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self.width()
        cx = w / 2.0

        # backdrop soft glow
        glow = QRadialGradient(cx, cx, cx)
        glow.setColorAt(0.0, QColor(80, 240, 255, 90))
        glow.setColorAt(0.55, QColor(20, 60, 80, 40))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(1, 1, w - 2, w - 2)

        # outer ring
        p.setPen(QPen(QColor(140, 250, 255, 200), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(6, 6, w - 12, w - 12)

        # rotating conic gradient ring (mimics arc-reactor energy loop)
        conic = QConicalGradient(cx, cx, self._angle)
        conic.setColorAt(0.00, QColor(0, 220, 255, 220))
        conic.setColorAt(0.35, QColor(0, 90, 130, 40))
        conic.setColorAt(0.65, QColor(0, 220, 255, 220))
        conic.setColorAt(1.00, QColor(0, 90, 130, 40))
        p.setPen(QPen(QBrush(conic), 3))
        p.drawEllipse(12, 12, w - 24, w - 24)

        # 8-way spokes
        p.save()
        p.translate(cx, cx)
        p.setPen(QPen(QColor(120, 240, 255, 180), 1.5))
        r_inner, r_outer = w * 0.18, w * 0.36
        for i in range(8):
            a = math.radians(i * 45 + self._angle * 0.5)
            x1 = math.cos(a) * r_inner
            y1 = math.sin(a) * r_inner
            x2 = math.cos(a) * r_outer
            y2 = math.sin(a) * r_outer
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        p.restore()

        # inner core
        core = QRadialGradient(cx, cx, w * 0.22)
        core.setColorAt(0.0, QColor(255, 255, 255, 255))
        core.setColorAt(0.45, QColor(120, 250, 255, 230))
        core.setColorAt(1.0, QColor(0, 90, 130, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(core))
        p.drawEllipse(int(cx - w * 0.22), int(cx - w * 0.22),
                      int(w * 0.44), int(w * 0.44))

    # ------- drag + click -------
    def mousePressEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton:
            self._pressed_pos = ev.globalPosition()
            self._drag_offset = ev.globalPosition() - QPointF(
                self.frameGeometry().topLeft()
            )
            self._is_dragging = False
            ev.accept()

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if self._drag_offset is None:
            return
        if not self._is_dragging and self._pressed_pos is not None:
            if (ev.globalPosition() - self._pressed_pos).manhattanLength() > 6:
                self._is_dragging = True
        if self._is_dragging:
            new_top_left = ev.globalPosition() - self._drag_offset
            self.move(int(new_top_left.x()), int(new_top_left.y()))
            ev.accept()

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        was_click = (
            ev.button() == Qt.MouseButton.LeftButton
            and not self._is_dragging
        )
        self._drag_offset = None
        self._pressed_pos = None
        self._is_dragging = False
        if was_click:
            self.restore_requested.emit()
        ev.accept()

    # ------- lifecycle -------
    def start_anim(self) -> None:
        if not self._tmr.isActive():
            self._tmr.start(40)

    def stop_anim(self) -> None:
        if self._tmr.isActive():
            self._tmr.stop()


# ----------------------------------------------------------------------
# System-tray icon (pystray, background thread)
# ----------------------------------------------------------------------
class TrayManager:
    """
    Wrapper around ``pystray`` running its event loop in a background
    thread.  All callbacks are executed inside that thread; the caller
    must therefore marshal Qt actions back to the GUI thread (we use a
    ``QTimer.singleShot(0, ...)`` in ``ui.py``).

    Left-click on the tray icon toggles microphone mute (icon turns red
    while muted). Right-click opens the classic menu ("Mostra" / "Esci").
    """

    # Colors (RGBA)
    _COLOR_ACTIVE_RING = (140, 250, 255, 255)
    _COLOR_ACTIVE_INNER = (0, 220, 255, 255)
    _COLOR_ACTIVE_CORE = (200, 250, 255, 255)
    _COLOR_ACTIVE_SPOKE = (120, 240, 255, 255)

    _COLOR_MUTED_RING = (255, 90, 110, 255)
    _COLOR_MUTED_INNER = (230, 40, 60, 255)
    _COLOR_MUTED_CORE = (255, 200, 205, 255)
    _COLOR_MUTED_SPOKE = (240, 90, 110, 255)

    def __init__(
        self,
        on_show: Callable[[], None],
        on_exit: Callable[[], None],
        on_mute_toggle: Optional[Callable[[], bool]] = None,
        title: str = "JARVIS",
    ) -> None:
        self._on_show = on_show
        self._on_exit = on_exit
        # Callback that toggles mute in the host app and returns the new
        # muted state (True = now muted). If None, tray still toggles its
        # own visual state without affecting the mic.
        self._on_mute_toggle = on_mute_toggle
        self._title = title
        self._icon = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._muted = False

    # ---- icon image ----
    @classmethod
    def _build_image(cls, size: int = 64, muted: bool = False):
        """Draw a small arc-reactor style PNG in memory (PIL).

        muted=True → red palette to signal the microphone is off.
        """
        from PIL import Image, ImageDraw

        if muted:
            ring = cls._COLOR_MUTED_RING
            inner = cls._COLOR_MUTED_INNER
            core = cls._COLOR_MUTED_CORE
            spoke = cls._COLOR_MUTED_SPOKE
        else:
            ring = cls._COLOR_ACTIVE_RING
            inner = cls._COLOR_ACTIVE_INNER
            core = cls._COLOR_ACTIVE_CORE
            spoke = cls._COLOR_ACTIVE_SPOKE

        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # outer ring
        d.ellipse((2, 2, size - 3, size - 3), outline=ring, width=3)
        # inner ring
        inner_off = size // 5
        d.ellipse(
            (inner_off, inner_off, size - inner_off - 1, size - inner_off - 1),
            outline=inner,
            width=2,
        )
        # core
        core_off = size // 3
        d.ellipse(
            (core_off, core_off, size - core_off - 1, size - core_off - 1),
            fill=core,
        )
        # spokes
        cx = size / 2
        r1, r2 = size * 0.22, size * 0.38
        for i in range(8):
            a = math.radians(i * 45)
            d.line(
                (
                    cx + math.cos(a) * r1,
                    cx + math.sin(a) * r1,
                    cx + math.cos(a) * r2,
                    cx + math.sin(a) * r2,
                ),
                fill=spoke,
                width=2,
            )
        # When muted, overlay a red diagonal slash to reinforce the
        # "microphone off" semantics.
        if muted:
            d.line(
                (int(size * 0.18), int(size * 0.18),
                 int(size * 0.82), int(size * 0.82)),
                fill=(255, 40, 60, 255),
                width=4,
            )
        return img

    # ---- lifecycle ----
    def start(self) -> None:
        if self._running:
            return
        try:
            import pystray
        except Exception as exc:  # pragma: no cover
            print(f"[Tray] pystray not available: {exc}")
            return

        image = self._build_image(muted=self._muted)
        # On Windows, `default=True` marks the item invoked by a single
        # left-click on the tray icon. We wire it to the mute toggle so
        # left-click = toggle mute, right-click = full menu.
        menu = pystray.Menu(
            pystray.MenuItem(
                self._mute_label,
                self._handle_mute_toggle,
                default=True,
            ),
            pystray.MenuItem("Mostra", self._handle_show),
            pystray.MenuItem("Esci", self._handle_exit),
        )
        self._icon = pystray.Icon("jarvis", image, self._title, menu)

        # ---------- Windows: force single left-click = mute toggle ----------
        # pystray's default `default=True` menu item is bound to
        # WM_LBUTTONDBLCLK on Windows, so with the stock behaviour the
        # user needs a DOUBLE click to toggle mute. The requirement is
        # "left click on tray -> mute". We patch the icon's WndProc so
        # that a single WM_LBUTTONUP also fires the mute toggle.
        try:
            import platform as _plat
            if _plat.system() == "Windows":
                self._install_single_click_hook()
        except Exception as exc:
            print(f"[Tray] single-click hook install failed: {exc}")

        self._running = True
        self._thread = threading.Thread(
            target=self._icon.run, daemon=True, name="tray-icon"
        )
        self._thread.start()

    def _install_single_click_hook(self) -> None:
        """Patch pystray's Win32 WndProc so that a *single* left-click on
        the tray icon toggles mute (matches the user requirement
        "tasto sinistro sul tray -> muto"). Safe no-op if the internal
        API changes: any failure is swallowed.
        """
        icon = self._icon
        if icon is None:
            return

        # pystray uses a bound method as WndProc; the tray messages arrive
        # via WM_APP + 1 (== 0x8001) with lParam containing the event
        # code. Left button up == 0x0202 (WM_LBUTTONUP).
        WM_LBUTTONUP = 0x0202
        original = getattr(icon, "_on_notify", None)
        if original is None:
            return

        # We can't reliably wrap the low-level WndProc across pystray
        # versions, so instead we hook `_on_notify` — the tray-message
        # dispatcher — and treat every WM_LBUTTONUP as a click on the
        # default menu item.
        def _wrapped(wparam, lparam):  # type: ignore
            try:
                # lparam holds the event id (LOWORD).
                event = lparam & 0xFFFF
                if event == WM_LBUTTONUP:
                    try:
                        self._handle_mute_toggle()
                    except Exception:
                        pass
                    return
            except Exception:
                pass
            return original(wparam, lparam)

        try:
            icon._on_notify = _wrapped  # type: ignore[attr-defined]
        except Exception:
            pass

    def stop(self) -> None:
        if not self._running:
            return
        try:
            if self._icon is not None:
                self._icon.stop()
        except Exception:
            pass
        self._running = False
        self._icon = None
        self._thread = None

    # ---- dynamic menu label ----
    def _mute_label(self, _item=None) -> str:
        return "Riattiva microfono" if self._muted else "Silenzia microfono"

    def _refresh_icon(self) -> None:
        """Rebuild the tray image + refresh menu (label + default marker)."""
        if self._icon is None:
            return
        try:
            self._icon.icon = self._build_image(muted=self._muted)
            self._icon.title = (
                f"{self._title} — MUTED" if self._muted else self._title
            )
            # Refresh the dynamic menu label. pystray re-evaluates the
            # menu when `update_menu` is called.
            self._icon.update_menu()
        except Exception:
            pass

    def set_muted(self, muted: bool) -> None:
        """External API: sync tray state when mute is toggled elsewhere
        (F4 shortcut, on-screen mute button, ...)."""
        if bool(muted) == self._muted:
            return
        self._muted = bool(muted)
        self._refresh_icon()

    # ---- menu handlers ----
    def _handle_mute_toggle(self, icon=None, item=None) -> None:  # noqa: ARG002
        # Flip local state first (optimistic UI), then delegate to the
        # host app which may override the final state.
        self._muted = not self._muted
        if self._on_mute_toggle is not None:
            try:
                new_state = self._on_mute_toggle()
                if isinstance(new_state, bool):
                    self._muted = new_state
            except Exception as exc:
                print(f"[Tray] mute toggle callback failed: {exc}")
        self._refresh_icon()

    def _handle_show(self, icon=None, item=None) -> None:  # noqa: ARG002
        try:
            self._on_show()
        finally:
            self.stop()

    def _handle_exit(self, icon=None, item=None) -> None:  # noqa: ARG002
        try:
            self._on_exit()
        finally:
            self.stop()

    @property
    def running(self) -> bool:
        return self._running

    @property
    def muted(self) -> bool:
        return self._muted
