"""Textual UI for Audiobook Downloader."""

from __future__ import annotations

import io
import os

from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Input,
    Label,
    ListItem,
    ListView,
    LoadingIndicator,
    RadioButton,
    RadioSet,
    RichLog,
    Static,
)
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual import on, work
from textual.reactive import reactive
from rich.console import Console

from scrapers import get_scraper
from search import search_all
import main as _main
from utils import sanitize_book_title


# ── Cover art ─────────────────────────────────────────────────────────────────

def _render_cover(artwork_data: bytes, width: int = 28) -> str:
    """Render image bytes as Rich markup using unicode half-block characters."""
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(artwork_data)).convert("RGB")
        h = max(1, int(width * img.height / img.width / 2))
        img = img.resize((width, h * 2), Image.LANCZOS)
        rows: list[str] = []
        for y in range(0, h * 2, 2):
            row = ""
            for x in range(width):
                r1, g1, b1 = img.getpixel((x, y))
                r2, g2, b2 = img.getpixel((x, y + 1))
                row += f"[rgb({r2},{g2},{b2}) on rgb({r1},{g1},{b1})]▄[/]"
            rows.append(row)
        return "\n".join(rows)
    except Exception:
        return "\n".join(["[dim]  (no cover)[/dim]"] * 10)


# ── Screens ───────────────────────────────────────────────────────────────────

class HomeScreen(Screen):
    BINDINGS = [("ctrl+q", "app.quit", "Quit")]

    def compose(self) -> ComposeResult:
        with Container(id="home-card"):
            yield Label("🎧  Audiobook Downloader", id="home-title")
            yield Label("Download from any supported site", id="home-sub")
            with RadioSet(id="mode"):
                yield RadioButton("Paste URL", value=True, id="rb-url")
                yield RadioButton("Search by title", id="rb-search")
            yield Input(placeholder="https://tokybook.com/...", id="main-input")
            yield Input(placeholder="Author name (optional)", id="author-input")
            yield Button("Go  ▶", variant="primary", id="go-btn")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#author-input").display = False
        self.query_one("#main-input", Input).focus()

    @on(RadioSet.Changed, "#mode")
    def _mode_changed(self, event: RadioSet.Changed) -> None:
        is_search = event.pressed.id == "rb-search"
        self.query_one("#main-input", Input).placeholder = (
            "Book title..." if is_search else "https://tokybook.com/..."
        )
        self.query_one("#author-input").display = is_search

    @on(Button.Pressed, "#go-btn")
    @on(Input.Submitted)
    def _go(self) -> None:
        val = self.query_one("#main-input", Input).value.strip()
        if not val:
            self.notify("Please enter a URL or title.", severity="warning")
            return
        mode = self.query_one("#mode", RadioSet)
        if mode.pressed_index == 0:
            scraper = get_scraper(val)
            if not scraper:
                self.notify("Unsupported site URL.", severity="error")
                return
            self.app.push_screen(BookInfoScreen(url=val, scraper=scraper))
        else:
            author = self.query_one("#author-input", Input).value.strip()
            self.app.push_screen(SearchScreen(query=f"{val} {author}".strip()))


