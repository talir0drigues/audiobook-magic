"""PyQt6 GUI for Audiobook Downloader."""

from __future__ import annotations

import functools
import io
import os
import sys
import traceback

from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QProgressBar,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath
from rich.console import Console

from scrapers import get_scraper
from search import search_all
import main as _main
from utils import sanitize_book_title


# ── Palette ────────────────────────────────────────────────────────────────────
#  _BG    — root page background         QWidget#bg (every screen's outer container)
#  _WIN   — window/panel surface         QFrame#panel (the rounded window card)
#  _CARD  — inner card/row surface       QFrame#card, #prog-card, #act-row
#  _BDR   — default border               card/act-row borders at rest
#  _BDRH  — highlighted border           panel border, scrollbar handle, error state
#  _LAV   — lavender accent              active tab, download progress bar, spin icons
#  _PINK  — pink accent                  combine progress bar, gradient endpoints
#  _DONE  — soft purple (done state)     done progress bar, saved chip, done icons
#  _RED   — red accent                   danger button, error activity icons
#  _TEXT  — primary text                 body copy, titles, button labels
#  _DIM   — dimmed text                  inactive tabs, placeholder text, back button
#  _FAINT — very dim / decorative        skip activity icons, subtle separators

_BG    = "#000000"
_WIN   = "#111111"
_CARD  = "#1a1a1a"
_BDR   = "#261640"
_BDRH  = "#37204e"
_LAV   = "#d8b4fe"
_PINK  = "#f9a8d4"
_DONE  = "#c4b5fd"
_RED   = "#fca5a5"
_TEXT  = "#ac97ff"
_DIM   = "#7876bb"
_FAINT = "#705597"

_TAB_ON = (
    f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
    f"stop:0 rgba(216,180,254,46),stop:1 rgba(249,168,212,30));"
    f" border: 1px solid rgba(216,180,254,56); color: {_LAV};"
    f" border-radius: 7px; padding: 7px 16px; font-weight: 600; font-size: 13px; }}"
)
_TAB_OFF = (
    f"QPushButton {{ background: transparent; border: none; color: {_DIM};"
    f" border-radius: 7px; padding: 7px 16px; font-weight: 500; font-size: 13px; }}"
    f" QPushButton:hover {{ color: {_TEXT}; }}"
)

APP_QSS = f"""
* {{
    font-family: ".AppleSystemUIFont", "Segoe UI", system-ui, Arial, sans-serif;
    font-size: 13px;
    color: {_TEXT};
}}
QWidget#bg {{ background: {_BG}; }}
QWidget {{ background: transparent; }}

QFrame#panel {{
    background: {_WIN};
    border: 1px solid {_BDRH};
    border-radius: 16px;
}}
QFrame#card {{
    background: {_CARD};
    border: 1px solid {_BDR};
    border-radius: 12px;
}}
QFrame#prog-card {{
    background: {_CARD};
    border: 1px solid {_BDR};
    border-radius: 12px;
}}
QFrame#act-row {{
    background: {_CARD};
    border: 1px solid {_BDR};
    border-radius: 9px;
}}
QFrame#saved-chip {{
    background: rgba(196,181,253,20);
    border: 1px solid rgba(196,181,253,46);
    border-radius: 9px;
}}
QFrame#tabs-bg {{
    background: rgba(0,0,0,160);
    border: 1px solid {_BDR};
    border-radius: 10px;
}}

QLineEdit {{
    background: rgba(0,0,0,170);
    border: 1px solid {_BDR};
    border-radius: 9px;
    padding: 8px 12px;
    color: rgba(255,255,255,165);
    selection-background-color: {_LAV};
    selection-color: #120826;
}}
QLineEdit:focus {{ border-color: {_LAV}; }}

QPushButton {{
    border-radius: 9px;
    padding: 9px 18px;
    font-size: 13px;
    font-weight: 600;
    border: none;
}}
QPushButton#primary {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 rgba(216,180,254,56),stop:1 rgba(249,168,212,38));
    border: 1px solid rgba(216,180,254,77);
    color: {_LAV};
}}
QPushButton#primary:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 rgba(216,180,254,90),stop:1 rgba(249,168,212,65));
}}
QPushButton#ghost {{
    background: rgba(255,255,255,10);
    border: 1px solid {_BDR};
    color: {_DIM};
}}
QPushButton#ghost:hover {{ border-color: {_LAV}; color: {_LAV}; }}
QPushButton#danger {{
    background: rgba(252,165,165,20);
    border: 1px solid rgba(252,165,165,46);
    color: {_RED};
}}
QPushButton#danger:hover {{ background: rgba(252,165,165,40); }}

QProgressBar {{
    background: rgba(255,255,255,15);
    border: none;
    border-radius: 2px;
    max-height: 4px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {_LAV},stop:1 {_PINK});
    border-radius: 2px;
}}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 6px; margin: 2px 0;
}}
QScrollBar::handle:vertical {{
    background: {_BDRH}; border-radius: 3px; min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_slot(fn):
    """Prevent PyQt6 from calling abort() when a slot raises an exception."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            traceback.print_exc()
    return wrapper


