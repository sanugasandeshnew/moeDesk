"""
MoeWalls Live Wallpaper Engine for Windows 10 / 11
Combines MoeWalls Online Wallpaper Store with PySide6 Native Windows Live Wallpaper Engine.
Theme: Full AMOLED Pitch Black (#000000) with macOS Liquid Glass Aesthetics.
"""
import sys
import os
import re
import json
import time
import hashlib
import ctypes
import shutil
import subprocess
import threading
from pathlib import Path
from ctypes import wintypes
from urllib.parse import urljoin
from io import BytesIO

import cloudscraper
import psutil
from bs4 import BeautifulSoup
from PIL import Image

from PySide6.QtCore import (
    Qt, QUrl, QTimer, QSize, Signal, QObject, QThread, QPoint, QPointF
)
from PySide6.QtGui import (
    QAction, QIcon, QPixmap, QPainter, QColor, QPolygon, QPolygonF, QLinearGradient,
    QGuiApplication, QImage, QPainterPath, QPen, QBrush
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QComboBox, QSlider, QCheckBox, QFileDialog,
    QSystemTrayIcon, QMenu, QFrame, QScrollArea, QGridLayout, QLineEdit,
    QStackedWidget, QProgressBar, QSizePolicy, QMessageBox, QDialog
)

APP_NAME = "moeDesk"
SERVER_NAME = "moeDesk-SingleInstance-v1"
VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".mov", ".avi", ".wmv", ".m4v", ".flv")
if getattr(sys, "frozen", False):
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    EXE_DIR = Path(sys.executable).parent
else:
    BUNDLE_DIR = Path(__file__).resolve().parent
    EXE_DIR = BUNDLE_DIR

BASE_DIR = BUNDLE_DIR

DATA_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "moeDesk"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = DATA_DIR / "settings.json"
IS_WIN = sys.platform == "win32"

# Safe persistent storage:
# Always use DATA_DIR (%APPDATA%\moeDesk) so downloaded wallpapers, thumbnails, and cache
# are never deleted by temporary directory cleanups (crucial for standalone onefile EXEs).
# Portable mode is only activated if a 'portable.txt' file is explicitly placed next to the executable.
if (EXE_DIR / "portable.txt").exists() or (EXE_DIR / "portable.dat").exists():
    STORE_DIR = EXE_DIR
else:
    STORE_DIR = DATA_DIR
WALLPAPERS_DIR = STORE_DIR / "wallpapers"
WALLPAPERS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = STORE_DIR / ".cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
PREVIEWS_DIR = CACHE_DIR / "previews"
PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
THUMBS_DIR = CACHE_DIR / "thumbnails"
THUMBS_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOADS_STATE_FILE = CACHE_DIR / "downloads_state.json"

CATEGORIES = [
    ("Latest", ""),
    ("Abstract", "abstract"),
    ("Animal", "animal"),
    ("Anime", "anime"),
    ("Fantasy", "fantasy"),
    ("Games", "games"),
    ("Landscape", "landscape"),
    ("Lifestyle", "lifestyle"),
    ("Movies", "movies"),
    ("Others", "others"),
    ("Pixel Art", "pixel-art"),
    ("Sci-fi", "sci-fi"),
    ("Vehicle", "vehicle")
]

DEFAULT_SETTINGS = {
    "last": "",
    "recent": [],
    "fit": "fill",
    "monitors": "all",
    "speed": 1.0,
    "volume": 40,
    "muted": True,
    "pause_busy": True,
    "pause_battery": True,
    "favorites": [],
}


def load_cfg():
    try:
        return {**DEFAULT_SETTINGS, **json.loads(CONFIG_FILE.read_text("utf-8"))}
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_cfg(cfg):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), "utf-8")
    except Exception:
        pass


# ───────────────────────── Win32 Desktop Injection ─────────────────────────
if IS_WIN:
    import winreg
    user32 = ctypes.windll.user32
    H = wintypes.HWND
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = H
    user32.FindWindowExW.argtypes = [H, H, wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowExW.restype = H
    user32.SendMessageTimeoutW.argtypes = [
        H, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)
    ]
    user32.SetParent.argtypes = [H, H]
    user32.SetParent.restype = H
    user32.GetParent.argtypes = [H]
    user32.GetParent.restype = H
    user32.IsWindow.argtypes = [H]
    user32.SetWindowPos.argtypes = [H, H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.ScreenToClient.argtypes = [H, ctypes.POINTER(wintypes.POINT)]
    user32.GetForegroundWindow.restype = H
    user32.GetAncestor.argtypes = [H, wintypes.UINT]
    user32.GetAncestor.restype = H
    user32.IsWindowVisible.argtypes = [H]
    user32.IsIconic.argtypes = [H]
    user32.IsZoomed.argtypes = [H]
    user32.GetClassNameW.argtypes = [H, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowRect.argtypes = [H, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowThreadProcessId.argtypes = [H, ctypes.POINTER(wintypes.DWORD)]
    _GWL = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    _SWL = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    _GWL.argtypes = [H, ctypes.c_int]
    _GWL.restype = ctypes.c_ssize_t
    _SWL.argtypes = [H, ctypes.c_int, ctypes.c_ssize_t]
    _SWL.restype = ctypes.c_ssize_t

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, H, wintypes.LPARAM)
    MONENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HANDLE,
                                     ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    class SPS(ctypes.Structure):
        _fields_ = [
            ("AC", ctypes.c_ubyte), ("Flag", ctypes.c_ubyte), ("Pct", ctypes.c_ubyte),
            ("Sys", ctypes.c_ubyte), ("Life", ctypes.c_ulong), ("Full", ctypes.c_ulong)
        ]

    def desktop_parent():
        progman = user32.FindWindowW("Progman", None)
        res = ctypes.c_size_t()
        user32.SendMessageTimeoutW(progman, 0x052C, 0xD, 0x1, 0, 1000, ctypes.byref(res))
        user32.SendMessageTimeoutW(progman, 0x052C, 0, 0, 0, 1000, ctypes.byref(res))
        found = []

        def cb(hwnd, _):
            if user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None):
                w = user32.FindWindowExW(None, hwnd, "WorkerW", None)
                if w:
                    found.append(w)
            return True

        user32.EnumWindows(WNDENUMPROC(cb), 0)
        if found:
            return found[0], 0
        defview = user32.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
        return progman, (defview or 1)

    def get_monitors():
        out = []

        def cb(h, dc, rect, lp):
            r = rect.contents
            out.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
            return True

        user32.EnumDisplayMonitors(None, None, MONENUMPROC(cb), 0)
        out.sort(key=lambda m: (m[0] != 0 or m[1] != 0, m[0], m[1]))
        return out

    def attach(hwnd, rect):
        parent, after = desktop_parent()
        style = _GWL(hwnd, -16)
        style = (style & ~0x80000000 & ~0x00C00000 & ~0x00040000) | 0x40000000 | 0x10000000 | 0x04000000
        _SWL(hwnd, -16, style)
        user32.SetParent(hwnd, parent)
        x, y, w, h = rect
        pt = wintypes.POINT(x, y)
        user32.ScreenToClient(parent, ctypes.byref(pt))
        user32.SetWindowPos(hwnd, after, pt.x, pt.y, w, h, 0x0010 | 0x0040 | 0x0020 | 0x0200)
        return parent

    def busy_foreground():
        # 1. Direct3D Fullscreen games & Presentation Mode (Standard Windows shell notification state)
        try:
            state = wintypes.DWORD()
            if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) == 0:
                # 2 = QUNS_BUSY (fullscreen app/presentation), 3 = QUNS_RUNNING_D3D_FULL_SCREEN (exclusive game), 4 = QUNS_PRESENTATION_MODE
                if state.value in (2, 3, 4):
                    return True
        except Exception:
            pass

        # 2. Foreground Window Check
        h = user32.GetForegroundWindow()
        if not h or not user32.IsWindowVisible(h) or user32.IsIconic(h):
            return False

        # Get top-level root window (handles focus inside child controls/browser tabs/iframes)
        root = user32.GetAncestor(h, 2)  # GA_ROOT = 2
        if root and user32.IsWindow(root):
            h = root

        # Check cloaked state (Windows 10/11 virtual desktops or background UWP apps)
        try:
            cloaked = wintypes.DWORD()
            if ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0:
                if cloaked.value != 0:
                    return False
        except Exception:
            pass

        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(h, buf, 256)
        if buf.value in (
            "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
            "Windows.UI.Core.CoreWindow", "XamlExplorerHostIslandWindow",
            "ForegroundStaging", "MultitaskingViewFrame", "TaskListThumbnailWnd"
        ):
            return False

        # If window is maximized
        if user32.IsZoomed(h):
            return True

        # If window is borderless fullscreen or covers the entire screen (games, YouTube/VLC F11)
        r = wintypes.RECT()
        if user32.GetWindowRect(h, ctypes.byref(r)):
            for x, y, w, h_mon in get_monitors():
                # Allow +/- 8px margin for Windows 10/11 invisible sizing borders and DPI scale rounding
                if r.left <= x + 8 and r.top <= y + 8 and r.right >= x + w - 8 and r.bottom >= y + h_mon - 8:
                    return True

        return False

    def on_battery():
        s = SPS()
        return bool(ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s))) and s.AC == 0

    def restore_wallpaper():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as k:
                p = winreg.QueryValueEx(k, "WallPaper")[0]
            ctypes.windll.user32.SystemParametersInfoW(0x14, 0, p, 0x3)
        except Exception:
            pass

    def launch_cmd():
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'
        pyw = Path(sys.executable).with_name("pythonw.exe")
        exe = pyw if pyw.exists() else Path(sys.executable)
        return f'"{exe}" "{Path(__file__).resolve()}"'

    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def autostart_enabled():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
                winreg.QueryValueEx(k, APP_NAME)
            return True
        except OSError:
            return False

    def set_autostart(on):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, launch_cmd() + " --tray")
            else:
                try:
                    winreg.DeleteValue(k, APP_NAME)
                except OSError:
                    pass

    def _ctx_key(ext):
        return rf"Software\Classes\SystemFileAssociations\{ext}\shell\SetLiveWallpaper"

    def context_enabled():
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ctx_key(".mp4")))
            return True
        except OSError:
            return False

    def set_context(on):
        for ext in VIDEO_EXTS:
            key = _ctx_key(ext)
            if on:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
                    winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "Set as Live Wallpaper")
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + r"\command") as k:
                    winreg.SetValueEx(k, "", 0, winreg.REG_SZ, launch_cmd() + ' "%1"')
            else:
                for sub in (key + r"\command", key):
                    try:
                        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
                    except OSError:
                        pass
else:
    def get_monitors():
        return [(s.geometry().x(), s.geometry().y(), s.geometry().width(), s.geometry().height())
                for s in QGuiApplication.screens()]
    def attach(hwnd, rect): return None
    def busy_foreground(): return False
    def on_battery(): return False
    def restore_wallpaper(): pass
    def autostart_enabled(): return False
    def set_autostart(on): pass
    def context_enabled(): return False
    def set_context(on): pass
    user32 = None


# ───────────────────────── Video Codec Detection ─────────────────────────
def get_video_codec(file_path):
    """Fast detection of video codec (AV1, H264, H265, VP9) by reading MP4/WebM atoms."""
    try:
        size = os.path.getsize(file_path)
        with open(file_path, "rb") as f:
            head = f.read(65536)
            tail = b""
            if size > 131072:
                f.seek(-65536, os.SEEK_END)
                tail = f.read(65536)
            chunk = head + tail
            if b"av01" in chunk:
                return "AV1"
            elif b"avc1" in chunk:
                return "H264"
            elif b"hvc1" in chunk or b"hev1" in chunk:
                return "H265"
            elif b"vp09" in chunk or b"vp9" in chunk:
                return "VP9"
    except Exception:
        pass
    return "Unknown"


# ───────────────────────── Live Wallpaper Engine ─────────────────────────
FIT_MODES = {
    "fill": Qt.AspectRatioMode.KeepAspectRatioByExpanding,
    "fit": Qt.AspectRatioMode.KeepAspectRatio,
    "stretch": Qt.AspectRatioMode.IgnoreAspectRatio
}


class Engine:
    def __init__(self, cfg, on_error):
        self.cfg = cfg
        self.on_error = on_error
        self.walls = []
        self.path = None
        self.user_paused = False
        self.auto_paused = False

    def rects(self):
        mons = get_monitors() or [(0, 0, 1920, 1080)]
        return mons[:1] if self.cfg.get("monitors") == "primary" else mons

    def start(self, path):
        self.stop(restore=False)
        self.path = os.path.abspath(path)
        self.user_paused = False
        for i, rect in enumerate(self.rects()):
            w = QVideoWidget()
            w.setWindowFlags(
                Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool |
                Qt.WindowType.WindowDoesNotAcceptFocus
            )
            w.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            w.setStyleSheet("background:black;")
            w.setGeometry(*rect)

            player = QMediaPlayer()
            audio = QAudioOutput()
            player.setAudioOutput(audio)
            player.setVideoOutput(w)
            player.setLoops(QMediaPlayer.Loops.Infinite)
            player.errorOccurred.connect(lambda e, s: self.on_error(s))
            player.setSource(QUrl.fromLocalFile(self.path))
            w.show()

            hwnd = int(w.winId())
            parent = attach(hwnd, rect)
            self.walls.append({"w": w, "p": player, "a": audio, "hwnd": hwnd, "parent": parent, "i": i})

        self.apply_settings()
        for wl in self.walls:
            wl["p"].play()
        self.update_play_state()

    def apply_settings(self):
        for wl in self.walls:
            wl["w"].setAspectRatioMode(FIT_MODES.get(self.cfg.get("fit", "fill"), FIT_MODES["fill"]))
            wl["a"].setVolume(self.cfg.get("volume", 40) / 100.0)
            wl["a"].setMuted(self.cfg.get("muted", True) or wl["i"] > 0)
            wl["p"].setPlaybackRate(float(self.cfg.get("speed", 1.0)))

    def update_play_state(self):
        play = not (self.user_paused or self.auto_paused)
        for wl in self.walls:
            if play and wl["p"].playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                wl["p"].play()
            elif not play and wl["p"].playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                wl["p"].pause()

    def relayout(self):
        if not self.walls or not self.path:
            return
        if len(self.rects()) != len(self.walls):
            return self.start(self.path)
        for wl, rect in zip(self.walls, self.rects()):
            wl["parent"] = attach(wl["hwnd"], rect)

    def tick(self):
        if not self.walls:
            return
        if IS_WIN and self.walls[0]["parent"] and not user32.IsWindow(self.walls[0]["parent"]):
            self.relayout()
        auto = False
        if self.cfg.get("pause_busy", True) and busy_foreground():
            auto = True
        if self.cfg.get("pause_battery", True) and on_battery():
            auto = True
        if auto != self.auto_paused:
            self.auto_paused = auto
            self.update_play_state()

    def toggle_pause(self):
        self.user_paused = not self.user_paused
        self.update_play_state()
        return self.user_paused

    def is_playing(self):
        return bool(self.walls) and not self.user_paused and not self.auto_paused

    def stop(self, restore=True):
        for wl in self.walls:
            wl["p"].stop()
            wl["p"].setVideoOutput(None)
            wl["w"].close()
            wl["w"].deleteLater()
        self.walls = []
        if restore and self.path:
            restore_wallpaper()
        if restore:
            self.path = None


# ───────────────────────── macOS Liquid Glass Theme (AMOLED Black) ─────────────────────────
MACOS_LIQUID_GLASS_QSS = """
/* Global Reset - True AMOLED Pitch Black */
QWidget {
    background-color: #000000;
    color: #F3F4F6;
    font-family: 'Segoe UI Variable Display', 'Segoe UI', -apple-system, sans-serif;
    font-size: 13px;
    selection-background-color: #0A84FF;
    selection-color: #FFFFFF;
}

/* Glass Panels */
QFrame#sidebar {
    background-color: #040406;
    border-right: 1px solid rgba(255, 255, 255, 0.08);
}

QFrame#glassCard, QFrame#downloadItemCard {
    background-color: rgba(255, 255, 255, 0.035);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
}
QFrame#glassCard:hover, QFrame#downloadItemCard:hover {
    background-color: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.16);
}

/* Top bar / Search bar */
QLineEdit#glassSearch {
    background-color: rgba(255, 255, 255, 0.05);
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 20px;
    padding: 9px 18px;
    font-size: 13px;
}
QLineEdit#glassSearch:focus {
    border: 1px solid #0A84FF;
    background-color: rgba(255, 255, 255, 0.08);
}

/* macOS Sidebar Pills */
QPushButton#navBtn {
    background: transparent;
    color: #9CA3AF;
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 10px 14px;
    font-weight: 500;
    font-size: 13px;
    text-align: left;
}
QPushButton#navBtn:hover {
    background: rgba(255, 255, 255, 0.06);
    color: #FFFFFF;
}
QPushButton#navBtnActive {
    background: rgba(10, 132, 255, 0.18);
    border: 1px solid rgba(10, 132, 255, 0.4);
    color: #60A5FA;
    font-weight: 600;
    font-size: 13px;
    border-radius: 10px;
    padding: 10px 14px;
    text-align: left;
}

/* Action Buttons */
QPushButton#primaryBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0A84FF, stop:1 #0066CC);
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 10px;
    font-weight: 600;
    padding: 7px 14px;
}
QPushButton#primaryBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #258CFF, stop:1 #0A78F0);
    border: 1px solid rgba(255, 255, 255, 0.35);
}

QPushButton#glassBtn {
    background: rgba(255, 255, 255, 0.06);
    color: #E5E7EB;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    padding: 7px 14px;
}
QPushButton#glassBtn:hover {
    background: rgba(255, 255, 255, 0.12);
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.22);
}

QPushButton#chipBtn {
    background: rgba(255, 255, 255, 0.04);
    color: #9CA3AF;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    padding: 5px 12px;
    font-size: 12px;
}
QPushButton#chipBtn:hover {
    background: rgba(255, 255, 255, 0.10);
    color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.2);
}
QPushButton#chipBtnActive {
    background: rgba(10, 132, 255, 0.22);
    color: #60A5FA;
    border: 1px solid rgba(10, 132, 255, 0.5);
    border-radius: 14px;
    padding: 5px 12px;
    font-size: 12px;
    font-weight: 600;
}

/* Scroll Area */
QScrollArea {
    background-color: transparent;
    border: none;
}
QScrollBar:vertical {
    width: 8px;
    background: transparent;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.14);
    min-height: 24px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(255, 255, 255, 0.28);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

/* Inputs & Combos */
QComboBox {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    padding: 6px 12px;
    color: #FFFFFF;
}
QComboBox#filterCombo {
    background-color: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
    color: #E5E7EB;
}
QComboBox#filterCombo:hover {
    background-color: rgba(255, 255, 255, 0.09);
    border-color: rgba(255, 255, 255, 0.25);
    color: #FFFFFF;
}
QComboBox:hover {
    border-color: rgba(255, 255, 255, 0.25);
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background-color: #121216;
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 8px;
    selection-background-color: #0A84FF;
    selection-color: #FFFFFF;
    color: #E5E7EB;
    padding: 4px;
}

QListWidget {
    background-color: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 6px;
    color: #E5E7EB;
}
QListWidget::item {
    border-radius: 8px;
    padding: 8px 10px;
    margin: 2px 0;
}
QListWidget::item:hover {
    background: rgba(255, 255, 255, 0.06);
}
QListWidget::item:selected {
    background: rgba(10, 132, 255, 0.3);
    color: #FFFFFF;
}

/* Sliders */
QSlider::groove:horizontal {
    height: 4px;
    background: rgba(255, 255, 255, 0.12);
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #0A84FF;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #FFFFFF;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
    border: 1px solid rgba(0, 0, 0, 0.2);
}

/* Checkbox */
QCheckBox {
    spacing: 10px;
    color: #D1D5DB;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.2);
    background: rgba(255, 255, 255, 0.05);
}
QCheckBox::indicator:hover {
    border-color: #0A84FF;
}
QCheckBox::indicator:checked {
    background: #0A84FF;
    border: 1px solid #0A84FF;
}

/* Progress bar */
QProgressBar {
    background: rgba(255, 255, 255, 0.08);
    border-radius: 4px;
    height: 6px;
    text-align: center;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0A84FF, stop:1 #00E5FF);
    border-radius: 4px;
}
"""


