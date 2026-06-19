import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs


class AudiozaicScraper:
    """
    Scraper for audiozaic.com.
    Audio links live on a separate /file-audio?slug32={POST_ID} page,
    not on the main book page, so we need a two-step fetch.
    Users may paste either the main book page URL or the /file-audio URL directly.
    """

    BASE_URL = "https://audiozaic.com"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    )

    def fetch_book_data(self, url):
        session = requests.Session()
        session.headers.update({"User-Agent": self.USER_AGENT, "Referer": self.BASE_URL})

        try:
            # If the user pasted the /file-audio URL directly, extract the post ID from it
            # and skip fetching the main book page.
            parsed = urlparse(url)
            if "file-audio" in parsed.path:
                post_id = parse_qs(parsed.query).get("slug32", [None])[0]
                if not post_id:
                    print("[!] Could not find slug32 in the /file-audio URL.")
                    return None
                audio_page_url = url
                title, author, cover_url = "Unknown", None, None
            else:
                response = session.get(url, timeout=15)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")

                h1 = soup.find("h1", class_="entry-title")
                raw_title = h1.get_text(strip=True) if h1 else "Unknown"
                title = self._clean_title(raw_title)
                author = self._extract_author(raw_title)

                cover_url = None
                cover_tag = soup.select_one(".entry-content img[src]")
                if cover_tag:
                    cover_url = cover_tag.get("src")

                post_id = self._extract_post_id(soup)
                if not post_id:
                    print("[!] Could not find post ID on audiozaic.com page.")
                    return None
                audio_page_url = f"{self.BASE_URL}/file-audio?slug32={post_id}"

            audio_response = session.get(
                audio_page_url, headers={"Referer": url}, timeout=15
            )
            audio_response.raise_for_status()
            audio_soup = BeautifulSoup(audio_response.text, "html.parser")

            # If we came in via a /file-audio URL, try to get the title from the player page
            if title == "Unknown":
                album_tag = audio_soup.find(class_="audioalbum")
                if album_tag:
                    title = self._clean_title(album_tag.get_text(strip=True))

            chapters = self._extract_chapters(audio_soup)
            if not chapters:
                print("[!] Could not find any chapters on audiozaic.com audio page.")
                return None

            return {
                "site": "audiozaic.com",
                "title": title,
                "author": author,
                "narrator": None,
                "year": None,
                "cover_url": cover_url,
                "chapters": chapters,
                "site_headers": {
                    "User-Agent": self.USER_AGENT,
                    "Referer": audio_page_url,
                },
            }

        except Exception as e:
            print(f"[!] Error scraping audiozaic.com: {e}")
            return None

    def _clean_title(self, raw_title):
        # Strip [Listen][Download] or similar bracket prefixes
        title = re.sub(r"^(\[.*?\]\s*)+", "", raw_title).strip()
        # Strip surrounding quotes: "Title"
        title = re.sub(r'^"(.*)"$', r"\1", title).strip()
        # Remove trailing "Audiobook Free", "Audiobook", etc.
        title = re.sub(r"\s*Audiobook.*$", "", title, flags=re.I).strip()
        # Remove "By Author" suffix
        title = re.sub(r"\s+[Bb]y\s+.+$", "", title).strip()
        return title or raw_title

    def _extract_author(self, raw_title):
        match = re.search(r"[Bb]y\s+([^\"]+?)(?:\s*\"|$)", raw_title)
        return match.group(1).strip() if match else None

    def _extract_post_id(self, soup):
        # Try button onclick: window.open('...?slug32=316', ...)
        button = soup.find("button", class_="redirect-press-final-link")
        if button and button.get("onclick"):
            match = re.search(r"slug32=(\d+)", button["onclick"])
            if match:
                return match.group(1)
        # Fallback: <body class="... postid-316 ...">
        body = soup.find("body")
        if body:
            for cls in body.get("class", []):
                match = re.match(r"postid-(\d+)", cls)
                if match:
                    return match.group(1)
        return None

    def _extract_chapters(self, soup):
        chapters = []
        for i, track in enumerate(soup.find_all("div", class_="track"), start=1):
            source = track.find("source", type="audio/mpeg")
            if source and source.get("src"):
                url = source["src"].split("?")[0]
                chapters.append({"title": f"Chapter {i:03d}", "url": url})
        return chapters
