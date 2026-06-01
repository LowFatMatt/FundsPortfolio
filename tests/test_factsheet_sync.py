"""Tests for factsheetslive data-capture helpers (region/theme + best-horizon).

These cover the pure parsing/mapping logic added to the offline sync pipeline;
no network access is required.
"""

import os
import sys

# The sync scripts live in scripts/ and import sibling helpers by bare name
# (e.g. `from _german_labels import ...`), so put that dir on the path.
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import _german_labels as gl  # noqa: E402
import build_customer_catalog as bcc  # noqa: E402
import sync_factsheetslive as sfl  # noqa: E402
from bs4 import BeautifulSoup  # noqa: E402


class TestRegionFromGerman:
    def test_north_america_combined_label(self):
        assert gl.region_from_german("Nordamerika / USA") == "north_america"

    def test_common_regions(self):
        assert gl.region_from_german("Europa") == "europe"
        assert gl.region_from_german("Deutschland") == "germany"
        assert gl.region_from_german("Asien") == "asia"
        assert gl.region_from_german("Schwellenländer") == "emerging_markets"
        assert gl.region_from_german("Global") == "global"

    def test_euro_area_maps_to_europe(self):
        # Euroland / Eurozone funds are European, not global catch-all.
        assert gl.region_from_german("Euroland") == "europe"
        assert gl.region_from_german("Eurozone") == "europe"

    def test_blank_defaults_to_global(self):
        assert gl.region_from_german("") == "global"
        assert gl.region_from_german("–") == "global"
        assert gl.region_from_german(None) == "global"

    def test_unknown_kept_lowercased(self):
        assert gl.region_from_german("Lateinamerika") == "lateinamerika"


class TestThemeFromGerman:
    def test_known_themes(self):
        assert gl.theme_from_german("Dividenden") == "dividends"
        assert gl.theme_from_german("Rohstoffe") == "commodities"
        assert gl.theme_from_german("Gesundheit") == "healthcare"
        assert gl.theme_from_german("Technologie") == "technology"
        assert gl.theme_from_german("Infrastruktur") == "infrastructure"
        assert gl.theme_from_german("Wasser") == "water"
        assert gl.theme_from_german("Verteidigung") == "defense"
        assert gl.theme_from_german("Ökologie") == "sustainability"

    def test_blank_is_none(self):
        assert gl.theme_from_german("–") == "NONE"
        assert gl.theme_from_german("") == "NONE"
        assert gl.theme_from_german(None) == "NONE"


class TestBestHorizon:
    def test_prefers_longer_horizon(self):
        assert bcc._best_horizon({"3y": 0.88, "1y": 1.44}) == 0.88

    def test_falls_back_to_shorter(self):
        # Nasdaq-100 ETF case: only a 1y value exists.
        assert bcc._best_horizon({"3y": None, "5y": None, "1y": 2.17}) == 2.17

    def test_none_when_empty(self):
        assert bcc._best_horizon({}) is None
        assert bcc._best_horizon(None) is None


class TestParseRegionTheme:
    def _soup(self, region, theme):
        html = (
            "<table>"
            f"<tr><td>Region</td><td>{region}</td></tr>"
            f"<tr><td>Thema</td><td>{theme}</td></tr>"
            "</table>"
        )
        return BeautifulSoup(html, "html.parser")

    def test_parses_and_maps(self):
        region, theme = sfl.parse_region_theme(self._soup("Nordamerika / USA", "Dividenden"))
        assert region == "north_america"
        assert theme == "dividends"

    def test_empty_thema_is_none(self):
        region, theme = sfl.parse_region_theme(self._soup("Global", "–"))
        assert region == "global"
        assert theme == "NONE"
