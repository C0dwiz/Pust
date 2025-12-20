# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

# ©️ Codrago, 2024-2025
# This file is a part of Heroku Userbot
# 🌐 https://github.com/coddrago/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

# SPDX-License-Identifier: GNU AGPL v3.0
#
# This file is a part of Heroku Userbot.
#
# Copyright (C) 2026 CodWiz

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import requests
from ruamel.yaml import YAML

from . import utils
from .database import Database
from .tl_cache import CustomTelegramClient
from .types import Module

logger = logging.getLogger(__name__)


LANG_PACKS_DIR = Path(__file__).parent / "langpacks"
DEFAULT_LANGUAGE = "en"


SUPPORTED_LANGUAGES: Dict[str, str] = {
    "en": "🇬🇧 English",
    "ru": "🇷🇺 Русский",
    "ua": "🇺🇦 Український",
    "de": "🇩🇪 Deutsch",
}


yaml = YAML(typ="safe")
yaml.default_flow_style = False


def format_string(text: str, kwargs: Dict[str, Any]) -> str:
    """Format string with named placeholders"""
    for key, value in kwargs.items():
        placeholder = f"{{{key}}}"
        if placeholder in text:
            text = text.replace(placeholder, str(value))
    return text


class BaseTranslator:
    """Base class for translation functionality"""

    def _get_pack_content(
        self,
        pack_path: Path,
        prefix: str = "heroku.modules.",
    ) -> Optional[Dict[str, Any]]:
        """Read and parse language pack from file"""
        try:
            content = pack_path.read_text(encoding="utf-8")
            return self._parse_pack_content(content, pack_path.suffix, prefix)
        except (OSError, UnicodeDecodeError) as e:
            logger.error("Failed to read pack %s: %s", pack_path, e)
            return None
        except Exception as e:
            logger.exception("Unexpected error reading pack %s: %s", pack_path, e)
            return None

    def _parse_pack_content(
        self,
        content: str,
        suffix: str,
        prefix: str = "heroku.modules.",
    ) -> Optional[Dict[str, Any]]:
        """
        Parse language pack content

        Supports both YAML and JSON formats with special handling for
        multi-language packs and module prefixes.
        """
        try:
            if suffix == ".json":
                return json.loads(content)

            parsed = yaml.load(content)
            if not parsed:
                logger.warning("Empty language pack content")
                return None

            if isinstance(parsed, dict) and all(
                isinstance(key, str) and len(key) == 2 for key in parsed.keys()
            ):
                return self._process_multi_language_pack(parsed, prefix)

            return self._process_single_language_pack(parsed, prefix)

        except (json.JSONDecodeError, yaml.YAMLError) as e:
            logger.error("Failed to parse language pack: %s", e)
            return None
        except Exception as e:
            logger.exception("Unexpected error parsing language pack: %s", e)
            return None

    def _process_multi_language_pack(
        self,
        content: Dict[str, Any],
        prefix: str,
    ) -> Dict[str, Dict[str, str]]:
        """Process multi-language YAML pack"""
        result = {}
        for language, pack in content.items():
            language_dict = {}
            for module, strings in pack.items():
                if not isinstance(strings, dict):
                    continue

                module_prefix = (
                    module[1:]  # Remove leading '$'
                    if module.startswith("$")
                    else f"{prefix}{module}"
                )

                for key, value in strings.items():
                    if key != "name":
                        language_dict[f"{module_prefix}.{key}"] = value

            if language_dict:
                result[language] = language_dict

        return result

    def _process_single_language_pack(
        self,
        content: Dict[str, Any],
        prefix: str,
    ) -> Dict[str, str]:
        """Process single language YAML pack"""
        result = {}
        for module, strings in content.items():
            if not isinstance(strings, dict):
                continue

            module_prefix = (
                module[1:]  # Remove leading '$'
                if module.startswith("$")
                else f"{prefix}{module}"
            )

            for key, value in strings.items():
                if key != "name":
                    result[f"{module_prefix}.{key}"] = value

        return result

    def get_key(self, key: str) -> Union[str, bool]:
        """Get translation for a key or False if not found"""
        return self._data.get(key, False)

    def get_text(self, text: str) -> Union[str, bool]:
        """Get translation for text (alias for get_key)"""
        return self.get_key(text) or text

    async def load_module_translations(
        self,
        pack_url: str,
    ) -> Union[bool, Dict[str, Any]]:
        """Load module translations from URL"""
        try:
            response = await utils.run_sync(requests.get, pack_url)
            response.raise_for_status()
            data = yaml.load(response.text)

            if not data:
                logger.warning("Empty response from %s", pack_url)
                return False

            if isinstance(data, dict) and all(
                isinstance(key, str) and len(key) == 2 for key in data.keys()
            ):
                current_lang = self.db.get(__name__, "lang", DEFAULT_LANGUAGE)
                if current_lang:
                    for language in current_lang.split():
                        if language in data:
                            return data[language]

                return data.get("en", {})

            return data

        except requests.exceptions.RequestException as e:
            logger.error("Network error loading translations from %s: %s", pack_url, e)
            return False
        except yaml.YAMLError as e:
            logger.error("Invalid YAML in translations from %s: %s", pack_url, e)
            return False
        except Exception as e:
            logger.exception(
                "Unexpected error loading translations from %s: %s", pack_url, e
            )
            return False