def _lbl(text: str, size: int = 13, color: str = _TEXT, bold: bool = False) -> QLabel:
    w = QLabel(text)
    style = f"color:{color}; font-size:{size}px;"
    if bold:
        style += " font-weight:700;"
    w.setStyleSheet(style)
    w.setWordWrap(True)
    return w


def _cap_lbl(text: str) -> QLabel:
    w = QLabel(text.upper())
    w.setStyleSheet(
        f"color:{_FAINT}; font-size:10px; letter-spacing:2px; font-weight:600;"
    )
    return w


def _rounded_pixmap(data: bytes, size: int = 110) -> QPixmap | None:
    try:
        pix = QPixmap()
        if not pix.loadFromData(data):
            return None
        w, h = pix.width(), pix.height()
        side = min(w, h)
        pix = pix.copy((w - side) // 2, (h - side) // 2, side, side)
        pix = pix.scaled(
            size, size,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        result = QPixmap(size, size)
        result.fill(Qt.GlobalColor.transparent)
        p = QPainter(result)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0, 0, size, size, 12, 12)
        p.setClipPath(path)
        p.drawPixmap(0, 0, pix)
        p.end()
        return result
    except Exception:
        return None


# ── Workers ────────────────────────────────────────────────────────────────────

class SearchWorker(QThread):
    results = pyqtSignal(list)

    def __init__(self, query: str) -> None:
        super().__init__()
        self._query = query

    def run(self) -> None:
        self.results.emit(list(search_all(self._query)))


class FetchWorker(QThread):
    book_ready = pyqtSignal(object)

    def __init__(self, url: str, scraper) -> None:
        super().__init__()
        self._url = url
        self._scraper = scraper

    def run(self) -> None:
        try:
            data = self._scraper.fetch_book_data(self._url)
            if data:
                data["title"] = sanitize_book_title(data.get("title", "Unknown Book"))
        except Exception:
            data = None
        self.book_ready.emit(data)


class DownloadWorker(QThread):
    dl_progress      = pyqtSignal(int, int, str)
    combine_progress = pyqtSignal(int, int, str)
    combine_started  = pyqtSignal()
    activity         = pyqtSignal(str, str, str)   # icon_type, text, meta
    finished         = pyqtSignal(str)
    error            = pyqtSignal(str)

    def __init__(self, book_data: dict) -> None:
        super().__init__()
        self._book_data = book_data

    def run(self) -> None:
        book_data = self._book_data
        n = len(book_data.get("chapters", []))
        null_console = Console(file=io.StringIO(), quiet=True)
        old_console = _main.console
        _main.console = null_console
        try:
            self.activity.emit("spin", f"Downloading {n} chapters…", "")

            def dl_cb(current: int, total: int, title: str) -> None:
                self.dl_progress.emit(current, total, title)

            book_dir, chapter_files = _main.download_and_tag_audiobook(
                book_data, progress_callback=dl_cb
            )
            self.activity.emit(
                "done",
                f"{len(chapter_files)} chapters downloaded and tagged",
                "",
            )

            if chapter_files:
                self.combine_started.emit()
                self.activity.emit("spin", "Merging audio, embedding chapter markers…", "")

                def combine_cb(current: int, total: int, title: str) -> None:
                    self.combine_progress.emit(current, total, title)

                _main.create_combined_audiobook(
                    book_data, book_dir, chapter_files, progress_callback=combine_cb
                )
                author = book_data.get("author", "")
                combined_name = (
                    f"{book_data['title']} - {author}" if author else book_data["title"]
                )
                self.activity.emit(
                    "done",
                    f"{combined_name}.mp3",
                    f"{len(chapter_files)} chapters",
                )

            self.finished.emit(book_dir)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            _main.console = old_console


# ── Reusable widgets ───────────────────────────────────────────────────────────

class ProgressCard(QFrame):
    def __init__(self, label: str, bar_id: str = "dl-bar") -> None:
        super().__init__()
        self.setObjectName("prog-card")
        self._bar_id = bar_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 10)
        self._header_lbl = _cap_lbl(label)
        self._fraction = _lbl("0 / 0", 12, _LAV)
        self._fraction.setStyleSheet(
            f"font-size:12px; font-weight:600; color:{_LAV};"
        )
        header.addWidget(self._header_lbl)
        header.addStretch()
        header.addWidget(self._fraction)
        layout.addLayout(header)

        self._bar = QProgressBar()
        self._bar.setTextVisible(False)
        self._bar.setMaximumHeight(4)
        self._bar.setValue(0)
        self._bar.setMaximum(100)
        layout.addWidget(self._bar)
        layout.addSpacing(8)

        self._chapter_lbl = _lbl("", 12, _FAINT)
        self._chapter_lbl.setWordWrap(False)
        layout.addWidget(self._chapter_lbl)

    def set_progress(self, current: int, total: int, title: str = "") -> None:
        self._fraction.setText(f"{current} / {total}")
        if total > 0:
            self._bar.setMaximum(total)
            self._bar.setValue(current)
        self._chapter_lbl.setText(title)

    def set_done(self, total: int, subtitle: str = "Complete") -> None:
        self._fraction.setText(f"{total} / {total}")
        self._fraction.setStyleSheet(
            f"font-size:12px; font-weight:600; color:{_DONE};"
        )
        if total > 0:
            self._bar.setMaximum(total)
            self._bar.setValue(total)
        self._bar.setStyleSheet(
            "QProgressBar::chunk {"
            f" background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {_LAV},stop:1 {_DONE});"
            " border-radius: 2px; }"
        )
        self._chapter_lbl.setText(subtitle)
        self._chapter_lbl.setStyleSheet(f"font-size:12px; color:rgba(196,181,253,100);")


