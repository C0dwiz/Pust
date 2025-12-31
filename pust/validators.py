# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

# ©️ Codrago, 2024-2025
# This file is a part of Pustserbot
# 🌐 https://github.com/coddrago/Pust
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

# SPDX-License-Identifier: GNU AGPL v3.0
#
# This file is a part of Pustserbot.
#
# Copyright (C) 2026 CodWiz

import functools
import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import grapheme
from emoji import get_emoji_unicode_dict

from . import utils
from .translations import SUPPORTED_LANGUAGES, translator

ConfigAllowedTypes = Union[Tuple, List, str, int, bool, None]


ALLOWED_EMOJIS = frozenset(get_emoji_unicode_dict("en").values())


class ValidationError(Exception):
    """
    Raised when config value cannot be converted properly.

    Must be raised with a string describing why the value is incorrect.
    It will be shown in .config if the user tries to set an incorrect value.
    """


class Validator:
    """
    Base class for config value validators.

    Args:
        validator: Sync function that raises `ValidationError` if the passed
                  value is incorrect (with explanation) and returns the converted
                  value if it is semantically correct.
                  ⚠️ If validator returns `None`, value will always be set to `None`
        doc: Documentation for this validator as a string, or dict in format:
             {
                 "en": "docstring",
                 "ru": "докстринг",
                 "ua": "докстрінг",
                 "de": "Dokumentation",
             }
             Use instrumental case with lowercase.
        _internal_id: Internal identifier (do not modify).
    """

    def __init__(
        self,
        validator: Callable[[ConfigAllowedTypes], Any],
        doc: Optional[Union[str, Dict[str, str]]] = None,
        _internal_id: Optional[str] = None,
    ):
        self.validate = validator
        self.internal_id = _internal_id

        if isinstance(doc, str):
            self.doc = {lang: doc for lang in SUPPORTED_LANGUAGES}
        elif isinstance(doc, dict):
            self.doc = doc
        else:
            self.doc = {lang: "No documentation" for lang in SUPPORTED_LANGUAGES}

    def __call__(self, value: ConfigAllowedTypes) -> Any:
        """Allow using validator as a callable."""
        return self.validate(value)


class Boolean(Validator):
    """
    Validates boolean values.

    Accepts: `1`, `"1"`, `True`, `"True"`, `"yes"`, `"on"`, `"y"` (case-insensitive)
    Rejects: `0`, `"0"`, `False`, `"False"`, `"no"`, `"off"`, `"n"` (case-insensitive)
    """

    _TRUE_VALUES = {
        "true",
        "1",
        "yes",
        "on",
        "y",
        "t",
        "True",
        "1",
        "Yes",
        "On",
        "Y",
        "T",
        True,
        1,
    }
    _FALSE_VALUES = {
        "false",
        "0",
        "no",
        "off",
        "n",
        "f",
        "False",
        "0",
        "No",
        "Off",
        "N",
        "F",
        False,
        0,
    }

    def __init__(self) -> None:
        super().__init__(
            validator=self._validate,
            doc=translator.get_dict("validators.boolean"),
            _internal_id="Boolean",
        )

    @classmethod
    def _validate(cls, value: ConfigAllowedTypes) -> bool:
        """Validate and convert to boolean."""

        if isinstance(value, str):
            value = value.strip()

        if value in cls._TRUE_VALUES:
            return True
        elif value in cls._FALSE_VALUES:
            return False

        raise ValidationError(f"Value must be a boolean, got {repr(value)}")


