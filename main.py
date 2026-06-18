import os
import requests
import subprocess
from http.client import IncompleteRead
from mutagen.id3 import (
    ID3,
    APIC,
    TALB,
    TPE1,
    TPE2,
    TCON,
    TDRC,
    TRCK,
    TIT2,
    CHAP,
    CTOC,
    CTOCFlags,
    ID3NoHeaderError,
)
from mutagen.mp3 import MP3 as MP3File
from rich.table import Table
from rich.console import Console
from rich.progress import Progress
import time

from scrapers import get_scraper
from scrapers.tokybook import TokybookScraper
from utils import sanitize_book_title, parse_chapter_ranges, yes
from search import search_all


console = Console()



def create_combined_audiobook(book_data, book_dir, chapter_files):
    """Concatenates chapter MP3s into one file and embeds ID3 chapter markers."""
    title = book_data["title"]
    author = book_data.get("author", "")
    combined_name = f"{title} - {author}" if author else title
    combined_name = sanitize_book_title(combined_name)
    combined_path = os.path.join(book_dir, f"{combined_name}.mp3")
    concat_list = os.path.join(book_dir, "_concat.txt")

    with open(concat_list, "w", encoding="utf-8") as f:
        for path in chapter_files:
            # repr() produces a quoted string with any single-quotes escaped
            f.write(f"file {repr(path)}\n")

    # Measure each chapter's duration first (needed for both progress and CHAP markers)
    timestamps_ms = []
    chapter_durations_s = []
    cumulative = 0.0
    for path in chapter_files:
        timestamps_ms.append(int(cumulative * 1000))
        try:
            dur = MP3File(path).info.length
        except Exception:
            dur = 0.0
        chapter_durations_s.append(dur)
        cumulative += dur
    total_ms = int(cumulative * 1000)
    total_s = cumulative

    n = len(chapter_files)
    console.print(f"\n[cyan]Combining {n} chapters (~{int(total_s // 60)} min)...[/cyan]")

    with Progress(console=console) as progress:
        task = progress.add_task("[cyan]Combining...", total=n)

        # Run ffmpeg in a subprocess and track progress via -progress pipe
        progress_read, progress_write = os.pipe()
        try:
            proc = subprocess.Popen(
                [
                    "ffmpeg",
                    "-f", "concat", "-safe", "0",
                    "-i", concat_list,
                    "-map_metadata", "-1",
                    "-c:a", "libmp3lame", "-q:a", "2",
                    "-progress", f"pipe:{progress_write}",
                    "-y", "-loglevel", "error",
                    combined_path,
                ],
                pass_fds=(progress_write,),
            )
            os.close(progress_write)

            buf = b""
            current_chapter = 0
            with os.fdopen(progress_read, "rb") as pf:
                for raw in pf:
                    buf += raw
                    if b"\n" not in buf:
                        continue
                    line, buf = buf.split(b"\n", 1)
                    key, _, val = line.decode(errors="ignore").partition("=")
                    if key.strip() == "out_time_us":
                        try:
                            elapsed_s = int(val.strip()) / 1_000_000
                        except ValueError:
                            continue
                        # Advance chapter counter based on elapsed time
                        new_chapter = 0
                        for idx, start_ms in enumerate(timestamps_ms):
                            if elapsed_s * 1000 >= start_ms:
                                new_chapter = idx + 1
                        new_chapter = min(new_chapter, n)
                        if new_chapter > current_chapter:
                            chap_title = book_data["chapters"][new_chapter - 1]["title"] if new_chapter <= len(book_data["chapters"]) else f"Chapter {new_chapter}"
                            progress.update(task, completed=new_chapter, description=f"[cyan]Chapter {new_chapter}/{n}: {chap_title}")
                            current_chapter = new_chapter

            proc.wait()
            if proc.returncode != 0:
                console.print("[red]FFmpeg failed to create combined file.[/red]")
                return
        except Exception as e:
            console.print(f"[red]FFmpeg error: {e}[/red]")
            return
        finally:
            if os.path.exists(concat_list):
                os.remove(concat_list)

    # Build fresh ID3 tag with chapter markers
    id3 = ID3()
    id3.add(TIT2(encoding=3, text=title))
    id3.add(TALB(encoding=3, text=title))
    id3.add(TCON(encoding=3, text="Audiobook"))
    if book_data.get("author"):
        id3.add(TPE1(encoding=3, text=book_data["author"]))
    if book_data.get("narrator"):
        id3.add(TPE2(encoding=3, text=book_data["narrator"]))
    if book_data.get("year"):
        id3.add(TDRC(encoding=3, text=book_data["year"]))
    if book_data.get("artwork_data") and book_data.get("mime_type"):
        id3.add(
            APIC(
                encoding=3,
                mime=book_data["mime_type"],
                type=3,
                desc="Cover",
                data=book_data["artwork_data"],
            )
        )

    chapter_ids = []
    for i, chapter in enumerate(book_data["chapters"]):
        if i >= len(chapter_files):
            break
        chap_id = f"chp{i}"
        start_ms = timestamps_ms[i]
        end_ms = timestamps_ms[i + 1] if i + 1 < len(timestamps_ms) else total_ms
        id3.add(
            CHAP(
                element_id=chap_id,
                start_time=start_ms,
                end_time=end_ms,
                start_offset=0xFFFFFFFF,
                end_offset=0xFFFFFFFF,
                sub_frames=[TIT2(encoding=3, text=chapter["title"])],
            )
        )
        chapter_ids.append(chap_id)

    if chapter_ids:
        id3.add(
            CTOC(
                element_id="toc",
                flags=CTOCFlags.TOP_LEVEL | CTOCFlags.ORDERED,
                child_element_ids=chapter_ids,
                sub_frames=[TIT2(encoding=3, text=title)],
            )
        )

    id3.save(combined_path, v2_version=3)
    console.print(f"[bold green]Combined file saved:[/bold green] {combined_path}")
    if chapter_ids:
        console.print(
            f"[dim]  {len(chapter_ids)} chapter markers embedded. "
            "Visible in Overcast, Podcast Addict, and other podcast/audiobook apps.[/dim]"
        )

    # Clean up individual chapter files
    deleted = 0
    for path in chapter_files:
        try:
            os.remove(path)
            deleted += 1
        except OSError:
            pass
    if deleted:
        console.print(f"[dim]Removed {deleted} individual chapter file(s).[/dim]")