class Translator(BaseTranslator):
    """Main translator class for Heroku modules"""

    def __init__(self, client: CustomTelegramClient, db: Database):
        self._client = client
        self.db = db
        self._data: Dict[str, str] = {}
        self.raw_data: Dict[str, Dict[str, str]] = {}

    async def init(self) -> bool:
        """Initialize translator with language packs"""
        try:
            default_pack = LANG_PACKS_DIR / f"{DEFAULT_LANGUAGE}.yml"
            if default_pack.exists():
                self._data = self._get_pack_content(default_pack) or {}
                self.raw_data[DEFAULT_LANGUAGE] = self._data.copy()
            else:
                logger.error("Default language pack not found: %s", default_pack)
                self._data = {}
                self.raw_data[DEFAULT_LANGUAGE] = {}

            any_loaded = False
            configured_lang = self.db.get(__name__, "lang")

            if configured_lang:
                any_loaded = await self._load_configured_languages(configured_lang)

            self._load_all_supported_languages()

            return any_loaded

        except Exception as e:
            logger.exception("Failed to initialize translator: %s", e)
            return False

    async def _load_configured_languages(self, configured_lang: str) -> bool:
        """Load user-configured languages"""
        any_loaded = False

        for language in configured_lang.split():
            if not language.strip():
                continue

            if utils.check_url(language):
                loaded = await self._load_remote_language(language)
                any_loaded = any_loaded or loaded
            else:
                loaded = self._load_local_language(language)
                any_loaded = any_loaded or loaded

        return any_loaded

    async def _load_remote_language(self, url: str) -> bool:
        """Load language pack from remote URL"""
        try:
            response = await utils.run_sync(requests.get, url)
            response.raise_for_status()

            suffix = f".{url.split('.')[-1]}" if "." in url else ""
            data = self._parse_pack_content(response.text, suffix)

            if data:
                self._data.update(data)
                self.raw_data[url] = data
                logger.debug("Loaded remote language pack: %s", url)
                return True

        except requests.exceptions.RequestException as e:
            logger.error("Failed to load remote language %s: %s", url, e)
        except Exception as e:
            logger.exception("Error loading remote language %s: %s", url, e)

        return False

    def _load_local_language(self, language: str) -> bool:
        """Load language pack from local files"""
        for extension in [".yml", ".yaml", ".json"]:
            pack_path = LANG_PACKS_DIR / f"{language}{extension}"
            if pack_path.exists():
                data = self._get_pack_content(pack_path)
                if data:
                    self._data.update(data)
                    self.raw_data[language] = data
                    logger.debug("Loaded local language pack: %s", language)
                    return True

        logger.warning("Language pack not found: %s", language)
        return False

    def _load_all_supported_languages(self) -> None:
        """Load all supported languages for external access"""
        for language in SUPPORTED_LANGUAGES:
            if language not in self.raw_data:
                pack_path = LANG_PACKS_DIR / f"{language}.yml"
                if pack_path.exists():
                    data = self._get_pack_content(pack_path)
                    if data:
                        self.raw_data[language] = data


