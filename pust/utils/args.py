# ©️ Codrago, 2024-2025
# This file is a part of Pust Userbot
# 🌐 https://github.com/coddrago/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

# SPDX-License-Identifier: GNU AGPL v3.0
#
# This file is a part of Pust Userbot.
#
# Copyright (C) 2026 CodWiz

import inspect
import logging
import shlex
import re
from enum import StrEnum, IntEnum
from typing import Any, List, Optional, Dict, Callable
from dataclasses import dataclass, field
from functools import wraps

import telethon
import telethon.extensions
import telethon.extensions.html
from telethon.tl.custom.message import Message

from .entity import escape_html

parser = telethon.utils.sanitize_parse_mode("html")
logger = logging.getLogger(__name__)


class ArgumentType(StrEnum):
    """Argument type enumeration"""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    UNKNOWN = "unknown"


class ParseMode(StrEnum):
    """Parse mode enumeration"""

    HTML = "html"
    MARKDOWN = "markdown"
    PLAIN = "plain"


class ValidationLevel(IntEnum):
    """Validation level enumeration"""

    NONE = 0
    BASIC = 1
    STRICT = 2
    EXTENDED = 3


class ArgumentSource(StrEnum):
    """Argument source enumeration"""

    COMMAND = "command"
    INLINE = "inline"
    CALLBACK = "callback"
    SCHEDULED = "scheduled"
    WEB = "web"
    UNKNOWN = "unknown"