def download_and_tag_audiobook(book_data):
    sanitized_title = book_data["title"]
    author_name = book_data.get("author")
    narrator_name = book_data.get("narrator")
    year_text = book_data.get("year")
    artwork_data = book_data.get("artwork_data")
    mime_type = book_data.get("mime_type")

    book_dir = os.path.join(os.getcwd(), "Audiobooks", sanitized_title)
    os.makedirs(book_dir, exist_ok=True)

    total_chapters = len(book_data["chapters"])
    console.print(
        f"\n[green]Found {total_chapters} chapters. Starting download...[/green]\n"
    )

    downloaded_files = []

    with Progress() as progress:
        task = progress.add_task(
            f"[cyan]Downloading {sanitized_title}...", total=total_chapters
        )
        session = requests.Session()
        for i, chapter in enumerate(book_data["chapters"], start=1):
            link = chapter["url"]
            chapter_title = chapter["title"]
            final_file_name = os.path.join(book_dir, f"{chapter_title}.mp3")

            try:
                # --- CHECK IF FILE EXISTS ---
                if os.path.exists(final_file_name):
                    next_chapter_idx = i  # 'i' is 1-based; list[i] is the next chapter
                    is_last_existing = False

                    if next_chapter_idx < len(book_data["chapters"]):
                        next_title = book_data["chapters"][next_chapter_idx]["title"]
                        next_path = os.path.join(book_dir, f"{next_title}.mp3")
                        if not os.path.exists(next_path):
                            is_last_existing = True
                    else:
                        is_last_existing = True

                    if book_data.get("site") == "tokybook.com" and is_last_existing:
                        progress.log(
                            f"[yellow]Resume detected: Redownloading last found file ({chapter_title})...[/yellow]"
                        )
                        # Fall through to download logic below
                    else:
                        progress.log(
                            f"[dim]Skipping {chapter_title}, already exists.[/dim]"
                        )
                        downloaded_files.append(final_file_name)
                        progress.advance(task)
                        continue

                # --- DOWNLOAD LOGIC ---

                # 1. TOKYBOOK (New Parallel Downloader)
                if book_data.get("site") == "tokybook.com":
                    progress.log(
                        f"[cyan]Downloading {chapter_title} (Parallel)...[/cyan]"
                    )
                    temp_ts_file = os.path.join(book_dir, f"{chapter_title}.ts")
                    TokybookScraper.download_chapter(
                        chapter, book_data, temp_ts_file, progress
                    )

                    progress.log(f"[dim]Converting {chapter_title} to MP3...[/dim]")
                    try:
                        subprocess.run(
                            [
                                "ffmpeg",
                                "-i",
                                temp_ts_file,
                                "-y",
                                "-vn",
                                "-acodec",
                                "libmp3lame",
                                "-q:a",
                                "2",
                                "-loglevel",
                                "error",
                                final_file_name,
                            ],
                            check=True,
                        )
                        if os.path.exists(temp_ts_file):
                            os.remove(temp_ts_file)
                    except subprocess.CalledProcessError:
                        progress.log(
                            f"[red]FFmpeg conversion failed for {chapter_title}[/red]"
                        )
                        progress.advance(task)
                        continue

                # 2. Session-based sites (direct MP3 links)
                elif book_data.get("site") in (
                    "goldenaudiobook.net",
                    "zaudiobooks.com",
                    "audiozaic.com",
                ):
                    headers = book_data.get("site_headers", {})
                    progress.log(f"[cyan]Downloading {chapter_title}...[/cyan]")
                    download_chapters_session(
                        session, link, final_file_name, headers, chapter_title, progress
                    )

                # 3. GENERIC FALLBACK (yt-dlp)
                else:
                    progress.log(
                        f"[cyan]Downloading {chapter_title} (yt-dlp)...[/cyan]"
                    )
                    output_template = os.path.join(book_dir, f"{chapter_title}.%(ext)s")
                    command = [
                        "yt-dlp",
                        "-x",
                        "--audio-format",
                        "mp3",
                        "--audio-quality",
                        "0",
                        "--retries",
                        "5",
                    ]
                    if book_data.get("site_headers"):
                        for key, value in book_data["site_headers"].items():
                            command.extend(["--add-header", f"{key}: {value}"])

                    command.extend(["-o", output_template, link])
                    result = subprocess.run(command, capture_output=True, text=True)

                    if result.returncode != 0:
                        progress.log(f"[red]Error downloading {chapter_title}[/red]")
                        progress.advance(task)
                        continue

                # --- Add ID3 tags ---
                try:
                    audio = ID3(final_file_name)
                except ID3NoHeaderError:
                    audio = ID3()

                audio.add(TALB(encoding=3, text=sanitized_title))
                audio.add(TCON(encoding=3, text="Audiobook"))
                audio.add(TRCK(encoding=3, text=f"{i}/{total_chapters}"))
                audio.add(TIT2(encoding=3, text=chapter_title))
                if author_name:
                    audio.add(TPE1(encoding=3, text=author_name))
                if narrator_name:
                    audio.add(TPE2(encoding=3, text=narrator_name))
                if year_text:
                    audio.add(TDRC(encoding=3, text=year_text))
                if artwork_data and mime_type:
                    audio.add(
                        APIC(
                            encoding=3,
                            mime=mime_type,
                            type=3,
                            desc="Cover",
                            data=artwork_data,
                        )
                    )
                audio.save(final_file_name, v2_version=3)
                downloaded_files.append(final_file_name)

            except Exception as e:
                console.print(f"[red]Error downloading {chapter_title}: {e}[/red]")
                progress.advance(task)
                continue

            progress.log(f"[green]✔ Completed {chapter_title}[/green]")
            progress.advance(task)

    console.print(
        "\n[bold green]All chapters downloaded and tagged successfully![/bold green]"
    )
    return book_dir, downloaded_files