class ActivityRow(QFrame):
    _ICONS = {
        "spin": ("↓",  f"background:rgba(216,180,254,23); color:{_LAV};"),
        "done": ("✓",  f"background:rgba(196,181,253,20); color:{_DONE};"),
        "skip": ("↷",  f"background:rgba(255,255,255,8);  color:{_FAINT};"),
        "err":  ("✕",  f"background:rgba(252,165,165,20); color:{_RED};"),
        "wait": ("⟳",  f"background:rgba(216,180,254,23); color:{_LAV};"),
    }

    def __init__(self, icon_type: str, text: str, meta: str = "") -> None:
        super().__init__()
        self.setObjectName("act-row")

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)

        char, icon_style = self._ICONS.get(icon_type, self._ICONS["skip"])
        icon_lbl = QLabel(char)
        icon_lbl.setFixedSize(22, 22)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            f"{icon_style} border-radius: 6px; font-size: 11px;"
        )
        row.addWidget(icon_lbl)

        text_lbl = _lbl(text, 12, _DIM if icon_type != "skip" else _FAINT)
        text_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        row.addWidget(text_lbl)

        if meta:
            meta_lbl = _lbl(meta, 10, _FAINT)
            meta_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(meta_lbl)


# ── Screens ────────────────────────────────────────────────────────────────────