class Integer(Validator):
    """
    Validates integer values.

    Args:
        digits: Exact number of digits required.
        minimum: Minimum allowed value (inclusive).
        maximum: Maximum allowed value (inclusive).
    """

    def __init__(
        self,
        *,
        digits: Optional[int] = None,
        minimum: Optional[int] = None,
        maximum: Optional[int] = None,
    ) -> None:
        if digits is not None and digits <= 0:
            raise ValueError("digits must be positive")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("minimum cannot be greater than maximum")

        doc = self._generate_documentation(digits, minimum, maximum)

        super().__init__(
            validator=functools.partial(
                self._validate,
                digits=digits,
                minimum=minimum,
                maximum=maximum,
            ),
            doc=doc,
            _internal_id="Integer",
        )

    @staticmethod
    def _generate_documentation(
        digits: Optional[int],
        minimum: Optional[int],
        maximum: Optional[int],
    ) -> Dict[str, str]:
        """Generate documentation based on constraints."""
        if minimum is not None and minimum != 0:
            if maximum is not None and maximum != 0:
                return translator.get_dict(
                    "validators.integer_range",
                    minimum=minimum,
                    maximum=maximum,
                )
            else:
                return translator.get_dict("validators.integer_min", minimum=minimum)
        elif maximum is not None and maximum != 0:
            return translator.get_dict("validators.integer_max", maximum=maximum)
        elif digits is not None:
            return translator.get_dict("validators.integer_digits", digits=digits)
        else:
            return translator.get_dict("validators.integer")

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        *,
        digits: Optional[int],
        minimum: Optional[int],
        maximum: Optional[int],
    ) -> int:
        """Validate and convert to integer."""
        if value is None:
            raise ValidationError("Value cannot be None")

        try:
            str_value = str(value).strip()

            str_value = str_value.replace(",", "")
            int_value = int(str_value)
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Value must be an integer, got {repr(value)}") from e

        if digits is not None:
            str_rep = str(abs(int_value))
            if len(str_rep) != digits:
                raise ValidationError(
                    f"Value must have exactly {digits} digits, got {len(str_rep)}"
                )

        if minimum is not None and int_value < minimum:
            raise ValidationError(f"Value must be at least {minimum}, got {int_value}")

        if maximum is not None and int_value > maximum:
            raise ValidationError(f"Value must be at most {maximum}, got {int_value}")

        return int_value


class Choice(Validator):
    """
    Validates that a value is in a predefined set of allowed values.

    Args:
        possible_values: List of allowed values.
    """

    def __init__(self, possible_values: List[ConfigAllowedTypes]) -> None:
        if not possible_values:
            raise ValueError("possible_values cannot be empty")

        self.possible_values = possible_values
        possible_str = " / ".join(str(v) for v in possible_values)

        super().__init__(
            validator=functools.partial(
                self._validate, possible_values=possible_values
            ),
            doc=translator.get_dict("validators.choice", possible=possible_str),
            _internal_id="Choice",
        )

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        *,
        possible_values: List[ConfigAllowedTypes],
    ) -> ConfigAllowedTypes:
        """Validate that value is in allowed list."""
        if value not in possible_values:
            possible_str = " / ".join(str(v) for v in possible_values)
            raise ValidationError(
                f"Value must be one of: {possible_str}, got {repr(value)}"
            )
        return value


class MultiChoice(Validator):
    """
    Validates that all values in a list are in a predefined set.

    Args:
        possible_values: List of allowed values.
    """

    def __init__(self, possible_values: List[ConfigAllowedTypes]) -> None:
        if not possible_values:
            raise ValueError("possible_values cannot be empty")

        self.possible_values = possible_values
        possible_str = " / ".join(str(v) for v in possible_values)

        super().__init__(
            validator=functools.partial(
                self._validate, possible_values=possible_values
            ),
            doc=translator.get_dict("validators.multichoice", possible=possible_str),
            _internal_id="MultiChoice",
        )

    @staticmethod
    def _validate(
        value: Union[ConfigAllowedTypes, List[ConfigAllowedTypes]],
        *,
        possible_values: List[ConfigAllowedTypes],
    ) -> List[ConfigAllowedTypes]:
        """Validate that all values are in allowed list."""

        if not isinstance(value, (list, tuple, set)):
            value = [value]

        value_list = list(value)
        invalid_values = []

        for item in value_list:
            if item not in possible_values:
                invalid_values.append(item)

        if invalid_values:
            possible_str = " / ".join(str(v) for v in possible_values)
            invalid_str = ", ".join(str(v) for v in invalid_values)
            raise ValidationError(
                f"Invalid values: {invalid_str}. Must be from: {possible_str}"
            )

        return list(set(value_list))


