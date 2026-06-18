from scrapers.tokybook import TokybookScraper
from scrapers.zaudiobooks import ZaudiobooksScraper
from scrapers.audiozaic import AudiozaicScraper
from scrapers.generic import GenericWordPressScraper

# (domain_fragment, scraper_factory, base_url) — order also sets search priority
REGISTRY = [
    ("tokybook.com",             TokybookScraper,                                      "https://tokybook.com"),
    ("goldenaudiobook.net",      lambda: GenericWordPressScraper("goldenaudiobook.net"), "https://goldenaudiobook.net"),
    ("bigaudiobooks.net",        lambda: GenericWordPressScraper("bigaudiobooks.net"),   "https://bigaudiobooks.net"),
    ("audiozaic.com",            AudiozaicScraper,                                      "https://audiozaic.com"),
    ("fulllengthaudiobooks.net", lambda: GenericWordPressScraper("fulllengthaudiobooks.net"), "https://fulllengthaudiobooks.net"),
    ("hdaudiobooks.net",         lambda: GenericWordPressScraper("hdaudiobooks.net"),   "https://hdaudiobooks.net"),
    ("zaudiobooks.com",          ZaudiobooksScraper,                                    "https://zaudiobooks.com"),
]


def get_scraper(url):
    for domain, factory, _ in REGISTRY:
        if domain in url:
            return factory()
    return None