class HomeScreen(QWidget):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__()
        self._win = window
        self._save_dir = os.path.expanduser("~/Audiobooks")
        self._mode = "url"
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner_v = QVBoxLayout(inner)
        inner_v.setContentsMargins(30, 30, 30, 30)
        inner_v.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(540)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(28, 28, 28, 28)
        pl.setSpacing(0)

        # Title
        title_lbl = QLabel("🎧  Audiobook Downloader")
        title_lbl.setStyleSheet(f"font-size:20px; font-weight:700; color:{_LAV};")
        pl.addWidget(title_lbl)
        pl.addSpacing(4)
        pl.addWidget(_lbl("tokybook · goldenaudiobook · audiozaic · and more", 12, _FAINT))
        pl.addSpacing(22)

        # Tabs
        tabs_bg = QFrame()
        tabs_bg.setObjectName("tabs-bg")
        tabs_bg.setFixedHeight(42)
        tabs_row = QHBoxLayout(tabs_bg)
        tabs_row.setContentsMargins(4, 4, 4, 4)
        tabs_row.setSpacing(2)
        self._tab_url = QPushButton("Paste URL")
        self._tab_url.setStyleSheet(_TAB_ON)
        self._tab_url.clicked.connect(lambda: self._set_mode("url"))
        self._tab_search = QPushButton("Search by title")
        self._tab_search.setStyleSheet(_TAB_OFF)
        self._tab_search.clicked.connect(lambda: self._set_mode("search"))
        tabs_row.addWidget(self._tab_url)
        tabs_row.addWidget(self._tab_search)
        pl.addWidget(tabs_bg)
        pl.addSpacing(18)

        # Form card
        card = QFrame()
        card.setObjectName("card")
        card_v = QVBoxLayout(card)
        card_v.setContentsMargins(18, 18, 18, 18)
        card_v.setSpacing(14)

        # URL field
        self._url_section = QWidget()
        us = QVBoxLayout(self._url_section)
        us.setContentsMargins(0, 0, 0, 0)
        us.setSpacing(6)
        us.addWidget(_cap_lbl("Book URL"))
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("https://tokybook.com/…")
        self._url_input.returnPressed.connect(self._go)
        us.addWidget(self._url_input)
        card_v.addWidget(self._url_section)

        # Search fields
        self._search_section = QWidget()
        ss = QVBoxLayout(self._search_section)
        ss.setContentsMargins(0, 0, 0, 0)
        ss.setSpacing(14)

        t_grp = QVBoxLayout()
        t_grp.setSpacing(6)
        t_grp.addWidget(_cap_lbl("Book Title"))
        self._title_input = QLineEdit()
        self._title_input.setPlaceholderText("e.g. Project Hail Mary")
        self._title_input.returnPressed.connect(self._go)
        t_grp.addWidget(self._title_input)

        a_grp = QVBoxLayout()
        a_grp.setSpacing(6)
        a_grp.addWidget(_cap_lbl("Author (optional)"))
        self._author_input = QLineEdit()
        self._author_input.setPlaceholderText("e.g. Andy Weir")
        self._author_input.returnPressed.connect(self._go)
        a_grp.addWidget(self._author_input)

        ss.addLayout(t_grp)
        ss.addLayout(a_grp)
        card_v.addWidget(self._search_section)
        self._search_section.setVisible(False)

        # Save to
        save_grp = QVBoxLayout()
        save_grp.setSpacing(6)
        save_grp.addWidget(_cap_lbl("Save to"))
        save_row = QHBoxLayout()
        save_row.setSpacing(8)
        self._save_input = QLineEdit(self._save_dir)
        save_row.addWidget(self._save_input)
        browse = QPushButton("📁  Browse")
        browse.setObjectName("ghost")
        browse.setFixedWidth(108)
        browse.clicked.connect(self._browse)
        save_row.addWidget(browse)
        save_grp.addLayout(save_row)
        card_v.addLayout(save_grp)

        pl.addWidget(card)
        pl.addSpacing(14)

        self._go_btn = QPushButton("Download  ▶")
        self._go_btn.setObjectName("primary")
        self._go_btn.setFixedHeight(42)
        self._go_btn.clicked.connect(self._go)
        pl.addWidget(self._go_btn)

        inner_v.addWidget(panel)

    @_safe_slot
    def _set_mode(self, mode: str) -> None:
        self._mode = mode
        if mode == "url":
            self._tab_url.setStyleSheet(_TAB_ON)
            self._tab_search.setStyleSheet(_TAB_OFF)
            self._url_section.setVisible(True)
            self._search_section.setVisible(False)
            self._go_btn.setText("Download  ▶")
        else:
            self._tab_url.setStyleSheet(_TAB_OFF)
            self._tab_search.setStyleSheet(_TAB_ON)
            self._url_section.setVisible(False)
            self._search_section.setVisible(True)
            self._go_btn.setText("Search  🔍")

    @_safe_slot
    def _browse(self, *_) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Save Folder", self._save_dir)
        if path:
            self._save_dir = path
            self._save_input.setText(path)

    @_safe_slot
    def _go(self, *_) -> None:
        save_dir = self._save_input.text().strip() or self._save_dir
        if self._mode == "url":
            url = self._url_input.text().strip()
            if not url:
                return
            scraper = get_scraper(url)
            if not scraper:
                self._url_input.setStyleSheet(
                    f"border-color:{_RED}; background:rgba(252,165,165,10);"
                    f" border-radius:9px; padding:8px 12px; color:rgba(255,255,255,165);"
                )
                return
            self._win.push_screen(BookInfoScreen(self._win, url=url, scraper=scraper, save_dir=save_dir))
        else:
            title = self._title_input.text().strip()
            if not title:
                return
            author = self._author_input.text().strip()
            query = f"{title} {author}".strip()
            self._win.push_screen(SearchScreen(self._win, query=query, save_dir=save_dir))