class Series(Validator):
    """
    Validates a series (list) of values.

    Args:
        validator: Validator for each item in the series.
        min_len: Minimum number of items required.
        max_len: Maximum number of items allowed.
        fixed_len: Exact number of items required.
    """

    def __init__(
        self,
        validator: Optional[Validator] = None,
        min_len: Optional[int] = None,
        max_len: Optional[int] = None,
        fixed_len: Optional[int] = None,
    ) -> None:
        if min_len is not None and min_len < 0:
            raise ValueError("min_len cannot be negative")
        if max_len is not None and max_len < 0:
            raise ValueError("max_len cannot be negative")
        if fixed_len is not None and fixed_len < 0:
            raise ValueError("fixed_len cannot be negative")
        if min_len is not None and max_len is not None and min_len > max_len:
            raise ValueError("min_len cannot be greater than max_len")

        doc = self._generate_documentation(validator, min_len, max_len, fixed_len)

        super().__init__(
            validator=functools.partial(
                self._validate,
                validator=validator,
                min_len=min_len,
                max_len=max_len,
                fixed_len=fixed_len,
            ),
            doc=doc,
            _internal_id="Series",
        )

    @staticmethod
    def _generate_documentation(
        validator: Optional[Validator],
        min_len: Optional[int],
        max_len: Optional[int],
        fixed_len: Optional[int],
    ) -> Dict[str, str]:
        """Generate documentation based on constraints."""
        translator.get_dict("validators.series")

        length_doc = ""
        if fixed_len is not None:
            length_doc = translator.get("validators.fixed_len", "en").format(
                fixed_len=fixed_len
            )
        elif min_len is not None and max_len is not None:
            length_doc = translator.get("validators.len_range", "en").format(
                min_len=min_len,
                max_len=max_len,
            )
        elif min_len is not None:
            length_doc = translator.get("validators.min_len", "en").format(
                min_len=min_len
            )
        elif max_len is not None:
            length_doc = translator.get("validators.max_len", "en").format(
                max_len=max_len
            )

        each_doc = ""
        if validator and hasattr(validator, "doc"):
            each_doc = translator.get("validators.each", "en").format(
                each=validator.doc.get("en", "")
            )

        result = {}
        for lang in SUPPORTED_LANGUAGES:
            base = translator.get("validators.series", lang)
            result[lang] = base.format(each=each_doc, len=length_doc)

        return result

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        *,
        validator: Optional[Validator],
        min_len: Optional[int],
        max_len: Optional[int],
        fixed_len: Optional[int],
    ) -> List[ConfigAllowedTypes]:
        """Validate and convert to list."""

        if isinstance(value, str):
            value = [item.strip() for item in value.split(",") if item.strip()]
        elif isinstance(value, (tuple, set)):
            value = list(value)
        elif not isinstance(value, list):
            value = [value]

        length = len(value)

        if fixed_len is not None and length != fixed_len:
            raise ValidationError(
                f"Series must have exactly {fixed_len} items, got {length}"
            )

        if min_len is not None and length < min_len:
            raise ValidationError(
                f"Series must have at least {min_len} items, got {length}"
            )

        if max_len is not None and length > max_len:
            raise ValidationError(
                f"Series must have at most {max_len} items, got {length}"
            )

        if validator:
            validated_items = []
            for i, item in enumerate(value):
                try:
                    validated_item = validator.validate(item)
                    validated_items.append(validated_item)
                except ValidationError as e:
                    raise ValidationError(
                        f"Item {i + 1} ({repr(item)}) is invalid: {str(e)}"
                    ) from e
            value = validated_items

        return value


class Link(Validator):
    """Validates URL values."""

    def __init__(self) -> None:
        super().__init__(
            validator=self._validate,
            doc=translator.get_dict("validators.link"),
            _internal_id="Link",
        )

    @staticmethod
    def _validate(value: ConfigAllowedTypes) -> str:
        """Validate and return URL."""
        if not value:
            raise ValidationError("URL cannot be empty")

        str_value = str(value).strip()

        if not utils.check_url(str_value):
            raise ValidationError(f"Invalid URL: {repr(str_value)}")

        return str_value