@dataclass
class ArgumentInfo:
    """Enhanced argument information with Python 3.12+ features"""

    value: str
    type: ArgumentType
    source: ArgumentSource
    position: int
    validated: bool = False
    validation_error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Check if argument is valid"""
        return self.validated and self.validation_error is None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "value": self.value,
            "type": self.type.value,
            "source": self.source.value,
            "position": self.position,
            "validated": self.validated,
            "validation_error": self.validation_error,
            "metadata": self.metadata,
        }


@dataclass
class ParsedCommand:
    """Enhanced parsed command information with Python 3.12+ features"""

    command: str
    args: List[ArgumentInfo]
    raw_args: str
    message: Optional[Message] = None
    parse_mode: ParseMode = ParseMode.PLAIN
    validation_level: ValidationLevel = ValidationLevel.BASIC
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_arg(self, index: int, default: Optional[str] = None) -> Optional[str]:
        """Get argument by index"""
        if 0 <= index < len(self.args):
            return self.args[index].value
        return default

    def get_args_by_type(self, arg_type: ArgumentType) -> List[ArgumentInfo]:
        """Get arguments by type"""
        return [arg for arg in self.args if arg.type == arg_type]

    def get_args_by_source(self, source: ArgumentSource) -> List[ArgumentInfo]:
        """Get arguments by source"""
        return [arg for arg in self.args if arg.source == source]

    def count(self) -> int:
        """Get total argument count"""
        return len(self.args)

    def is_empty(self) -> bool:
        """Check if command has no arguments"""
        return len(self.args) == 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "command": self.command,
            "args": [arg.to_dict() for arg in self.args],
            "raw_args": self.raw_args,
            "parse_mode": self.parse_mode.value,
            "validation_level": self.validation_level.value,
            "metadata": self.metadata,
        }


def iter_attrs(obj: object, /) -> list[tuple[str, object]]:
    """
    Returns list of attributes of object

    :param obj: Object to iterate over
    :return: List of attributes and their values
    """
    return ((attr, getattr(obj, attr)) for attr in dir(obj))


def get_kwargs() -> dict[str, object]:
    """
    Get kwargs of function, in which is called

    :return: kwargs
    """
    keys, _, _, values = inspect.getargvalues(inspect.currentframe().f_back)
    return {key: values[key] for key in keys if key != "self"}


def parse_command(
    message: Message | str,
    parse_mode: ParseMode = ParseMode.PLAIN,
    validation_level: ValidationLevel = ValidationLevel.BASIC,
    source: ArgumentSource = ArgumentSource.UNKNOWN,
) -> ParsedCommand:
    """Enhanced command parsing with modern Python 3.12+ features"""
    message_text = getattr(message, "message", message)

    if not message_text:
        return ParsedCommand(
            command="",
            args=[],
            raw_args="",
            message=message,
            parse_mode=parse_mode,
            validation_level=validation_level,
        )

    parts = message_text.split(maxsplit=1)
    command = parts[0]
    raw_args = parts[1] if len(parts) > 1 else ""

    args = []
    if raw_args:
        args = _parse_arguments(raw_args, parse_mode, validation_level, source)

    return ParsedCommand(
        command=command,
        args=args,
        raw_args=raw_args,
        message=message,
        parse_mode=parse_mode,
        validation_level=validation_level,
    )


def _parse_arguments(
    args_text: str,
    parse_mode: ParseMode,
    validation_level: ValidationLevel,
    source: ArgumentSource,
) -> List[ArgumentInfo]:
    """Parse arguments with enhanced validation"""
    args = []

    match args_text:
        case str(text):
            try:
                split_args = shlex.split(text)
                for i, arg in enumerate(split_args):
                    if len(arg) > 0:
                        arg_info = ArgumentInfo(
                            value=arg,
                            type=_detect_argument_type(arg),
                            source=source,
                            position=i,
                        )

                        if validation_level != ValidationLevel.NONE:
                            _validate_argument(arg_info, validation_level)

                        args.append(arg_info)

            except ValueError as e:
                arg_info = ArgumentInfo(
                    value=text,
                    type=ArgumentType.STRING,
                    source=source,
                    position=0,
                    validation_error=f"Cannot split argument: {e}",
                )

                if validation_level != ValidationLevel.NONE:
                    arg_info.validated = False

                args.append(arg_info)
        case _:
            pass

    return args


def _detect_argument_type(value: str) -> ArgumentType:
    """Detect argument type with enhanced logic"""

    if value.lstrip("-").isdigit():
        return ArgumentType.INTEGER

    try:
        float(value)
        return ArgumentType.FLOAT
    except ValueError:
        pass

    if value.lower() in ("true", "false", "yes", "no", "1", "0"):
        return ArgumentType.BOOLEAN

    if "," in value and value.count(",") > 1:
        return ArgumentType.LIST

    return ArgumentType.STRING


def _validate_argument(arg_info: ArgumentInfo, level: ValidationLevel) -> None:
    """Validate argument based on level"""
    match level:
        case ValidationLevel.BASIC:
            if not arg_info.value.strip():
                arg_info.validated = False
                arg_info.validation_error = "Argument cannot be empty"

        case ValidationLevel.STRICT:
            match arg_info.type:
                case ArgumentType.INTEGER:
                    try:
                        int(arg_info.value)
                        arg_info.validated = True
                    except ValueError:
                        arg_info.validated = False
                        arg_info.validation_error = "Invalid integer format"

                case ArgumentType.FLOAT:
                    try:
                        float(arg_info.value)
                        arg_info.validated = True
                    except ValueError:
                        arg_info.validated = False
                        arg_info.validation_error = "Invalid float format"

                case ArgumentType.BOOLEAN:
                    if arg_info.value.lower() not in (
                        "true",
                        "false",
                        "yes",
                        "no",
                        "1",
                        "0",
                    ):
                        arg_info.validated = False
                        arg_info.validation_error = "Invalid boolean value"
                    else:
                        arg_info.validated = True

                case ArgumentType.LIST:
                    items = [item.strip() for item in arg_info.value.split(",")]
                    if not all(items):
                        arg_info.validated = False
                        arg_info.validation_error = "List cannot have empty items"
                    else:
                        arg_info.validated = True

                case ArgumentType.STRING:
                    if len(arg_info.value) > 1000:
                        arg_info.validated = False
                        arg_info.validation_error = (
                            "String too long (max 1000 characters)"
                        )
                    else:
                        arg_info.validated = True

                case _:
                    arg_info.validated = True

        case ValidationLevel.EXTENDED:
            _validate_argument(arg_info, ValidationLevel.STRICT)

            if arg_info.type == ArgumentType.STRING:
                dangerous_patterns = [
                    "eval(",
                    "exec(",
                    "__import__",
                    "open(",
                    "file(",
                    "os.",
                    "subprocess.",
                    "<script",
                    "javascript:",
                    "vbscript:",
                    "powershell:",
                    "cmd.exe",
                ]

                if any(
                    pattern in arg_info.value.lower() for pattern in dangerous_patterns
                ):
                    arg_info.validated = False
                    arg_info.validation_error = "Potentially dangerous content detected"

                sql_patterns = [
                    "select ",
                    "insert ",
                    "update ",
                    "delete ",
                    "drop ",
                    "create ",
                    "alter ",
                    "truncate ",
                ]
                if any(pattern in arg_info.value.lower() for pattern in sql_patterns):
                    arg_info.validated = False
                    arg_info.validation_error = (
                        "Potentially dangerous SQL pattern detected"
                    )

                xss_patterns = [
                    "<script",
                    "javascript:",
                    "onload=",
                    "onerror=",
                    "onclick=",
                ]
                if any(pattern in arg_info.value.lower() for pattern in xss_patterns):
                    arg_info.validated = False
                    arg_info.validation_error = (
                        "Potentially dangerous XSS pattern detected"
                    )

                path_patterns = ["../", "..\\", "/etc/", "/sys/"]
                if any(pattern in arg_info.value for pattern in path_patterns):
                    arg_info.validated = False
                    arg_info.validation_error = (
                        "Potentially dangerous path traversal pattern detected"
                    )


def get_args(message: Message | str) -> List[str]:
    """Get arguments from message with enhanced features"""
    parsed = parse_command(message)
    return [arg.value for arg in parsed.args]


def get_args_raw(message: Message | str) -> str:
    """Get the parameters to the command as a raw string with enhanced features"""
    parsed = parse_command(message)
    return parsed.raw_args


def get_parsed_command(
    message: Message | str,
    parse_mode: ParseMode = ParseMode.PLAIN,
    validation_level: ValidationLevel = ValidationLevel.BASIC,
    source: ArgumentSource = ArgumentSource.UNKNOWN,
) -> ParsedCommand:
    """Get enhanced parsed command information"""
    return parse_command(message, parse_mode, validation_level, source)


def validate_arguments(
    args: List[ArgumentInfo],
    level: ValidationLevel = ValidationLevel.BASIC,
) -> bool:
    """Validate a list of arguments"""
    for arg in args:
        if not arg.is_valid():
            return False
    return True


def argument_validator(
    level: ValidationLevel = ValidationLevel.BASIC,
    custom_validators: Optional[List[Callable[[ArgumentInfo], bool]]] = None,
):
    """Enhanced argument validation decorator"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if "args" in kwargs:
                parsed_args = kwargs["args"]
                if isinstance(parsed_args, ParsedCommand):
                    if not validate_arguments(parsed_args.args, level):
                        raise ValueError("Argument validation failed")

                    if custom_validators:
                        for validator in custom_validators:
                            if not all(validator(arg) for arg in parsed_args.args):
                                raise ValueError("Custom validation failed")

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def argument_transformer(
    transformers: Dict[ArgumentType, Callable[[str], str]] | None = None,
):
    """Enhanced argument transformation decorator"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if "args" in kwargs:
                parsed_args = kwargs["args"]
                if isinstance(parsed_args, ParsedCommand):
                    for arg in parsed_args.args:
                        if arg.type in (transformers or {}):
                            try:
                                transformed_value = transformers[arg.type](arg.value)
                                arg.value = transformed_value
                                arg.type = _detect_argument_type(transformed_value)
                            except Exception as e:
                                logger.warning(
                                    f"Failed to transform argument {arg.value}: {e}"
                                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def get_args_html(message: Message) -> str:
    """
    Get the parameters to the command as string with HTML (not split)
    :param message: Message to get arguments from
    :return: String with HTML arguments
    """
    prefix = message.client.loader.get_prefix()

    if not (message := message.text):
        return ""

    if not message.startswith(prefix):
        return ""

    text, entities = telethon.extensions.html.parse(message)
    return telethon.extensions.html.unparse(
        escape_html(text[len(prefix + get_args_raw(message).split(maxsplit=1)[0]) :]),
        entities,
    )


def get_args_html_parsed(message: Message) -> str:
    """
    Get the parameters to the command as string with HTML (not split)
    :param message: Message to get arguments from
    :return: Valid HTML
    """
    text, entities = telethon.extensions.html.parse(get_args_html(message))
    return telethon.extensions.html.unparse(escape_html(text), entities)