def download_chapters_session(
    session, url, final_file_name, headers, chapter_title, progress
):
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            with session.get(url, headers=headers, stream=True, timeout=(10, 180)) as r:
                if r.status_code == 403:
                    raise requests.exceptions.HTTPError("403 Forbidden")
                r.raise_for_status()
                with open(final_file_name, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            return
        except (requests.exceptions.RequestException, IncompleteRead) as e:
            progress.log(
                f"[yellow]Attempt {attempt + 1} failed for {chapter_title}: {e}[/yellow] [link={url}]{url}[/link]"
            )
            if isinstance(e, requests.exceptions.HTTPError) and "403" in str(e):
                subprocess.run(["open", url])  # works only on macOS
            if attempt < max_attempts - 1:
                time.sleep(5**attempt)
    raise Exception(
        f"Failed to download {chapter_title} ({url}) after {max_attempts} attempts"
    )


if __name__ == "__main__":
    console.print("[bold cyan]--- Audiobook Downloader ---[/bold cyan]")

    if subprocess.run(["ffmpeg", "-version"], capture_output=True).returncode != 0:
        console.print(
            "[red]Error: ffmpeg is not installed. Check the README for installation instructions.[/red]"
        )
        exit()

    # --- 0. URL or Search ---
    console.print(
        "\n[yellow]Enter a book URL, or type [bold]'s'[/bold] to search by title: [/yellow]",
        end="",
    )
    first_input = console.input("").strip()

    if first_input.lower().strip() in ("s", "search"):
        book_title_query = console.input("[yellow]Book title: [/yellow]").strip()
        if not book_title_query:
            console.print("[red]No title entered. Exiting.[/red]")
            exit()
        author_query = console.input(
            "[yellow]Author name (optional, press Enter to skip): [/yellow]"
        ).strip()
        query = f"{book_title_query} {author_query}".strip()

        console.print(f"\n[cyan]Searching for:[/cyan] {query}\n")
        input_book_url = None
        scraper = None

        for site_name, result_title, result_url in search_all(query):
            console.print(
                f"[green]Found on {site_name}:[/green] {result_title}\n"
                f"  [dim]{result_url}[/dim]"
            )
            if yes(console.input("[yellow]Is this the book you're looking for? (y/n): [/yellow]")):
                input_book_url = result_url
                scraper = get_scraper(input_book_url)
                break
            console.print("[dim]Searching next site...[/dim]\n")

        if not input_book_url or not scraper:
            console.print("[red]No matching book found across all supported sites.[/red]")
            exit()
    else:
        input_book_url = first_input
        scraper = get_scraper(input_book_url)
        if not scraper:
            console.print(
                "[red]Error: Unsupported website. Please enter a valid URL from a supported site.[/red]"
            )
            exit()

    # --- 1. Scrape data ---
    book_data = scraper.fetch_book_data(input_book_url)

    if not book_data:
        console.print("[bold red]Could not retrieve book data. Exiting.[/bold red]")
        exit()

    book_data["title"] = sanitize_book_title(book_data.get("title", "Unknown_Book"))

    # --- 2. Review and Override Metadata ---
    details_table = Table(title="Scraped Book Details", show_lines=True)
    details_table.add_column("Field", style="bold cyan", width=15)
    details_table.add_column("Value", style="white", min_width=45)
    details_table.add_row("Title", book_data.get("title", "N/A"))
    details_table.add_row("Author", book_data.get("author", "N/A"))
    details_table.add_row("Narrator", book_data.get("narrator", "N/A"))
    details_table.add_row("Year", book_data.get("year", "N/A"))
    details_table.add_row("Cover Art URL", book_data.get("cover_url", "N/A"))
    console.print(details_table)

    if yes(console.input("[yellow]Do you want to change any of these details? (y/n): [/yellow]")):
        console.print(
            "\n[cyan]Enter new details. Press Enter to keep the current value.[/cyan]"
        )
        book_data["title"] = sanitize_book_title(
            console.input(f"Title [{book_data.get('title', '')}]: ").strip()
            or book_data.get("title")
        )
        book_data["author"] = console.input(
            f"Author [{book_data.get('author', '')}]: "
        ).strip() or book_data.get("author")
        book_data["narrator"] = console.input(
            f"Narrator [{book_data.get('narrator', '')}]: "
        ).strip() or book_data.get("narrator")
        book_data["year"] = console.input(
            f"Year [{book_data.get('year', '')}]: "
        ).strip() or book_data.get("year")
        book_data["cover_url"] = console.input(
            f"Cover URL [{book_data.get('cover_url', '')}]: "
        ).strip() or book_data.get("cover_url")

    # --- 3. Chapter Selection Menu ---
    total_chapters = len(book_data["chapters"])
    # Store the true total for ID3 tags later
    book_data["total_chapters_count"] = total_chapters

    console.print(f"\n[green]Found {total_chapters} chapters.[/green]")
    choice = console.input(
        "[yellow]Press [bold]Enter[/bold] to download ALL, or type [bold]'s'[/bold] to select specific chapters: [/yellow]"
    )

    final_chapter_list = []

    if choice.lower().strip() in ("s", "select") or yes(choice):
        console.print(f"\n[bold]Chapters available: 1 to {total_chapters}[/bold]")
        console.print(
            "You can specify individual chapters or ranges (e.g., '1-5, 8, 10')."
        )
        console.print(
            "Downloaded chapters will be skipped. To redownload any chapter delete it in the downloads folder."
        )
        selection = console.input(
            "\n[yellow]Enter chapter numbers/ranges to download: [/yellow]"
        ).lower().strip()
        selected_indices = parse_chapter_ranges(selection, total_chapters)

        if not selected_indices:
            console.print("[red]No valid chapters selected. Exiting.[/red]")
            exit()

        selected_table = Table(
            title=f"Selected {len(selected_indices)} Chapters",
            show_header=True,
            header_style="bold magenta",
        )
        selected_table.add_column("#", style="dim", width=4)
        selected_table.add_column("Chapter Title")

        for idx in selected_indices:
            if 0 <= idx < len(book_data["chapters"]):
                title = book_data["chapters"][idx].get("title", "Unknown")
                selected_table.add_row(f"{idx + 1:02}", title)

        console.print(selected_table)

        # Build new list, ensuring we keep track of original index for ID3 tags
        for idx in selected_indices:
            chapter = book_data["chapters"][idx]
            chapter["track_num"] = idx + 1  # 1-based index
            final_chapter_list.append(chapter)
    else:
        # User wants all chapters
        for i, chapter in enumerate(book_data["chapters"]):
            chapter["track_num"] = i + 1
            final_chapter_list.append(chapter)

    book_data["chapters"] = final_chapter_list

    # --- 3. Download cover art ---
    if book_data.get("cover_url"):
        console.print("\n[cyan]Downloading cover art...[/cyan]")
        try:
            artwork_response = requests.get(book_data["cover_url"])
            artwork_response.raise_for_status()
            content_type = artwork_response.headers.get("Content-Type", "")
            if not content_type.startswith("image/"):
                pass
            else:
                book_data["artwork_data"] = artwork_response.content
                book_data["mime_type"] = (
                    "image/jpeg"
                    if content_type == "image/jpeg"
                    or book_data["cover_url"].lower().endswith((".jpg", ".jpeg"))
                    else "image/png"
                )
        except requests.exceptions.RequestException as e:
            console.print(
                f"[yellow]Warning: Could not download cover art. Error: {e}[/yellow]"
            )

    # --- 4. Start the download process ---
    book_dir, downloaded_files = download_and_tag_audiobook(book_data)

    # --- 5. Offer combined single-file audiobook ---
    if len(downloaded_files) > 1:
        if yes(console.input("[yellow]Create a single combined audiobook file with chapter markers? (y/n): [/yellow]")):
            create_combined_audiobook(book_data, book_dir, downloaded_files)