class String(Validator):
    """
    Validates string values with length constraints.

    Args:
        length: Exact length required.
        min_len: Minimum length required.
        max_len: Maximum length allowed.
    """

    def __init__(
        self,
        length: Optional[int] = None,
        min_len: Optional[int] = None,
        max_len: Optional[int] = None,
    ) -> None:
        if length is not None and length < 0:
            raise ValueError("length cannot be negative")
        if min_len is not None and min_len < 0:
            raise ValueError("min_len cannot be negative")
        if max_len is not None and max_len < 0:
            raise ValueError("max_len cannot be negative")
        if min_len is not None and max_len is not None and min_len > max_len:
            raise ValueError("min_len cannot be greater than max_len")

        doc = self._generate_documentation(length, min_len, max_len)

        super().__init__(
            validator=functools.partial(
                self._validate,
                length=length,
                min_len=min_len,
                max_len=max_len,
            ),
            doc=doc,
            _internal_id="String",
        )

    @staticmethod
    def _generate_documentation(
        length: Optional[int],
        min_len: Optional[int],
        max_len: Optional[int],
    ) -> Dict[str, str]:
        """Generate documentation based on length constraints."""
        if length is not None:
            return translator.get_dict("validators.string_fixed_len", length=length)
        elif min_len is not None and max_len is not None:
            return translator.get_dict(
                "validators.string_len_range",
                min_len=min_len,
                max_len=max_len,
            )
        elif min_len is not None:
            return translator.get_dict("validators.string_min_len", min_len=min_len)
        elif max_len is not None:
            return translator.get_dict("validators.string_max_len", max_len=max_len)
        else:
            return translator.get_dict("validators.string")

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        *,
        length: Optional[int],
        min_len: Optional[int],
        max_len: Optional[int],
    ) -> str:
        """Validate string length."""
        str_value = str(value)

        char_count = len(list(grapheme.graphemes(str_value)))

        if length is not None and char_count != length:
            raise ValidationError(
                f"String must be exactly {length} characters, got {char_count}"
            )

        if min_len is not None and char_count < min_len:
            raise ValidationError(
                f"String must be at least {min_len} characters, got {char_count}"
            )

        if max_len is not None and char_count > max_len:
            raise ValidationError(
                f"String must be at most {max_len} characters, got {char_count}"
            )

        return str_value


class RegExp(Validator):
    """
    Validates values against a regular expression.

    Args:
        regex: Regular expression pattern.
        flags: Compilation flags for the regex.
        description: Description of the regex pattern.
    """

    def __init__(
        self,
        regex: str,
        flags: Optional[Union[int, re.RegexFlag]] = None,
        description: Optional[Union[Dict[str, str], str]] = None,
    ) -> None:
        try:
            compiled_regex = re.compile(regex, flags=flags or 0)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {regex}") from e

        self.compiled_regex = compiled_regex
        self.pattern = regex

        if description is None:
            doc = translator.get_dict("validators.regex", regex=regex)
        elif isinstance(description, str):
            doc = {lang: description for lang in SUPPORTED_LANGUAGES}
        else:
            doc = description

        super().__init__(
            validator=functools.partial(self._validate, compiled_regex=compiled_regex),
            doc=doc,
            _internal_id="RegExp",
        )

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        *,
        compiled_regex: re.Pattern,
    ) -> str:
        """Validate against regex pattern."""
        str_value = str(value)

        if not compiled_regex.match(str_value):
            raise ValidationError(f"Value must match pattern: {compiled_regex.pattern}")

        return str_value


