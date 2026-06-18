import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

from scrapers import REGISTRY

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)

_RESULT_SELECTORS = [
    "article .entry-title a",
    "article h2 a",
    "article h3 a",
    ".post-title a",
    ".entry-title a",
    "article a[href]",
]


def _search_site(base_url, query):
    try:
        r = requests.get(
            f"{base_url}/?s={quote_plus(query)}",
            headers={"User-Agent": USER_AGENT},
            timeout=12,
        )
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for sel in _RESULT_SELECTORS:
            tag = soup.select_one(sel)
            if tag and tag.get("href"):
                return {"title": tag.get_text(strip=True) or tag["href"], "url": tag["href"]}
    except Exception:
        pass
    return None


def search_all(query):
    """Yield (site_name, title, url) for the first result found on each site."""
    for domain, _, base_url in REGISTRY:
        result = _search_site(base_url, query)
        if result:
            yield domain, result["title"], result["url"]