def make_app_icon():
    search_dirs = [BASE_DIR]
    if getattr(sys, "frozen", False):
        search_dirs.append(Path(sys.executable).parent)
    for d in search_dirs:
        ico_path = d / "app_icon.ico"
        if ico_path.exists():
            return QIcon(str(ico_path))
        png_path = d / "app_icon.png"
        if png_path.exists():
            return QIcon(str(png_path))
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, 64, 64)
    g.setColorAt(0, QColor("#0A84FF"))
    g.setColorAt(1, QColor("#00E5FF"))
    p.setBrush(g)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(2, 2, 60, 60, 16, 16)
    p.setBrush(QColor("white"))
    p.drawPolygon(QPolygon([QPoint(25, 18), QPoint(25, 46), QPoint(48, 32)]))
    p.end()
    return QIcon(pm)


def make_eye_icon(color="#FFFFFF", size=20):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.6)
    p.setPen(pen)

    # Eye outline
    path = QPainterPath()
    path.moveTo(2, size / 2)
    path.cubicTo(size * 0.3, size * 0.15, size * 0.7, size * 0.15, size - 2, size / 2)
    path.cubicTo(size * 0.7, size * 0.85, size * 0.3, size * 0.85, 2, size / 2)
    p.drawPath(path)

    # Pupil
    p.setBrush(QColor(color))
    p.drawEllipse(QPointF(size / 2, size / 2), size * 0.18, size * 0.18)
    p.end()
    return QIcon(pm)


def make_trash_icon(color="#EF4444", size=20):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.5)
    p.setPen(pen)

    # Lid & handle
    p.drawLine(3, 5, size - 3, 5)
    p.drawLine(7, 3, size - 7, 3)

    # Body
    path = QPainterPath()
    path.moveTo(5, 5)
    path.lineTo(6, size - 3)
    path.quadTo(6, size - 2, 7, size - 2)
    path.lineTo(size - 7, size - 2)
    path.quadTo(size - 6, size - 2, size - 6, size - 3)
    path.lineTo(size - 5, 5)
    p.drawPath(path)

    # Vertical ribs
    p.drawLine(size * 0.4, 8, size * 0.4, size - 5)
    p.drawLine(size * 0.6, 8, size * 0.6, size - 5)
    p.end()
    return QIcon(pm)


def make_heart_icon(color="#EC4899", size=18, filled=True):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    w = float(size)
    h = float(size)

    path = QPainterPath()
    path.moveTo(0.50 * w, 0.32 * h)
    path.cubicTo(0.45 * w, 0.12 * h, 0.12 * w, 0.12 * h, 0.12 * w, 0.40 * h)
    path.cubicTo(0.12 * w, 0.60 * h, 0.32 * w, 0.74 * h, 0.50 * w, 0.90 * h)
    path.cubicTo(0.68 * w, 0.74 * h, 0.88 * w, 0.60 * h, 0.88 * w, 0.40 * h)
    path.cubicTo(0.88 * w, 0.12 * h, 0.55 * w, 0.12 * h, 0.50 * w, 0.32 * h)
    path.closeSubpath()

    c = QColor(color)
    if filled:
        p.setBrush(QBrush(c))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)
    else:
        p.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(c, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPath(path)

    p.end()
    return QIcon(pm)


def make_play_icon(color="#FFFFFF", size=18):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    poly = QPolygonF([
        QPointF(size * 0.28, size * 0.2),
        QPointF(size * 0.8, size * 0.5),
        QPointF(size * 0.28, size * 0.8)
    ])
    p.drawPolygon(poly)
    p.end()
    return QIcon(pm)


def make_pause_icon(color="#FFFFFF", size=18):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    w = size * 0.22
    h = size * 0.6
    y = size * 0.2
    p.drawRoundedRect(size * 0.22, y, w, h, 2, 2)
    p.drawRoundedRect(size * 0.56, y, w, h, 2, 2)
    p.end()
    return QIcon(pm)


def make_cancel_icon(color="#EF4444", size=18):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    m = size * 0.26
    p.drawLine(QPointF(m, m), QPointF(size - m, size - m))
    p.drawLine(QPointF(size - m, m), QPointF(m, size - m))
    p.end()
    return QIcon(pm)


def make_folder_icon(color="#9CA3AF", size=18):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color), 1.6))
    p.setBrush(QColor(color).lighter(120))
    path = QPainterPath()
    path.moveTo(size * 0.15, size * 0.3)
    path.lineTo(size * 0.42, size * 0.3)
    path.lineTo(size * 0.52, size * 0.42)
    path.lineTo(size * 0.85, size * 0.42)
    path.lineTo(size * 0.85, size * 0.78)
    path.lineTo(size * 0.15, size * 0.78)
    path.closeSubpath()
    p.drawPath(path)
    p.end()
    return QIcon(pm)


# ───────────────────────── Scraper Worker & Signals ─────────────────────────
class ScraperSignals(QObject):
    results_ready = Signal(list, bool)  # (items, append)
    card_thumbnail_ready = Signal(int, bytes)
    status_msg = Signal(str)
    download_progress = Signal(str, int, float, float)
    download_finished = Signal(str, str, bool)
    open_preview_signal = Signal(str, str, bool, str)  # (title, url_or_path, is_local, post_url)
    load_more_done = Signal(bool)
    local_thumb_ready = Signal(str, str)  # (file_path, thumb_path)


# ───────────────────────── Live Video Preview Modal ─────────────────────────
class LivePreviewDialog(QDialog):
    preview_ready_signal = Signal(str)
    preview_error_signal = Signal(str)

    def __init__(self, title, video_url_or_path=None, is_local=False, parent_win=None, post_url=None):
        super().__init__(parent_win)
        self.win = parent_win
        self.post_url = post_url
        self.title_text = title
        self.is_closed = False
        self.current_video_path = video_url_or_path if is_local else None

        self.setWindowTitle(f"Preview: {title}")
        self.setMinimumSize(820, 520)
        self.resize(880, 560)
        self.setStyleSheet("""
            QDialog {
                background-color: #050505;
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 14px;
            }
            QLabel {
                color: #FFFFFF;
                font-family: 'Segoe UI Variable Display', 'Segoe UI', sans-serif;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Header Row
        header = QHBoxLayout()
        t_label = QLabel(title if len(title) <= 50 else title[:48] + "…")
        t_label.setStyleSheet("font-size: 15px; font-weight: 700; color: #FFFFFF;")
        header.addWidget(t_label)
        header.addStretch(1)

        btn_close_top = QPushButton("Close")
        btn_close_top.setObjectName("glassBtn")
        btn_close_top.clicked.connect(self.close)
        header.addWidget(btn_close_top)
        layout.addLayout(header)

        # Center Stack (Loading View vs Video Player)
        self.center_stack = QStackedWidget()

        # Loading View
        self.loading_frame = QFrame()
        self.loading_frame.setStyleSheet("""
            QFrame {
                background-color: #080808;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
            }
        """)
        loading_layout = QVBoxLayout(self.loading_frame)
        loading_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_lbl = QLabel("Preparing live video preview...")
        self.loading_lbl.setStyleSheet("font-size: 14px; font-weight: 600; color: #9CA3AF;")
        self.loading_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_layout.addWidget(self.loading_lbl)
        self.center_stack.addWidget(self.loading_frame)

        # Video Player Widget
        self.video_widget = QVideoWidget()
        self.video_widget.setStyleSheet("background-color: #000000; border-radius: 10px;")
        self.center_stack.addWidget(self.video_widget)

        layout.addWidget(self.center_stack, 1)

        # Bottom Action Bar
        bottom = QHBoxLayout()
        bottom.setSpacing(10)

        self.btn_set_live = QPushButton("Set as Live Wallpaper")
        self.btn_set_live.setObjectName("primaryBtn")
        self.btn_set_live.setFixedHeight(34)
        if is_local and video_url_or_path:
            self.btn_set_live.clicked.connect(lambda: [self.win.apply_wallpaper(video_url_or_path), self.close()])
        else:
            self.btn_set_live.clicked.connect(lambda: [self.win.download_and_apply(self.post_url, self.title_text, auto_apply=True), self.close()])
        bottom.addWidget(self.btn_set_live)

        self.btn_fav = QPushButton()
        self.btn_fav.setObjectName("glassBtn")
        self.btn_fav.setFixedSize(38, 34)
        self.btn_fav.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fav.clicked.connect(self.on_fav_clicked)
        bottom.addWidget(self.btn_fav)
        self.update_fav_btn()

        if not is_local:
            self.btn_dl = QPushButton("Download MP4")
            self.btn_dl.setObjectName("glassBtn")
            self.btn_dl.setFixedHeight(34)
            self.btn_dl.clicked.connect(lambda: [self.win.download_and_apply(self.post_url, self.title_text, auto_apply=False), self.close()])
            bottom.addWidget(self.btn_dl)

        bottom.addStretch(1)

        btn_close = QPushButton("Close Preview")
        btn_close.setObjectName("glassBtn")
        btn_close.setFixedHeight(34)
        btn_close.clicked.connect(self.close)
        bottom.addWidget(btn_close)

        layout.addLayout(bottom)

        # Initialize Player
        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video_widget)
        self.player.setLoops(QMediaPlayer.Loops.Infinite)
        self.audio.setMuted(True)

        self.preview_ready_signal.connect(self.on_preview_ready)
        self.preview_error_signal.connect(self.on_preview_error)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.errorOccurred.connect(self._on_player_error)

        if is_local and video_url_or_path:
            self.on_preview_ready(video_url_or_path)
        elif video_url_or_path and not is_local:
            self.player.setSource(QUrl(video_url_or_path))
            self.center_stack.setCurrentIndex(1)
            self.player.play()
        elif post_url:
            self.start_preview_pipeline(post_url, title)

    def _on_media_status(self, status):
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self.player.play()

    def _on_player_error(self, err, err_str):
        print(f"Preview player error: {err} - {err_str}")
        if not self.is_closed and self.center_stack.currentIndex() == 0:
            self.loading_lbl.setText(f"Playback error: {err_str}")
            self.loading_lbl.setStyleSheet("font-size: 13px; color: #EF4444;")

    def on_preview_ready(self, file_path):
        if self.is_closed:
            return
        self.current_video_path = file_path
        self.player.setSource(QUrl.fromLocalFile(os.path.abspath(file_path)))
        self.center_stack.setCurrentIndex(1)
        self.player.play()

    def on_preview_error(self, err_msg):
        if self.is_closed:
            return
        self.loading_lbl.setText(f"Preview unavailable: {err_msg}")
        self.loading_lbl.setStyleSheet("font-size: 13px; color: #EF4444;")

    def update_fav_btn(self):
        if not self.win:
            return
        is_fav = self.win.is_favorite(title=self.title_text, file_path=self.current_video_path or "", post_url=self.post_url or "")
        if is_fav:
            self.btn_fav.setIcon(make_heart_icon("#EC4899", 18, filled=True))
            self.btn_fav.setToolTip("Remove from Favorites")
            self.btn_fav.setStyleSheet("QPushButton { border: 1px solid rgba(236, 72, 153, 0.6); background: rgba(236, 72, 153, 0.15); border-radius: 8px; } QPushButton:hover { background: rgba(236, 72, 153, 0.28); border: 1px solid #EC4899; }")
        else:
            self.btn_fav.setIcon(make_heart_icon("#FFFFFF", 18, filled=False))
            self.btn_fav.setToolTip("Add to Favorites")
            self.btn_fav.setStyleSheet("QPushButton { border: 1px solid rgba(255, 255, 255, 0.15); background: rgba(255, 255, 255, 0.05); border-radius: 8px; } QPushButton:hover { background: rgba(255, 255, 255, 0.12); border: 1px solid rgba(255, 255, 255, 0.35); }")

    def on_fav_clicked(self):
        if self.win:
            self.win.toggle_favorite(title=self.title_text, file_path=self.current_video_path or "", post_url=self.post_url or "")
            self.update_fav_btn()

    def start_preview_pipeline(self, post_url, title):
        def _worker():
            try:
                res = self.win.scraper.get(post_url, timeout=12)
                soup = BeautifulSoup(res.text, "html.parser")
                src = soup.select_one("video source")
                video_tag = soup.select_one("video")
                raw_src = (src and src.get("src")) or (video_tag and video_tag.get("src"))

                if not raw_src:
                    matches = re.findall(r'https?://[^\s"\'<>]+\.(?:mp4|webm)', res.text)
                    if matches:
                        raw_src = matches[0]

                if not raw_src:
                    self.preview_error_signal.emit("No video preview found on page.")
                    return

                preview_url = urljoin("https://moewalls.com", raw_src)
                safe_slug = re.sub(r'[^a-zA-Z0-9_\-]', '_', title).strip('_')[:40]
                cached_mp4 = PREVIEWS_DIR / f"{safe_slug}.mp4"

                if cached_mp4.exists() and cached_mp4.stat().st_size > 10240:
                    self.preview_ready_signal.emit(str(cached_mp4))
                    return

                ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
                temp_mp4 = cached_mp4.with_suffix(".tmp.mp4")
                cmd = [
                    ffmpeg_bin, "-y",
                    "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "-i", preview_url,
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-crf", "26",
                    "-pix_fmt", "yuv420p",
                    "-an",
                    "-movflags", "+faststart",
                    str(temp_mp4)
                ]
                creationflags = subprocess.CREATE_NO_WINDOW if IS_WIN else 0
                p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
                if p.returncode == 0 and temp_mp4.exists() and temp_mp4.stat().st_size > 1024:
                    if cached_mp4.exists():
                        try:
                            cached_mp4.unlink()
                        except Exception:
                            pass
                    temp_mp4.replace(cached_mp4)
                    self.preview_ready_signal.emit(str(cached_mp4))
                else:
                    self.preview_error_signal.emit("Transcode failed.")
            except Exception as e:
                self.preview_error_signal.emit(str(e))

        threading.Thread(target=_worker, daemon=True).start()

    def closeEvent(self, event):
        self.is_closed = True
        self.player.stop()
        self.player.setVideoOutput(None)
        super().closeEvent(event)


# ───────────────────────── Local Wallpaper Card Widget ─────────────────────────
class LocalWallpaperCard(QFrame):
    def __init__(self, file_path, parent_win):
        parent_widget = getattr(parent_win, "lib_container", parent_win)
        super().__init__(parent_widget)
        self.setObjectName("glassCard")
        self.file_path = str(file_path)
        self.win = parent_win
        path_obj = Path(file_path)
        self.title_text = path_obj.stem

        self.setFixedWidth(276)
        self.setFixedHeight(265)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Image Label with Click-to-Preview
        self.img_label = QLabel()
        self.img_label.setFixedSize(252, 142)
        self.img_label.setStyleSheet("background-color: #0d0d11; border-radius: 8px;")
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.img_label.setToolTip(f"{self.title_text}\n\nClick thumbnail to preview live video")
        self.img_label.mousePressEvent = lambda e: self.win.on_open_preview(self.title_text, self.file_path, is_local=True, post_url="")

        # Floating Favorite Heart Button (Top-Right of Image)
        self.fav_btn = QPushButton(self.img_label)
        self.fav_btn.setObjectName("favFloatingBtn")
        self.fav_btn.setFixedSize(28, 28)
        self.fav_btn.move(252 - 36, 8)
        self.fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fav_btn.clicked.connect(self.on_fav_clicked)
        self.update_fav_state()

        layout.addWidget(self.img_label)

        # Title Label
        display_title = self.title_text if len(self.title_text) <= 30 else self.title_text[:28] + "…"
        codec = get_video_codec(self.file_path)
        codec_tag = f" [{codec}]" if codec == "AV1" else ""
        self.title_label = QLabel(display_title + codec_tag)
        self.title_label.setToolTip(f"{self.title_text}\nPath: {self.file_path}")
        if codec == "AV1":
            self.title_label.setStyleSheet("font-weight: 600; font-size: 13px; color: #FFBD2E;")
        else:
            self.title_label.setStyleSheet("font-weight: 600; font-size: 13px; color: #FFFFFF;")
        layout.addWidget(self.title_label)

        # Button row: Set Live | Preview (Eye Icon) | Delete (Bin Icon)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.live_btn = QPushButton("Set Live")
        self.live_btn.setObjectName("primaryBtn")
        self.live_btn.setFixedHeight(32)
        self.live_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.live_btn.clicked.connect(lambda: self.win.apply_wallpaper(self.file_path))
        btn_row.addWidget(self.live_btn, 1)

        self.prev_btn = QPushButton()
        self.prev_btn.setObjectName("glassBtn")
        self.prev_btn.setIcon(make_eye_icon("#FFFFFF", 18))
        self.prev_btn.setIconSize(QSize(18, 18))
        self.prev_btn.setToolTip("Preview Video")
        self.prev_btn.setFixedSize(40, 32)
        self.prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.prev_btn.clicked.connect(lambda: self.win.on_open_preview(self.title_text, self.file_path, is_local=True, post_url=""))
        btn_row.addWidget(self.prev_btn)

        self.del_btn = QPushButton()
        self.del_btn.setObjectName("glassBtn")
        self.del_btn.setIcon(make_trash_icon("#EF4444", 18))
        self.del_btn.setIconSize(QSize(18, 18))
        self.del_btn.setToolTip("Delete Wallpaper")
        self.del_btn.setFixedSize(40, 32)
        self.del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.del_btn.clicked.connect(lambda: self.win.delete_local_wallpaper(self.file_path))
        btn_row.addWidget(self.del_btn)

        layout.addLayout(btn_row)

        self.load_thumbnail()

    def set_thumbnail_pixmap(self, pixmap):
        scaled = pixmap.scaled(
            252, 142,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation
        )
        x = (scaled.width() - 252) // 2
        y = (scaled.height() - 142) // 2
        cropped = scaled.copy(x, y, 252, 142)

        rounded = QPixmap(252, 142)
        rounded.fill(Qt.GlobalColor.transparent)
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, 252, 142, 8, 8)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, cropped)
        painter.end()

        self.img_label.setPixmap(rounded)

    def load_thumbnail(self):
        safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', self.title_text)[:40]
        thumb_path = THUMBS_DIR / f"{safe_name}.jpg"

        if thumb_path.exists() and thumb_path.stat().st_size > 500:
            pix = QPixmap(str(thumb_path))
            if not pix.isNull():
                self.set_thumbnail_pixmap(pix)
                return

        def _extract():
            ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
            cmd = [
                ffmpeg_bin, "-y",
                "-ss", "00:00:01",
                "-i", self.file_path,
                "-vframes", "1",
                "-vf", "scale=320:180:force_original_aspect_ratio=increase,crop=320:180",
                str(thumb_path)
            ]
            creationflags = subprocess.CREATE_NO_WINDOW if IS_WIN else 0
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
            if res.returncode == 0 and thumb_path.exists():
                self.win.signals.local_thumb_ready.emit(self.file_path, str(thumb_path))

        threading.Thread(target=_extract, daemon=True).start()

    def update_fav_state(self):
        is_fav = self.win.is_favorite(title=self.title_text, file_path=self.file_path)
        if is_fav:
            self.fav_btn.setIcon(make_heart_icon("#EC4899", 15, filled=True))
            self.fav_btn.setToolTip("Remove from Favorites")
            self.fav_btn.setStyleSheet("QPushButton#favFloatingBtn { background: rgba(0, 0, 0, 0.75); border: 1px solid rgba(236, 72, 153, 0.7); border-radius: 14px; } QPushButton#favFloatingBtn:hover { background: rgba(236, 72, 153, 0.35); border: 1px solid #EC4899; }")
        else:
            self.fav_btn.setIcon(make_heart_icon("#FFFFFF", 15, filled=False))
            self.fav_btn.setToolTip("Add to Favorites")
            self.fav_btn.setStyleSheet("QPushButton#favFloatingBtn { background: rgba(0, 0, 0, 0.60); border: 1px solid rgba(255, 255, 255, 0.25); border-radius: 14px; } QPushButton#favFloatingBtn:hover { background: rgba(255, 255, 255, 0.20); border: 1px solid rgba(255, 255, 255, 0.6); }")

    def on_fav_clicked(self):
        self.win.toggle_favorite(title=self.title_text, file_path=self.file_path)


# ───────────────────────── Online Wallpaper Card Widget ─────────────────────────
class WallpaperCard(QFrame):
    def __init__(self, index, title, img_url, post_url, parent_win, res_text="", has_sound=False):
        parent_widget = getattr(parent_win, "cards_container", parent_win)
        super().__init__(parent_widget)
        self.setObjectName("glassCard")
        self.index = index
        self.title_text = title
        self.img_url = img_url
        self.post_url = post_url
        self.win = parent_win
        self.res_text = res_text
        self.has_sound = has_sound

        self.setFixedWidth(276)
        self.setFixedHeight(265)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Image Label with Click-to-Preview
        self.img_label = QLabel()
        self.img_label.setFixedSize(252, 142)
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.img_label.setToolTip("Click to watch Live Video Preview")
        self.img_label.setStyleSheet("background-color: rgba(255, 255, 255, 0.03); border-radius: 10px;")
        self.img_label.mousePressEvent = lambda e: self.win.open_online_preview(self.post_url, self.title_text)

        # Download Progress Overlay (Over Image Label)
        self.progress_overlay = QFrame(self.img_label)
        self.progress_overlay.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 0.82);
                border-radius: 10px;
            }
        """)
        self.progress_overlay.resize(252, 142)
        ov_layout = QVBoxLayout(self.progress_overlay)
        ov_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ov_layout.setSpacing(4)

        self.progress_pct_lbl = QLabel("0%")
        self.progress_pct_lbl.setStyleSheet("font-size: 26px; font-weight: 800; color: #0A84FF; background: transparent;")
        self.progress_pct_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ov_layout.addWidget(self.progress_pct_lbl)

        self.progress_sub_lbl = QLabel("Downloading…")
        self.progress_sub_lbl.setStyleSheet("font-size: 11px; font-weight: 500; color: #D1D5DB; background: transparent;")
        self.progress_sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ov_layout.addWidget(self.progress_sub_lbl)

        self.progress_overlay.hide()

        # Resolution Tag Badge (Top-Left of Thumbnail)
        badge_x = 8
        if res_text:
            self.res_badge = QLabel(res_text, self.img_label)
            self.res_badge.setStyleSheet("""
                background-color: rgba(0, 0, 0, 0.70);
                color: #E5E7EB;
                font-size: 10px;
                font-weight: 700;
                padding: 2px 6px;
                border-radius: 5px;
                border: 1px solid rgba(255, 255, 255, 0.18);
            """)
            self.res_badge.adjustSize()
            self.res_badge.move(badge_x, 8)
            self.res_badge.show()
            badge_x += self.res_badge.width() + 4

        # Sound Badge (Top-Left next to resolution)
        if has_sound:
            self.sound_badge = QLabel("Audio", self.img_label)
            self.sound_badge.setStyleSheet("""
                background-color: rgba(10, 132, 255, 0.85);
                color: #FFFFFF;
                font-size: 9px;
                font-weight: 700;
                padding: 2px 5px;
                border-radius: 5px;
                border: 1px solid rgba(56, 189, 248, 0.45);
            """)
            self.sound_badge.adjustSize()
            self.sound_badge.move(badge_x, 8)
            self.sound_badge.show()

        # Floating Favorite Heart Button (Top-Right of Image)
        self.fav_btn = QPushButton(self.img_label)
        self.fav_btn.setObjectName("favFloatingBtn")
        self.fav_btn.setFixedSize(28, 28)
        self.fav_btn.move(252 - 36, 8)
        self.fav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fav_btn.clicked.connect(self.on_fav_clicked)
        self.update_fav_state()

        layout.addWidget(self.img_label)

        # Title Label
        display_title = title if len(title) <= 30 else title[:28] + "…"
        self.title_label = QLabel(display_title)
        self.title_label.setToolTip(f"{title}\n\nClick thumbnail to preview live video")
        self.title_label.setStyleSheet("font-weight: 600; font-size: 13px; color: #FFFFFF;")
        layout.addWidget(self.title_label)

        # Button row (Set Live & Download / In Library)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        safe_title = "".join(c for c in title if c.isalnum() or c in " _-").rstrip()
        self.local_path = WALLPAPERS_DIR / f"{safe_title}.mp4"
        is_in_library = self.local_path.is_file() and self.local_path.stat().st_size > 1024 * 1024

        self.live_btn = QPushButton("Set Live")
        self.live_btn.setObjectName("primaryBtn")
        self.live_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if is_in_library:
            self.live_btn.clicked.connect(lambda: self.win.apply_wallpaper(str(self.local_path)))
        else:
            self.live_btn.clicked.connect(lambda: self.win.download_and_apply(self.post_url, self.title_text, auto_apply=True, thumbnail_url=self.img_url))
        btn_row.addWidget(self.live_btn, 3)

        self.dl_btn = QPushButton("In Library" if is_in_library else "Download")
        self.dl_btn.setObjectName("glassBtn")
        self.dl_btn.setToolTip("Already saved in Library" if is_in_library else "Download MP4 to Wallpapers Folder")
        self.dl_btn.setCursor(Qt.CursorShape.PointingHandCursor if not is_in_library else Qt.CursorShape.ArrowCursor)
        self.dl_btn.setEnabled(not is_in_library)
        self.dl_btn.clicked.connect(lambda: self.win.download_and_apply(self.post_url, self.title_text, auto_apply=False, thumbnail_url=self.img_url))
        btn_row.addWidget(self.dl_btn, 2)

        layout.addLayout(btn_row)

    def update_download_progress(self, pct, mb_cur, mb_tot):
        if not self.progress_overlay.isVisible():
            self.progress_overlay.show()
            self.progress_overlay.raise_()
            self.dl_btn.setEnabled(False)
            self.live_btn.setEnabled(False)
        self.progress_pct_lbl.setStyleSheet("font-size: 26px; font-weight: 800; color: #0A84FF; background: transparent;")
        self.progress_pct_lbl.setText(f"{pct}%")
        self.progress_sub_lbl.setText(f"{mb_cur:.1f} / {mb_tot:.1f} MB")

    def set_download_paused(self):
        if self.progress_overlay.isVisible():
            self.progress_pct_lbl.setStyleSheet("font-size: 26px; font-weight: 800; color: #FFBD2E; background: transparent;")
            self.progress_sub_lbl.setText("Paused")
            self.dl_btn.setText("Resume")
            self.dl_btn.setEnabled(True)
            self.live_btn.setEnabled(True)

    def on_download_finished(self, save_path):
        self.progress_overlay.hide()
        self.local_path = Path(save_path)
        self.dl_btn.setText("In Library")
        self.dl_btn.setEnabled(False)
        self.live_btn.setEnabled(True)
        try:
            self.live_btn.clicked.disconnect()
        except Exception:
            pass
        self.live_btn.clicked.connect(lambda: self.win.apply_wallpaper(str(self.local_path)))

    def on_download_failed(self, err_msg):
        self.progress_overlay.hide()
        self.dl_btn.setEnabled(True)
        self.live_btn.setEnabled(True)

    def update_fav_state(self):
        is_fav = self.win.is_favorite(title=self.title_text, post_url=self.post_url)
        if is_fav:
            self.fav_btn.setIcon(make_heart_icon("#EC4899", 15, filled=True))
            self.fav_btn.setToolTip("Remove from Favorites")
            self.fav_btn.setStyleSheet("QPushButton#favFloatingBtn { background: rgba(0, 0, 0, 0.75); border: 1px solid rgba(236, 72, 153, 0.7); border-radius: 14px; } QPushButton#favFloatingBtn:hover { background: rgba(236, 72, 153, 0.35); border: 1px solid #EC4899; }")
        else:
            self.fav_btn.setIcon(make_heart_icon("#FFFFFF", 15, filled=False))
            self.fav_btn.setToolTip("Add to Favorites")
            self.fav_btn.setStyleSheet("QPushButton#favFloatingBtn { background: rgba(0, 0, 0, 0.60); border: 1px solid rgba(255, 255, 255, 0.25); border-radius: 14px; } QPushButton#favFloatingBtn:hover { background: rgba(255, 255, 255, 0.20); border: 1px solid rgba(255, 255, 255, 0.6); }")

    def on_fav_clicked(self):
        self.win.toggle_favorite(title=self.title_text, post_url=self.post_url, img_url=self.img_url)

    def set_thumbnail(self, img_bytes):
        try:
            pixmap = QPixmap()
            pixmap.loadFromData(img_bytes)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    252, 142,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                )
                target = QPixmap(252, 142)
                target.fill(Qt.GlobalColor.transparent)
                p = QPainter(target)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                path = QPainterPath()
                path.addRoundedRect(0, 0, 252, 142, 10, 10)
                p.setClipPath(path)
                p.drawPixmap(0, 0, scaled)
                p.end()
                self.img_label.setPixmap(target)
        except Exception as e:
            print("Thumbnail set error:", e)