class Float(Validator):
    """
    Validates floating-point values.

    Args:
        minimum: Minimum allowed value (inclusive).
        maximum: Maximum allowed value (inclusive).
    """

    def __init__(
        self,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
    ) -> None:
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError("minimum cannot be greater than maximum")

        doc = self._generate_documentation(minimum, maximum)

        super().__init__(
            validator=functools.partial(
                self._validate,
                minimum=minimum,
                maximum=maximum,
            ),
            doc=doc,
            _internal_id="Float",
        )

    @staticmethod
    def _generate_documentation(
        minimum: Optional[float],
        maximum: Optional[float],
    ) -> Dict[str, str]:
        """Generate documentation based on constraints."""
        if minimum is not None and minimum != 0:
            if maximum is not None and maximum != 0:
                return translator.get_dict(
                    "validators.float_range",
                    minimum=minimum,
                    maximum=maximum,
                )
            else:
                return translator.get_dict("validators.float_min", minimum=minimum)
        elif maximum is not None and maximum != 0:
            return translator.get_dict("validators.float_max", maximum=maximum)
        else:
            return translator.get_dict("validators.float")

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        *,
        minimum: Optional[float],
        maximum: Optional[float],
    ) -> float:
        """Validate and convert to float."""
        if value is None:
            raise ValidationError("Value cannot be None")

        try:
            str_value = str(value).strip().replace(",", ".")
            float_value = float(str_value)
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Value must be a number, got {repr(value)}") from e

        if minimum is not None and float_value < minimum:
            raise ValidationError(
                f"Value must be at least {minimum}, got {float_value}"
            )

        if maximum is not None and float_value > maximum:
            raise ValidationError(f"Value must be at most {maximum}, got {float_value}")

        return float_value


class TelegramID(Validator):
    """Validates Telegram ID values."""

    def __init__(self) -> None:
        super().__init__(
            validator=self._validate,
            doc=translator.get_dict("validators.telegram_id"),
            _internal_id="TelegramID",
        )

    @staticmethod
    def _validate(value: ConfigAllowedTypes) -> int:
        """Validate and return Telegram ID."""
        if not value:
            raise ValidationError("Telegram ID cannot be empty")

        try:
            str_value = str(value).strip()

            if str_value.startswith("-100"):
                str_value = str_value[4:]

            int_value = int(str_value)
        except (ValueError, TypeError) as e:
            raise ValidationError(f"Invalid Telegram ID: {repr(value)}") from e

        if int_value < 0:
            raise ValidationError(f"Telegram ID cannot be negative: {int_value}")

        if int_value > 2**64 - 1:
            raise ValidationError(f"Telegram ID too large: {int_value}")

        return int_value


class Union(Validator):
    """Validates that a value matches at least one of multiple validators."""

    def __init__(self, *validators: Validator) -> None:
        if not validators:
            raise ValueError("At least one validator is required")

        self.validators = validators

        doc = self._generate_documentation(validators)

        super().__init__(
            validator=functools.partial(self._validate, validators=validators),
            doc=doc,
            _internal_id="Union",
        )

    @staticmethod
    def _generate_documentation(validators: Tuple[Validator, ...]) -> Dict[str, str]:
        """Generate combined documentation."""
        base_doc = translator.get_dict("validators.union")

        result = {}
        for lang in SUPPORTED_LANGUAGES:
            lines = []
            for validator in validators:
                validator_doc = validator.doc.get(lang, validator.doc.get("en", ""))
                if validator_doc:
                    lines.append(f"- {validator_doc[0].upper()}{validator_doc[1:]}")

            result[lang] = base_doc.get(lang, "").format(options="\n".join(lines))

        return result

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        *,
        validators: Tuple[Validator, ...],
    ) -> Any:
        """Try each validator until one succeeds."""
        errors = []

        for validator in validators:
            try:
                return validator.validate(value)
            except ValidationError as e:
                errors.append(str(e))

        error_list = "\n".join(f"- {err}" for err in errors)
        raise ValidationError(f"Value does not match any validator:\n{error_list}")


class NoneType(Validator):
    """Validates that a value is None."""

    def __init__(self) -> None:
        super().__init__(
            validator=self._validate,
            doc=translator.get_dict("validators.empty"),
            _internal_id="NoneType",
        )

    @staticmethod
    def _validate(value: ConfigAllowedTypes) -> None:
        """Validate that value is None or empty."""
        if value is not None and value != "" and value != [] and value != {}:
            raise ValidationError(f"Value must be empty, got {repr(value)}")
        return None


class Hidden(Validator):
    """Hidden validator (same as underlying validator but without UI display)."""

    def __init__(self, validator: Optional[Validator] = None) -> None:
        if validator is None:
            validator = String()

        super().__init__(
            validator=functools.partial(self._validate, validator=validator),
            doc=validator.doc,
            _internal_id="Hidden",
        )

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        *,
        validator: Validator,
    ) -> Any:
        """Validate using underlying validator."""
        return validator.validate(value)


