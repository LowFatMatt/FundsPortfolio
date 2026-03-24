# Branding Guide

This project supports hoster‑level branding via a **brand pack**. A brand pack is a folder containing a JSON config plus optional assets (logo + CSS overrides). No code changes are required.

## Quick Start
1. Copy `brand/default` to a new folder, e.g. `brand/acme`.
2. Edit `brand/acme/brand.json` with your colors, fonts, and tokens.
3. Replace `brand/acme/logo.svg` with your logo (SVG or PNG).
4. Optionally edit `brand/acme/overrides.css` for extra CSS tweaks.
5. Set the environment variable: `BRAND=acme`.

Docker Compose example:
```
BRAND=acme docker compose up --build -d
```

The app will fall back to `brand/default` if a brand is missing.

## Brand Pack Structure
```
brand/
  default/
    brand.json
    logo.svg
    overrides.css
  acme/
    brand.json
    logo.svg
    overrides.css
```

## brand.json Schema (Core Tokens)
- `name`: Display name for the brand.
- `logo`: Filename for the logo (relative to the brand folder).
- `overrides_css`: Filename for the CSS override file.
- `font_import_url`: Optional Google Fonts URL.
- `fonts.body`: CSS font stack for body text.
- `fonts.heading`: CSS font stack for headings.
- `colors.*`: Color tokens used to populate CSS variables.
- `radii.*`: Border radii for cards/inputs/buttons.
- `spacing.*`: Page and card padding tokens.
- `effects.*`: Shadows and blur tokens.

Example:
```json
{
  "name": "Acme Finance",
  "logo": "logo.svg",
  "overrides_css": "overrides.css",
  "font_import_url": "https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@300;400;600&display=swap",
  "fonts": {
    "body": "'Source Sans 3', system-ui, sans-serif",
    "heading": "'Source Sans 3', system-ui, sans-serif"
  },
  "colors": {
    "bg": "#f4f6f9",
    "card": "#ffffff",
    "card_border": "#d6dde6",
    "text_primary": "#1f2a37",
    "text_secondary": "#5b6675",
    "accent": "#003b8e",
    "accent_hover": "#002f73"
  },
  "radii": {
    "card": "14px",
    "button": "8px",
    "input": "8px",
    "pill": "999px"
  },
  "spacing": {
    "page_padding": "2rem 1rem",
    "card_padding": "2rem"
  },
  "effects": {
    "card_shadow": "0 10px 24px rgba(9, 30, 66, 0.08)",
    "button_shadow": "0 6px 16px rgba(0, 59, 142, 0.2)",
    "button_shadow_hover": "0 8px 22px rgba(0, 59, 142, 0.28)"
  }
}
```

## How It Works
- The app reads `brand/<BRAND>/brand.json` on startup.
- Tokens are injected as CSS variables in `templates/index.html`.
- Assets are served from `/brand/<asset>` (logo + overrides).

## Tips
- Keep contrast high for accessibility.
- Prefer SVG logos for crisp rendering.
- Use `overrides.css` for layout tweaks that go beyond tokens.