# ───────────────────────── Downloads Engine & Manager ─────────────────────────
class DownloadSignals(QObject):
    progress = Signal(str, int, float, float, str)  # (task_id, pct, mb_cur, mb_tot, speed_str)
    status_changed = Signal(str, str)              # (task_id, new_status)
    finished = Signal(str, str, bool)              # (task_id, file_path, auto_apply)
    failed = Signal(str, str)                      # (task_id, error_msg)
    state_updated = Signal()                       # notification that task list changed


class DownloadWorker(threading.Thread):
    def __init__(self, task, scraper, signals):
        super().__init__(daemon=True)
        self.task = task
        self.task_id = task["id"]
        self.scraper = scraper
        self.signals = signals
        self._pause_requested = threading.Event()
        self._cancel_requested = threading.Event()

    def request_pause(self):
        self._pause_requested.set()

    def request_cancel(self):
        self._cancel_requested.set()

    def run(self):
        task_id = self.task_id
        post_url = self.task.get("post_url", "")
        safe_title = self.task.get("safe_title", "")
        part_path = Path(self.task.get("part_path", str(WALLPAPERS_DIR / f"{safe_title}.mp4.part")))
        final_path = Path(self.task.get("file_path", str(WALLPAPERS_DIR / f"{safe_title}.mp4")))

        try:
            # Cache thumbnail image if not exists
            thumb_url = self.task.get("thumbnail_url")
            thumb_file = THUMBS_DIR / f"{safe_title}.jpg"
            if thumb_url and not thumb_file.is_file():
                try:
                    t_res = self.scraper.get(thumb_url, timeout=10)
                    if t_res.status_code == 200 and len(t_res.content) > 500:
                        with open(thumb_file, "wb") as tf:
                            tf.write(t_res.content)
                except Exception:
                    pass

            mp4_url = self.task.get("mp4_url")
            headers = {'Referer': 'https://moewalls.com/'}

            # If post_url provided, fetch page to ensure valid session/cookies on MoeWalls
            if post_url:
                try:
                    res = self.scraper.get(post_url, headers=headers, timeout=15)
                    soup = BeautifulSoup(res.text, 'html.parser')
                    dl_btn = soup.find('a', id='moe-download') or soup.find('a', class_='lcc-wall')
                    if dl_btn and dl_btn.get('data-url'):
                        mp4_url = f"https://go.moewalls.com/download.php?video={dl_btn.get('data-url')}"
                    elif not mp4_url:
                        v_source = soup.select_one('video source')
                        v_tag = soup.select_one('video')
                        raw_src = (v_source and v_source.get('src')) or (v_tag and v_tag.get('src'))
                        if raw_src:
                            mp4_url = urljoin(post_url, raw_src)
                        else:
                            matches = re.findall(r'https?://[^\s"\'<>]+\.mp4', res.text)
                            if matches:
                                mp4_url = matches[0]
                except Exception as e:
                    if not mp4_url:
                        raise e

            if not mp4_url:
                self.task["status"] = "failed"
                self.task["error"] = "No download link found on page"
                self.signals.failed.emit(task_id, "No download link found")
                return

            self.task["mp4_url"] = mp4_url

            # Range request check
            existing_bytes = part_path.stat().st_size if part_path.is_file() else 0
            req_headers = {'Referer': post_url if post_url else 'https://moewalls.com/'}
            if existing_bytes > 0:
                req_headers['Range'] = f"bytes={existing_bytes}-"

            with self.scraper.get(mp4_url, headers=req_headers, stream=True, timeout=30) as r:
                if r.status_code == 206:
                    mode = "ab"
                    downloaded = existing_bytes
                    cr = r.headers.get("Content-Range", "")
                    if "/" in cr:
                        total_size = int(cr.split("/")[-1])
                    else:
                        total_size = downloaded + int(r.headers.get("Content-Length", 0))
                elif r.status_code == 200:
                    mode = "wb"
                    downloaded = 0
                    total_size = int(r.headers.get("Content-Length", 0))
                else:
                    r.raise_for_status()

                self.task["total_bytes"] = total_size
                self.task["downloaded_bytes"] = downloaded
                self.task["status"] = "downloading"
                self.signals.status_changed.emit(task_id, "downloading")

                last_time = time.time()
                bytes_since_last = 0

                with open(part_path, mode) as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if self._pause_requested.is_set():
                            f.flush()
                            self.task["status"] = "paused"
                            self.task["downloaded_bytes"] = downloaded
                            self.task["speed_str"] = "Paused"
                            self.signals.status_changed.emit(task_id, "paused")
                            return

                        if self._cancel_requested.is_set():
                            f.flush()
                            self.task["status"] = "cancelled"
                            if part_path.is_file():
                                part_path.unlink(missing_ok=True)
                            self.signals.status_changed.emit(task_id, "cancelled")
                            return

                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            bytes_since_last += len(chunk)

                            now = time.time()
                            dt = now - last_time
                            if dt >= 0.4:
                                speed_mb = (bytes_since_last / dt) / (1024 * 1024)
                                speed_str = f"{speed_mb:.1f} MB/s" if speed_mb >= 0.1 else f"{(bytes_since_last / dt) / 1024:.0f} KB/s"
                                bytes_since_last = 0
                                last_time = now
                                pct = int((downloaded / total_size) * 100) if total_size > 0 else 0
                                mb_cur = downloaded / (1024 * 1024)
                                mb_tot = total_size / (1024 * 1024)

                                self.task["downloaded_bytes"] = downloaded
                                self.task["total_bytes"] = total_size
                                self.task["speed_str"] = speed_str
                                self.task["pct"] = pct
                                self.signals.progress.emit(task_id, pct, mb_cur, mb_tot, speed_str)

            # Successfully completed stream
            if final_path.is_file():
                final_path.unlink()
            part_path.rename(final_path)

            self.task["status"] = "completed"
            self.task["downloaded_bytes"] = total_size
            self.task["pct"] = 100
            self.task["speed_str"] = ""
            self.signals.finished.emit(task_id, str(final_path), self.task.get("auto_apply", False))

        except Exception as e:
            err_msg = str(e)
            self.task["status"] = "failed"
            self.task["error"] = err_msg
            self.signals.failed.emit(task_id, err_msg)