class Emoji(Validator):
    """
    Validates emoji strings.

    Args:
        length: Exact number of emojis required.
        min_len: Minimum number of emojis required.
        max_len: Maximum number of emojis allowed.
    """

    def __init__(
        self,
        length: Optional[int] = None,
        min_len: Optional[int] = None,
        max_len: Optional[int] = None,
    ) -> None:
        if length is not None and length < 0:
            raise ValueError("length cannot be negative")
        if min_len is not None and min_len < 0:
            raise ValueError("min_len cannot be negative")
        if max_len is not None and max_len < 0:
            raise ValueError("max_len cannot be negative")
        if min_len is not None and max_len is not None and min_len > max_len:
            raise ValueError("min_len cannot be greater than max_len")

        doc = self._generate_documentation(length, min_len, max_len)

        super().__init__(
            validator=functools.partial(
                self._validate,
                length=length,
                min_len=min_len,
                max_len=max_len,
            ),
            doc=doc,
            _internal_id="Emoji",
        )

    @staticmethod
    def _generate_documentation(
        length: Optional[int],
        min_len: Optional[int],
        max_len: Optional[int],
    ) -> Dict[str, str]:
        """Generate documentation based on constraints."""
        if length is not None:
            return translator.get_dict("validators.emoji_fixed_len", length=length)
        elif min_len is not None and max_len is not None:
            return translator.get_dict(
                "validators.emoji_len_range",
                min_len=min_len,
                max_len=max_len,
            )
        elif min_len is not None:
            return translator.get_dict("validators.emoji_min_len", min_len=min_len)
        elif max_len is not None:
            return translator.get_dict("validators.emoji_max_len", max_len=max_len)
        else:
            return translator.get_dict("validators.emoji")

    @staticmethod
    def _validate(
        value: ConfigAllowedTypes,
        *,
        length: Optional[int],
        min_len: Optional[int],
        max_len: Optional[int],
    ) -> str:
        """Validate emoji string."""
        str_value = str(value)

        graphemes = list(grapheme.graphemes(str_value))
        emoji_count = len(graphemes)

        if length is not None and emoji_count != length:
            raise ValidationError(
                f"Must have exactly {length} emojis, got {emoji_count}"
            )

        if min_len is not None and emoji_count < min_len:
            raise ValidationError(
                f"Must have at least {min_len} emojis, got {emoji_count}"
            )

        if max_len is not None and emoji_count > max_len:
            raise ValidationError(
                f"Must have at most {max_len} emojis, got {emoji_count}"
            )

        for i, grapheme_str in enumerate(graphemes):
            if grapheme_str not in ALLOWED_EMOJIS:
                raise ValidationError(
                    f"Character at position {i + 1} is not a valid emoji: {repr(grapheme_str)}"
                )

        return str_value


class EntityLike(Validator):
    """Validates Telegram entity-like strings (usernames, links, IDs)."""

    _ENTITY_REGEX = re.compile(
        r"^(?:@|https?://t\.me/)?"
        r"(?:[a-zA-Z0-9_]{5,32}|[a-zA-Z0-9_]{1,32}\?[a-zA-Z0-9_]{1,32})$"
    )

    def __init__(self) -> None:
        super().__init__(
            validator=self._validate,
            doc=translator.get_dict("validators.entity_like"),
            _internal_id="EntityLike",
        )

    @staticmethod
    def _validate(value: ConfigAllowedTypes) -> Union[str, int]:
        """Validate and normalize Telegram entity."""
        if not value:
            raise ValidationError("Entity cannot be empty")

        str_value = str(value).strip()

        if str_value.lstrip("-").isdigit():
            try:
                int_value = int(str_value)

                if str_value.startswith("-100"):
                    return int(str_value[4:])
                return int_value
            except (ValueError, TypeError):
                pass

        if not EntityLike._ENTITY_REGEX.match(str_value):
            raise ValidationError(f"Invalid Telegram entity: {repr(str_value)}")

        if str_value.startswith("https://t.me/"):
            str_value = str_value[13:]  # Remove "https://t.me/"

        if not str_value.startswith("@"):
            str_value = f"@{str_value}"

        return str_value
