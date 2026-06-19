# Audiobook Downloader

Downloads audiobooks from multiple sites, tags each chapter with ID3 metadata, and can combine all chapters into a single MP3 with embedded chapter markers.

> This project is intended for personal and educational use only. Please respect copyright laws and each site's terms of service.

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-Cross--Platform-009688)
![License](https://img.shields.io/badge/License-MIT-orange)

## Supported Sites

- [tokybook.com](https://tokybook.com)
- [goldenaudiobook.net](https://goldenaudiobook.net)
- [bigaudiobooks.net](https://bigaudiobooks.net)
- [audiozaic.com](https://audiozaic.com)
- [fulllengthaudiobooks.net](https://fulllengthaudiobooks.net)
- [hdaudiobooks.net](https://hdaudiobooks.net)
- [zaudiobooks.com](https://zaudiobooks.com)

## Features

- **Search by title** — type a book title and optional author instead of a URL; the script searches all supported sites and asks you to confirm before downloading
- **Chapter selection** — download all chapters or pick specific ones/ranges (e.g. `1-5, 8, 10`)
- **ID3 tagging** — embeds title, author, narrator, year, track number, and cover art into every chapter file
- **Combined file** — merges all chapters into a single `[Combined].mp3` with embedded chapter markers (compatible with VLC, Overcast, and most modern players)
- **Smart resume** — skips chapters that are already downloaded

## Setup

### Option 1 — Download and double-click (no setup required)

**macOS**

[![Download macOS](https://img.shields.io/badge/Download-macOS-black?logo=apple)](https://github.com/talir0drigues/audiobook-magic/releases/latest/download/AudiobookDownloader-macOS.zip)

1. Download and unzip — you'll get an `AudiobookDownloader-macOS` folder
2. Double-click `Audiobook Downloader.app` inside it

Installs Homebrew, FFmpeg, and uv automatically on the first run.

> **First time only — macOS will block the app. Two ways to allow it:**
> - Right-click the app → **Open** → click **Open** in the dialog, or
> - Try to open it normally, then go to **System Settings → Privacy & Security** → scroll down and click **Open Anyway**

**Windows**

[![Download Windows](https://img.shields.io/badge/Download-Windows-0078D4?logo=windows)](https://github.com/talir0drigues/audiobook-magic/releases/latest/download/AudiobookDownloader.exe)

Requires [FFmpeg](https://ffmpeg.org/) — install it once with `winget install ffmpeg`.

> First time only: Windows SmartScreen may warn "unrecognized app". Click **More info → Run anyway**.

---

### Option 2 — Command line (manual setup)

Requires [Python 3.11+](https://www.python.org/downloads/) and [FFmpeg](https://ffmpeg.org/).

**Install FFmpeg:**

```bash
# macOS
brew install ffmpeg

# Linux
sudo apt install ffmpeg

# Windows
winget install ffmpeg
```

**Run with uv (recommended — no separate install step):**

```bash
uv run main.py
```

**Run with pip:**

```bash
pip install -r requirements.txt
python main.py
```

## Usage

When the script starts:

```
Enter a book URL, or type 's' to search by title:
```

**By URL** — paste a link from any supported site.

**By search:**

```
Book title: Project Hail Mary
Author name (optional): Andy Weir

Searching for: Project Hail Mary Andy Weir

Found on tokybook.com: Project Hail Mary Audiobook – Andy Weir
  https://tokybook.com/project-hail-mary/
Is this the book you're looking for? (y/n):
```

Type `y` to confirm, `n` to check the next site. Once confirmed, the script will:

1. Show scraped metadata and let you edit any field
2. Ask whether to download all chapters or a specific selection
3. Download and tag each chapter into `Audiobooks/<Title>/`
4. Ask whether to create a combined single-file audiobook with chapter markers

## Playing the Combined File

The combined MP3 has embedded chapter markers (ID3 CHAP/CTOC). General music players ignore these — use a podcast or audiobook app to get chapter navigation and position memory.

**iOS (free)**
- [BookPlayer](https://apps.apple.com/app/bookplayer/id1138219998) — best option; shows chapters, remembers position, speed control, sleep timer

**Android (free)**
- [Voice Audiobook Player](https://play.google.com/store/apps/details?id=de.ph1b.audiobook) — open source, clean UI, remembers position per book
- [Smart AudioBook Player](https://play.google.com/store/apps/details?id=ak.alizandro.smartaudiobookplayer) — free tier available, chapter support, speed control
- [Listen Audiobook Player](https://play.google.com/store/apps/details?id=com.acmeandroid.listen) — free, handles large single-file audiobooks well

> **Note:** Chapter navigation (skipping between chapters) only works in apps that support ID3 chapter markers. All apps above do. VLC plays the file but shows no chapter UI.

## Adding a New Site

Most audiobook sites follow the same WordPress pattern. Add a config entry to `scrapers/generic.py`:

```python
"newsite.com": {
    "h1_selectors":    ["h1.entry-title"],
    "cover_selectors": [".wp-caption img"],
    "audio_selectors": ['.entry source[type="audio/mpeg"]'],
    "year_selector":   None,
    "author_first":    True,
    "split_re":        r"\s*[-–]\s*",
    "strip_re":        r"\s*Audiobook\s*$",
},
```

Then register it in `scrapers/__init__.py`:

```python
("newsite.com", lambda: GenericWordPressScraper("newsite.com"), "https://newsite.com"),
```

For sites with a non-standard structure, create a dedicated scraper class (see `scrapers/tokybook.py` or `scrapers/audiozaic.py` as examples) and add it to the registry the same way.

## Acknowledgements

- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [FFmpeg](https://ffmpeg.org/)
- [Requests](https://requests.readthedocs.io/)
- [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/bs4/doc/)
- [Mutagen](https://mutagen.readthedocs.io/)
- [Rich](https://github.com/Textualize/rich)
- [uv](https://github.com/astral-sh/uv)