class DownloadManager(QObject):
    def __init__(self, parent_win):
        super().__init__()
        self.win = parent_win
        self.scraper = parent_win.scraper
        self.signals = DownloadSignals()
        self.tasks = {}
        self.workers = {}
        self._lock = threading.Lock()

        self.signals.progress.connect(self._on_progress)
        self.signals.status_changed.connect(self._on_status_changed)
        self.signals.finished.connect(self._on_finished)
        self.signals.failed.connect(self._on_failed)

        self.load_state()

    def load_state(self):
        if not DOWNLOADS_STATE_FILE.is_file():
            return
        try:
            with open(DOWNLOADS_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for task_id, t in data.items():
                    # Crash recovery: if previous session crashed while downloading, restore to paused
                    if t.get("status") in ("downloading", "queued"):
                        t["status"] = "paused"
                        t["speed_str"] = "Paused"
                        part = Path(t.get("part_path", ""))
                        if part.is_file():
                            t["downloaded_bytes"] = part.stat().st_size
                            if t.get("total_bytes", 0) > 0:
                                t["pct"] = int((t["downloaded_bytes"] / t["total_bytes"]) * 100)
                        else:
                            t["downloaded_bytes"] = 0
                            t["pct"] = 0
                    self.tasks[task_id] = t
            self.save_state()
        except Exception as e:
            print("Error loading downloads state:", e)

    def save_state(self):
        with self._lock:
            try:
                clean_data = {}
                for tid, t in self.tasks.items():
                    clean_data[tid] = {
                        "id": t.get("id"),
                        "post_url": t.get("post_url"),
                        "title": t.get("title"),
                        "safe_title": t.get("safe_title"),
                        "thumbnail_url": t.get("thumbnail_url", ""),
                        "mp4_url": t.get("mp4_url"),
                        "file_path": t.get("file_path"),
                        "part_path": t.get("part_path"),
                        "status": t.get("status"),
                        "downloaded_bytes": t.get("downloaded_bytes", 0),
                        "total_bytes": t.get("total_bytes", 0),
                        "speed_str": t.get("speed_str", ""),
                        "pct": t.get("pct", 0),
                        "auto_apply": t.get("auto_apply", False),
                        "error": t.get("error", "")
                    }
                with open(DOWNLOADS_STATE_FILE, "w", encoding="utf-8") as f:
                    json.dump(clean_data, f, indent=2)
            except Exception as e:
                print("Error saving downloads state:", e)

    def start_or_resume(self, post_url, title, auto_apply=False, thumbnail_url=""):
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-").rstrip()
        final_path = WALLPAPERS_DIR / f"{safe_title}.mp4"
        part_path = WALLPAPERS_DIR / f"{safe_title}.mp4.part"

        if final_path.is_file() and final_path.stat().st_size > 1024 * 1024:
            if auto_apply:
                self.win.apply_wallpaper(str(final_path))
            return

        task_id = safe_title
        if task_id in self.workers and self.workers[task_id].is_alive():
            return

        if task_id in self.tasks:
            task = self.tasks[task_id]
            task["auto_apply"] = auto_apply
            task["status"] = "queued"
            task["speed_str"] = "Resuming…"
            if thumbnail_url:
                task["thumbnail_url"] = thumbnail_url
        else:
            task = {
                "id": task_id,
                "post_url": post_url,
                "title": title,
                "safe_title": safe_title,
                "thumbnail_url": thumbnail_url,
                "mp4_url": None,
                "file_path": str(final_path),
                "part_path": str(part_path),
                "status": "queued",
                "downloaded_bytes": part_path.stat().st_size if part_path.is_file() else 0,
                "total_bytes": 0,
                "speed_str": "Connecting…",
                "pct": 0,
                "auto_apply": auto_apply,
                "error": ""
            }
            self.tasks[task_id] = task

        worker = DownloadWorker(task, self.scraper, self.signals)
        self.workers[task_id] = worker
        worker.start()

        self.save_state()
        self.win.update_sidebar_badge()
        self.signals.state_updated.emit()

    def pause(self, task_id):
        worker = self.workers.get(task_id)
        if worker and worker.is_alive():
            worker.request_pause()
        elif task_id in self.tasks:
            self.tasks[task_id]["status"] = "paused"
            self.tasks[task_id]["speed_str"] = "Paused"
            self.save_state()
            self.signals.state_updated.emit()
            self.win.update_sidebar_badge()

    def resume(self, task_id):
        task = self.tasks.get(task_id)
        if not task:
            return
        if task_id in self.workers and self.workers[task_id].is_alive():
            return

        task["status"] = "queued"
        task["speed_str"] = "Resuming…"
        worker = DownloadWorker(task, self.scraper, self.signals)
        self.workers[task_id] = worker
        worker.start()

        self.save_state()
        self.signals.state_updated.emit()
        self.win.update_sidebar_badge()

    def cancel(self, task_id):
        worker = self.workers.get(task_id)
        if worker and worker.is_alive():
            worker.request_cancel()
        elif task_id in self.tasks:
            part = Path(self.tasks[task_id].get("part_path", ""))
            if part.is_file():
                part.unlink(missing_ok=True)
            del self.tasks[task_id]
            self.save_state()
            self.signals.state_updated.emit()
            self.win.update_sidebar_badge()

    def pause_all(self):
        for tid, w in list(self.workers.items()):
            if w.is_alive():
                w.request_pause()

    def resume_all(self):
        for tid, t in list(self.tasks.items()):
            if t.get("status") in ("paused", "failed"):
                self.resume(tid)

    def clear_completed(self):
        to_del = [tid for tid, t in self.tasks.items() if t.get("status") == "completed"]
        for tid in to_del:
            del self.tasks[tid]
        self.save_state()
        self.signals.state_updated.emit()

    def _on_progress(self, task_id, pct, mb_cur, mb_tot, speed_str):
        if task_id in self.tasks:
            t = self.tasks[task_id]
            t["pct"] = pct
            t["downloaded_bytes"] = int(mb_cur * 1024 * 1024)
            t["total_bytes"] = int(mb_tot * 1024 * 1024)
            t["speed_str"] = speed_str
            post_url = t.get("post_url", "")
            self.win.on_download_progress(post_url, pct, mb_cur, mb_tot)
            if hasattr(self.win, "downloads_active_cards"):
                card = self.win.downloads_active_cards.get(task_id)
                if card:
                    card.update_progress(pct, mb_cur, mb_tot, speed_str)

    def _on_status_changed(self, task_id, new_status):
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = new_status
            if new_status == "paused":
                self.tasks[task_id]["speed_str"] = "Paused"
                post_url = self.tasks[task_id].get("post_url", "")
                self.win.on_download_paused(post_url)
            self.save_state()
            self.win.update_sidebar_badge()
            self.signals.state_updated.emit()

    def _on_finished(self, task_id, file_path, auto_apply):
        if task_id in self.workers:
            del self.workers[task_id]
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = "completed"
            self.tasks[task_id]["pct"] = 100
            self.tasks[task_id]["speed_str"] = ""
            post_url = self.tasks[task_id].get("post_url", "")
            self.win.on_download_finished(post_url, file_path, auto_apply)
        self.save_state()
        self.win.update_sidebar_badge()
        self.signals.state_updated.emit()

    def _on_failed(self, task_id, error_msg):
        if task_id in self.workers:
            del self.workers[task_id]
        if task_id in self.tasks:
            self.tasks[task_id]["status"] = "failed"
            self.tasks[task_id]["error"] = error_msg
            post_url = self.tasks[task_id].get("post_url", "")
            for card in self.win.card_widgets:
                if card.post_url == post_url:
                    card.on_download_failed(error_msg)
                    break
        self.save_state()
        self.win.update_sidebar_badge()
        self.signals.state_updated.emit()


# ───────────────────────── Downloads Page Cards & Thumbnails ─────────────────────────
def render_rounded_thumb(pixmap, w=96, h=54, radius=8):
    if pixmap.isNull():
        return render_thumb_placeholder(w, h, radius)
    scaled = pixmap.scaled(
        w, h,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation
    )
    x = max(0, (scaled.width() - w) // 2)
    y = max(0, (scaled.height() - h) // 2)
    cropped = scaled.copy(x, y, w, h)

    target = QPixmap(w, h)
    target.fill(Qt.GlobalColor.transparent)
    p = QPainter(target)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, w, h, radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, cropped)
    p.end()
    return target


def render_thumb_placeholder(w=96, h=54, radius=8):
    target = QPixmap(w, h)
    target.fill(Qt.GlobalColor.transparent)
    p = QPainter(target)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, w, h, radius, radius)
    p.setClipPath(path)
    p.fillRect(0, 0, w, h, QColor("#121216"))
    p.setBrush(QColor("#2A2A36"))
    p.setPen(Qt.PenStyle.NoPen)
    poly = QPolygonF([
        QPointF(w * 0.44, h * 0.36),
        QPointF(w * 0.58, h * 0.5),
        QPointF(w * 0.44, h * 0.64)
    ])
    p.drawPolygon(poly)
    p.end()
    return target


def load_wallpaper_thumb_pixmap(safe_title, file_path="", w=96, h=54):
    p1 = THUMBS_DIR / f"{safe_title}.jpg"
    if p1.is_file():
        pm = QPixmap(str(p1))
        if not pm.isNull():
            return render_rounded_thumb(pm, w, h)

    if file_path:
        h_md5 = hashlib.md5(str(file_path).encode("utf-8")).hexdigest()
        p2 = THUMBS_DIR / f"{h_md5}.jpg"
        if p2.is_file():
            pm = QPixmap(str(p2))
            if not pm.isNull():
                return render_rounded_thumb(pm, w, h)

    return None


class ActiveDownloadCard(QFrame):
    def __init__(self, task, manager, parent=None):
        super().__init__(parent)
        self.setObjectName("downloadItemCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.task_id = task["id"]
        self.safe_title = task.get("safe_title", task["id"])
        self.file_path = task.get("file_path", "")
        self.thumbnail_url = task.get("thumbnail_url", "")
        self.manager = manager
        self.setFixedHeight(84)
        self.setMaximumWidth(880)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 14, 12)
        layout.setSpacing(14)

        # 16:9 Thumbnail
        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(96, 54)
        self.thumb_lbl.setStyleSheet("border-radius: 8px; background-color: #121216;")
        self.thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.thumb_lbl)

        # Info & Progress Column
        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setSpacing(5)

        # Top line: Title & Status Badge
        top_line = QHBoxLayout()
        top_line.setSpacing(8)
        self.title_lbl = QLabel(task.get("title", "Wallpaper"))
        self.title_lbl.setStyleSheet("font-weight: 700; font-size: 13px; color: #FFFFFF;")
        top_line.addWidget(self.title_lbl, 1)

        self.status_badge = QLabel()
        top_line.addWidget(self.status_badge)
        info_col.addLayout(top_line)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(task.get("pct", 0))
        info_col.addWidget(self.progress_bar)

        # Bottom stats
        self.stats_lbl = QLabel()
        self.stats_lbl.setStyleSheet("font-size: 11px; color: #9CA3AF;")
        info_col.addWidget(self.stats_lbl)

        layout.addLayout(info_col, 1)

        # Action Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)

        self.btn_toggle = QPushButton()
        self.btn_toggle.setObjectName("glassBtn")
        self.btn_toggle.setFixedSize(36, 36)
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.clicked.connect(self.on_toggle_clicked)
        btn_box.addWidget(self.btn_toggle)

        self.btn_cancel = QPushButton()
        self.btn_cancel.setObjectName("glassBtn")
        self.btn_cancel.setFixedSize(36, 36)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setIcon(make_cancel_icon("#EF4444", 16))
        self.btn_cancel.setIconSize(QSize(16, 16))
        self.btn_cancel.setToolTip("Cancel and remove download")
        self.btn_cancel.clicked.connect(lambda: self.manager.cancel(self.task_id))
        btn_box.addWidget(self.btn_cancel)

        layout.addLayout(btn_box)

        self.load_thumbnail()
        self.sync_state(task)

    def load_thumbnail(self):
        pm = load_wallpaper_thumb_pixmap(self.safe_title, file_path=self.file_path, w=96, h=54)
        if pm:
            self.thumb_lbl.setPixmap(pm)
        else:
            self.thumb_lbl.setPixmap(render_thumb_placeholder(96, 54))

    def sync_state(self, task):
        status = task.get("status", "queued")
        pct = task.get("pct", 0)
        self.progress_bar.setValue(pct)

        cur_mb = task.get("downloaded_bytes", 0) / (1024 * 1024)
        tot_mb = task.get("total_bytes", 0) / (1024 * 1024)
        speed = task.get("speed_str", "")

        if status == "downloading":
            self.status_badge.setText("Downloading")
            self.status_badge.setStyleSheet("color: #0A84FF; background-color: rgba(10, 132, 255, 0.15); border: 1px solid rgba(10, 132, 255, 0.25); border-radius: 4px; padding: 2px 8px; font-weight: 700; font-size: 11px;")
            self.btn_toggle.setIcon(make_pause_icon("#FFFFFF", 16))
            self.btn_toggle.setIconSize(QSize(16, 16))
            self.btn_toggle.setToolTip("Pause Download")
            self.stats_lbl.setText(f"{cur_mb:.1f} / {tot_mb:.1f} MB ({pct}%) • {speed}")
        elif status == "paused":
            self.status_badge.setText("Paused")
            self.status_badge.setStyleSheet("color: #FFBD2E; background-color: rgba(255, 189, 46, 0.15); border: 1px solid rgba(255, 189, 46, 0.25); border-radius: 4px; padding: 2px 8px; font-weight: 700; font-size: 11px;")
            self.btn_toggle.setIcon(make_play_icon("#FFFFFF", 16))
            self.btn_toggle.setIconSize(QSize(16, 16))
            self.btn_toggle.setToolTip("Resume Download")
            self.stats_lbl.setText(f"Paused • {cur_mb:.1f} / {tot_mb:.1f} MB ({pct}%)")
        elif status == "failed":
            self.status_badge.setText("Failed")
            self.status_badge.setStyleSheet("color: #EF4444; background-color: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 4px; padding: 2px 8px; font-weight: 700; font-size: 11px;")
            self.btn_toggle.setIcon(make_play_icon("#FFFFFF", 16))
            self.btn_toggle.setIconSize(QSize(16, 16))
            self.btn_toggle.setToolTip("Retry Download")
            err = task.get("error", "Error")
            self.stats_lbl.setText(f"Failed: {err}")
        else:
            self.status_badge.setText("Queued")
            self.status_badge.setStyleSheet("color: #9CA3AF; background-color: rgba(156, 163, 175, 0.15); border: 1px solid rgba(156, 163, 175, 0.25); border-radius: 4px; padding: 2px 8px; font-weight: 700; font-size: 11px;")
            self.btn_toggle.setIcon(make_pause_icon("#FFFFFF", 16))
            self.btn_toggle.setIconSize(QSize(16, 16))
            self.stats_lbl.setText("Connecting to server…")

    def update_progress(self, pct, mb_cur, mb_tot, speed_str):
        self.progress_bar.setValue(pct)
        self.stats_lbl.setText(f"{mb_cur:.1f} / {mb_tot:.1f} MB ({pct}%) • {speed_str}")

    def on_toggle_clicked(self):
        task = self.manager.tasks.get(self.task_id)
        if not task:
            return
        if task.get("status") == "downloading":
            self.manager.pause(self.task_id)
        else:
            self.manager.resume(self.task_id)


class CompletedDownloadCard(QFrame):
    def __init__(self, task, manager, parent_win, parent=None):
        super().__init__(parent)
        self.setObjectName("downloadItemCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.task_id = task["id"]
        self.safe_title = task.get("safe_title", task["id"])
        self.manager = manager
        self.win = parent_win
        self.file_path = task.get("file_path", "")
        self.title_text = task.get("title", Path(self.file_path).stem)
        self.setFixedHeight(80)
        self.setMaximumWidth(880)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 14, 10)
        layout.setSpacing(14)

        # 16:9 Thumbnail
        self.thumb_lbl = QLabel()
        self.thumb_lbl.setFixedSize(96, 54)
        self.thumb_lbl.setStyleSheet("border-radius: 8px; background-color: #121216;")
        self.thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.thumb_lbl.setToolTip("Click to watch Live Video Preview")
        self.thumb_lbl.mousePressEvent = lambda e: self.win.on_open_preview(self.title_text, self.file_path, is_local=True, post_url="")
        layout.addWidget(self.thumb_lbl)

        # Info Column
        info_col = QVBoxLayout()
        info_col.setContentsMargins(0, 0, 0, 0)
        info_col.setSpacing(4)

        self.title_lbl = QLabel(self.title_text)
        self.title_lbl.setStyleSheet("font-weight: 700; font-size: 13px; color: #FFFFFF;")
        info_col.addWidget(self.title_lbl)

        p = Path(self.file_path)
        sz_mb = (p.stat().st_size / (1024 * 1024)) if p.is_file() else (task.get("total_bytes", 0) / (1024 * 1024))
        sub_text = f"{sz_mb:.1f} MB • Ready in Library"
        self.sub_lbl = QLabel(sub_text)
        self.sub_lbl.setStyleSheet("font-size: 11px; color: #10B981; font-weight: 500;")
        info_col.addWidget(self.sub_lbl)

        layout.addLayout(info_col, 1)

        # Action Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)

        # Set Live Button
        self.btn_set_live = QPushButton("Set Live")
        self.btn_set_live.setObjectName("primaryBtn")
        self.btn_set_live.setFixedHeight(32)
        self.btn_set_live.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_set_live.clicked.connect(lambda: self.win.apply_wallpaper(self.file_path))
        btn_box.addWidget(self.btn_set_live)

        # Preview Button
        self.btn_prev = QPushButton()
        self.btn_prev.setObjectName("glassBtn")
        self.btn_prev.setFixedSize(36, 32)
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_prev.setIcon(make_eye_icon("#FFFFFF", 16))
        self.btn_prev.setIconSize(QSize(16, 16))
        self.btn_prev.setToolTip("Preview Video")
        self.btn_prev.clicked.connect(lambda: self.win.on_open_preview(self.title_text, self.file_path, is_local=True, post_url=""))
        btn_box.addWidget(self.btn_prev)

        # Show in Folder Button
        self.btn_folder = QPushButton()
        self.btn_folder.setObjectName("glassBtn")
        self.btn_folder.setFixedSize(36, 32)
        self.btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_folder.setIcon(make_folder_icon("#9CA3AF", 16))
        self.btn_folder.setIconSize(QSize(16, 16))
        self.btn_folder.setToolTip("Show in Folder")
        self.btn_folder.clicked.connect(self.on_show_in_folder)
        btn_box.addWidget(self.btn_folder)

        # Delete Button
        self.btn_del = QPushButton()
        self.btn_del.setObjectName("glassBtn")
        self.btn_del.setFixedSize(36, 32)
        self.btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_del.setIcon(make_trash_icon("#EF4444", 16))
        self.btn_del.setIconSize(QSize(16, 16))
        self.btn_del.setToolTip("Delete Wallpaper")
        self.btn_del.clicked.connect(lambda: self.win.delete_local_wallpaper(self.file_path))
        btn_box.addWidget(self.btn_del)

        layout.addLayout(btn_box)

        self.load_thumbnail()

    def load_thumbnail(self):
        pm = load_wallpaper_thumb_pixmap(self.safe_title, file_path=self.file_path, w=96, h=54)
        if pm:
            self.thumb_lbl.setPixmap(pm)
            return

        self.thumb_lbl.setPixmap(render_thumb_placeholder(96, 54))

        thumb_path = THUMBS_DIR / f"{self.safe_title}.jpg"
        def _extract():
            if not os.path.isfile(self.file_path):
                return
            ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
            cmd = [
                ffmpeg_bin, "-y",
                "-ss", "00:00:01",
                "-i", self.file_path,
                "-vframes", "1",
                "-vf", "scale=192:108:force_original_aspect_ratio=increase,crop=192:108",
                str(thumb_path)
            ]
            creationflags = subprocess.CREATE_NO_WINDOW if IS_WIN else 0
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
            if res.returncode == 0 and thumb_path.exists():
                QTimer.singleShot(0, lambda: self._on_thumb_extracted(str(thumb_path)))

        threading.Thread(target=_extract, daemon=True).start()

    def _on_thumb_extracted(self, path):
        pm = QPixmap(path)
        if not pm.isNull():
            self.thumb_lbl.setPixmap(render_rounded_thumb(pm, 96, 54))

    def on_show_in_folder(self):
        try:
            p = os.path.abspath(self.file_path)
            if os.path.isfile(p):
                subprocess.Popen(f'explorer /select,"{p}"')
            else:
                subprocess.Popen(f'explorer "{str(WALLPAPERS_DIR)}"')
        except Exception as e:
            print("Folder open error:", e)