class SearchScreen(QWidget):
    def __init__(self, window: "MainWindow", query: str, save_dir: str) -> None:
        super().__init__()
        self._win = window
        self._query = query
        self._save_dir = save_dir
        self._results: list[tuple[str, str, str]] = []
        self._build()
        self._search()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner_v = QVBoxLayout(inner)
        inner_v.setContentsMargins(30, 30, 30, 30)
        inner_v.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        self._panel = QFrame()
        self._panel.setObjectName("panel")
        self._panel.setFixedWidth(540)
        pl = QVBoxLayout(self._panel)
        pl.setContentsMargins(28, 28, 28, 28)
        pl.setSpacing(0)

        # Back nav
        nav = QHBoxLayout()
        nav.setSpacing(10)
        back_nav = QPushButton("← Back")
        back_nav.setObjectName("ghost")
        back_nav.clicked.connect(self._win.pop_screen)
        heading = _lbl(f'Results for "{self._query}"', 15, _TEXT, bold=True)
        nav.addWidget(back_nav)
        nav.addWidget(heading)
        nav.addStretch()
        pl.addLayout(nav)
        pl.addSpacing(18)

        # Status / spinner label
        self._status_lbl = _lbl("Searching…", 12, _FAINT)
        pl.addWidget(self._status_lbl)
        pl.addSpacing(8)

        # Results container (scroll area inside panel)
        self._results_area = QWidget()
        self._results_v = QVBoxLayout(self._results_area)
        self._results_v.setContentsMargins(0, 0, 0, 0)
        self._results_v.setSpacing(8)
        self._results_area.setVisible(False)
        pl.addWidget(self._results_area)
        pl.addSpacing(14)

        # Actions
        actions = QHBoxLayout()
        self._open_btn = QPushButton("Open Selected  →")
        self._open_btn.setObjectName("primary")
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._open_selected)
        actions.addStretch()
        actions.addWidget(self._open_btn)
        pl.addLayout(actions)

        inner_v.addWidget(self._panel)

        self._selected_idx: int | None = None

    def _search(self) -> None:
        self._worker = SearchWorker(self._query)
        self._worker.results.connect(self._show_results)
        self._worker.start()

    @_safe_slot
    def _show_results(self, results: list) -> None:
        self._results = results
        self._status_lbl.setVisible(False)
        if not results:
            self._status_lbl.setText("No results found across all supported sites.")
            self._status_lbl.setStyleSheet(f"color:{_RED}; font-size:13px;")
            self._status_lbl.setVisible(True)
            return
        for i, (site, title, _url) in enumerate(results):
            item = self._make_result_item(i, title, site)
            self._results_v.addWidget(item)
        self._results_v.addStretch()
        self._results_area.setVisible(True)

    def _make_result_item(self, idx: int, title: str, site: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        frame.setCursor(Qt.CursorShape.PointingHandCursor)
        frame.setProperty("idx", idx)

        v = QVBoxLayout(frame)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(3)
        v.addWidget(_lbl(title, 13, _TEXT, bold=True))
        v.addWidget(_lbl(site, 11, _FAINT))

        frame.mousePressEvent = lambda _e, i=idx: self._select(i)
        return frame

    def _select(self, idx: int) -> None:
        self._selected_idx = idx
        # Highlight selected item
        for i in range(self._results_area.layout().count() - 1):  # -1 for stretch
            item_widget = self._results_area.layout().itemAt(i).widget()
            if item_widget:
                if i == idx:
                    item_widget.setStyleSheet(
                        "QFrame { background: rgba(216,180,254,20);"
                        " border: 1px solid rgba(216,180,254,71); border-radius: 12px; }"
                    )
                else:
                    item_widget.setStyleSheet("")
        self._open_btn.setEnabled(True)

    @_safe_slot
    def _open_selected(self, *_) -> None:
        if self._selected_idx is None:
            return
        _site, _title, url = self._results[self._selected_idx]
        scraper = get_scraper(url)
        if scraper:
            self._win.replace_screen(
                BookInfoScreen(self._win, url=url, scraper=scraper, save_dir=self._save_dir)
            )


class BookInfoScreen(QWidget):
    def __init__(self, window: "MainWindow", url: str, scraper, save_dir: str) -> None:
        super().__init__()
        self._win = window
        self._url = url
        self._scraper = scraper
        self._save_dir = save_dir
        self._book_data: dict | None = None
        self._build()
        self._fetch()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner_v = QVBoxLayout(inner)
        inner_v.setContentsMargins(30, 30, 30, 30)
        inner_v.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(540)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(28, 28, 28, 28)
        pl.setSpacing(0)

        # Back nav
        nav = QHBoxLayout()
        nav.setSpacing(10)
        back_btn = QPushButton("← Back")
        back_btn.setObjectName("ghost")
        back_btn.clicked.connect(self._win.pop_screen)
        nav.addWidget(back_btn)
        nav.addWidget(_lbl("Book Details", 15, _TEXT, bold=True))
        nav.addStretch()
        pl.addLayout(nav)
        pl.addSpacing(18)

        # Loading state
        self._loading_lbl = _lbl("Loading…", 13, _FAINT)
        pl.addWidget(self._loading_lbl)

        # Book info card (hidden until loaded)
        self._book_card = QFrame()
        self._book_card.setObjectName("card")
        book_v = QVBoxLayout(self._book_card)
        book_v.setContentsMargins(18, 18, 18, 18)
        book_v.setSpacing(0)

        info_row = QHBoxLayout()
        info_row.setSpacing(20)
        info_row.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._cover_lbl = QLabel()
        self._cover_lbl.setFixedSize(110, 110)
        self._cover_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_lbl.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 rgba(216,180,254,46),stop:1 rgba(249,168,212,25));"
            f" border-radius: 12px; font-size: 32px;"
        )
        self._cover_lbl.setText("📖")
        info_row.addWidget(self._cover_lbl)

        meta_v = QVBoxLayout()
        meta_v.setSpacing(5)
        meta_v.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._meta_title    = _lbl("", 16, _TEXT, bold=True)
        self._meta_author   = _lbl("", 12, _DIM)
        self._meta_narrator = _lbl("", 12, _DIM)
        self._meta_year     = _lbl("", 12, _DIM)
        self._meta_badges   = _lbl("", 11, _FAINT)
        for w in (self._meta_title, self._meta_author, self._meta_narrator,
                  self._meta_year, self._meta_badges):
            meta_v.addWidget(w)
        meta_v.addStretch()
        info_row.addLayout(meta_v)
        book_v.addLayout(info_row)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"background: {_BDR}; max-height: 1px; border: none;")
        book_v.addSpacing(18)
        book_v.addWidget(div)
        book_v.addSpacing(18)

        actions = QHBoxLayout()
        back2 = QPushButton("← Back")
        back2.setObjectName("ghost")
        back2.clicked.connect(self._win.pop_screen)
        self._dl_btn = QPushButton("Download  ▶")
        self._dl_btn.setObjectName("primary")
        self._dl_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._dl_btn.clicked.connect(self._start_download)
        actions.addWidget(back2)
        actions.addWidget(self._dl_btn)
        book_v.addLayout(actions)

        self._book_card.setVisible(False)
        pl.addWidget(self._book_card)

        inner_v.addWidget(panel)

    def _fetch(self) -> None:
        self._worker = FetchWorker(self._url, self._scraper)
        self._worker.book_ready.connect(self._show)
        self._worker.start()

    @_safe_slot
    def _show(self, book_data: dict | None) -> None:
        self._loading_lbl.setVisible(False)
        if not book_data:
            self._loading_lbl.setText("Could not load book data. Check the URL and try again.")
            self._loading_lbl.setStyleSheet(f"color:{_RED}; font-size:13px;")
            self._loading_lbl.setVisible(True)
            return
        self._book_data = book_data

        # Cover art
        if book_data.get("artwork_data"):
            pix = _rounded_pixmap(book_data["artwork_data"], 110)
            if pix:
                self._cover_lbl.setPixmap(pix)
                self._cover_lbl.setText("")
                self._cover_lbl.setStyleSheet("border-radius: 12px;")

        # Metadata
        title    = book_data.get("title", "Unknown")
        author   = book_data.get("author") or "—"
        narrator = book_data.get("narrator")
        year     = book_data.get("year")
        n        = len(book_data.get("chapters", []))
        site     = book_data.get("site", "")

        self._meta_title.setText(title)
        self._meta_author.setText(f"by  {author}")
        self._meta_narrator.setText(f"read by  {narrator}" if narrator else "")
        self._meta_narrator.setVisible(bool(narrator))
        self._meta_year.setText(f"year  {year}" if year else "")
        self._meta_year.setVisible(bool(year))
        badges = f"{n} chapters" + (f"  ·  {site}" if site else "")
        self._meta_badges.setText(badges)

        self._book_card.setVisible(True)

    @_safe_slot
    def _start_download(self, *_) -> None:
        if self._book_data:
            self._book_data["save_dir"] = self._save_dir
            self._win.push_screen(DownloadScreen(self._win, book_data=self._book_data))


