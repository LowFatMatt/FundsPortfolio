#!/usr/bin/env python3
"""One-off brand-asset scraper (MVP-3): logos + "Sparkasse Web" text fonts.

Renders each Kundenportal site in headless Chromium (the Provinzial portals
are hash-routed SPAs), dismisses consent banners where possible, and
inventories:

* favicons / og:image / header & logo <img> candidates,
* actually-downloaded font resources (performance resource entries),
* stylesheet references to the "Sparkasse Web" font family,

then (with ``--download``) saves the best logo candidate per brand to
``brand/<slug>/logo.<ext>`` and the font files to
``brand/<slug>/fonts/sparkasse-web-<n>.woff2``.

Usage: python3 scripts/scrape_brand_assets.py [--download] [--timeout 45]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
TARGETS = {
    "provinzial-nord": "https://nord.meineprovinzial.provinzial.de/#/kundenportal/services/schaden-melden?vz=Ji8oJg%3D%3D",
    "provinzial-west": "https://west.meineprovinzial.provinzial.de/#/kundenportal/services/schaden-melden?vz=Ji8oJg%3D%3D",
    "hfk": "https://nord.meinefeuerkasse.provinzial.de/#/kundenportal/services/schaden-melden",
    "sparkassen": "https://www.sparkasse.de/pk/produkte/versicherung/haus-und-wohnungsversicherung/hausratversicherung.html",
}
CONSENT_TEXTS = [
    "Alle akzeptieren", "Akzeptieren", "Zustimmen", "Einverstanden",
    "Auswahl speichern", "Alle zulassen", "Zustimmen und fortfahren",
    "Akzeptieren & schließen", "OK",
]

INVENTORY_JS = r"""
(url) => {
  const abs = (u) => { try { return new URL(u, url).href; } catch { return null; } };
  const out = { favicons: [], headerImgs: [], logoImgs: [], ogImage: null,
                fontResources: [], fontFamilyRefs: [] };
  document.querySelectorAll('link[rel*="icon"]').forEach(l => {
    const h = abs(l.href); if (h) out.favicons.push({ rel: l.rel, href: h });
  });
  const og = document.querySelector('meta[property="og:image"]');
  if (og) out.ogImage = abs(og.content);
  document.querySelectorAll(
    'header img, ion-header img, nav img, [class*="header" i] img, [class*="app-bar" i] img'
  ).forEach(i => {
    const s = i.currentSrc || i.src;
    if (s) out.headerImgs.push({ src: abs(s), alt: i.alt || '', cls: String(i.className || '') });
  });
  document.querySelectorAll('img[src*="logo" i], img[alt*="logo" i]').forEach(i => {
    const s = i.currentSrc || i.src;
    if (s) out.logoImgs.push({ src: abs(s), alt: i.alt || '', cls: String(i.className || '') });
  });
  for (const f of document.fonts) out.fontFamilyRefs.push(String(f.family) + ' :: ' + f.status);
  if (performance.getEntriesByType) {
    performance.getEntriesByType('resource').forEach(r => {
      if (/\\.(woff2?|ttf|otf)(\\?|#|$)/i.test(r.name)) out.fontResources.push(r.name);
    });
  }
  // Deep walk incl. shadow roots (Ionic components) — logos are NOT
  // plain header <img> elements on these portals.
  const deep = [];
  const walkDom = (root, depth) => {
    if (depth > 12) return;
    for (const el of root.querySelectorAll('*')) {
      if (el.shadowRoot) walkDom(el.shadowRoot, depth + 1);
      const tag = el.tagName;
      let src = '';
      if (tag === 'IMG' || tag === 'SOURCE' || tag === 'ION-IMG') {
        src = el.currentSrc || el.src || el.srcset || '';
      }
      if (src) {
        deep.push({ kind: 'img', src: abs(src), tag,
                    alt: el.alt || '', cls: String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : (el.className || '')) });
      }
      try {
        const bg = getComputedStyle(el).backgroundImage;
        if (bg && bg !== 'none' && /url\(/.test(bg)) {
          const m = bg.match(/url\(([^)]+)\)/);
          const u = m ? abs(m[1].replace(/["']/g, '')) : null;
          if (u && /\.(svg|png|webp|jpe?g)/i.test(u)) {
            deep.push({ kind: 'bg', src: u, tag, alt: '', cls: String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : (el.className || '')) });
          }
        }
      } catch {}
    }
  };
  walkDom(document, 0);
  out.deepAssets = deep.slice(0, 250);

  for (const sheet of document.styleSheets) {
    let rules; try { rules = sheet.cssRules; } catch { continue; }
    const walk = (rs) => {
      for (const r of rs) {
        try {
          if (r.style) {
            const ff = r.style.getPropertyValue('font-family');
            if (ff && /sparkasse/i.test(ff)) out.fontFamilyRefs.push('CSS: ' + ff);
          }
          if (r instanceof CSSFontFaceRule) {
            const fam = r.style.getPropertyValue('font-family');
            const src = r.style.getPropertyValue('src');
            out.fontFamilyRefs.push('FONTFACE: ' + fam + ' -> ' + src.slice(0, 160));
          }
        } catch {}
        if (r.cssRules) walk(r.cssRules);
      }
    };
    walk(rules);
  }
  return out;
}
"""


def try_dismiss_consent(page) -> bool:
    clicked = False
    frames = [page, *page.frames]
    for frame in frames:
        for text in CONSENT_TEXTS:
            for sel in (
                f'button:has-text("{text}")',
                f'a:has-text("{text}")',
                f'[role="button"]:has-text("{text}")',
                f'label:has-text("{text}")',
            ):
                try:
                    loc = frame.locator(sel)
                    if loc.count():
                        loc.first.click(timeout=1000)
                        page.wait_for_timeout(400)
                        clicked = True
                except Exception:
                    continue
    return clicked


def download(url: str, dest: str, referer: str) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(data)
    return len(data)


def pick_logo(inv: dict) -> list[str]:
    """Logo candidates, best first: explicit logo imgs (svg first), then
    shadow-DOM assets (the portals render their wordmark inside Ionic
    components as DAM <ion-img> srcs), then plain header imgs."""
    candidates = [e["src"] for e in inv.get("logoImgs", []) if e.get("src")]
    for e in inv.get("deepAssets", []):
        src = str(e.get("src") or "")
        hay = f"{src} {e.get('cls', '')} {e.get('alt', '')}".lower()
        if any(k in hay for k in ("logo", "briefkopf", "wordmark", "tenant_header")):
            candidates.append(src)
    candidates += [e["src"] for e in inv.get("headerImgs", []) if e.get("src")]
    seen, ordered = set(), []
    for src in candidates:
        low = src.lower()
        if any(x in low for x in ("favicon", "icon-")) and "logo" not in low:
            continue
        if src not in seen:
            seen.add(src)
            ordered.append(src)
    ordered.sort(key=lambda u: (not u.lower().split("?")[0].endswith(".svg"),))
    return ordered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="save picked assets")
    parser.add_argument("--timeout", type=int, default=45, help="page load timeout s")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    report = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=UA, viewport={"width": 1440, "height": 900}, locale="de-DE"
        )
        for slug, url in TARGETS.items():
            page = context.new_page()
            entry = {"url": url}
            try:
                page.goto(url, wait_until="load", timeout=args.timeout * 1000)
                page.wait_for_timeout(2500)  # SPA render
                try_dismiss_consent(page)
                page.wait_for_timeout(1200)
                entry["inventory"] = page.evaluate(INVENTORY_JS, page.url)
                entry["title"] = page.title
            except Exception as exc:  # noqa: BLE001 — report and continue
                entry["error"] = repr(exc)
            report[slug] = entry
            page.close()
        browser.close()

    if args.download:
        for slug, entry in report.items():
            inv = entry.get("inventory") or {}
            brand_dir = os.path.join(BASE_DIR, "brand", slug)

            logo_candidates = pick_logo(inv)
            entry["logo_candidates"] = logo_candidates
            for i, src in enumerate(logo_candidates[:3]):
                ext = ".svg" if ".svg" in src.lower() else (
                    ".png" if ".png" in src.lower() else ".img"
                )
                dest = os.path.join(brand_dir, f"logo-candidate-{i}{ext}")
                try:
                    size = download(src, dest, entry["url"])
                    entry.setdefault("downloaded", []).append(f"{dest} ({size} B)")
                except Exception as exc:  # noqa: BLE001
                    entry.setdefault("download_errors", []).append(f"{src}: {exc!r}")

            fonts = sorted(set(inv.get("fontResources", [])))
            # Provinzial portals expose four "Sparkasse Web" weights as WOFF
            # font-face srcs — pull the full set, not only what the landing
            # view happened to download.
            for ref in inv.get("fontFamilyRefs", []):
                if ref.startswith("FONTFACE:") and "Sparkasse" in ref:
                    m = re.search(r'url\("([^"]+)"\)', ref)
                    if m:
                        full = urllib.parse.urljoin(entry["url"], m.group(1))
                        if full not in fonts:
                            fonts.append(full)
            entry["font_candidates"] = fonts
            for src in fonts[:8]:
                base = os.path.basename(urllib.parse.urlparse(src).path) or "font"
                dest = os.path.join(brand_dir, "fonts", base)
                try:
                    size = download(src, dest, entry["url"])
                    entry.setdefault("downloaded", []).append(f"{dest} ({size} B)")
                except Exception as exc:  # noqa: BLE001
                    entry.setdefault("download_errors", []).append(f"{src}: {exc!r}")

    # Some playwright-inventoried values resist JSON (e.g. SVG className
    # objects) — never let the report die after the run did its work.
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