class SearchScreen(Screen):
    BINDINGS = [("escape", "go_back", "Back")]

    def __init__(self, query: str) -> None:
        super().__init__()
        self._query = query
        self._results: list[tuple[str, str, str]] = []

    def compose(self) -> ComposeResult:
        with Container(id="search-card"):
            yield Label(f'Searching: "{self._query}"', id="search-heading")
            yield LoadingIndicator(id="spinner")
            yield Label("No results found across all sites.", id="no-results")
            yield ListView(id="results-list")
            yield Button("← Back", variant="default", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#no-results").display = False
        self.query_one("#results-list").display = False
        self._do_search()

    @work(thread=True)
    def _do_search(self) -> None:
        results = list(search_all(self._query))
        self.app.call_from_thread(self._show_results, results)

    def _show_results(self, results: list) -> None:
        self.query_one("#spinner").display = False
        if not results:
            self.query_one("#no-results").display = True
            return
        self._results = results
        lv = self.query_one("#results-list", ListView)
        for site, title, _ in results:
            lv.append(ListItem(Label(f"[bold]{title}[/bold]\n[dim]{site}[/dim]")))
        lv.display = True

    @on(ListView.Selected, "#results-list")
    def _pick(self, event: ListView.Selected) -> None:
        idx = event.list_view.index
        _, _, url = self._results[idx]
        scraper = get_scraper(url)
        if scraper:
            self.app.switch_screen(BookInfoScreen(url=url, scraper=scraper))

    @on(Button.Pressed, "#back-btn")
    def action_go_back(self) -> None:
        self.app.pop_screen()


class BookInfoScreen(Screen):
    BINDINGS = [("escape", "go_back", "Back")]

    def __init__(self, url: str, scraper) -> None:
        super().__init__()
        self._url = url
        self._scraper = scraper
        self._book_data: dict | None = None

    def compose(self) -> ComposeResult:
        with Container(id="book-card"):
            yield LoadingIndicator(id="book-spinner")
            with Horizontal(id="book-body"):
                yield Static("", id="cover-art")
                with Vertical(id="book-meta"):
                    yield Label("", id="meta-title")
                    yield Label("", id="meta-author")
                    yield Label("", id="meta-narrator")
                    yield Label("", id="meta-year")
                    yield Label("", id="meta-chapters")
                    yield Label("", id="meta-site")
            with Horizontal(id="book-actions"):
                yield Button("Download  ▶", variant="primary", id="dl-btn")
                yield Button("← Back", variant="default", id="back-btn")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#book-body").display = False
        self.query_one("#book-actions").display = False
        self._fetch()

    @work(thread=True)
    def _fetch(self) -> None:
        book_data = self._scraper.fetch_book_data(self._url)
        if book_data:
            book_data["title"] = sanitize_book_title(
                book_data.get("title", "Unknown Book")
            )
        self.app.call_from_thread(self._show, book_data)

    def _show(self, book_data: dict | None) -> None:
        self.query_one("#book-spinner").display = False
        if not book_data:
            self.notify("Could not load book data.", severity="error")
            return

        self._book_data = book_data

        # Cover art
        if book_data.get("artwork_data"):
            self.query_one("#cover-art", Static).update(
                _render_cover(book_data["artwork_data"])
            )

        # Metadata
        title = book_data.get("title", "Unknown")
        author = book_data.get("author") or "—"
        narrator = book_data.get("narrator")
        year = book_data.get("year")
        n = len(book_data.get("chapters", []))
        site = book_data.get("site", "")

        self.query_one("#meta-title", Label).update(f"[bold]{title}[/bold]")
        self.query_one("#meta-author", Label).update(f"[dim]by[/dim]  {author}")
        if narrator:
            self.query_one("#meta-narrator", Label).update(
                f"[dim]read by[/dim]  {narrator}"
            )
        if year:
            self.query_one("#meta-year", Label).update(f"[dim]year[/dim]  {year}")
        self.query_one("#meta-chapters", Label).update(f"[dim]chapters[/dim]  {n}")
        if site:
            self.query_one("#meta-site", Label).update(f"[dim]source[/dim]  {site}")

        self.query_one("#book-body").display = True
        self.query_one("#book-actions").display = True

    @on(Button.Pressed, "#dl-btn")
    def _download(self) -> None:
        if self._book_data:
            self.app.push_screen(DownloadScreen(book_data=self._book_data))

    @on(Button.Pressed, "#back-btn")
    def action_go_back(self) -> None:
        self.app.pop_screen()


class DownloadScreen(Screen):
    # Disable escape while downloading to avoid partial downloads
    BINDINGS = [("escape", "noop", "")]

    def __init__(self, book_data: dict) -> None:
        super().__init__()
        self._book_data = book_data
        self._done = False

    def compose(self) -> ComposeResult:
        with Container(id="dl-card"):
            yield Label(
                f"[bold]{self._book_data['title']}[/bold]", id="dl-book-title"
            )
            yield Label("", id="dl-status")
            yield RichLog(id="dl-log", highlight=True, markup=True, wrap=True)
            with Horizontal(id="dl-footer"):
                yield Button("← New Download", variant="primary", id="done-btn")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#dl-footer").display = False
        self._start()

    @work(thread=True)
    def _start(self) -> None:
        log = self.query_one("#dl-log", RichLog)

        def ui_log(msg: str) -> None:
            self.app.call_from_thread(log.write, msg)

        def ui_status(msg: str) -> None:
            self.app.call_from_thread(
                self.query_one("#dl-status", Label).update, msg
            )

        # Redirect main.py's console so Rich Progress doesn't corrupt Textual's display
        null_console = Console(file=io.StringIO(), quiet=True)
        old_console = _main.console
        _main.console = null_console

        try:
            ui_status("[cyan]Downloading chapters...[/cyan]")
            ui_log(f"[cyan]Starting:[/cyan] {self._book_data['title']}")

            book_dir, chapter_files = _main.download_and_tag_audiobook(
                self._book_data
            )

            ui_log(f"[green]✓ Downloaded {len(chapter_files)} chapters[/green]")

            if chapter_files:
                ui_status("[cyan]Combining into one file...[/cyan]")
                ui_log("[cyan]Combining chapters...[/cyan]")
                _main.create_combined_audiobook(
                    self._book_data, book_dir, chapter_files
                )
                author = self._book_data.get("author", "")
                combined_name = (
                    f"{self._book_data['title']} - {author}"
                    if author
                    else self._book_data["title"]
                )
                ui_log(f"[green]✓ Combined file:[/green] {combined_name}.mp3")

            ui_status("[bold green]Done![/bold green]")
            ui_log(f"\n[bold green]Saved to:[/bold green] {book_dir}")
        except Exception as e:
            ui_log(f"[red]Error: {e}[/red]")
            ui_status("[red]Download failed.[/red]")
        finally:
            _main.console = old_console

        self.app.call_from_thread(self._finish)

    def _finish(self) -> None:
        self.query_one("#dl-footer").display = True
        self.BINDINGS = [("escape", "go_home", "Home")]

    @on(Button.Pressed, "#done-btn")
    def action_go_home(self) -> None:
        # Pop back to HomeScreen
        self.app.pop_screen()
        self.app.pop_screen()

    def action_noop(self) -> None:
        pass


# ── App ───────────────────────────────────────────────────────────────────────

CSS = """
/* ── Global ── */
Screen {
    background: $background;
    align: center middle;
}

Footer {
    background: $surface;
}

/* ── Home ── */
#home-card {
    width: 64;
    height: auto;
    border: round $primary;
    padding: 2 4;
    background: $surface;
}

#home-title {
    text-align: center;
    text-style: bold;
    color: $primary;
    margin-bottom: 0;
    width: 100%;
}

#home-sub {
    text-align: center;
    color: $text-muted;
    margin-bottom: 2;
    width: 100%;
}

#mode {
    height: auto;
    border: none;
    background: transparent;
    margin-bottom: 1;
}

#main-input, #author-input {
    margin-bottom: 1;
}

#go-btn {
    width: 100%;
    margin-top: 1;
}

/* ── Search ── */
#search-card {
    width: 80;
    height: auto;
    max-height: 80vh;
    border: round $primary;
    padding: 2 4;
    background: $surface;
}

#search-heading {
    text-style: bold;
    color: $primary;
    margin-bottom: 1;
}

#no-results {
    color: $warning;
    margin-bottom: 1;
}

#results-list {
    height: auto;
    max-height: 28;
    margin-bottom: 1;
}

/* ── Book Info ── */
#book-card {
    width: 94;
    height: auto;
    border: round $primary;
    padding: 2 4;
    background: $surface;
}

#book-body {
    height: auto;
    margin-bottom: 2;
}

#cover-art {
    width: 30;
    margin-right: 3;
    height: auto;
}

#book-meta {
    width: 1fr;
    height: auto;
}

#meta-title {
    color: $primary;
    margin-bottom: 1;
    text-wrap: wrap;
}

#meta-author, #meta-narrator, #meta-year, #meta-chapters, #meta-site {
    color: $text;
    margin-bottom: 0;
}

#book-actions {
    height: auto;
}

#dl-btn {
    margin-right: 1;
}

/* ── Download ── */
#dl-card {
    width: 94;
    height: 88vh;
    border: round $primary;
    padding: 2 4;
    background: $surface;
}

#dl-book-title {
    color: $primary;
    margin-bottom: 0;
}

#dl-status {
    margin-bottom: 1;
    height: 1;
}

#dl-log {
    height: 1fr;
    border: round $surface-lighten-2;
    padding: 0 1;
    margin-bottom: 1;
}

#dl-footer {
    height: auto;
}
"""


class AudiobookApp(App):
    CSS = CSS
    TITLE = "Audiobook Downloader"
    SUB_TITLE = "tokybook · goldenaudiobook · audiozaic · more"

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())


if __name__ == "__main__":
    if os.system("ffmpeg -version > /dev/null 2>&1") != 0:
        print("Error: ffmpeg is not installed. See README for install instructions.")
        raise SystemExit(1)
    AudiobookApp().run()