# ───────── Hardware & System Monitor Infrastructure ─────────
def detect_processor_name():
    raw_name = ""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        raw_name = str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        winreg.CloseKey(key)
    except Exception:
        pass

    if not raw_name:
        try:
            import platform
            raw_name = platform.processor() or "CPU"
        except Exception:
            raw_name = "CPU"

    full_name = raw_name
    s = re.sub(r'\(R\)|\(TM\)|CPU|@.*|Processor|with.*Graphics|\d+-Core', '', raw_name, flags=re.IGNORECASE)
    s = re.sub(r'\s+', ' ', s).strip()

    # AMD Threadripper
    if "threadripper" in raw_name.lower():
        return "Threadripper", full_name

    # AMD Ryzen (e.g. Ryzen 5 5600X, Ryzen 7 7800X3D, Ryzen 9)
    m_ryzen = re.search(r'Ryzen\s*(\d+)?(?:\s+([A-Za-z0-9]+))?', s, re.IGNORECASE)
    if m_ryzen:
        tier = m_ryzen.group(1) or ""
        model = m_ryzen.group(2) or ""
        parts = ["Ryzen"]
        if tier:
            parts.append(tier)
        if model and model.lower() not in ("series", "processor", "with", "radeon"):
            parts.append(model)
        short = " ".join(parts)
        if len(short) > 13:
            short = f"Ryzen {tier}" if tier else short[:13]
        return short, full_name

    # Intel Core i3 / i5 / i7 / i9 (e.g. i7-8665U, i5-12400F)
    m_intel_model = re.search(r'(i[3579]-[\w]+)', s, re.IGNORECASE)
    if m_intel_model:
        return m_intel_model.group(1), full_name

    # Intel Core Ultra (e.g. Ultra 7 155H)
    m_ultra = re.search(r'(Ultra\s*\d+[\w]*)', s, re.IGNORECASE)
    if m_ultra:
        return m_ultra.group(1), full_name

    # Intel Core i5 / i7 without hyphen
    m_intel_gen = re.search(r'Core\s+(i[3579])', s, re.IGNORECASE)
    if m_intel_gen:
        return m_intel_gen.group(1), full_name

    # Other processors (Athlon, Xeon, Celeron, Pentium, Snapdragon)
    for kw in ("Athlon", "EPYC", "Xeon", "Celeron", "Pentium", "Snapdragon"):
        if kw.lower() in s.lower():
            m_kw = re.search(rf'({kw}(?:\s+[\w]+)?)', s, re.IGNORECASE)
            if m_kw:
                return m_kw.group(1)[:13], full_name

    words = s.split()
    short = " ".join(words[:2]) if len(words) >= 2 else (words[0] if words else "CPU")
    return short[:13], full_name


def detect_primary_gpu_name():
    try:
        class DISPLAY_DEVICEW(ctypes.Structure):
            _fields_ = [
                ('cb', wintypes.DWORD),
                ('DeviceName', wintypes.WCHAR * 32),
                ('DeviceString', wintypes.WCHAR * 128),
                ('StateFlags', wintypes.DWORD),
                ('DeviceID', wintypes.WCHAR * 128),
                ('DeviceKey', wintypes.WCHAR * 128)
            ]

        dd = DISPLAY_DEVICEW()
        dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        i = 0
        best_name = ""
        while ctypes.windll.user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
            if dd.StateFlags & 0x1:
                raw = dd.DeviceString
                if "Virtual" not in raw and "Basic" not in raw:
                    best_name = raw
                    if dd.StateFlags & 0x4:
                        break
            i += 1

        if not best_name:
            return "GPU", "Graphics Adapter"

        full_name = best_name
        short_name = re.sub(r'\(R\)|\(TM\)', '', full_name, flags=re.I)
        short_name = re.sub(r'\bNVIDIA\b|\bGeForce\b|\bAMD\b|\bRadeon\b|\bGraphics\b|\bLaptop GPU\b', '', short_name, flags=re.I)
        short_name = re.sub(r'\bIntel\b', '', short_name, flags=re.I)
        short_name = ' '.join(short_name.split())
        if not short_name:
            short_name = full_name[:12]
        elif len(short_name) > 14:
            short_name = short_name[:12] + "…"

        return short_name, full_name
    except Exception:
        return "GPU", "Graphics Adapter"


class WindowsGpuMonitor:
    def __init__(self):
        self.available = False
        self.hQuery = None
        self.hCounter = None
        try:
            self.pdh = ctypes.windll.pdh
            h_q = wintypes.HANDLE()
            if self.pdh.PdhOpenQueryW(None, 0, ctypes.byref(h_q)) == 0:
                self.hQuery = h_q
                h_c = wintypes.HANDLE()
                st = self.pdh.PdhAddCounterW(self.hQuery, '\\GPU Engine(*)\\Utilization Percentage', 0, ctypes.byref(h_c))
                if st == 0:
                    self.hCounter = h_c
                    self.pdh.PdhCollectQueryData(self.hQuery)
                    self.available = True
                else:
                    self.pdh.PdhCloseQuery(self.hQuery)
                    self.hQuery = None
        except Exception:
            self.available = False

    def get_utilization(self, target_pids=None):
        if not self.available or not self.hQuery:
            return 0.0
        try:
            class PDH_FMT_COUNTERVALUE(ctypes.Structure):
                _fields_ = [
                    ('CStatus', wintypes.DWORD),
                    ('doubleValue', ctypes.c_double)
                ]

            class PDH_FMT_COUNTERVALUE_ITEM_W(ctypes.Structure):
                _fields_ = [
                    ('szName', wintypes.LPWSTR),
                    ('FmtValue', PDH_FMT_COUNTERVALUE)
                ]

            if self.pdh.PdhCollectQueryData(self.hQuery) != 0:
                return 0.0

            dwBufferSize = wintypes.DWORD(0)
            dwItemCount = wintypes.DWORD(0)
            self.pdh.PdhGetFormattedCounterArrayW(self.hCounter, 0x00000200, ctypes.byref(dwBufferSize), ctypes.byref(dwItemCount), None)

            if dwBufferSize.value > 0:
                buf = ctypes.create_string_buffer(dwBufferSize.value)
                if self.pdh.PdhGetFormattedCounterArrayW(self.hCounter, 0x00000200, ctypes.byref(dwBufferSize), ctypes.byref(dwItemCount), buf) == 0:
                    pItem = ctypes.cast(buf, ctypes.POINTER(PDH_FMT_COUNTERVALUE_ITEM_W))
                    total_gpu = 0.0
                    for i in range(dwItemCount.value):
                        if pItem[i].FmtValue.CStatus == 0:
                            if target_pids is not None:
                                name = pItem[i].szName or ""
                                if any(f"pid_{p}_" in name for p in target_pids):
                                    total_gpu += pItem[i].FmtValue.doubleValue
                            else:
                                total_gpu += pItem[i].FmtValue.doubleValue
                    return min(100.0, max(0.0, total_gpu))
        except Exception:
            pass
        return 0.0

    def close(self):
        if self.hQuery:
            try:
                self.pdh.PdhCloseQuery(self.hQuery)
            except Exception:
                pass
            self.hQuery = None


