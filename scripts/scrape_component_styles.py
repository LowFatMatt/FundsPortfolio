#!/usr/bin/env python3
"""One-off: extract computed styles of two Kundenportal elements so our
prototype can copy them faithfully (MVP-3b refinement, 2026-10-06):

* ``pnw-wizard-progress-bar``  — the wizard stepper: real rendered font
  family/size/weight (the document-level scan only saw "Sparkasse Web"; the
  components may override via shadow-root adoptedStyleSheets) plus the
  step-bubble metrics,
* ``kupo-kachel-radio-button`` (and its grid) — the tile anatomy: border,
  radius, padding, indicator, hover background.

Playwright CSS locators pierce open shadow roots, so the deep
``pnw-root > ion-app > …`` paths resolve without manual shadow walking.

Usage: python3 scripts/scrape_component_styles.py [nord|west|hfk]
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
TARGETS = {
    "nord": "https://nord.meineprovinzial.provinzial.de/#/kundenportal/services/schaden-melden?vz=Ji8oJg%3D%3D",
    "west": "https://west.meineprovinzial.provinzial.de/#/kundenportal/services/schaden-melden?vz=Ji8oJg%3D%3D",
    "hfk": "https://nord.meinefeuerkasse.provinzial.de/#/kundenportal/services/schaden-melden",
}

# Walk an element's composed tree (host + open shadow roots) and collect the
# computed styles that matter for cloning the design.
WALK_JS = """
(el) => {
  const interesting = [];
  const pick = (cs) => ({
    fontFamily: cs.fontFamily,
    fontSize: cs.fontSize,
    fontWeight: cs.fontWeight,
    lineHeight: cs.lineHeight,
    letterSpacing: cs.letterSpacing,
    color: cs.color,
    background: cs.backgroundColor,
    backgroundImage: cs.backgroundImage === 'none' ? '' : cs.backgroundImage,
    border: cs.border,
    borderRadius: cs.borderRadius,
    boxShadow: cs.boxShadow === 'none' ? '' : cs.boxShadow,
    padding: cs.padding,
    margin: cs.margin,
    width: cs.width,
    height: cs.height,
    display: cs.display,
    gap: cs.gap,
  });
  const walk = (root, depth) => {
    if (depth > 14 || interesting.length > 60) return;
    for (const el of root.querySelectorAll('*')) {
      let cs;
      try { cs = getComputedStyle(el); } catch { continue; }
      const hasDecoration =
        (cs.border && cs.border !== '0px none rgb(0, 0, 0)') ||
        cs.backgroundColor !== 'rgba(0, 0, 0, 0)' ||
        cs.boxShadow !== 'none' ||
        parseFloat(cs.fontSize) >= 14;
      if (hasDecoration) {
        interesting.push({ tag: el.tagName.toLowerCase(),
                           cls: String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : (el.className || '')).slice(0, 60),
                           text: (el.textContent || '').trim().slice(0, 40),
                           styles: pick(cs) });
      }
      if (el.shadowRoot) walk(el.shadowRoot, depth + 1);
    }
  };
  walk(el, 0);
  return interesting;
}
"""

# All @font-face rules incl. shadow-root adoptedStyleSheets.
FONTFACE_JS = """
() => {
  const faces = [];
  const collect = (sheetList, origin) => {
    for (const sheet of sheetList) {
      let rules; try { rules = sheet.cssRules; } catch { continue; }
      for (const r of rules) {
        if (r instanceof CSSFontFaceRule) {
          faces.push({ origin, family: r.style.getPropertyValue('font-family'),
                       weight: r.style.getPropertyValue('font-weight'),
                       style: r.style.getPropertyValue('font-style'),
                       src: r.style.getPropertyValue('src').slice(0, 200) });
        }
      }
    }
  };
  collect(document.styleSheets, 'document');
  const walk = (root) => {
    for (const el of root.querySelectorAll('*')) {
      if (el.shadowRoot) {
        collect(el.shadowRoot.adoptedStyleSheets || [], 'adopted:' + el.tagName.toLowerCase());
        walk(el.shadowRoot);
      }
    }
  };
  walk(document);
  return faces;
}
"""


def try_dismiss_consent(page) -> None:
    for frame in [page, *page.frames]:
        for text in ("Alle akzeptieren", "Akzeptieren", "Zustimmen", "Einverstanden"):
            for sel in (f'button:has-text("{text}")', f'a:has-text("{text}")'):
                try:
                    loc = frame.locator(sel)
                    if loc.count():
                        loc.first.click(timeout=800)
                        page.wait_for_timeout(300)
                except Exception:
                    continue


def main() -> int:
    slug = sys.argv[1] if len(sys.argv) > 1 else "nord"
    url = TARGETS.get(slug, TARGETS["nord"])

    from playwright.sync_api import sync_playwright

    report = {"target": url, "hosts": {}}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=UA, viewport={"width": 1440, "height": 900}, locale="de-DE"
        )
        page = context.new_page()
        page.goto(url, wait_until="load", timeout=60_000)
        page.wait_for_timeout(2500)
        try_dismiss_consent(page)
        page.wait_for_timeout(1500)

        report["documentFontFaces"] = page.evaluate(FONTFACE_JS)

        for host_tag in (
            "pnw-wizard-progress-bar",
            "kupo-kachel-radio-button",
            "kupo-kachel-radio-group ion-grid",
            "pnw-page-state-frame",
            "body",
        ):
            loc = page.locator(host_tag)
            try:
                el = loc.first
                el.wait_for(state="attached", timeout=8000)
                report["hosts"][host_tag] = el.evaluate(WALK_JS)
            except Exception as exc:  # noqa: BLE001
                report["hosts"][host_tag] = f"not found: {exc!r}"

        # Hover state of the first tile (the user loved the hover wash).
        try:
            tile = page.locator("kupo-kachel-radio-button").first
            tile.hover(timeout=5000)
            page.wait_for_timeout(350)
            report["hosts"]["kupo-kachel-radio-button:hover"] = tile.evaluate(WALK_JS)
        except Exception as exc:  # noqa: BLE001
            report["hosts"]["kupo-kachel-radio-button:hover"] = f"hover failed: {exc!r}"

        browser.close()

    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
