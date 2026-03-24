# i18n Guide

This project supports multiple languages for the UI and questionnaire.

## Structure
- UI strings: `static/i18n/<lang>.json`
- Questionnaire strings: `funds_portfolio/questionnaire/translations/<lang>.json`
- Decision strings: `funds_portfolio/portfolio/translations/<lang>.json`

## Add a New Language
1. Copy `static/i18n/en.json` to your language code (e.g., `static/i18n/fr.json`).
2. Copy `funds_portfolio/questionnaire/translations/en.json` to your language code.
3. Copy `funds_portfolio/portfolio/translations/en.json` to your language code.
4. Translate the values (keep keys unchanged).
5. Update `supportedLangs` in `static/js/app.js` to include the new code.

## Notes
- Missing keys fall back to English.
- Dynamic region/theme labels use the `regions` and `themes` maps in the questionnaire translation file.
