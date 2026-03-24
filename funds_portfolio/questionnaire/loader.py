"""
Questionnaire loader - loads and validates preferences_schema.json
"""

import json
import os
import copy
from collections import Counter
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class QuestionnaireLoader:
    """Loads and validates questionnaire schema from JSON"""

    def __init__(self, schema_path: str = "/app/preferences_schema.json"):
        """
        Initialize QuestionnaireLoader with path to questionnaire schema.

        Args:
            schema_path: Path to preferences_schema.json file.  Defaults point at
                         container location; falls back to project-root when
                         running tests locally.
        """
        if not os.path.exists(schema_path):
            alt = os.path.join(os.getcwd(), "preferences_schema.json")
            if os.path.exists(alt):
                logger.debug("using fallback questionnaire schema path %s", alt)
                schema_path = alt
        self.schema_path = schema_path
        self._questionnaire = None
        self._response_schema = None
        self._translations = self._load_translations()
        self._funds_db_path = self._resolve_funds_db_path()
        self._funds_mtime = None
        self.load_schema()
        self._refresh_dynamic_options_if_needed(force=True)

    def load_schema(self) -> bool:
        """
        Load questionnaire schema from JSON file.

        Returns:
            True if load successful, False otherwise
        """
        try:
            if not os.path.exists(self.schema_path):
                logger.error("Questionnaire schema not found at %s", self.schema_path)
                return False

            with open(self.schema_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._questionnaire = data.get("questionnaire", {})
            self._response_schema = data.get("response_schema", {})

            logger.info("Loaded questionnaire schema from %s", self.schema_path)
            return True

        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to load questionnaire schema: %s", e)
            return False

    def get_questionnaire(self, language: Optional[str] = None) -> Dict:
        """
        Get the full questionnaire schema.

        Returns:
            Questionnaire dictionary with sections and options
        """
        self._refresh_dynamic_options_if_needed()
        if not language:
            return self._questionnaire or {}
        return self._translate_questionnaire(language)

    def get_sections(self) -> List[Dict]:
        """
        Get all questionnaire sections.

        Returns:
            List of section dictionaries
        """
        self._refresh_dynamic_options_if_needed()
        return self._questionnaire.get("sections", []) if self._questionnaire else []

    def get_section_by_id(self, section_id: str) -> Optional[Dict]:
        """
        Get a single questionnaire section by ID.

        Args:
            section_id: Section ID (e.g., 'investment_goal')

        Returns:
            Section dictionary if found, None otherwise
        """
        sections = self.get_sections()
        for section in sections:
            if section.get("id") == section_id:
                return section
        return None

    def get_response_schema(self) -> Dict:
        """
        Get the response schema (for validation).

        Returns:
            Response schema dictionary
        """
        return self._response_schema or {}

    def _load_translations(self) -> Dict[str, Dict]:
        translations = {}
        base_dir = os.path.join(os.path.dirname(__file__), "translations")
        if not os.path.isdir(base_dir):
            return translations

        for filename in os.listdir(base_dir):
            if not filename.endswith(".json"):
                continue
            lang = filename[:-5]
            path = os.path.join(base_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    translations[lang] = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("Failed to load translation %s: %s", path, e)
        return translations

    def _translate_questionnaire(self, language: str) -> Dict:
        if not self._questionnaire:
            return {}

        translations = self._translations.get(language) or self._translations.get("en")
        if not translations:
            return self._questionnaire

        translated = copy.deepcopy(self._questionnaire)
        section_map = translations.get("sections", {})
        region_map = translations.get("regions", {})
        theme_map = translations.get("themes", {})

        for section in translated.get("sections", []):
            section_id = section.get("id")
            sec_t = section_map.get(section_id, {})

            if sec_t.get("name"):
                section["name"] = sec_t["name"]
            if sec_t.get("title"):
                section["title"] = sec_t["title"]
            elif sec_t.get("name") and not section.get("title"):
                section["title"] = sec_t["name"]
            if sec_t.get("description"):
                section["description"] = sec_t["description"]

            option_map = sec_t.get("options", {})
            for opt in section.get("options", []):
                opt_id = opt.get("id")
                if opt_id in option_map:
                    opt["label"] = option_map[opt_id]

            if section_id == "preferred_regions" and region_map:
                for opt in section.get("options", []):
                    value = opt.get("value")
                    if value in region_map:
                        opt["label"] = region_map[value]

            if section_id == "preferred_themes" and theme_map:
                for opt in section.get("options", []):
                    value = opt.get("value")
                    if value in theme_map:
                        opt["label"] = theme_map[value]

        return translated

    def validate_answers(self, user_answers: Dict) -> tuple[bool, List[str]]:
        """
        Validate user answers against questionnaire schema.

        Args:
            user_answers: Dictionary of user answers

        Returns:
            Tuple of (is_valid: bool, errors: List[str])
        """
        errors = []
        sections = self.get_sections()

        for section in sections:
            section_id = section.get("id")
            is_required = section.get("required", False)

            # Check if required field is present
            if is_required and section_id not in user_answers:
                errors.append(f'Required field "{section_id}" is missing')
                continue

            if section_id not in user_answers:
                continue

            user_value = user_answers[section_id]
            section_type = section.get("type")
            options = section.get("options", [])
            valid_values = [opt.get("value") for opt in options]

            # Validate based on field type
            if section_type == "single_select":
                if user_value not in valid_values:
                    errors.append(
                        f'Invalid value "{user_value}" for field "{section_id}". '
                        f"Must be one of: {', '.join(valid_values)}"
                    )

            elif section_type == "multi_select":
                if not isinstance(user_value, list):
                    errors.append(f'Field "{section_id}" must be an array')
                    continue

                for val in user_value:
                    if val not in valid_values:
                        errors.append(
                            f'Invalid value "{val}" in field "{section_id}". '
                            f"Must be one of: {', '.join(valid_values)}"
                        )

        return (len(errors) == 0, errors)

    def map_answers_to_risk_profile(self, user_answers: Dict) -> int:
        """
        Map user answers to a risk profile (1-4).

        Risk profile calculation:
        - risk_approach: 1=conservative, 2=moderate_low, 3=moderate, 4=aggressive
        - loss_tolerance: 1=low, 4=high
        - Average of the two (rounded)

        Args:
            user_answers: Dictionary of validated user answers

        Returns:
            Risk profile (1-4)
        """
        risk_score = 0
        count = 0

        # Get risk_approach score
        if "risk_approach" in user_answers:
            risk_section = self.get_section_by_id("risk_approach")
            if risk_section:
                for opt in risk_section.get("options", []):
                    if opt.get("value") == user_answers["risk_approach"]:
                        risk_score += opt.get("risk_profile", 2)
                        count += 1
                        break

        # Get loss_tolerance score
        if "loss_tolerance" in user_answers:
            loss_section = self.get_section_by_id("loss_tolerance")
            if loss_section:
                for opt in loss_section.get("options", []):
                    if opt.get("value") == user_answers["loss_tolerance"]:
                        risk_score += opt.get("loss_tolerance_score", 2)
                        count += 1
                        break

        # Default to moderate (2.5) if no scores found
        if count == 0:
            return 3

        # Average and round (minimum 1, maximum 4)
        avg_risk = risk_score / count
        risk_profile = round(avg_risk)
        return max(1, min(4, risk_profile))

    def is_loaded(self) -> bool:
        """
        Check if questionnaire schema is loaded.

        Returns:
            True if schema is loaded, False otherwise
        """
        return self._questionnaire is not None

    def _resolve_funds_db_path(self) -> Optional[str]:
        candidate = "/app/funds_database.json"
        if os.path.exists(candidate):
            return candidate
        alt = os.path.join(os.getcwd(), "funds_database.json")
        if os.path.exists(alt):
            return alt
        logger.warning("Funds database not found for dynamic options.")
        return None

    def _refresh_dynamic_options_if_needed(self, force: bool = False) -> None:
        if not self._funds_db_path or not os.path.exists(self._funds_db_path):
            return

        try:
            mtime = os.path.getmtime(self._funds_db_path)
        except OSError:
            return

        if not force and self._funds_mtime == mtime:
            return

        if self._apply_dynamic_options():
            self._funds_mtime = mtime

    def _apply_dynamic_options(self) -> bool:
        if not self._questionnaire:
            return False

        if not self._funds_db_path or not os.path.exists(self._funds_db_path):
            return False

        try:
            with open(self._funds_db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load funds database for dynamic options: %s", e)
            return False

        funds = data.get("funds_database", [])
        region_counts: Counter[str] = Counter()
        theme_counts: Counter[str] = Counter()

        for fund in funds:
            region = fund.get("region")
            if region:
                region_counts[str(region).strip().lower()] += 1

            theme = fund.get("theme")
            if theme:
                theme_counts[str(theme).strip().upper()] += 1

        region_options = self._build_region_options(region_counts)
        theme_options = self._build_theme_options(theme_counts)

        self._set_section_options("preferred_regions", region_options)
        self._set_section_options("preferred_themes", theme_options)
        return True

    def _set_section_options(self, section_id: str, options: List[Dict]) -> None:
        sections = (
            self._questionnaire.get("sections", []) if self._questionnaire else []
        )
        for section in sections:
            if section.get("id") == section_id:
                section["options"] = options
                return

    def _build_region_options(self, counts: Counter) -> List[Dict]:
        if not counts:
            return []

        label_map = {
            "global": "Global - spread across all major markets",
            "europe": "Europe - focus on European markets",
            "north_america": "North America - US and Canadian markets",
            "eurozone": "Eurozone - countries using the euro",
            "united_kingdom": "United Kingdom - UK market focus",
            "germany": "Germany - German market focus",
            "asia": "Asia - developed and emerging Asia",
            "emerging_markets": "Emerging Markets - high-growth developing economies",
        }

        preferred_order = [
            "global",
            "europe",
            "north_america",
            "eurozone",
            "united_kingdom",
            "germany",
            "asia",
            "emerging_markets",
        ]

        remaining = [r for r in counts.keys() if r not in preferred_order]
        remaining.sort(key=lambda r: (-counts[r], r))

        ordered = [r for r in preferred_order if r in counts] + remaining

        options = []
        for value in ordered:
            label = label_map.get(value, value.replace("_", " ").title())
            options.append(
                {
                    "id": f"region_{value}",
                    "label": label,
                    "value": value,
                    "optimizer_region": value.upper(),
                }
            )
        return options

    def _build_theme_options(self, counts: Counter) -> List[Dict]:
        label_map = {
            "SUSTAINABILITY": "Sustainability & Climate - clean energy, environmental protection",
            "TECHNOLOGY": "Technology & Innovation - AI, semiconductors, digitalisation",
            "HEALTHCARE": "Healthcare & Life Sciences - biotech, medical devices, pharma",
        }

        options = [
            {
                "id": "theme_none",
                "label": "No specific theme - just a well-diversified portfolio",
                "value": "none",
                "optimizer_theme": "NONE",
            }
        ]

        themes = [t for t in counts.keys() if t and t.upper() != "NONE"]
        themes.sort(key=lambda t: (-counts[t], t))

        for theme in themes:
            value = theme.lower()
            label = label_map.get(theme, theme.replace("_", " ").title())
            options.append(
                {
                    "id": f"theme_{value}",
                    "label": label,
                    "value": value,
                    "optimizer_theme": theme,
                }
            )
        return options


# Singleton instance for application-wide use
_questionnaire_loader_instance = None


def get_questionnaire_loader(
    schema_path: str = "/app/preferences_schema.json",
) -> QuestionnaireLoader:
    """
    Get or create the global QuestionnaireLoader instance.

    Args:
        schema_path: Path to preferences_schema.json (used on first call)

    Returns:
        QuestionnaireLoader singleton instance
    """
    global _questionnaire_loader_instance
    if _questionnaire_loader_instance is None:
        _questionnaire_loader_instance = QuestionnaireLoader(schema_path)
    return _questionnaire_loader_instance