class DownloadScreen(QWidget):
    def __init__(self, window: "MainWindow", book_data: dict) -> None:
        super().__init__()
        self._win = window
        self._book_data = book_data
        self._total = len(book_data.get("chapters", []))
        self._build()
        self._start_download()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner_v = QVBoxLayout(inner)
        inner_v.setContentsMargins(30, 30, 30, 30)
        inner_v.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setFixedWidth(540)
        self._pl = QVBoxLayout(panel)
        self._pl.setContentsMargins(28, 28, 28, 28)
        self._pl.setSpacing(0)

        # Header
        header_v = QVBoxLayout()
        header_v.setSpacing(4)
        self._book_title_lbl = _lbl(self._book_data.get("title", ""), 17, _TEXT, bold=True)
        header_v.addWidget(self._book_title_lbl)

        status_row = QHBoxLayout()
        status_row.setSpacing(7)
        self._dot = QLabel("●")
        self._dot.setFixedWidth(14)
        self._dot.setStyleSheet(f"color:{_LAV}; font-size:8px;")
        self._status_lbl = _lbl("Starting…", 12, _DIM)
        status_row.addWidget(self._dot)
        status_row.addWidget(self._status_lbl)
        status_row.addStretch()
        header_v.addLayout(status_row)
        self._pl.addLayout(header_v)
        self._pl.addSpacing(18)

        # Download progress card
        self._dl_card = ProgressCard("Download")
        self._dl_card.set_progress(0, self._total, "Preparing…")
        self._pl.addWidget(self._dl_card)
        self._pl.addSpacing(10)

        # Combine progress card (hidden until combine phase)
        self._combine_card = ProgressCard("Combine")
        self._combine_card.set_progress(0, self._total, "Waiting…")
        self._combine_card.setVisible(False)
        self._pl.addWidget(self._combine_card)
        self._pl.addSpacing(10)

        # Activity feed
        self._feed_widget = QWidget()
        self._feed_v = QVBoxLayout(self._feed_widget)
        self._feed_v.setContentsMargins(0, 0, 0, 0)
        self._feed_v.setSpacing(8)
        self._feed_v.addStretch()
        self._pl.addWidget(self._feed_widget)
        self._pl.addSpacing(10)

        # Saved chip (hidden until done)
        self._saved_chip = QFrame()
        self._saved_chip.setObjectName("saved-chip")
        saved_row = QHBoxLayout(self._saved_chip)
        saved_row.setContentsMargins(12, 10, 12, 10)
        saved_row.setSpacing(8)
        saved_row.addWidget(_lbl("📁", 14, _DONE))
        self._saved_path_lbl = _lbl("", 12, _DONE)
        saved_row.addWidget(self._saved_path_lbl)
        saved_row.addStretch()
        self._saved_chip.setVisible(False)
        self._pl.addWidget(self._saved_chip)
        self._pl.addSpacing(14)

        # Actions
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self._new_btn = QPushButton("← New Download")
        self._new_btn.setObjectName("ghost")
        self._new_btn.setVisible(False)
        self._new_btn.clicked.connect(self._go_home)
        self._exit_btn = QPushButton("Exit  ✕")
        self._exit_btn.setObjectName("danger")
        self._exit_btn.clicked.connect(QApplication.instance().quit)
        actions.addStretch()
        actions.addWidget(self._new_btn)
        actions.addWidget(self._exit_btn)
        self._pl.addLayout(actions)

        inner_v.addWidget(panel)

    def _add_activity(self, icon_type: str, text: str, meta: str = "") -> None:
        row = ActivityRow(icon_type, text, meta)
        # Insert before the stretch
        count = self._feed_v.count()
        self._feed_v.insertWidget(count - 1, row)

    @_safe_slot
    def _start_download(self, *_) -> None:
        self._worker = DownloadWorker(self._book_data)
        self._worker.dl_progress.connect(self._on_dl_progress)
        self._worker.combine_progress.connect(self._on_combine_progress)
        self._worker.combine_started.connect(self._on_combine_started)
        self._worker.activity.connect(self._on_activity)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()
        self._status_lbl.setText("Downloading chapters…")
        self._status_lbl.setStyleSheet(f"font-size:12px; color:rgba(216,180,254,0.6);")

    @_safe_slot
    def _on_dl_progress(self, current: int, total: int, title: str) -> None:
        self._dl_card.set_progress(current, total, title)

    @_safe_slot
    def _on_combine_progress(self, current: int, total: int, title: str) -> None:
        self._combine_card.set_progress(current, total, title)

    @_safe_slot
    def _on_combine_started(self) -> None:
        self._dl_card.set_done(self._total, "All chapters downloaded")
        self._combine_card.setVisible(True)
        self._status_lbl.setText("Combining into single file…")
        self._status_lbl.setStyleSheet(f"font-size:12px; color:rgba(249,168,212,0.6);")

    @_safe_slot
    def _on_activity(self, icon_type: str, text: str, meta: str) -> None:
        self._add_activity(icon_type, text, meta)

    @_safe_slot
    def _on_finished(self, book_dir: str) -> None:
        n = self._total
        self._dl_card.set_done(n, "All chapters downloaded")
        self._combine_card.set_done(n, "Combined file ready")
        self._dot.setStyleSheet(f"color:{_DONE}; font-size:8px;")
        self._status_lbl.setText("All done!")
        self._status_lbl.setStyleSheet(f"font-size:12px; font-weight:600; color:{_DONE};")
        self._saved_path_lbl.setText(book_dir)
        self._saved_chip.setVisible(True)
        self._new_btn.setVisible(True)

    @_safe_slot
    def _on_error(self, msg: str) -> None:
        self._add_activity("err", f"Error: {msg}", "")
        self._status_lbl.setText("Download failed")
        self._status_lbl.setStyleSheet(f"font-size:12px; color:{_RED};")
        self._dot.setStyleSheet(f"color:{_RED}; font-size:8px;")
        self._new_btn.setVisible(True)

    @_safe_slot
    def _go_home(self, *_) -> None:
        # Pop down to HomeScreen
        while len(self._win._stack) > 1:
            self._win.pop_screen()


