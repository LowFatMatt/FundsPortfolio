from urllib.parse import urlparse


def get_scraper_for_url(url: str):
    """Return a scraper instance for the given kiid_url, or None if unknown."""
    if not url:
        return None
    netloc = urlparse(url).netloc.lower()
    # Lazy import providers to avoid import cycles
    if "finanzen.net" in netloc:
        from .finanzen import FinanzenNetScraper

        return FinanzenNetScraper()

    if "justetf.com" in netloc:
        try:
            from .justetf import JustETFScraper

            return JustETFScraper()
        except Exception:
            return None

    if "finanzfluss.de" in netloc:
        try:
            from .finanzfluss import FinanzflussScraper

            return FinanzflussScraper()
        except Exception:
            return None

    return None
