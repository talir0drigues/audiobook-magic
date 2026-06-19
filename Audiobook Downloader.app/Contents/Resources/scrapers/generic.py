import re
import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)

# Per-site config for scrapers that follow the standard WordPress audiobook pattern:
# h1 with "Author - Title Audiobook", <source type="audio/mpeg"> tags for chapters.
SITE_CONFIGS = {
    "goldenaudiobook.net": {
        "h1_selectors":    ["h1.title-page", "h1"],
        "cover_selectors": ["figure.wp-caption img", ".wp-caption img"],
        "audio_selectors": ["audio.wp-audio-shortcode source"],
        "year_selector":   "time.entry-date",
        "author_first":    True,
        "split_re":        r"\s*[–-]\s*",
        "strip_re":        r"\s*Audiobook\s*$",
    },
    "bigaudiobooks.net": {
        "h1_selectors":    ["h1.title-page", "h1"],
        "cover_selectors": [".wp-caption img", "meta[property='og:image']"],
        "audio_selectors": ['.post-single source[type="audio/mpeg"]'],
        "year_selector":   None,
        "author_first":    True,
        "split_re":        r"\s*[-–]\s*",
        "strip_re":        r"\s*(Audiobook|Audio Book|Free)\s*$",
    },
    "hdaudiobooks.net": {
        "h1_selectors":    ['h1[itemprop="headline"]', "h1"],
        "cover_selectors": ['img[itemprop="image"]', "meta[property='og:image']"],
        "audio_selectors": ['.entry source[type="audio/mpeg"]', '.entry-box source[type="audio/mpeg"]'],
        "year_selector":   None,
        "author_first":    False,  # format is "Title - Author"
        "split_re":        r"\s*[-–]\s*",
        "strip_re":        r"\s*\(AUDIOBOOK\)\s*$",
    },
    "fulllengthaudiobooks.net": {
        "h1_selectors":    ["h1.entry-title.post-title", "h1"],
        "cover_selectors": [".wp-caption img"],
        "audio_selectors": ['.entry source[type="audio/mpeg"]'],
        "year_selector":   None,
        "author_first":    True,
        "split_re":        r"\s*[-–]\s*",
        "strip_re":        r"\s*(Audiobook Free|Audio Book Online|Audiobook|Free)\s*$",
    },
}


class GenericWordPressScraper:
    def __init__(self, domain):
        self.domain = domain
        self.cfg = SITE_CONFIGS[domain]

    def fetch_book_data(self, url):
        cfg = self.cfg
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT, "Referer": url}, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None

        # Title and author
        h1 = next((soup.select_one(s) for s in cfg["h1_selectors"] if soup.select_one(s)), None)
        raw = re.sub(cfg["strip_re"], "", h1.get_text(strip=True) if h1 else "", flags=re.I).strip()
        parts = re.split(cfg["split_re"], raw, maxsplit=1)
        if len(parts) == 2:
            author, title = (parts[0], parts[1]) if cfg["author_first"] else (parts[1], parts[0])
        else:
            author, title = None, raw

        # Year
        year = None
        if cfg["year_selector"]:
            t = soup.select_one(cfg["year_selector"])
            if t and t.get("datetime"):
                year = t["datetime"][:4]

        # Cover image
        cover_url = None
        for sel in cfg["cover_selectors"]:
            tag = soup.select_one(sel)
            if tag:
                cover_url = tag.get("data-lazy-src") or tag.get("src") or tag.get("content")
                if cover_url:
                    break

        # Chapters
        chapters = []
        for sel in cfg["audio_selectors"]:
            sources = soup.select(sel)
            if sources:
                for i, src in enumerate(sources, start=1):
                    src_url = src.get("src", "").split("?")[0]
                    if src_url:
                        chapters.append({"title": f"Chapter {i:03d}", "url": src_url})
                break

        if not chapters:
            return None

        return {
            "site": self.domain,
            "title": title.strip(),
            "author": author.strip() if author else None,
            "narrator": None,
            "year": year,
            "cover_url": cover_url,
            "chapters": chapters,
            "site_headers": {"User-Agent": USER_AGENT, "Referer": url},
        }