# ── Main window ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Audiobook Downloader")
        self.setMinimumSize(620, 600)
        self.resize(620, 760)

        root = QWidget()
        root.setObjectName("bg")
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)

        self._container = QStackedWidget()
        layout.addWidget(self._container)

        self._stack: list[QWidget] = []
        self.push_screen(HomeScreen(self))

    def push_screen(self, screen: QWidget) -> None:
        self._container.addWidget(screen)
        self._container.setCurrentWidget(screen)
        self._stack.append(screen)

    def pop_screen(self) -> None:
        if len(self._stack) <= 1:
            return
        old = self._stack.pop()
        self._container.setCurrentWidget(self._stack[-1])
        self._container.removeWidget(old)
        old.deleteLater()

    def replace_screen(self, screen: QWidget) -> None:
        if self._stack:
            old = self._stack.pop()
            self._container.addWidget(screen)
            self._container.setCurrentWidget(screen)
            self._container.removeWidget(old)
            old.deleteLater()
        self._stack.append(screen)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import subprocess

    if subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0:
        app = QApplication(sys.argv)
        msg = QMessageBox()
        msg.setWindowTitle("FFmpeg required")
        msg.setText(
            "FFmpeg is not installed.\n\n"
            "Install it with Homebrew:\n"
            "  brew install ffmpeg\n\n"
            "Or download from https://ffmpeg.org/"
        )
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.exec()
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("Audiobook Downloader")
    app.setStyleSheet(APP_QSS)

    # Fusion style for consistent cross-platform rendering
    app.setStyle("Fusion")
    app.setStyleSheet(APP_QSS)  # re-apply after setStyle

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
