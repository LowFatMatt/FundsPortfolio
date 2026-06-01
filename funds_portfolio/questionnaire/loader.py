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

    # Sections the decision engine actually consumes, with the implicit default
    # applied when the answer is missing. Keeps API tests resilient to partial
    # payloads; the chosen defaults represent the least-constraining option.
    LOGIC_RELEVANT_DEFAULTS: Dict[str, object] = {
        "risk_approach": "conservative",
        "loss_tolerance": "low_loss_tolerance",
        "esg_preference": "no_requirement",
        "etf_preference": "no_preference",
        "preferred_regions": ["global"],
        "preferred_themes": ["none"],
    }

    def apply_defaults(self, user_answers: Dict) -> tuple[Dict, List[str]]:
        """Fill missing logic-relevant answers with their implicit defaults.

        Returns a (answers, applied) tuple where ``answers`` is a copy of the
        input with defaults injected for any missing logic-relevant section,
        and ``applied`` is a list of human-readable notes describing each
        implicit answer that was added (for logging / server_logs).
        """
        answers = dict(user_answers or {})
        applied: List[str] = []

        for section_id, default_value in self.LOGIC_RELEVANT_DEFAULTS.items():
            if section_id in answers:
                continue
            value = (
                list(default_value)
                if isinstance(default_value, list)
                else default_value
            )
            answers[section_id] = value
            applied.append(
                f'No answer for "{section_id}" - applied default "{value}"'
            )

        return answers, applied

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
        """Emit the fixed canonical region whitelist.

        Options are always returned in the canonical order regardless of how
        many funds back each region, so empty categories (e.g. north_america
        with no funds) stay visible as deliberate test/coverage signals.
        Translation files override these labels at serve time.
        """
        label_map = {
            "germany": "Germany - German market focus",
            "europe": "Europe - focus on European markets",
            "north_america": "North America - US and Canadian markets",
            "asia": "Asia - developed and emerging Asia",
            "emerging_markets": "Emerging Markets - high-growth developing economies",
            "global": "Global - anything not covered by the regions above",
        }

        canonical_regions = [
            "germany",
            "europe",
            "north_america",
            "asia",
            "emerging_markets",
            "global",
        ]

        options = []
        for value in canonical_regions:
            options.append(
                {
                    "id": f"region_{value}",
                    "label": label_map[value],
                    "value": value,
                    "fund_count": counts.get(value, 0),
                }
            )
        return options

    def _build_theme_options(self, counts: Counter) -> List[Dict]:
        """Emit the fixed canonical theme whitelist.

        Like regions, all canonical themes are always returned regardless of
        fund counts so that newly-introduced themes with no backing funds yet
        (e.g. megatrends, water, ai_robotics, dividends) surface as gaps.
        DB tag names are kept verbatim (commodities, defense, ...).
        Translation files override these labels at serve time.
        """
        label_map = {
            "none": "No specific theme - just a well-diversified portfolio",
            "sustainability": "Sustainability & Climate - clean energy, environmental protection",
            "technology": "Technology & Innovation - AI, semiconductors, digitalisation",
            "healthcare": "Healthcare & Life Sciences - biotech, medical devices, pharma",
            "commodities": "Commodities & Raw Materials - metals, energy, agriculture",
            "infrastructure": "Infrastructure - transport, utilities, communication networks",
            "defense": "Security & Defense - aerospace, defense, cybersecurity",
            "energy": "Energy - traditional and renewable energy producers",
            "megatrends": "Megatrends - broad structural growth trends",
            "water": "Water - water supply, treatment and efficiency",
            "ai_robotics": "AI & Robotics - artificial intelligence and automation",
            "dividends": "Dividends - stable, income-generating companies",
        }

        canonical_themes = [
            "none",
            "sustainability",
            "technology",
            "healthcare",
            "commodities",
            "infrastructure",
            "defense",
            "energy",
            "megatrends",
            "water",
            "ai_robotics",
            "dividends",
        ]

        options = []
        for value in canonical_themes:
            options.append(
                {
                    "id": f"theme_{value}",
                    "label": label_map[value],
                    "value": value,
                    "fund_count": counts.get(value.upper(), 0),
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