class ExternalTranslator(BaseTranslator):
    """External translator for modules that need language dicts"""

    def __init__(self):
        self.data: Dict[str, Dict[str, str]] = {}
        self._load_all_languages()

    def _load_all_languages(self) -> None:
        """Load all supported languages"""
        for language in SUPPORTED_LANGUAGES:
            pack_path = LANG_PACKS_DIR / f"{language}.yml"
            if pack_path.exists():
                content = self._get_pack_content(pack_path, prefix="")
                if content:
                    self.data[language] = content
                else:
                    self.data[language] = {}
            else:
                logger.warning("Language pack not found: %s", language)
                self.data[language] = {}

    def get(self, key: str, lang: str) -> str:
        """Get translation for a key in specific language"""
        if lang not in self.data:
            logger.warning("Language not loaded: %s", lang)
            return key

        return self.data[lang].get(key, key)

    def get_dict(self, key: str, **kwargs) -> Dict[str, str]:
        """Get translations for a key in all languages"""
        result = {}
        for lang, lang_data in self.data.items():
            text = lang_data.get(key, key)
            if kwargs:
                text = format_string(text, kwargs)
            result[lang] = text

        return result


class Strings:
    """String manager for module translations"""

    def __init__(self, mod: Module, translator: Optional[Translator] = None):
        self._mod = mod
        self._translator = translator
        self._base_strings: Dict[str, str] = mod.strings  # Backup original strings
        self.external_strings: Dict[str, str] = {}

        if not translator:
            logger.debug(
                "Module %s initialized without translator", mod.__class__.__name__
            )

    def get(self, key: str, lang: Optional[str] = None) -> str:
        """Get translation for a key in specific language"""
        if lang and self._translator and lang in self._translator.raw_data:
            try:
                full_key = f"{self._mod.__module__}.{key}"
                return self._translator.raw_data[lang].get(full_key, self[key])
            except KeyError:
                pass

        return self[key]

    def __getitem__(self, key: str) -> str:
        """Get translation for a key using configured language"""
        if key in self.external_strings:
            return self.external_strings[key]

        if self._translator:
            full_key = f"{self._mod.__module__}.{key}"
            translated = self._translator.get_key(full_key)
            if translated:
                return translated

            configured_lang = self._translator.db.get(
                __name__, "lang", DEFAULT_LANGUAGE
            )
            if configured_lang:
                for language in configured_lang.split():
                    lang_attr = f"strings_{language}"
                    if hasattr(self._mod, lang_attr):
                        lang_strings = getattr(self._mod, lang_attr)
                        if isinstance(lang_strings, dict) and key in lang_strings:
                            return lang_strings[key]

        return self._base_strings.get(key, "Unknown strings")

    def __call__(
        self,
        key: str,
        _: Optional[Any] = None,  # Compatibility tweak for FTG/GeekTG
    ) -> str:
        """Allow calling instance like a function (compatibility)"""
        return self[key]

    def __iter__(self):
        """Iterate over base string keys"""
        return iter(self._base_strings)

    def keys(self) -> List[str]:
        """Get all string keys"""
        return list(self._base_strings.keys())

    def values(self) -> List[str]:
        """Get all string values (translated where possible)"""
        return [self[key] for key in self._base_strings]

    def items(self) -> List[tuple[str, str]]:
        """Get all key-value pairs"""
        return [(key, self[key]) for key in self._base_strings]


translator = ExternalTranslator()
