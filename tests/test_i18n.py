import unittest
from unittest.mock import AsyncMock, patch

from shared.i18n import DEFAULT_LANGUAGE, available_languages, normalize_language, t


class CatalogTests(unittest.TestCase):
    def test_english_catalog_is_available(self):
        self.assertIn("en", available_languages())
        self.assertEqual(available_languages()["en"], "English")

    def test_nested_key_and_placeholder(self):
        text = t("settings.language_set", language="English")
        self.assertEqual(text, "Language set to English.")

    def test_unknown_language_falls_back_to_english(self):
        self.assertEqual(normalize_language("de"), DEFAULT_LANGUAGE)

    def test_language_variants_normalize_to_base(self):
        self.assertEqual(normalize_language("en-US"), "en")

    def test_missing_key_returns_key(self):
        self.assertEqual(t("does.not.exist"), "does.not.exist")

    def test_bad_placeholder_uses_raw_template(self):
        text = t("settings.language_set", wrong="value")
        self.assertEqual(text, "Language set to {language}.")

    def test_language_for_reads_user_settings(self):
        from shared.i18n import language_for

        settings = type("Settings", (), {"lang": "en"})()
        session = object()
        with patch(
            "DB.repo.user_setting_repo.UserSettingsRepo.get_user_settings",
            AsyncMock(return_value=settings),
        ):
            import asyncio

            self.assertEqual(asyncio.run(language_for(session, 42)), "en")


if __name__ == "__main__":
    unittest.main()