class SidebarMonitorCard(QFrame):
    def __init__(self, cpu_name="CPU", full_cpu_name="", gpu_name="GPU", full_gpu_name="", parent=None):
        super().__init__(parent)
        self.setObjectName("glassCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            QFrame#glassCard {
                background-color: rgba(255, 255, 255, 0.035);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # 1. CPU Row (Custom CPU model name, e.g. i7-8665U, Ryzen 5)
        r_cpu = QHBoxLayout()
        self.lbl_cpu = QLabel(cpu_name)
        self.lbl_cpu.setToolTip(f"{full_cpu_name or cpu_name} utilization by moeDesk")
        self.lbl_cpu.setStyleSheet("font-weight: 700; font-size: 11px; color: #E5E7EB;")
        r_cpu.addWidget(self.lbl_cpu)
        self.val_cpu = QLabel("0.0%")
        self.val_cpu.setStyleSheet("font-weight: 700; font-size: 11px; color: #0A84FF;")
        r_cpu.addStretch(1)
        r_cpu.addWidget(self.val_cpu)
        layout.addLayout(r_cpu)

        self.bar_cpu = QProgressBar()
        self.bar_cpu.setFixedHeight(4)
        self.bar_cpu.setTextVisible(False)
        self.bar_cpu.setRange(0, 100)
        self.bar_cpu.setStyleSheet("QProgressBar { background: rgba(255, 255, 255, 0.08); border-radius: 2px; } QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0A84FF, stop:1 #00E5FF); border-radius: 2px; }")
        layout.addWidget(self.bar_cpu)

        # 2. RAM Row
        r_ram = QHBoxLayout()
        lbl_ram = QLabel("RAM")
        lbl_ram.setToolTip("RAM memory consumed by moeDesk")
        lbl_ram.setStyleSheet("font-weight: 700; font-size: 11px; color: #E5E7EB;")
        r_ram.addWidget(lbl_ram)
        self.val_ram = QLabel("0 MB")
        self.val_ram.setStyleSheet("font-weight: 700; font-size: 11px; color: #A855F7;")
        r_ram.addStretch(1)
        r_ram.addWidget(self.val_ram)
        layout.addLayout(r_ram)

        self.bar_ram = QProgressBar()
        self.bar_ram.setFixedHeight(4)
        self.bar_ram.setTextVisible(False)
        self.bar_ram.setRange(0, 100)
        self.bar_ram.setStyleSheet("QProgressBar { background: rgba(255, 255, 255, 0.08); border-radius: 2px; } QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6366F1, stop:1 #A855F7); border-radius: 2px; }")
        layout.addWidget(self.bar_ram)

        # 3. GPU Row (Custom GPU name, e.g. UHD 620)
        r_gpu = QHBoxLayout()
        self.lbl_gpu = QLabel(gpu_name)
        self.lbl_gpu.setToolTip(f"{full_gpu_name or gpu_name} utilization by moeDesk")
        self.lbl_gpu.setStyleSheet("font-weight: 700; font-size: 11px; color: #E5E7EB;")
        r_gpu.addWidget(self.lbl_gpu)
        self.val_gpu = QLabel("0.0%")
        self.val_gpu.setStyleSheet("font-weight: 700; font-size: 11px; color: #10B981;")
        r_gpu.addStretch(1)
        r_gpu.addWidget(self.val_gpu)
        layout.addLayout(r_gpu)

        self.bar_gpu = QProgressBar()
        self.bar_gpu.setFixedHeight(4)
        self.bar_gpu.setTextVisible(False)
        self.bar_gpu.setRange(0, 100)
        self.bar_gpu.setStyleSheet("QProgressBar { background: rgba(255, 255, 255, 0.08); border-radius: 2px; } QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #34D399); border-radius: 2px; }")
        layout.addWidget(self.bar_gpu)

        # 4. Storage Row (Total downloaded wallpaper size)
        r_st = QHBoxLayout()
        r_st.setContentsMargins(0, 3, 0, 0)
        lbl_st = QLabel("Storage")
        lbl_st.setStyleSheet("font-weight: 700; font-size: 11px; color: #E5E7EB;")
        r_st.addWidget(lbl_st)
        self.val_st = QLabel("0 MB")
        self.val_st.setStyleSheet("font-weight: 700; font-size: 11px; color: #FBBF24;")
        r_st.addStretch(1)
        r_st.addWidget(self.val_st)
        layout.addLayout(r_st)

        self.bar_st = QProgressBar()
        self.bar_st.setFixedHeight(4)
        self.bar_st.setTextVisible(False)
        self.bar_st.setRange(0, 100)
        self.bar_st.setStyleSheet("QProgressBar { background: rgba(255, 255, 255, 0.08); border-radius: 2px; } QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #F59E0B, stop:1 #FBBF24); border-radius: 2px; }")
        layout.addWidget(self.bar_st)

        self.lbl_st_count = QLabel("0 Wallpapers in Library")
        self.lbl_st_count.setStyleSheet("font-size: 9.5px; color: #9CA3AF;")
        layout.addWidget(self.lbl_st_count)

    def update_metrics(self, cpu_pct, ram_str, ram_bar_val, gpu_pct, storage_str, storage_pct, count_str):
        self.val_cpu.setText(f"{cpu_pct:.1f}%")
        self.val_cpu.setToolTip(f"moeDesk CPU Usage: {cpu_pct:.1f}%")
        cpu_bar = min(100, max(2 if cpu_pct > 0.05 else 0, int(cpu_pct)))
        self.bar_cpu.setValue(cpu_bar)

        self.val_ram.setText(ram_str)
        self.val_ram.setToolTip(f"moeDesk RAM Usage: {ram_str}")
        self.bar_ram.setValue(min(100, max(2 if ram_str != "0 MB" else 0, int(ram_bar_val))))

        self.val_gpu.setText(f"{gpu_pct:.1f}%")
        self.val_gpu.setToolTip(f"moeDesk GPU Utilization: {gpu_pct:.1f}%")
        gpu_bar = min(100, max(2 if gpu_pct > 0.05 else 0, int(gpu_pct)))
        self.bar_gpu.setValue(gpu_bar)

        self.val_st.setText(storage_str)
        self.bar_st.setValue(min(100, max(0, int(storage_pct))))
        self.lbl_st_count.setText(count_str)


# ───────────────────────── Main Unified Window ─────────────────────────
class MainWindow(QWidget):
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.engine = Engine(cfg, lambda m: self.say(f"Playback error: {m}"))
        self.scraper = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
        )
        self.cpu_short_name, self.cpu_full_name = detect_processor_name()
        self.gpu_short_name, self.gpu_full_name = detect_primary_gpu_name()
        self.gpu_monitor = WindowsGpuMonitor()
        self.main_proc = psutil.Process(os.getpid())
        try:
            self.main_proc.cpu_percent(None)  # Prime baseline
        except Exception:
            pass
        self.tracked_child_procs = {}
        self.smoothed_cpu = 0.0

        self.download_manager = DownloadManager(self)
        self.download_manager.signals.state_updated.connect(self._on_download_state_updated)

        self.signals = ScraperSignals()
        self.signals.results_ready.connect(self.on_results_ready)
        self.signals.card_thumbnail_ready.connect(self.on_card_thumbnail_ready)
        self.signals.status_msg.connect(self.say)
        self.signals.download_progress.connect(self.on_download_progress)
        self.signals.download_finished.connect(self.on_download_finished)
        self.signals.open_preview_signal.connect(self.on_open_preview)
        self.signals.local_thumb_ready.connect(self.on_local_thumb_ready)

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(make_app_icon())
        self.setAcceptDrops(True)
        self.setStyleSheet(MACOS_LIQUID_GLASS_QSS)
        self.resize(1120, 750)
        self.setMinimumSize(960, 650)
        self._told_tray = False
        self.card_widgets = []
        self.current_page = 1
        self.current_query = ""
        self.current_category = ""
        self.is_loading_more = False
        self.lib_current_section = "all"

        self.init_ui()
        self.init_tray()

        # Fast watchdog for auto-pause and fullscreen detection (responsive within 300ms)
        self.fast_timer = QTimer(self)
        self.fast_timer.timeout.connect(self.engine_fast_tick)
        self.fast_timer.start(300)

        # Hardware & Storage metrics poll timer (every 2 seconds)
        self.metrics_timer = QTimer(self)
        self.metrics_timer.timeout.connect(self.update_system_metrics)
        self.metrics_timer.start(2000)

        # Multi-monitor change handler
        self.relayout_timer = QTimer(self)
        self.relayout_timer.setSingleShot(True)
        self.relayout_timer.timeout.connect(self.engine.relayout)
        app = QGuiApplication.instance()
        for sig in (app.screenAdded, app.screenRemoved, app.primaryScreenChanged):
            sig.connect(lambda *_: self.relayout_timer.start(1000))
        for s_ in QGuiApplication.screens():
            s_.geometryChanged.connect(lambda *_: self.relayout_timer.start(1000))

        # Initial fetch of latest wallpapers
        self.start_online_search(query="")
        QTimer.singleShot(300, self.update_system_metrics)

    def init_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ───────── Left Sidebar (macOS Liquid Glass) ─────────
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(16, 18, 16, 16)
        side_layout.setSpacing(10)

        # App Title & macOS Dot Accents
        top_brand = QVBoxLayout()
        top_brand.setSpacing(4)
        dots_layout = QHBoxLayout()
        dots_layout.setSpacing(6)
        for color in ("#FF5F56", "#FFBD2E", "#27C93F"):
            dot = QLabel()
            dot.setFixedSize(11, 11)
            dot.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
            dots_layout.addWidget(dot)
        dots_layout.addStretch(1)
        top_brand.addLayout(dots_layout)

        title_lbl = QLabel(APP_NAME)
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: #FFFFFF; margin-top: 6px;")
        top_brand.addWidget(title_lbl)

        tagline_lbl = QLabel("best free lightweight experience")
        tagline_lbl.setStyleSheet("font-size: 11px; font-weight: 400; color: #9CA3AF; margin-bottom: 6px;")
        top_brand.addWidget(tagline_lbl)

        side_layout.addLayout(top_brand)
        side_layout.addSpacing(10)

        # Navigation Buttons
        self.nav_buttons = []
        self.btn_discover = QPushButton("Discover")
        self.btn_library = QPushButton("Library")
        self.btn_downloads = QPushButton("Downloads")
        self.btn_settings = QPushButton("Settings")

        for idx, btn in enumerate([self.btn_discover, self.btn_library, self.btn_downloads, self.btn_settings]):
            btn.setObjectName("navBtn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, i=idx: self.switch_page(i))
            side_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        side_layout.addStretch(1)

        # Hardware & Storage Monitor Card (Directly above Current Wallpaper)
        self.system_monitor_card = SidebarMonitorCard(
            self.cpu_short_name, self.cpu_full_name,
            self.gpu_short_name, self.gpu_full_name
        )
        side_layout.addWidget(self.system_monitor_card)
        side_layout.addSpacing(6)

        # Now Playing Card (Bottom Sidebar)
        self.now_playing_box = QFrame()
        self.now_playing_box.setObjectName("glassCard")
        np_layout = QVBoxLayout(self.now_playing_box)
        np_layout.setContentsMargins(12, 12, 12, 12)
        np_layout.setSpacing(8)

        np_header = QHBoxLayout()
        self.np_dot = QLabel()
        self.np_dot.setFixedSize(8, 8)
        self.np_dot.setStyleSheet("background-color: #6B7280; border-radius: 4px;")
        np_header.addWidget(self.np_dot)

        np_title = QLabel("CURRENT WALLPAPER")
        np_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #9CA3AF; letter-spacing: 0.5px;")
        np_header.addWidget(np_title)
        np_header.addStretch(1)

        self.np_status_badge = QLabel("STOPPED")
        self.np_status_badge.setStyleSheet("font-size: 9px; font-weight: 700; color: #9CA3AF; background: rgba(255, 255, 255, 0.08); border-radius: 4px; padding: 1px 6px;")
        np_header.addWidget(self.np_status_badge)
        np_layout.addLayout(np_header)

        self.np_name_lbl = QLabel("None (Stopped)")
        self.np_name_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #FFFFFF;")
        self.np_name_lbl.setWordWrap(True)
        np_layout.addWidget(self.np_name_lbl)

        np_ctrls = QHBoxLayout()
        self.btn_sidebar_pause = QPushButton("Pause")
        self.btn_sidebar_pause.setObjectName("glassBtn")
        self.btn_sidebar_pause.setFixedHeight(28)
        self.btn_sidebar_pause.clicked.connect(self.toggle_pause)
        np_ctrls.addWidget(self.btn_sidebar_pause)

        self.btn_sidebar_stop = QPushButton("Stop")
        self.btn_sidebar_stop.setObjectName("glassBtn")
        self.btn_sidebar_stop.setFixedHeight(28)
        self.btn_sidebar_stop.clicked.connect(self.stop_wallpaper)
        np_ctrls.addWidget(self.btn_sidebar_stop)
        np_layout.addLayout(np_ctrls)

        side_layout.addWidget(self.now_playing_box)
        root.addWidget(sidebar)

        # ───────── Main Content Area (QStackedWidget) ─────────
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background-color: #000000;")

        # Page 0: Discover (Online MoeWalls Store)
        self.page_discover = self.create_discover_page()
        self.stack.addWidget(self.page_discover)

        # Page 1: My Library
        self.page_library = self.create_library_page()
        self.stack.addWidget(self.page_library)

        # Page 2: Downloads Manager
        self.page_downloads = self.create_downloads_page()
        self.stack.addWidget(self.page_downloads)

        # Page 3: Settings & Engine Controls
        self.page_settings = self.create_settings_page()
        self.stack.addWidget(self.page_settings)

        root.addWidget(self.stack, 1)

        # Update sidebar badge count
        self.update_sidebar_badge()

        # Set default active navigation tab
        self.switch_page(0)

    # ───────── Page 0: Discover Online (MoeWalls) ─────────
    def create_discover_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(14)

        # Top Bar: Search Input & Button
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("glassSearch")
        self.search_input.setPlaceholderText("Search online wallpapers (e.g., anime girl, cyberpunk, 4K, cars, nature)...")
        self.search_input.returnPressed.connect(self.on_search_trigger)
        top_bar.addWidget(self.search_input, 1)

        search_btn = QPushButton("Search")
        search_btn.setObjectName("primaryBtn")
        search_btn.setFixedWidth(90)
        search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        search_btn.clicked.connect(self.on_search_trigger)
        top_bar.addWidget(search_btn)
        layout.addLayout(top_bar)

        # Quick Filter Categories & Dropdowns Strip
        cat_filter_row = QHBoxLayout()
        cat_filter_row.setContentsMargins(0, 0, 0, 0)
        cat_filter_row.setSpacing(10)

        # 1. Quick Filter Categories (Horizontal Scrollable Strip)
        chips_scroll = QScrollArea()
        chips_scroll.setWidgetResizable(True)
        chips_scroll.setFixedHeight(38)
        chips_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        chips_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        chips_scroll.setStyleSheet("background: transparent; border: none;")

        chips_widget = QWidget()
        chips_widget.setStyleSheet("background: transparent;")
        chips_layout = QHBoxLayout(chips_widget)
        chips_layout.setContentsMargins(0, 0, 0, 0)
        chips_layout.setSpacing(8)

        self.category_buttons = []
        for name, slug in CATEGORIES:
            cbtn = QPushButton(name)
            cbtn.setObjectName("chipBtnActive" if slug == "" else "chipBtn")
            cbtn.setCursor(Qt.CursorShape.PointingHandCursor)
            cbtn.clicked.connect(lambda checked=False, s=slug, b=cbtn: self.on_category_clicked(s, b))
            chips_layout.addWidget(cbtn)
            self.category_buttons.append((cbtn, slug))
        chips_layout.addStretch(1)

        chips_scroll.setWidget(chips_widget)
        cat_filter_row.addWidget(chips_scroll, 1)

        # 2. Right Side Controls (Ordered Left-to-Right):
        # A) 1st: Popularity / Sort Dropdown
        self.cb_sort = QComboBox()
        self.cb_sort.setObjectName("filterCombo")
        self.cb_sort.setFixedHeight(34)
        self.cb_sort.setMinimumWidth(125)
        self.cb_sort.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb_sort.setToolTip("Sort by popularity or date")
        self.cb_sort.addItem("Latest", "newest")
        self.cb_sort.addItem("Most Upvoted", "most_upvotes")
        self.cb_sort.addItem("Most Discussed", "most_commented")
        self.cb_sort.addItem("Oldest", "oldest")
        self.cb_sort.currentIndexChanged.connect(self.on_filter_changed)
        cat_filter_row.addWidget(self.cb_sort)

        # B) 2nd: Resolution Dropdown (No ticks, "All Resolutions" on top)
        self.cb_res = QComboBox()
        self.cb_res.setObjectName("filterCombo")
        self.cb_res.setFixedHeight(34)
        self.cb_res.setMinimumWidth(130)
        self.cb_res.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb_res.setToolTip("Filter by resolution")
        self.cb_res.addItem("All Resolutions", "")
        self.cb_res.addItem("1280x720", "139")
        self.cb_res.addItem("1920x1080", "33")
        self.cb_res.addItem("2560x1080", "759")
        self.cb_res.addItem("2560x1440", "310")
        self.cb_res.addItem("3440x1440", "142")
        self.cb_res.addItem("3840x2160", "192")
        self.cb_res.addItem("5120x1440", "7085")
        self.cb_res.currentIndexChanged.connect(self.on_filter_changed)
        cat_filter_row.addWidget(self.cb_res)

        # C) 3rd: Sound Toggle Button
        self.sound_filter_active = False
        self.btn_sound_filter = QPushButton("Sound: Off")
        self.btn_sound_filter.setFixedHeight(34)
        self.btn_sound_filter.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sound_filter.setToolTip("Toggle wallpapers with audio/sound")
        self._update_sound_button_style()
        self.btn_sound_filter.clicked.connect(self.toggle_sound_filter)
        cat_filter_row.addWidget(self.btn_sound_filter)

        layout.addLayout(cat_filter_row)

        # Status label (hidden for clean UI)
        self.online_status_lbl = QLabel()
        self.online_status_lbl.setVisible(False)

        # Scrollable Grid of Wallpaper Cards
        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_main_layout = QVBoxLayout(self.cards_container)
        self.cards_main_layout.setContentsMargins(4, 4, 4, 24)
        self.cards_main_layout.setSpacing(20)

        self.cards_grid = QGridLayout()
        self.cards_grid.setContentsMargins(0, 0, 0, 0)
        self.cards_grid.setSpacing(16)
        self.cards_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.cards_main_layout.addLayout(self.cards_grid)

        # Load More Button
        self.load_more_box = QHBoxLayout()
        self.btn_load_more = QPushButton("Load More Wallpapers")
        self.btn_load_more.setObjectName("glassBtn")
        self.btn_load_more.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_load_more.setFixedHeight(38)
        self.btn_load_more.setFixedWidth(240)
        self.btn_load_more.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_load_more.clicked.connect(self.load_next_page)
        self.btn_load_more.setVisible(False)
        self.load_more_box.addStretch(1)
        self.load_more_box.addWidget(self.btn_load_more)
        self.load_more_box.addStretch(1)
        self.cards_main_layout.addLayout(self.load_more_box)

        self.cards_scroll.setWidget(self.cards_container)
        layout.addWidget(self.cards_scroll, 1)
        return page

    # ───────── Page 1: My Library ─────────
    def create_library_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(14)

        header_row = QHBoxLayout()
        lib_title = QLabel("My Local Wallpapers")
        lib_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        header_row.addWidget(lib_title)
        header_row.addStretch(1)

        btn_import = QPushButton("Import Video...")
        btn_import.setObjectName("primaryBtn")
        btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_import.clicked.connect(self.browse_video)
        header_row.addWidget(btn_import)

        btn_folder = QPushButton("Open Folder")
        btn_folder.setObjectName("glassBtn")
        btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_folder.clicked.connect(lambda: os.startfile(WALLPAPERS_DIR) if IS_WIN else None)
        header_row.addWidget(btn_folder)

        btn_refresh_lib = QPushButton("Refresh")
        btn_refresh_lib.setObjectName("glassBtn")
        btn_refresh_lib.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_refresh_lib.clicked.connect(self.refresh_library)
        header_row.addWidget(btn_refresh_lib)
        layout.addLayout(header_row)

        drop_box = QLabel("Drag and Drop any video file here (MP4 · MKV · WEBM · MOV · AVI · WMV)")
        drop_box.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_box.setStyleSheet(
            "border: 2px dashed rgba(255, 255, 255, 0.15); border-radius: 14px; "
            "padding: 18px; color: #9CA3AF; font-size: 13px; background: rgba(255, 255, 255, 0.02);"
        )
        layout.addWidget(drop_box)

        # Segmented Filter Bar: All Wallpapers (X) | Favorites (Y)
        sec_bar = QHBoxLayout()
        sec_bar.setSpacing(10)

        self.btn_lib_all = QPushButton("All Wallpapers (0)")
        self.btn_lib_all.setObjectName("chipBtnActive")
        self.btn_lib_all.setFixedHeight(32)
        self.btn_lib_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_lib_all.clicked.connect(lambda: self.switch_library_section("all"))
        sec_bar.addWidget(self.btn_lib_all)

        self.btn_lib_favs = QPushButton("Favorites (0)")
        self.btn_lib_favs.setObjectName("chipBtn")
        self.btn_lib_favs.setFixedHeight(32)
        self.btn_lib_favs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_lib_favs.setIcon(make_heart_icon("#EC4899", 15, filled=True))
        self.btn_lib_favs.setIconSize(QSize(15, 15))
        self.btn_lib_favs.clicked.connect(lambda: self.switch_library_section("favorites"))
        sec_bar.addWidget(self.btn_lib_favs)

        sec_bar.addStretch(1)
        layout.addLayout(sec_bar)

        self.lib_status_lbl = QLabel("Loading local wallpapers…")
        self.lib_status_lbl.setStyleSheet("font-size: 13px; color: #9CA3AF; padding: 2px 4px;")
        layout.addWidget(self.lib_status_lbl)

        # Empty state notification
        self.lib_empty_lbl = QLabel()
        self.lib_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lib_empty_lbl.setStyleSheet("font-size: 13px; font-weight: 500; color: #6B7280; padding: 36px 20px;")
        self.lib_empty_lbl.hide()
        layout.addWidget(self.lib_empty_lbl)

        # Visual Grid in ScrollArea
        self.lib_scroll = QScrollArea()
        self.lib_scroll.setWidgetResizable(True)
        self.lib_scroll.setStyleSheet("background: transparent; border: none;")

        self.lib_container = QWidget()
        self.lib_container.setStyleSheet("background: transparent;")
        self.lib_main_layout = QVBoxLayout(self.lib_container)
        self.lib_main_layout.setContentsMargins(0, 4, 0, 16)
        self.lib_main_layout.setSpacing(16)

        self.lib_grid = QGridLayout()
        self.lib_grid.setSpacing(16)
        self.lib_main_layout.addLayout(self.lib_grid)
        self.lib_main_layout.addStretch(1)

        self.lib_scroll.setWidget(self.lib_container)
        layout.addWidget(self.lib_scroll, 1)

        self.lib_card_widgets = []
        return page

    # ───────── Page 2: Downloads Manager (Method 1: Segmented View) ─────────
    def create_downloads_page(self):
        page = QWidget()
        page.setStyleSheet("background-color: #000000;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 22, 28, 20)
        layout.setSpacing(16)

        # 1. Top Header Row: Title, Subtitle, and Live Total Speed Pill
        top_bar = QHBoxLayout()
        top_bar.setSpacing(14)

        header_vbox = QVBoxLayout()
        header_vbox.setSpacing(4)
        dl_title = QLabel("Downloads")
        dl_title.setStyleSheet("font-size: 22px; font-weight: 700; color: #FFFFFF;")
        header_vbox.addWidget(dl_title)

        dl_sub = QLabel("Manage download queue and offline wallpaper files")
        dl_sub.setStyleSheet("font-size: 12px; color: #9CA3AF;")
        header_vbox.addWidget(dl_sub)
        top_bar.addLayout(header_vbox, 1)

        # Live Speed Badge Pill
        self.dl_speed_badge = QLabel("Idle")
        self.dl_speed_badge.setStyleSheet(
            "background-color: rgba(255, 255, 255, 0.04); color: #9CA3AF; "
            "border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 14px; "
            "padding: 5px 14px; font-size: 12px; font-weight: 600;"
        )
        top_bar.addWidget(self.dl_speed_badge)
        layout.addLayout(top_bar)

        # 2. Segmented Pill Tab Bar & Action Controls
        tab_row = QHBoxLayout()
        tab_row.setSpacing(12)

        # Segmented Switcher Container
        seg_container = QFrame()
        seg_container.setStyleSheet(
            "background-color: rgba(255, 255, 255, 0.04); "
            "border: 1px solid rgba(255, 255, 255, 0.08); "
            "border-radius: 10px;"
        )
        seg_layout = QHBoxLayout(seg_container)
        seg_layout.setContentsMargins(4, 4, 4, 4)
        seg_layout.setSpacing(6)

        self.btn_tab_active = QPushButton("Downloading (0)")
        self.btn_tab_active.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tab_active.clicked.connect(lambda: self.set_downloads_tab(0))
        seg_layout.addWidget(self.btn_tab_active)

        self.btn_tab_completed = QPushButton("Completed (0)")
        self.btn_tab_completed.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_tab_completed.clicked.connect(lambda: self.set_downloads_tab(1))
        seg_layout.addWidget(self.btn_tab_completed)

        tab_row.addWidget(seg_container)
        tab_row.addStretch(1)

        # Context Action Buttons
        self.btn_resume_all = QPushButton("Resume All")
        self.btn_resume_all.setObjectName("glassBtn")
        self.btn_resume_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_resume_all.clicked.connect(self.download_manager.resume_all)
        tab_row.addWidget(self.btn_resume_all)

        self.btn_pause_all = QPushButton("Pause All")
        self.btn_pause_all.setObjectName("glassBtn")
        self.btn_pause_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause_all.clicked.connect(self.download_manager.pause_all)
        tab_row.addWidget(self.btn_pause_all)

        self.btn_clear_comp = QPushButton("Clear History")
        self.btn_clear_comp.setObjectName("glassBtn")
        self.btn_clear_comp.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_comp.clicked.connect(self.download_manager.clear_completed)
        self.btn_clear_comp.hide()
        tab_row.addWidget(self.btn_clear_comp)

        layout.addLayout(tab_row)

        # 3. Stacked Pages for Segmented Views (Page 0: Downloading, Page 1: Completed)
        self.dl_stack = QStackedWidget()
        self.dl_stack.setStyleSheet("background: transparent;")

        # Page 0: Active & Paused View
        page_active = QWidget()
        pa_layout = QVBoxLayout(page_active)
        pa_layout.setContentsMargins(0, 8, 0, 0)
        pa_layout.setSpacing(0)

        active_scroll = QScrollArea()
        active_scroll.setWidgetResizable(True)
        active_scroll.setStyleSheet("background: transparent; border: none;")

        self.active_content = QWidget()
        self.active_content.setStyleSheet("background: transparent;")
        self.active_scroll_layout = QVBoxLayout(self.active_content)
        self.active_scroll_layout.setContentsMargins(0, 6, 0, 16)
        self.active_scroll_layout.setSpacing(12)
        self.active_scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.lbl_no_active = QLabel("No active or paused downloads\nWallpapers you download from Discover will appear here.")
        self.lbl_no_active.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_no_active.setStyleSheet("color: #6B7280; font-size: 13px; padding: 48px 0;")
        self.active_scroll_layout.addWidget(self.lbl_no_active)

        active_scroll.setWidget(self.active_content)
        pa_layout.addWidget(active_scroll)
        self.dl_stack.addWidget(page_active)

        # Page 1: Completed View
        page_completed = QWidget()
        pc_layout = QVBoxLayout(page_completed)
        pc_layout.setContentsMargins(0, 8, 0, 0)
        pc_layout.setSpacing(0)

        completed_scroll = QScrollArea()
        completed_scroll.setWidgetResizable(True)
        completed_scroll.setStyleSheet("background: transparent; border: none;")

        self.completed_content = QWidget()
        self.completed_content.setStyleSheet("background: transparent;")
        self.completed_scroll_layout = QVBoxLayout(self.completed_content)
        self.completed_scroll_layout.setContentsMargins(0, 6, 0, 16)
        self.completed_scroll_layout.setSpacing(12)
        self.completed_scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.lbl_no_completed = QLabel("No completed downloads in history\nCompleted wallpapers will be saved here for quick playback.")
        self.lbl_no_completed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_no_completed.setStyleSheet("color: #6B7280; font-size: 13px; padding: 48px 0;")
        self.completed_scroll_layout.addWidget(self.lbl_no_completed)

        completed_scroll.setWidget(self.completed_content)
        pc_layout.addWidget(completed_scroll)
        self.dl_stack.addWidget(page_completed)

        layout.addWidget(self.dl_stack, 1)

        self.downloads_active_cards = {}
        self.downloads_completed_cards = {}
        self.current_dl_tab = 0

        self.set_downloads_tab(0)

        return page

    def set_downloads_tab(self, tab_idx):
        self.current_dl_tab = tab_idx
        self.dl_stack.setCurrentIndex(tab_idx)

        active_pill_style = (
            "background-color: #0A84FF; color: #FFFFFF; font-weight: 700; "
            "border-radius: 7px; padding: 6px 18px; font-size: 12px; border: none;"
        )
        inactive_pill_style = (
            "background-color: transparent; color: #9CA3AF; font-weight: 600; "
            "border-radius: 7px; padding: 6px 18px; font-size: 12px; border: none;"
        )

        if tab_idx == 0:
            self.btn_tab_active.setStyleSheet(active_pill_style)
            self.btn_tab_completed.setStyleSheet(inactive_pill_style)
            self.btn_resume_all.show()
            self.btn_pause_all.show()
            self.btn_clear_comp.hide()
        else:
            self.btn_tab_active.setStyleSheet(inactive_pill_style)
            self.btn_tab_completed.setStyleSheet(active_pill_style)
            self.btn_resume_all.hide()
            self.btn_pause_all.hide()
            self.btn_clear_comp.show()

    def refresh_downloads_page(self):
        if not hasattr(self, "downloads_active_cards"):
            return

        for c in self.downloads_active_cards.values():
            c.deleteLater()
        self.downloads_active_cards.clear()

        for c in self.downloads_completed_cards.values():
            c.deleteLater()
        self.downloads_completed_cards.clear()

        tasks = list(self.download_manager.tasks.values())
        active_tasks = [t for t in tasks if t.get("status") in ("downloading", "paused", "queued", "failed")]
        completed_tasks = [t for t in tasks if t.get("status") == "completed"]

        # Update button labels with counts
        self.btn_tab_active.setText(f"Downloading ({len(active_tasks)})")
        self.btn_tab_completed.setText(f"Completed ({len(completed_tasks)})")

        # Update speed badge
        active_downloading = [t for t in active_tasks if t.get("status") == "downloading"]
        if active_downloading:
            spd = active_downloading[0].get("speed_str", "0.0 MB/s")
            self.dl_speed_badge.setText(f"Speed: {spd}")
            self.dl_speed_badge.setStyleSheet(
                "background-color: rgba(10, 132, 255, 0.15); color: #0A84FF; "
                "border: 1px solid rgba(10, 132, 255, 0.35); border-radius: 14px; "
                "padding: 5px 14px; font-size: 12px; font-weight: 700;"
            )
        else:
            self.dl_speed_badge.setText("Idle")
            self.dl_speed_badge.setStyleSheet(
                "background-color: rgba(255, 255, 255, 0.04); color: #9CA3AF; "
                "border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 14px; "
                "padding: 5px 14px; font-size: 12px; font-weight: 600;"
            )

        # Populate Active Tasks
        if active_tasks:
            self.lbl_no_active.hide()
            for t in reversed(active_tasks):
                card = ActiveDownloadCard(t, self.download_manager, self.active_content)
                self.active_scroll_layout.addWidget(card)
                self.downloads_active_cards[t["id"]] = card
        else:
            self.lbl_no_active.show()

        # Populate Completed Tasks
        if completed_tasks:
            self.lbl_no_completed.hide()
            for t in reversed(completed_tasks):
                card = CompletedDownloadCard(t, self.download_manager, self, self.completed_content)
                self.completed_scroll_layout.addWidget(card)
                self.downloads_completed_cards[t["id"]] = card
        else:
            self.lbl_no_completed.show()

    # ───────── Page 3: Settings & Engine Controls ─────────
    def create_settings_page(self):
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(18)

        stitle = QLabel("Engine Settings")
        stitle.setStyleSheet("font-size: 20px; font-weight: 700; color: #FFFFFF;")
        layout.addWidget(stitle)

        # ── Group 1: Display & Playback ──
        g1 = QFrame()
        g1.setObjectName("glassCard")
        g1_lay = QVBoxLayout(g1)
        g1_lay.setContentsMargins(18, 16, 18, 16)
        g1_lay.setSpacing(12)

        g1_lbl = QLabel("Display and Playback")
        g1_lbl.setStyleSheet("font-size: 15px; font-weight: 600; color: #FFFFFF;")
        g1_lay.addWidget(g1_lbl)

        def add_combo_row(lbl_text, items, cfg_key):
            row = QHBoxLayout()
            lbl = QLabel(lbl_text)
            lbl.setStyleSheet("color: #D1D5DB;")
            row.addWidget(lbl, 1)
            cb = QComboBox()
            for text, val in items:
                cb.addItem(text, val)
            cb.setCurrentIndex(max(0, cb.findData(self.cfg.get(cfg_key))))
            cb.currentIndexChanged.connect(lambda _: self.change_setting(cfg_key, cb.currentData()))
            row.addWidget(cb, 2)
            g1_lay.addLayout(row)

        add_combo_row("Target Monitors:", [("All Monitors", "all"), ("Primary Monitor Only", "primary")], "monitors")
        add_combo_row("Video Scaling:", [("Fill (Crop edges)", "fill"), ("Fit (Black bars)", "fit"), ("Stretch", "stretch")], "fit")
        add_combo_row("Playback Speed:", [("0.5×", 0.5), ("0.75×", 0.75), ("1.0× (Normal)", 1.0), ("1.25×", 1.25), ("1.5×", 1.5), ("2.0×", 2.0)], "speed")
        layout.addWidget(g1)

        # ── Group 2: Audio Controls ──
        g2 = QFrame()
        g2.setObjectName("glassCard")
        g2_lay = QVBoxLayout(g2)
        g2_lay.setContentsMargins(18, 16, 18, 16)
        g2_lay.setSpacing(12)

        g2_lbl = QLabel("Audio Controls")
        g2_lbl.setStyleSheet("font-size: 15px; font-weight: 600; color: #FFFFFF;")
        g2_lay.addWidget(g2_lbl)

        vol_row = QHBoxLayout()
        vol_txt = QLabel("Wallpaper Volume:")
        vol_txt.setStyleSheet("color: #D1D5DB;")
        vol_row.addWidget(vol_txt, 1)

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(self.cfg.get("volume", 40))
        self.vol_slider.valueChanged.connect(lambda v: self.change_setting("volume", v))
        vol_row.addWidget(self.vol_slider, 2)

        self.mute_chk = QCheckBox("Mute Audio")
        self.mute_chk.setChecked(self.cfg.get("muted", True))
        self.mute_chk.toggled.connect(lambda v: self.change_setting("muted", v))
        vol_row.addWidget(self.mute_chk)
        g2_lay.addLayout(vol_row)
        layout.addWidget(g2)

        # ── Group 3: Performance & Battery Saving ──
        g3 = QFrame()
        g3.setObjectName("glassCard")
        g3_lay = QVBoxLayout(g3)
        g3_lay.setContentsMargins(18, 16, 18, 16)
        g3_lay.setSpacing(12)

        g3_lbl = QLabel("Performance and Power Saving")
        g3_lbl.setStyleSheet("font-size: 15px; font-weight: 600; color: #FFFFFF;")
        g3_lay.addWidget(g3_lbl)

        def add_check_row(text, checked, fn):
            c = QCheckBox(text)
            c.setChecked(checked)
            c.toggled.connect(fn)
            g3_lay.addWidget(c)
            return c

        add_check_row(
            "Auto-pause when another app is maximized or fullscreen (Saves GPU & Battery)",
            self.cfg.get("pause_busy", True),
            lambda v: self.change_setting("pause_busy", v)
        )
        add_check_row(
            "Auto-pause when running on laptop battery power",
            self.cfg.get("pause_battery", True),
            lambda v: self.change_setting("pause_battery", v)
        )
        layout.addWidget(g3)

        # ── Group 4: Windows Integration ──
        g4 = QFrame()
        g4.setObjectName("glassCard")
        g4_lay = QVBoxLayout(g4)
        g4_lay.setContentsMargins(18, 16, 18, 16)
        g4_lay.setSpacing(12)

        g4_lbl = QLabel("Windows Integration")
        g4_lbl.setStyleSheet("font-size: 15px; font-weight: 600; color: #FFFFFF;")
        g4_lay.addWidget(g4_lbl)

        c_startup = QCheckBox("Start automatically with Windows")
        c_startup.setChecked(autostart_enabled())
        c_startup.toggled.connect(self.toggle_autostart)
        g4_lay.addWidget(c_startup)

        c_ctx = QCheckBox("Add 'Set as Live Wallpaper' to right-click menu of video files")
        c_ctx.setChecked(context_enabled())
        c_ctx.toggled.connect(self.toggle_context)
        g4_lay.addWidget(c_ctx)
        layout.addWidget(g4)

        layout.addStretch(1)
        scroll.setWidget(container)

        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.addWidget(scroll)
        return page

    # ───────── Navigation Switcher ─────────
    def switch_page(self, index):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            if i == index:
                btn.setObjectName("navBtnActive")
            else:
                btn.setObjectName("navBtn")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        if index == 0:
            QTimer.singleShot(50, self.reposition_cards)
        elif index == 1:
            self.refresh_library()
            QTimer.singleShot(50, self.reposition_library_cards)
        elif index == 2:
            self.refresh_downloads_page()

    def reposition_cards(self):
        if not hasattr(self, "cards_scroll") or not self.card_widgets:
            return
        avail_w = self.cards_scroll.viewport().width()
        if avail_w <= 100:
            avail_w = self.width() - 280

        card_w = 276
        spacing = 16
        cols = max(2, (avail_w - 24) // (card_w + spacing))

        for idx, card in enumerate(self.card_widgets):
            row = idx // cols
            col = idx % cols
            self.cards_grid.addWidget(card, row, col)

    def switch_library_section(self, section):
        self.lib_current_section = section
        if section == "all":
            self.btn_lib_all.setObjectName("chipBtnActive")
            self.btn_lib_favs.setObjectName("chipBtn")
        else:
            self.btn_lib_all.setObjectName("chipBtn")
            self.btn_lib_favs.setObjectName("chipBtnActive")
        self.btn_lib_all.style().unpolish(self.btn_lib_all)
        self.btn_lib_all.style().polish(self.btn_lib_all)
        self.btn_lib_favs.style().unpolish(self.btn_lib_favs)
        self.btn_lib_favs.style().polish(self.btn_lib_favs)
        self.reposition_library_cards()

    def update_library_tab_counts(self):
        if not hasattr(self, "btn_lib_all") or not hasattr(self, "btn_lib_favs"):
            return
        all_count = len(self.lib_card_widgets)
        fav_count = sum(1 for card in self.lib_card_widgets if self.is_favorite(title=card.title_text, file_path=card.file_path))
        self.btn_lib_all.setText(f"All Wallpapers ({all_count})")
        self.btn_lib_favs.setText(f"Favorites ({fav_count})")

    def is_favorite(self, title="", file_path="", post_url=""):
        favs = self.cfg.get("favorites", [])
        clean_title = title.strip().lower() if title else ""
        clean_file = Path(file_path).stem.lower() if file_path else ""
        for item in favs:
            if isinstance(item, str):
                if item.strip().lower() in (clean_title, clean_file):
                    return True
            elif isinstance(item, dict):
                t = item.get("title", "").strip().lower()
                p = item.get("post_url", "")
                f = Path(item.get("file_path", "")).stem.lower() if item.get("file_path") else ""
                if (clean_title and t == clean_title) or (post_url and p == post_url) or (clean_file and (t == clean_file or f == clean_file)):
                    return True
        return False

    def toggle_favorite(self, title, file_path="", post_url="", img_url=""):
        favs = self.cfg.setdefault("favorites", [])
        fav = self.is_favorite(title, file_path, post_url)
        clean_title = title.strip().lower() if title else ""
        clean_file = Path(file_path).stem.lower() if file_path else ""

        if fav:
            new_favs = []
            for item in favs:
                if isinstance(item, str):
                    if item.strip().lower() in (clean_title, clean_file):
                        continue
                elif isinstance(item, dict):
                    t = item.get("title", "").strip().lower()
                    p = item.get("post_url", "")
                    f = Path(item.get("file_path", "")).stem.lower() if item.get("file_path") else ""
                    if (clean_title and t == clean_title) or (post_url and p == post_url) or (clean_file and (t == clean_file or f == clean_file)):
                        continue
                new_favs.append(item)
            self.cfg["favorites"] = new_favs
            self.say(f"Removed from Favorites: {title}")
        else:
            item_data = {
                "title": title,
                "file_path": file_path,
                "post_url": post_url,
                "img_url": img_url
            }
            favs.append(item_data)
            self.say(f"Added to Favorites: {title}")

        save_cfg(self.cfg)
        self.update_all_favorite_buttons()
        return not fav

    def update_all_favorite_buttons(self):
        for card in getattr(self, "card_widgets", []):
            if hasattr(card, "update_fav_state"):
                card.update_fav_state()

        for card in getattr(self, "lib_card_widgets", []):
            if hasattr(card, "update_fav_state"):
                card.update_fav_state()

        self.update_library_tab_counts()
        if hasattr(self, "stack") and self.stack.currentIndex() == 1:
            if getattr(self, "lib_current_section", "all") == "favorites":
                self.reposition_library_cards()

    def reposition_library_cards(self):
        if not hasattr(self, "lib_scroll") or not hasattr(self, "lib_grid"):
            return

        # Safely remove layout items without unparenting widgets (never call setParent(None))
        while self.lib_grid.count():
            self.lib_grid.takeAt(0)

        filter_fav = getattr(self, "lib_current_section", "all") == "favorites"

        visible_cards = []
        for card in self.lib_card_widgets:
            if hasattr(self, "lib_container") and card.parent() != self.lib_container:
                card.setParent(self.lib_container)
            is_fav = self.is_favorite(title=card.title_text, file_path=card.file_path)
            if filter_fav:
                if is_fav:
                    visible_cards.append(card)
                    card.show()
                else:
                    card.hide()
            else:
                visible_cards.append(card)
                card.show()

        if hasattr(self, "lib_empty_lbl"):
            if not visible_cards:
                if filter_fav:
                    self.lib_empty_lbl.setText("No favorite wallpapers yet.\nClick the heart icon on any wallpaper in Discover or Library to add it here.")
                    self.lib_empty_lbl.show()
                else:
                    self.lib_empty_lbl.setText("No local wallpapers found. Download from Discover or import your own videos.")
                    self.lib_empty_lbl.show()
            else:
                self.lib_empty_lbl.hide()

        avail_w = self.lib_scroll.viewport().width()
        if avail_w <= 100:
            avail_w = self.width() - 280

        card_w = 276
        spacing = 16
        cols = max(2, (avail_w - 24) // (card_w + spacing))

        for idx, card in enumerate(visible_cards):
            row = idx // cols
            col = idx % cols
            self.lib_grid.addWidget(card, row, col)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reposition_cards()
        self.reposition_library_cards()

    def _update_sound_button_style(self):
        if not hasattr(self, "btn_sound_filter"):
            return
        if getattr(self, "sound_filter_active", False):
            self.btn_sound_filter.setText("Sound: On")
            self.btn_sound_filter.setStyleSheet("""
                QPushButton {
                    background-color: #0A84FF;
                    color: #FFFFFF;
                    font-size: 11px;
                    font-weight: 700;
                    border: 1px solid #38BDF8;
                    border-radius: 8px;
                    padding: 4px 12px;
                }
                QPushButton:hover {
                    background-color: #0070E0;
                }
            """)
        else:
            self.btn_sound_filter.setText("Sound: Off")
            self.btn_sound_filter.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 255, 255, 0.05);
                    color: #9CA3AF;
                    font-size: 11px;
                    font-weight: 600;
                    border: 1px solid rgba(255, 255, 255, 0.12);
                    border-radius: 8px;
                    padding: 4px 12px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 0.09);
                    color: #FFFFFF;
                    border-color: rgba(255, 255, 255, 0.22);
                }
            """)

    def toggle_sound_filter(self):
        self.sound_filter_active = not getattr(self, "sound_filter_active", False)
        self._update_sound_button_style()
        self.on_filter_changed()

    def on_filter_changed(self):
        self.current_page = 1
        query = self.search_input.text().strip() if hasattr(self, "search_input") else ""
        self.start_online_search(
            query=query,
            category_slug=getattr(self, "current_category", ""),
            page=1,
            append=False
        )

    def on_category_clicked(self, slug, active_btn):
        for btn, s in self.category_buttons:
            if btn == active_btn:
                btn.setObjectName("chipBtnActive")
            else:
                btn.setObjectName("chipBtn")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.search_input.clear()
        self.current_page = 1
        self.current_query = ""
        self.current_category = slug
        self.start_online_search(category_slug=slug, page=1, append=False)

    def on_search_trigger(self):
        query = self.search_input.text().strip()
        for btn, s in self.category_buttons:
            btn.setObjectName("chipBtn")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self.current_page = 1
        self.current_query = query
        self.current_category = ""
        self.start_online_search(query=query, page=1, append=False)

    def load_next_page(self):
        if self.is_loading_more:
            return
        self.is_loading_more = True
        self.current_page += 1
        self.btn_load_more.setText("Loading More Wallpapers…")
        self.btn_load_more.setEnabled(False)
        self.btn_load_more.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.search_input.clearFocus()
        self.setFocus()
        self.start_online_search(
            query=self.current_query,
            category_slug=self.current_category,
            page=self.current_page,
            append=True
        )

    # ───────── Online Scraper Methods ─────────
    def start_online_search(self, query="", category_slug="", page=1, append=False):
        if query:
            desc = f"'{query}' (Page {page})"
        elif category_slug:
            desc = f"category '{category_slug}' (Page {page})"
        else:
            desc = f"Latest (Page {page})"

        if not append:
            self.online_status_lbl.setText(f"Fetching wallpapers for {desc}…")
            for card in self.card_widgets:
                card.deleteLater()
            self.card_widgets = []
            self.btn_load_more.setVisible(False)
        else:
            self.online_status_lbl.setText(f"Loading more wallpapers for {desc}…")

        threading.Thread(
            target=self._scrape_thread,
            args=(query, category_slug, page, append),
            daemon=True
        ).start()

    def _scrape_thread(self, query="", category_slug="", page=1, append=False):
        order = self.cb_sort.currentData() if hasattr(self, "cb_sort") else "newest"
        res_term = self.cb_res.currentData() if hasattr(self, "cb_res") else ""
        sound_only = getattr(self, "sound_filter_active", False)

        params = {}
        if query:
            params["s"] = query
            base = f"https://moewalls.com/page/{page}/" if page > 1 else "https://moewalls.com/"
        elif category_slug:
            base = f"https://moewalls.com/category/{category_slug}/page/{page}/" if page > 1 else f"https://moewalls.com/category/{category_slug}/"
        else:
            base = f"https://moewalls.com/page/{page}/" if page > 1 else "https://moewalls.com/"

        taxonomies = []
        if res_term:
            taxonomies.append("resolutions")
            params["resolutions-terms"] = res_term
        if sound_only:
            taxonomies.append("groups")
            params["groups-terms"] = "182"

        if taxonomies:
            params["filter-by-taxonomies"] = ",".join(taxonomies)

        if order and order != "newest":
            params["order"] = order

        try:
            res = self.scraper.get(base, params=params, timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
            articles = soup.select("article.entry-tpl-grid")

            items = []
            for art in articles:
                t_el = art.select_one(".entry-title a")
                i_el = art.select_one("img")
                if t_el and i_el:
                    title = t_el.text.strip()
                    post_url = urljoin("https://moewalls.com", t_el.get("href", ""))
                    raw_img = i_el.get("data-src") or i_el.get("data-lazy-src") or i_el.get("src")
                    if raw_img:
                        img_url = urljoin("https://moewalls.com", raw_img)
                        res_el = art.find(class_="entry-resolutions")
                        res_text = res_el.text.strip() if res_el else ""
                        has_sound = "groups-sound" in art.get("class", [])
                        items.append({
                            "title": title,
                            "img_url": img_url,
                            "post_url": post_url,
                            "res": res_text,
                            "has_sound": has_sound
                        })

            self.signals.results_ready.emit(items, append)
        except Exception as e:
            self.signals.status_msg.emit(f"Fetch Error: {e}")
            self.signals.load_more_done.emit(False)

    def on_results_ready(self, items, append):
        self.is_loading_more = False
        self.lib_current_section = "all"
        saved_scroll = self.cards_scroll.verticalScrollBar().value() if append else 0

        if not items:
            if not append:
                self.online_status_lbl.setText("No wallpapers found.")
                self.btn_load_more.setVisible(False)
            else:
                self.online_status_lbl.setText("All wallpapers loaded in this category.")
                self.btn_load_more.setText("All Wallpapers Loaded")
                self.btn_load_more.setEnabled(False)
            return

        start_idx = len(self.card_widgets) if append else 0
        for i, item in enumerate(items):
            idx = start_idx + i
            card = WallpaperCard(
                idx, item["title"], item["img_url"], item["post_url"], self,
                item.get("res", ""), item.get("has_sound", False)
            )
            self.card_widgets.append(card)

            # Fetch thumbnail in background
            threading.Thread(
                target=self._fetch_card_thumb,
                args=(idx, item["img_url"]),
                daemon=True
            ).start()

        self.reposition_cards()

        # Update Load More button
        self.btn_load_more.setVisible(True)
        if len(items) < 16:
            self.btn_load_more.setText("All Wallpapers Loaded")
            self.btn_load_more.setEnabled(False)
        else:
            self.btn_load_more.setText("Load More Wallpapers")
            self.btn_load_more.setEnabled(True)

        if append and items and 0 <= start_idx < len(self.card_widgets):
            first_new_card = self.card_widgets[start_idx]
            QTimer.singleShot(60, lambda: self.cards_scroll.ensureWidgetVisible(first_new_card, 0, 40))
            QTimer.singleShot(180, lambda: self.cards_scroll.ensureWidgetVisible(first_new_card, 0, 40))

    def _fetch_card_thumb(self, index, img_url):
        try:
            data = self.scraper.get(img_url, timeout=10).content
            self.signals.card_thumbnail_ready.emit(index, data)
        except Exception:
            pass

    def on_card_thumbnail_ready(self, index, img_bytes):
        if 0 <= index < len(self.card_widgets):
            self.card_widgets[index].set_thumbnail(img_bytes)

    def open_online_preview(self, post_url, title):
        # Offline first: check if already in Library
        safe_title = "".join(c for c in title if c.isalnum() or c in " _-").rstrip()
        local_full = WALLPAPERS_DIR / f"{safe_title}.mp4"
        if local_full.is_file() and local_full.stat().st_size > 10240:
            self.on_open_preview(title, str(local_full), is_local=True, post_url="")
            return

        safe_slug = re.sub(r'[^a-zA-Z0-9_\-]', '_', title).strip('_')[:40]
        cached_mp4 = PREVIEWS_DIR / f"{safe_slug}.mp4"

        # Instant preview if already cached
        if cached_mp4.exists() and cached_mp4.stat().st_size > 10240:
            self.on_open_preview(title, str(cached_mp4), is_local=True, post_url=post_url)
            return

        # Open modal immediately in loading state
        dlg = LivePreviewDialog(title, None, is_local=False, parent_win=self, post_url=post_url)
        dlg.exec()

    def on_open_preview(self, title, url_or_path, is_local, post_url):
        dlg = LivePreviewDialog(title, url_or_path, is_local=is_local, parent_win=self, post_url=post_url)
        dlg.exec()

    def preview_selected_library_item(self):
        if self.lib_card_widgets:
            first = self.lib_card_widgets[0]
            self.on_open_preview(first.title_text, first.file_path, is_local=True, post_url="")

    # ───────── Download & Set Wallpaper Logic ─────────
    def download_and_apply(self, post_url, title, auto_apply=True, thumbnail_url=""):
        self.download_manager.start_or_resume(post_url, title, auto_apply=auto_apply, thumbnail_url=thumbnail_url)

    def on_download_progress(self, post_url, pct, mb_cur, mb_tot):
        for card in self.card_widgets:
            if card.post_url == post_url:
                card.update_download_progress(pct, mb_cur, mb_tot)
                break

    def on_download_paused(self, post_url):
        for card in self.card_widgets:
            if card.post_url == post_url:
                card.set_download_paused()
                break

    def on_download_finished(self, post_url, save_path, auto_apply):
        for card in self.card_widgets:
            if card.post_url == post_url:
                card.on_download_finished(save_path)
                break
        self.refresh_library()
        if auto_apply:
            self.apply_wallpaper(save_path)

    def update_sidebar_badge(self):
        if not hasattr(self, "btn_downloads") or not hasattr(self, "download_manager"):
            return
        active_count = sum(1 for t in self.download_manager.tasks.values() if t.get("status") in ("downloading", "queued"))
        if active_count > 0:
            self.btn_downloads.setText(f"Downloads ({active_count})")
        else:
            self.btn_downloads.setText("Downloads")

    def _on_download_state_updated(self):
        self.update_sidebar_badge()
        if hasattr(self, "stack") and self.stack.currentIndex() == 2:
            self.refresh_downloads_page()

    def set_static_background(self, img_url, title):
        self.say(f"Setting static background: {title}…")

        def _worker():
            try:
                data = self.scraper.get(img_url, timeout=15).content
                fpath = str(WALLPAPERS_DIR / "current_wallpaper.jpg")
                with open(fpath, "wb") as f:
                    f.write(data)
                if IS_WIN:
                    ctypes.windll.user32.SystemParametersInfoW(20, 0, fpath, 3)
                self.signals.status_msg.emit(f"Static wallpaper applied: {title}")
            except Exception as e:
                self.signals.status_msg.emit(f"Failed to set static wallpaper: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    # ───────── Engine Control & Library Actions ─────────
    def say(self, msg):
        pass  # Notice bar removed for ultra-clean UI

    def change_setting(self, key, value):
        self.cfg[key] = value
        save_cfg(self.cfg)
        if key == "monitors" and self.engine.path:
            self.engine.start(self.engine.path)
        else:
            self.engine.apply_settings()

    def browse_video(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Choose a Video Wallpaper", str(Path.home() / "Videos"),
            "Videos (*" + " *".join(VIDEO_EXTS) + ");;All files (*.*)"
        )
        if p:
            self.apply_wallpaper(p)

    def apply_selected_library_item(self):
        if self.lib_card_widgets:
            self.apply_wallpaper(self.lib_card_widgets[0].file_path)
        else:
            self.browse_video()

    def apply_wallpaper(self, path, bypass_warning=False):
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            self.say("File not found: " + path)
            return

        # AV1 Hardware Decode Warning
        codec = get_video_codec(path)
        if codec == "AV1" and not bypass_warning:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("GPU Hardware Warning (AV1 Codec)")
            msg_box.setText(
                f"<b>{Path(path).name}</b> is encoded in <b>AV1 format</b>.<br><br>"
                "Your graphics card does not support hardware AV1 decoding.<br>"
                "Playing this video may result in a black screen, stuttering, or errors.<br><br>"
                "Do you still want to try playing it?"
            )
            msg_box.setIcon(QMessageBox.Icon.Warning)
            btn_try = msg_box.addButton("Try Playing Anyway", QMessageBox.ButtonRole.AcceptRole)
            btn_cancel = msg_box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            msg_box.setStyleSheet(
                "QMessageBox { background-color: #121216; color: #FFFFFF; font-family: 'Segoe UI'; }"
                "QLabel { color: #FFFFFF; font-size: 13px; }"
                "QPushButton { background: rgba(255, 255, 255, 0.08); color: #FFFFFF; border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 8px; padding: 6px 14px; font-weight: 600; }"
                "QPushButton:hover { background: rgba(255, 255, 255, 0.18); }"
            )
            msg_box.exec()
            if msg_box.clickedButton() != btn_try:
                self.say("Cancelled playback of unsupported AV1 wallpaper.")
                return

        self.engine.start(path)
        rec = [p for p in self.cfg.get("recent", []) if p != path]
        self.cfg["recent"] = ([path] + rec)[:25]
        self.cfg["last"] = path
        save_cfg(self.cfg)

        name = Path(path).stem
        self.np_name_lbl.setText(name if len(name) <= 24 else name[:22] + "…")
        self.np_name_lbl.setToolTip(name)
        self.np_dot.setStyleSheet("background-color: #27C93F; border-radius: 4px;")
        self.btn_sidebar_pause.setText("Pause")
        self.say("Playing: " + Path(path).name)

    def toggle_pause(self):
        if not self.engine.walls:
            return
        paused = self.engine.toggle_pause()
        self.btn_sidebar_pause.setText("Resume" if paused else "Pause")
        self.np_dot.setStyleSheet("background-color: #FFBD2E; border-radius: 4px;" if paused else "background-color: #27C93F; border-radius: 4px;")
        self.say("Paused" if paused else "Playing")

    def stop_wallpaper(self):
        self.engine.stop(restore=True)
        self.cfg["last"] = ""
        save_cfg(self.cfg)
        self.np_name_lbl.setText("None (Stopped)")
        self.np_dot.setStyleSheet("background-color: #6B7280; border-radius: 4px;")
        self.say("Stopped. Restored default Windows wallpaper.")

    def on_local_thumb_ready(self, file_path, thumb_path):
        for card in self.lib_card_widgets:
            if os.path.abspath(card.file_path) == os.path.abspath(file_path):
                pix = QPixmap(thumb_path)
                if not pix.isNull():
                    card.set_thumbnail_pixmap(pix)
                break

    def delete_local_wallpaper(self, file_path):
        p = Path(file_path)
        ans = QMessageBox.question(
            self,
            "Delete Wallpaper",
            f"Are you sure you want to delete '{p.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if ans == QMessageBox.StandardButton.Yes:
            try:
                if self.engine.path and os.path.abspath(self.engine.path) == os.path.abspath(file_path):
                    self.stop_wallpaper()
                if os.path.exists(file_path):
                    os.remove(file_path)
                self.say(f"Deleted: {p.name}")
                self.refresh_library()
            except Exception as e:
                self.say(f"Delete failed: {e}")

    def refresh_library(self):
        for card in self.lib_card_widgets:
            card.hide()
            self.lib_grid.removeWidget(card)
            card.deleteLater()
        self.lib_card_widgets = []

        found_videos = []

        # 1. Search in wallpapers folder
        if WALLPAPERS_DIR.is_dir():
            for ext in VIDEO_EXTS:
                for f in WALLPAPERS_DIR.glob(f"*{ext}"):
                    resolved = str(f.resolve())
                    if resolved not in found_videos:
                        found_videos.append(resolved)

        # 2. Add recent videos from settings
        for p in self.cfg.get("recent", []):
            if p not in found_videos and os.path.isfile(p):
                found_videos.append(p)

        if not found_videos:
            self.lib_status_lbl.setText("No local wallpapers found. Download from Discover or import your own videos.")
            self.update_library_tab_counts()
            self.reposition_library_cards()
            return

        self.lib_status_lbl.setText(f"{len(found_videos)} local live wallpapers ready")

        for p in found_videos:
            card = LocalWallpaperCard(p, self)
            self.lib_card_widgets.append(card)

        self.reposition_library_cards()
        self.update_library_tab_counts()

    def update_system_metrics(self):
        try:
            # 1. Process CPU & RAM of moeDesk itself (and its subprocesses)
            if not hasattr(self, "main_proc"):
                self.main_proc = psutil.Process(os.getpid())
                try:
                    self.main_proc.cpu_percent(None)
                except Exception:
                    pass
                self.tracked_child_procs = {}
                self.smoothed_cpu = 0.0

            # Collect active child processes and prime any new ones
            pids = {self.main_proc.pid}
            try:
                for child in self.main_proc.children(recursive=True):
                    pids.add(child.pid)
                    if child.pid not in self.tracked_child_procs:
                        try:
                            child.cpu_percent(None)
                            self.tracked_child_procs[child.pid] = child
                        except Exception:
                            pass
            except Exception:
                pass

            # Calculate total raw CPU percentage across all cores
            total_raw_cpu = 0.0
            rss_bytes = 0
            try:
                if self.main_proc.is_running():
                    total_raw_cpu += self.main_proc.cpu_percent(None)
                    rss_bytes += self.main_proc.memory_info().rss
            except Exception:
                pass

            dead_pids = []
            for c_pid, c_proc in list(self.tracked_child_procs.items()):
                try:
                    if c_proc.is_running():
                        total_raw_cpu += c_proc.cpu_percent(None)
                        rss_bytes += c_proc.memory_info().rss
                    else:
                        dead_pids.append(c_pid)
                except Exception:
                    dead_pids.append(c_pid)

            for d_pid in dead_pids:
                self.tracked_child_procs.pop(d_pid, None)

            cpu_count = psutil.cpu_count() or 1
            curr_cpu = total_raw_cpu / cpu_count

            # Smooth CPU metric with Exponential Moving Average (EMA) to prevent flickering
            if getattr(self, "smoothed_cpu", 0.0) == 0.0:
                self.smoothed_cpu = curr_cpu
            else:
                self.smoothed_cpu = (self.smoothed_cpu * 0.35) + (curr_cpu * 0.65)

            cpu_pct = max(0.1, self.smoothed_cpu) if self.smoothed_cpu > 0.05 else 0.0
            ram_mb = rss_bytes / (1024 * 1024)
            ram_str = f"{ram_mb:.0f} MB" if ram_mb < 1000 else f"{ram_mb/1024:.1f} GB"
            ram_bar_val = min(100.0, (ram_mb / 600.0) * 100.0)

            # 2. Process GPU utilization (moeDesk video decoder & render surface)
            gpu_pct = self.gpu_monitor.get_utilization(target_pids=pids) if hasattr(self, 'gpu_monitor') and self.gpu_monitor else 0.0

            # 3. Wallpaper Library Storage
            total_bytes = 0
            count = 0
            if os.path.exists(WALLPAPERS_DIR):
                for f in os.listdir(WALLPAPERS_DIR):
                    p = os.path.join(WALLPAPERS_DIR, f)
                    if os.path.isfile(p):
                        total_bytes += os.path.getsize(p)
                        if f.lower().endswith(VIDEO_EXTS):
                            count += 1

            if total_bytes >= 1024 * 1024 * 1024:
                storage_str = f"{total_bytes / (1024 * 1024 * 1024):.1f} GB"
            else:
                storage_str = f"{total_bytes / (1024 * 1024):.0f} MB"

            # Progress bar relative to 10 GB
            storage_pct = min(100.0, (total_bytes / (10 * 1024 * 1024 * 1024)) * 100.0)
            count_str = f"{count} Wallpapers in Library"

            self.system_monitor_card.update_metrics(cpu_pct, ram_str, ram_bar_val, gpu_pct, storage_str, storage_pct, count_str)
        except Exception:
            pass

    def engine_fast_tick(self):
        self.engine.tick()
        if self.engine.walls:
            if self.engine.auto_paused:
                self.np_dot.setStyleSheet("background-color: #FFBD2E; border-radius: 4px;")
                self.np_status_badge.setText("AUTO-PAUSED")
                self.np_status_badge.setStyleSheet("font-size: 9px; font-weight: 700; color: #FFBD2E; background: rgba(255, 189, 46, 0.15); border-radius: 4px; padding: 1px 6px;")
                self.np_status_badge.setToolTip("Auto-paused because another application is maximized or fullscreen (Saves GPU & Battery)")
            elif self.engine.user_paused:
                self.np_dot.setStyleSheet("background-color: #FFBD2E; border-radius: 4px;")
                self.np_status_badge.setText("PAUSED")
                self.np_status_badge.setStyleSheet("font-size: 9px; font-weight: 700; color: #FFBD2E; background: rgba(255, 189, 46, 0.15); border-radius: 4px; padding: 1px 6px;")
                self.np_status_badge.setToolTip("Paused by user")
            elif self.engine.is_playing():
                self.np_dot.setStyleSheet("background-color: #27C93F; border-radius: 4px;")
                self.np_status_badge.setText("PLAYING")
                self.np_status_badge.setStyleSheet("font-size: 9px; font-weight: 700; color: #27C93F; background: rgba(39, 201, 63, 0.15); border-radius: 4px; padding: 1px 6px;")
                self.np_status_badge.setToolTip("Live wallpaper is actively playing on desktop")
            else:
                self.np_dot.setStyleSheet("background-color: #6B7280; border-radius: 4px;")
                self.np_status_badge.setText("STOPPED")
                self.np_status_badge.setStyleSheet("font-size: 9px; font-weight: 700; color: #9CA3AF; background: rgba(255, 255, 255, 0.08); border-radius: 4px; padding: 1px 6px;")
        else:
            self.np_dot.setStyleSheet("background-color: #6B7280; border-radius: 4px;")
            self.np_status_badge.setText("STOPPED")
            self.np_status_badge.setStyleSheet("font-size: 9px; font-weight: 700; color: #9CA3AF; background: rgba(255, 255, 255, 0.08); border-radius: 4px; padding: 1px 6px;")

    def engine_tick(self):
        self.engine_fast_tick()

    def toggle_autostart(self, v):
        try:
            set_autostart(v)
        except Exception as e:
            self.say(f"Could not change startup setting: {e}")

    def toggle_context(self, v):
        try:
            set_context(v)
        except Exception as e:
            self.say(f"Could not change right-click menu: {e}")

    # ───────── Tray Icon & Window Lifecycle ─────────
    def init_tray(self):
        self.tray = QSystemTrayIcon(make_app_icon(), self)
        m = QMenu()
        m.setStyleSheet(
            "QMenu { background-color: #121216; color: #FFFFFF; border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 8px; padding: 4px; }"
            "QMenu::item { padding: 6px 14px; border-radius: 6px; }"
            "QMenu::item:selected { background-color: #0A84FF; }"
        )
        for text, fn in [
            ("Open MoeWalls Engine", self.show_front),
            ("Pause / Resume", self.toggle_pause),
            ("Mute / Unmute", lambda: self.mute_chk.setChecked(not self.mute_chk.isChecked())),
            ("Stop Wallpaper", self.stop_wallpaper),
            ("Quit", self.quit_app)
        ]:
            a = QAction(text, m)
            a.triggered.connect(fn)
            m.addAction(a)

        self.tray.setContextMenu(m)
        self.tray.setToolTip(APP_NAME)
        self.tray.activated.connect(
            lambda r: self.show_front() if r == QSystemTrayIcon.ActivationReason.Trigger else None
        )
        self.tray.show()

    def show_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self):
        if hasattr(self, 'gpu_monitor') and self.gpu_monitor:
            try:
                self.gpu_monitor.close()
            except Exception:
                pass
        self.engine.stop(restore=True)
        self.tray.hide()
        QApplication.quit()

    def closeEvent(self, e):
        e.ignore()
        self.hide()
        if not self._told_tray:
            self.tray.showMessage(APP_NAME, "Running in background. Click or right-click the tray icon to restore or quit.")
            self._told_tray = True

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            f = u.toLocalFile()
            if f.lower().endswith(VIDEO_EXTS):
                self.apply_wallpaper(f)
                return
        self.say("Dropped file is not a supported video format.")


# ───────────────────────── Application Entry Point ─────────────────────────
def main():
    args = sys.argv[1:]
    tray_only = "--tray" in args
    vids = [a for a in args if not a.startswith("--")]

    if IS_WIN:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Sanuga.MoeWallsLiveEngine")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Single-instance enforcement
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if sock.waitForConnected(300):
        target = os.path.abspath(vids[0]) if vids else "SHOW"
        sock.write(target.encode("utf-8"))
        sock.flush()
        sock.waitForBytesWritten(1000)
        return 0

    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)

    cfg = load_cfg()
    win = MainWindow(cfg)

    def on_conn():
        c = server.nextPendingConnection()
        c.waitForReadyRead(500)
        msg = bytes(c.readAll()).decode("utf-8", "ignore").strip()
        if msg == "SHOW" or not msg:
            win.show_front()
        else:
            win.apply_wallpaper(msg)

    server.newConnection.connect(on_conn)

    # Initial video application
    if vids:
        win.apply_wallpaper(vids[0])
    elif cfg.get("last") and os.path.isfile(cfg["last"]):
        win.apply_wallpaper(cfg["last"])

    if not tray_only:
        win.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
