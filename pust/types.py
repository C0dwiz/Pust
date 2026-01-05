# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

# ©️ Codrago, 2024-2025
# This file is a part of Pustserbot
# 🌐 https://github.com/coddrago/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

# SPDX-License-Identifier: GNU AGPL v3.0
#
# This file is a part of Pustserbot.
#
# Copyright (C) 2026 CodWiz

from __future__ import annotations

import ast
import asyncio
import contextlib
import copy
import importlib
import importlib.machinery
import importlib.util
import inspect
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from importlib.abc import SourceLoader
from types import CodeType
from typing import TYPE_CHECKING, Any, Callable, Optional, Protocol, TypeAlias, Union

import requests
from telethon.hints import EntityLike
from telethon.tl.functions.account import UpdateNotifySettingsRequest
from telethon.tl.types import (
    Channel,
    ChannelForbidden,
    ChannelFull,
    InputPeerNotifySettings,
    Message,
    UserFull,
)

from . import version
from ._reference_finder import replace_all_refs
from .inline.types import (
    BotInlineCall,
    BotInlineMessage,
    BotMessage,
    InlineCall,
    InlineMessage,
    InlineQuery,
    InlineUnit,
)
from .pointers import PointerDict, PointerList

if TYPE_CHECKING:
    from .inline.core import InlineManager
    from .loader import Modules
    from .tl_cache import CustomTelegramClient

    class Module:
        pass


__all__ = [
    "JSONSerializable",
    "PustReplyMarkup",
    "ListLike",
    "Command",
    "StringLoader",
    "Module",
    "get_commands",
    "get_inline_handlers",
    "get_callback_handlers",
    "BotInlineCall",
    "BotMessage",
    "InlineCall",
    "InlineMessage",
    "InlineQuery",
    "InlineUnit",
    "BotInlineMessage",
    "PointerDict",
    "PointerList",
    "Library",
    "LoadError",
    "CoreOverwriteError",
    "CoreUnloadError",
    "SelfUnload",
    "SelfSuspend",
    "StopLoop",
    "ModuleConfig",
    "LibraryConfig",
    "ConfigValue",
    "CacheRecordEntity",
    "CacheRecordPerms",
    "CacheRecordFullChannel",
    "CacheRecordFullUser",
]

logger = logging.getLogger(__name__)


from typing import TYPE_CHECKING  # noqa: E402

if TYPE_CHECKING:
    JSONSerializable = str | int | float | bool | list | dict | None
    PustReplyMarkup = list[list[dict]] | list[dict] | dict
    ListLike = list | set | tuple
    Command = Callable[..., Any]
else:
    JSONSerializable = Union[str, int, float, bool, list, dict, None]
    PustReplyMarkup = Union[list[list[dict]], list[dict], dict]
    ListLike = Union[list, set, tuple]
    Command = Callable[..., Any]


class ModuleType(StrEnum):
    """Module type enumeration"""

    CORE = "core"
    USER = "user"
    SYSTEM = "system"
    INLINE = "inline"


class SecurityLevel(IntEnum):
    """Security level enumeration"""

    OWNER = 1 << 0
    SUDO = 1 << 1
    SUPPORT = 1 << 2
    GROUP_OWNER = 1 << 3
    GROUP_ADMIN_ADD_ADMINS = 1 << 4
    GROUP_ADMIN_CHANGE_INFO = 1 << 5
    GROUP_ADMIN_BAN_USERS = 1 << 6
    GROUP_ADMIN_DELETE_MESSAGES = 1 << 7
    GROUP_ADMIN_PIN_MESSAGES = 1 << 8
    GROUP_ADMIN_INVITE_USERS = 1 << 9
    GROUP_ADMIN = 1 << 10
    GROUP_MEMBER = 1 << 11
    PM = 1 << 12
    EVERYONE = 1 << 13


class LoadStatus(StrEnum):
    """Module load status enumeration"""

    LOADING = "loading"
    LOADED = "loaded"
    UNLOADING = "unloading"
    UNLOADED = "unloaded"
    ERROR = "error"


class AsyncCommand(Protocol):
    """Protocol for async commands"""

    async def __call__(self, message: Message) -> Any: ...


class SyncCommand(Protocol):
    """Protocol for sync commands"""

    def __call__(self, message: Message) -> Any: ...


class ModuleLike(Protocol):
    """Protocol for module-like objects"""

    name: str
    strings: dict[str, str]
    commands: dict[str, Command]

    async def load(self) -> None: ...
    async def unload(self) -> None: ...


class StringLoader(SourceLoader):
    """Load a Python module from string data"""

    def __init__(self, data: str | bytes, origin: str) -> None:
        match data:
            case str():
                self.data: bytes = data.encode("utf-8")
            case bytes():
                self.data = data
            case _:
                raise TypeError(f"Expected str or bytes, got {type(data).__name__}")

        self.origin = origin

    def get_source(self, fullname: str) -> str:
        """Get source code as string"""
        return self.data.decode("utf-8")

    def get_code(self, fullname: str) -> CodeType | None:
        """Get compiled code object"""
        source = self.get_data(fullname)
        if source:
            return compile(
                source.decode("utf-8"),
                self.origin,
                "exec",
                dont_inherit=True,
            )
        return None

    def get_filename(self, fullname: str) -> str:
        """Get filename for module"""
        return self.origin

    def get_data(self, path: str) -> bytes:
        """Get raw bytes data"""
        return self.data


class Module:
    """Base class for all Pustodules"""

    strings = {"name": "Unknown"}
    """There is no help for this module"""

    def config_complete(self) -> None:
        """Called when module.config is populated"""

    async def client_ready(self) -> None:
        """Called after client is ready (after config_loaded)"""

    def internal_init(self) -> None:
        """Initialize module with required dependencies"""
        self.allmodules: Modules
        self.db = self.allmodules.db
        self._db = self.allmodules.db

        self.client: CustomTelegramClient = self.allmodules.client
        self._client: CustomTelegramClient = self.allmodules.client

        self.lookup = self.allmodules.lookup
        self.get_prefix = self.allmodules.get_prefix
        self.get_prefixes = self.allmodules.get_prefixes

        self.inline: InlineManager = self.allmodules.inline
        self.allclients: list[CustomTelegramClient] = self.allmodules.allclients

        self.tg_id: int = self._client.tg_id
        self._tg_id: int = self._client.tg_id

    async def on_unload(self) -> None:
        """Called after unloading / reloading module"""

    async def on_dlmod(self) -> None:
        """
        Called after the module is first time loaded with .dlmod or .loadmod

        Possible use-cases:
        - Send reaction to author's channel message
        - Create asset folder
        - ...

        ⚠️ Note, that any error there will not interrupt module load, and will just
        send a message to logs with verbosity INFO and exception traceback
        """

    async def invoke(
        self,
        command: str,
        args: Optional[str] = None,
        peer: Optional[EntityLike] = None,
        message: Optional[Message] = None,
        edit: bool = False,
    ) -> Message:
        """
        Invoke another command

        Args:
            command: Command to invoke
            args: Arguments to pass to command
            peer: Peer to send the command to. If not specified, will send to the current chat
            message: Message to edit or respond to
            edit: Whether to edit the message

        Returns:
            The message that was sent or edited

        Raises:
            ValueError: If command not found or neither peer nor message specified
        """
        if command not in self.allmodules.commands:
            raise ValueError(f"Command {command} not found")

        if not message and not peer:
            raise ValueError("Either peer or message must be specified")

        cmd = f"{self.get_prefix()}{command} {args or ''}".strip()

        if peer:
            message_obj = await self._client.send_message(peer, cmd)
        else:
            if edit:
                message_obj = await message.edit(cmd)
            else:
                message_obj = await message.respond(cmd)

        await self.allmodules.commands[command](message_obj)
        return message_obj

    @property
    def commands(self) -> dict[str, Command]:
        """List of commands that module supports"""
        return get_commands(self)

    @property
    def Pustommands(self) -> dict[str, Command]:
        """Alias for commands (compatibility)"""
        return get_commands(self)

    @property
    def inline_handlers(self) -> dict[str, Command]:
        """List of inline handlers that module supports"""
        return get_inline_handlers(self)

    @property
    def Pustnline_handlers(self) -> dict[str, Command]:
        """Alias for inline_handlers (compatibility)"""
        return get_inline_handlers(self)

    @property
    def callback_handlers(self) -> dict[str, Command]:
        """List of callback handlers that module supports"""
        return get_callback_handlers(self)

    @property
    def Pustallback_handlers(self) -> dict[str, Command]:
        """Alias for callback_handlers (compatibility)"""
        return get_callback_handlers(self)

    @property
    def watchers(self) -> dict[str, Command]:
        """List of watchers that module supports"""
        return get_watchers(self)

    @property
    def Pustatchers(self) -> dict[str, Command]:
        """Alias for watchers (compatibility)"""
        return get_watchers(self)

    @commands.setter
    def commands(self, value: Any) -> None:
        """Prevent setting commands directly"""

    @Pustommands.setter
    def Pustommands(self, value: Any) -> None:
        """Prevent setting commands directly"""

    @inline_handlers.setter
    def inline_handlers(self, value: Any) -> None:
        """Prevent setting inline_handlers directly"""

    @Pustnline_handlers.setter
    def Pustnline_handlers(self, value: Any) -> None:
        """Prevent setting inline_handlers directly"""

    @callback_handlers.setter
    def callback_handlers(self, value: Any) -> None:
        """Prevent setting callback_handlers directly"""

    @Pustallback_handlers.setter
    def Pustallback_handlers(self, value: Any) -> None:
        """Prevent setting callback_handlers directly"""

    @watchers.setter
    def watchers(self, value: Any) -> None:
        """Prevent setting watchers directly"""

    @Pustatchers.setter
    def Pustatchers(self, value: Any) -> None:
        """Prevent setting watchers directly"""

    async def animate(
        self,
        message: Union[Message, InlineMessage],
        frames: list[str],
        interval: Union[float, int],
        *,
        inline: bool = False,
    ) -> Union[Message, InlineMessage, None]:
        """
        Animate message with sequential frames

        Args:
            message: Message to animate
            frames: List of strings which are the frames of animation
            interval: Animation delay in seconds
            inline: Whether to use inline bot for animation

        Returns:
            The last message in animation

        Note:
            If `inline=True`, first frame will be shown with an empty
            button due to Telegram API limitations
        """
        from . import utils

        with contextlib.suppress(AttributeError):
            _Pustlient_id_logging_tag = copy.copy(self.client.tg_id)  # noqa: F841

        if interval < 0.1:
            logger.warning("Resetting animation interval to 0.1s to avoid floodwaits")
            interval = 0.1

        result = None
        for frame in frames:
            try:
                if isinstance(message, Message):
                    if inline:
                        message = await self.inline.form(
                            message=message,
                            text=frame,
                            reply_markup={"text": "\u0020\u2800", "data": "empty"},
                        )
                    else:
                        message = await utils.answer(message, frame)
                elif isinstance(message, InlineMessage) and inline:
                    await message.edit(frame)

                result = message
                await asyncio.sleep(interval)
            except Exception as e:
                logger.error("Animation frame error: %s", e)
                break

        return result

    def get(
        self,
        key: str,
        default: Optional[JSONSerializable] = None,
    ) -> JSONSerializable:
        """Get value from module's database section"""
        return self._db.get(self.__class__.__name__, key, default)

    def set(self, key: str, value: JSONSerializable) -> bool:
        """Set value in module's database section"""
        return self._db.set(self.__class__.__name__, key, value)

    def pointer(
        self,
        key: str,
        default: Optional[JSONSerializable] = None,
        item_type: Optional[Any] = None,
    ) -> Union[JSONSerializable, PointerList, PointerDict]:
        """Get a pointer to database key"""
        return self._db.pointer(self.__class__.__name__, key, default, item_type)

    async def _decline(
        self,
        call: InlineCall,
        channel: EntityLike,
        event: asyncio.Event,
    ) -> None:
        """Handle decline of join request"""
        from . import utils

        declined = self._db.get("Pustain", "declined_joins", [])
        declined.append(channel.id)
        self._db.set(
            "Pustain",
            "declined_joins",
            list(set(declined)),
        )
        event.status = False
        event.set()
        await call.edit(
            (
                "✖️ <b>Declined joining <a"
                f' href="https://t.me/{channel.username}">{utils.escape_html(channel.title)}</a></b>'
            ),
            photo=(
                "https://raw.githubusercontent.com/coddrago/assets/refs/heads/main/"
                "Pusteclined_jr.png"
            ),
        )

    async def request_join(
        self,
        peer: EntityLike,
        reason: str,
        assure_joined: Optional[bool] = False,
    ) -> bool:
        """
        Request to join a channel

        Args:
            peer: The channel to join
            reason: The reason for joining
            assure_joined: If True, module will not load unless channel is joined

        Returns:
            Status of the request (True if joined or approved)

        Raises:
            LoadError: If assure_joined=True and user declines or is banned
            TypeError: If peer is not a channel
        """
        from . import utils

        try:
            channel = await self.client.get_entity(peer)
        except Exception as e:
            logger.error("Failed to get channel entity: %s", e)
            return False

        if isinstance(channel, ChannelForbidden):
            if assure_joined:
                raise LoadError(
                    f"You need to join {channel.title} in order to use this module, "
                    "but you have been banned there"
                )
            return False

        declined_joins = self._db.get("Pustain", "declined_joins", [])
        if channel.id in declined_joins:
            if assure_joined:
                raise LoadError(
                    f"You need to join @{getattr(channel, 'username', 'channel')} "
                    "in order to use this module"
                )
            return False

        if not isinstance(channel, Channel):
            raise TypeError("`peer` field must be a channel")

        if getattr(channel, "left", True):
            try:
                channel = await self.client.force_get_entity(peer)
            except Exception as e:
                logger.error("Failed to force get channel entity: %s", e)
                return False

        if not getattr(channel, "left", True):
            return True

        event = asyncio.Event()
        try:
            await self.client(
                UpdateNotifySettingsRequest(
                    peer=self.inline.bot_username,
                    settings=InputPeerNotifySettings(
                        show_previews=False,
                        silent=False,
                    ),
                )
            )
        except Exception as e:
            logger.warning("Failed to update notify settings: %s", e)

        try:
            await self.inline.bot.send_photo(
                self.tg_id,
                (
                    "https://raw.githubusercontent.com/coddrago/assets/refs/heads/main/"
                    "Pustoin_request.png"
                ),
                caption=(
                    self._client.loader.lookup("translations")
                    .strings("requested_join")
                    .format(
                        self.__class__.__name__,
                        channel.username,
                        utils.escape_html(channel.title),
                        utils.escape_html(reason),
                    )
                ),
                reply_markup=self.inline.generate_markup(
                    [
                        {
                            "text": "💫 Approve",
                            "callback": self.lookup("loader").approve_internal,
                            "args": (channel, event),
                        },
                        {
                            "text": "✖️ Decline",
                            "callback": self._decline,
                            "args": (channel, event),
                        },
                    ]
                ),
            )
        except Exception as e:
            logger.error("Failed to send join request: %s", e)
            return False

        self.Pustait_channel_approve = (
            self.__class__.__name__,
            channel,
            reason,
        )
        event.status = False
        await event.wait()

        with contextlib.suppress(AttributeError):
            delattr(self, "Pustait_channel_approve")

        if assure_joined and not event.status:
            raise LoadError(
                f"You need to join @{channel.username} in order to use this module"
            )

        return event.status

    async def import_lib(
        self,
        url: str,
        *,
        suspend_on_error: Optional[bool] = False,
        _did_requirements: bool = False,
    ) -> "Library":
        """
        Import library from URL

        Args:
            url: URL to import library from
            suspend_on_error: Raise SelfSuspend if library can't be loaded
            _did_requirements: Internal flag for retry after installing requirements

        Returns:
            Library instance

        Raises:
            ValueError: Invalid URL
            RuntimeError: Library requirements not met
            ImportError: Library import failed
        """
        from . import utils
        from .loader import USER_INSTALL, VALID_PIP_PACKAGES
        from .translations import Strings

        def _raise(e: Exception) -> None:
            """Raise appropriate error based on suspend_on_error flag"""
            if suspend_on_error:
                raise SelfSuspend("Required library is not available or is corrupted.")
            raise e

        if not utils.check_url(url):
            _raise(ValueError("Invalid URL for library"))

        try:
            response = await utils.run_sync(requests.get, url)
            response.raise_for_status()
            code = response.text
        except Exception as e:
            _raise(e)

        if re.search(r"# ?scope: ?Pustin", code):
            match = re.search(r"# ?scope: ?Pustin ((\d+\.){2}\d+)", code)
            if match:
                ver = tuple(map(int, match.group(1).split(".")))
                if version.__version__ < ver:
                    _raise(
                        RuntimeError(
                            f"Library requires Pustersion {'{}.{}.{}'.format(*ver)}+"
                        )
                    )

        module_name = f"Pustibraries.{url.replace('%', '%%').replace('.', '%d')}"
        origin = f"<library {url}>"

        spec = importlib.machinery.ModuleSpec(
            module_name,
            StringLoader(code, origin),
            origin=origin,
        )

        try:
            instance = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = instance
            spec.loader.exec_module(instance)
        except ImportError as e:
            logger.info(
                "Library loading failed, attempting dependency installation (%s)",
                e.name,
            )

            try:
                requirements_match = VALID_PIP_PACKAGES.search(code)
                if requirements_match:
                    requirements = list(
                        filter(
                            lambda x: not x.startswith(("-", "_", ".")),
                            map(str.strip, requirements_match.group(1).split()),
                        )
                    )
                else:
                    logger.warning(
                        "No valid pip packages specified, attempting from error"
                    )
                    requirements = [e.name]
            except Exception:
                requirements = [e.name]

            logger.debug("Installing requirements: %s", requirements)

            if not requirements or _did_requirements:
                _raise(e)

            pip_cmd = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "-q",
                "--disable-pip-version-check",
                "--no-warn-script-location",
            ]

            if USER_INSTALL:
                pip_cmd.append("--user")

            pip_cmd.extend(requirements)

            pip = await asyncio.create_subprocess_exec(*pip_cmd)
            rc = await pip.wait()

            if rc != 0:
                _raise(e)

            importlib.invalidate_caches()
            return await self.import_lib(
                url,
                suspend_on_error=suspend_on_error,
                _did_requirements=True,
            )

        lib_obj = None
        for value in vars(instance).values():
            if inspect.isclass(value) and issubclass(value, Library):
                lib_obj = value()
                break

        if not lib_obj:
            _raise(ImportError("Invalid library. No class found"))

        if not lib_obj.__class__.__name__.endswith("Lib"):
            _raise(
                ImportError(
                    f"Invalid library. Classname {lib_obj.__class__.__name__} "
                    "does not end with 'Lib'"
                )
            )

        if (
            all(
                line.replace(" ", "") != "#scope:no_stats" for line in code.splitlines()
            )
            and self._db.get("Pustain", "stats", True)
            and utils.check_url(url)
        ):
            with contextlib.suppress(Exception):
                await self.lookup("loader")._send_stats(url)

        lib_obj.source_url = url.strip("/")
        lib_obj.allmodules = self.allmodules
        lib_obj.internal_init()

        for old_lib in self.allmodules.libraries:
            if old_lib.name == lib_obj.name:
                old_version = getattr(old_lib, "version", None)
                new_version = getattr(lib_obj, "version", None)

                if (not old_version and not new_version) or (
                    isinstance(old_version, tuple)
                    and isinstance(new_version, tuple)
                    and old_version >= new_version
                ):
                    logger.debug("Using existing instance of library %s", old_lib.name)
                    return old_lib

        if hasattr(lib_obj, "init"):
            if not callable(lib_obj.init):
                _raise(ValueError("Library init() must be callable"))

            try:
                await lib_obj.init()
            except Exception as e:
                _raise(RuntimeError(f"Library init() failed: {e}"))

        if hasattr(lib_obj, "config"):
            if not isinstance(lib_obj.config, LibraryConfig):
                _raise(
                    RuntimeError("Library config must be a `LibraryConfig` instance")
                )

            libcfg = lib_obj.db.get(
                lib_obj.__class__.__name__,
                "__config__",
                {},
            )

            for conf in lib_obj.config:
                try:
                    value = (
                        libcfg[conf]
                        if conf in libcfg
                        else os.environ.get(f"{lib_obj.__class__.__name__}.{conf}")
                        or lib_obj.config.getdef(conf)
                    )
                    lib_obj.config.set_no_raise(conf, value)
                except Exception as e:
                    logger.warning("Failed to set config %s: %s", conf, e)

        if hasattr(lib_obj, "strings"):
            lib_obj.strings = Strings(lib_obj, getattr(self, "translator", None))

        lib_obj.translator = getattr(self, "translator", None)

        for old_lib in self.allmodules.libraries:
            if old_lib.name == lib_obj.name:
                if hasattr(old_lib, "on_lib_update") and callable(
                    old_lib.on_lib_update
                ):
                    await old_lib.on_lib_update(lib_obj)

                replace_all_refs(old_lib, lib_obj)
                logger.debug(
                    "Replacing existing instance of library %s with updated object",
                    lib_obj.name,
                )
                return lib_obj

        self.allmodules.libraries.append(lib_obj)
        return lib_obj


class Library:
    """Base class for all external libraries"""

    def internal_init(self) -> None:
        """Initialize library with required dependencies"""
        self.name = self.__class__.__name__
        self.db = self.allmodules.db
        self._db = self.allmodules.db
        self.client = self.allmodules.client
        self._client = self.allmodules.client
        self.tg_id = self._client.tg_id
        self._tg_id = self._client.tg_id
        self.lookup = self.allmodules.lookup
        self.get_prefix = self.allmodules.get_prefix
        self.get_prefixes = self.allmodules.get_prefixes
        self.inline = self.allmodules.inline
        self.allclients = self.allmodules.allclients

    def _lib_get(
        self,
        key: str,
        default: Optional[JSONSerializable] = None,
    ) -> JSONSerializable:
        """Get value from library's database section"""
        return self._db.get(self.__class__.__name__, key, default)

    def _lib_set(self, key: str, value: JSONSerializable) -> bool:
        """Set value in library's database section"""
        return self._db.set(self.__class__.__name__, key, value)

    def _lib_pointer(
        self,
        key: str,
        default: Optional[JSONSerializable] = None,
    ) -> Union[JSONSerializable, PointerDict, PointerList]:
        """Get a pointer to library's database key"""
        return self._db.pointer(self.__class__.__name__, key, default)


class LoadError(Exception):
    """Raised when module cannot be loaded, shows error to user"""

    def __init__(self, error_message: str) -> None:
        self._error = error_message
        super().__init__(error_message)

    def __str__(self) -> str:
        return self._error


class CoreOverwriteError(LoadError):
    """Raised when trying to overwrite core module or command"""

    def __init__(
        self,
        module: Optional[str] = None,
        command: Optional[str] = None,
    ) -> None:
        self.type = "module" if module else "command"
        self.target = module or command
        super().__init__(str(self))

    def __str__(self) -> str:
        return (
            f"{'Module' if self.type == 'module' else 'Command'} {self.target} "
            "will not be overwritten because it's core"
        )


class CoreUnloadError(Exception):
    """Raised when trying to unload core module"""

    def __init__(self, module: str) -> None:
        self.module = module
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"Module {self.module} will not be unloaded because it's core"


class SelfUnload(Exception):
    """Silently unloads module when raised in `client_ready`"""

    def __init__(self, error_message: str = "") -> None:
        self._error = error_message
        super().__init__(error_message)

    def __str__(self) -> str:
        return self._error


class SelfSuspend(Exception):
    """
    Silently suspends module when raised in `client_ready`

    Commands and watchers will not be registered.
    Module won't be unloaded from db and will be restored after restart,
    unless the exception is raised again.
    """

    def __init__(self, error_message: str = "") -> None:
        self._error = error_message
        super().__init__(error_message)

    def __str__(self) -> str:
        return self._error


class StopLoop(Exception):
    """Stops the loop in which it is raised"""


class ModuleConfig(dict):
    """Configuration container for modules and libraries"""

    def __init__(self, *entries: Union[str, "ConfigValue"]) -> None:
        if all(isinstance(entry, ConfigValue) for entry in entries):
            self._config = {config.option: config for config in entries}
        else:
            keys = []
            values = []
            defaults = []
            docstrings = []

            for i, entry in enumerate(entries):
                if i % 3 == 0:
                    keys.append(entry)
                elif i % 3 == 1:
                    values.append(entry)
                    defaults.append(entry)
                else:
                    docstrings.append(entry)

            self._config = {
                key: ConfigValue(option=key, default=default, doc=doc)
                for key, default, doc in zip(keys, defaults, docstrings)
            }

        super().__init__(
            {option: config.value for option, config in self._config.items()}
        )

    def getdoc(self, key: str, message: Optional[Message] = None) -> str:
        """Get documentation for configuration key"""
        ret = self._config[key].doc

        if callable(ret):
            try:
                ret = ret(message)
            except Exception:
                ret = ret()

        return ret

    def getdef(self, key: str) -> Any:
        """Get default value for configuration key"""
        return self._config[key].default

    def __setitem__(self, key: str, value: Any) -> None:
        if key in self._config:
            self._config[key].value = value
            super().__setitem__(key, value)
        else:
            raise KeyError(f"Configuration key {key} not found")

    def set_no_raise(self, key: str, value: Any) -> None:
        """Set configuration value without raising validation errors"""
        if key in self._config:
            self._config[key].set_no_raise(value)
            super().__setitem__(key, value)
        else:
            raise KeyError(f"Configuration key {key} not found")

    def __getitem__(self, key: str) -> Any:
        try:
            return self._config[key].value
        except KeyError:
            return None

    def reload(self) -> None:
        """Reload all configuration values from internal state"""
        for key in self._config:
            super().__setitem__(key, self._config[key].value)

    def change_validator(
        self,
        key: str,
        validator: Callable[[JSONSerializable], JSONSerializable],
    ) -> None:
        """Change validator for configuration key"""
        if key in self._config:
            self._config[key].validator = validator
        else:
            raise KeyError(f"Configuration key {key} not found")


LibraryConfig = ModuleConfig


class _Placeholder:
    """Placeholder to indicate default value should be used"""


async def wrap(func: Callable[[], Any]) -> Any:
    """Safely execute async function suppressing exceptions"""
    with contextlib.suppress(Exception):
        return await func()
    return None


def syncwrap(func: Callable[[], Any]) -> Any:
    """Safely execute sync function suppressing exceptions"""
    with contextlib.suppress(Exception):
        return func()
    return None


@dataclass(repr=True)
class ConfigValue:
    """Single configuration value with validation and callbacks"""

    option: str
    default: Any = None
    doc: Union[Callable[[], str], str] = "No description"
    value: Any = field(default_factory=_Placeholder)
    validator: Optional[Callable[[JSONSerializable], JSONSerializable]] = None
    on_change: Optional[Union[Callable[[], Any], Callable]] = None

    def __post_init__(self) -> None:
        """Initialize value to default if not set"""
        if isinstance(self.value, _Placeholder):
            self.value = self.default

    def set_no_raise(self, value: Any) -> bool:
        """
        Set value without raising validation errors

        Should only be used internally
        """
        return self.__setattr__("value", value, ignore_validation=True)

    def __setattr__(
        self,
        key: str,
        value: Any,
        *,
        ignore_validation: bool = False,
    ) -> None:
        if key == "value":
            if isinstance(value, str):
                try:
                    value = ast.literal_eval(value)
                except (ValueError, SyntaxError):
                    pass

            if isinstance(value, (set, tuple)):
                value = list(value)

            if isinstance(value, list):
                value = [
                    item.strip() if isinstance(item, str) else item for item in value
                ]

            if self.validator is not None and value is not None:
                from . import validators

                try:
                    value = self.validator.validate(value)
                except validators.ValidationError as e:
                    if not ignore_validation:
                        raise e

                    logger.debug(
                        "Config value %s was invalid (%s), resetting to default %s",
                        self.option,
                        value,
                        self.default,
                    )
                    value = self.default

            if value is None and self.validator is not None:
                defaults = {
                    "String": "",
                    "Integer": 0,
                    "Boolean": False,
                    "Series": [],
                    "Float": 0.0,
                }
                validator_id = getattr(self.validator, "internal_id", None)
                if validator_id in defaults:
                    logger.debug(
                        "Config value %s was None, resetting to %s",
                        self.option,
                        defaults[validator_id],
                    )
                    value = defaults[validator_id]

            self._save_marker = True

        object.__setattr__(self, key, value)

        if key == "value" and not ignore_validation and callable(self.on_change):
            if inspect.iscoroutinefunction(self.on_change):
                asyncio.ensure_future(wrap(self.on_change))
            else:
                syncwrap(self.on_change)


def _get_members(
    mod: Module,
    ending: str,
    attribute: Optional[str] = None,
    strict: bool = False,
) -> dict[str, Callable]:
    """
    Get methods of module ending with specific suffix or having attribute

    Args:
        mod: Module instance
        ending: Method suffix to match
        attribute: Attribute that must be present
        strict: Whether to match exact ending or just suffix

    Returns:
        Dictionary of method_name: method
    """
    result = {}

    for method_name in dir(mod):
        if isinstance(getattr(type(mod), method_name, None), property):
            continue

        method = getattr(mod, method_name)
        if not callable(method):
            continue

        suffix_match = method_name == ending if strict else method_name.endswith(ending)

        attr_match = attribute and getattr(method, attribute, False)

        if suffix_match or attr_match:
            if suffix_match:
                clean_name = (
                    method_name.rsplit(ending, 1)[0] if not strict else method_name
                ).lower()
            else:
                clean_name = method_name.lower()

            result[clean_name] = method

    return result


class CacheRecordEntity:
    """Cache record for Telegram entities"""

    def __init__(
        self,
        hashable_entity: "Hashable",  # type: ignore  # noqa: F821
        resolved_entity: EntityLike,
        exp: int,
    ) -> None:
        self.entity = copy.deepcopy(resolved_entity)
        self._hashable_entity = copy.deepcopy(hashable_entity)
        self._exp = round(time.time() + exp)
        self.ts = time.time()

    @property
    def expired(self) -> bool:
        """Check if cache record is expired"""
        return self._exp < time.time()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CacheRecordEntity):
            return NotImplemented
        return hash(other) == hash(self)

    def __hash__(self) -> int:
        return hash(self._hashable_entity)

    def __str__(self) -> str:
        return f"CacheRecordEntity of {self.entity}"

    def __repr__(self) -> str:
        return (
            f"CacheRecordEntity(entity={type(self.entity).__name__}(...), "
            f"exp={self._exp})"
        )


class CacheRecordPerms:
    """Cache record for user permissions in channels"""

    def __init__(
        self,
        hashable_entity: "Hashable",  # type: ignore  # noqa: F821
        hashable_user: "Hashable",  # type: ignore  # noqa: F821
        resolved_perms: EntityLike,
        exp: int,
    ) -> None:
        self.perms = copy.deepcopy(resolved_perms)
        self._hashable_entity = copy.deepcopy(hashable_entity)
        self._hashable_user = copy.deepcopy(hashable_user)
        self._exp = round(time.time() + exp)
        self.ts = time.time()

    @property
    def expired(self) -> bool:
        """Check if cache record is expired"""
        return self._exp < time.time()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CacheRecordPerms):
            return NotImplemented
        return hash(other) == hash(self)

    def __hash__(self) -> int:
        return hash((self._hashable_entity, self._hashable_user))

    def __str__(self) -> str:
        return f"CacheRecordPerms of {self.perms}"

    def __repr__(self) -> str:
        return (
            f"CacheRecordPerms(perms={type(self.perms).__name__}(...), exp={self._exp})"
        )


class CacheRecordFullChannel:
    """Cache record for full channel information"""

    def __init__(self, channel_id: int, full_channel: ChannelFull, exp: int) -> None:
        self.channel_id = channel_id
        self.full_channel = full_channel
        self._exp = round(time.time() + exp)
        self.ts = time.time()

    @property
    def expired(self) -> bool:
        """Check if cache record is expired"""
        return self._exp < time.time()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CacheRecordFullChannel):
            return NotImplemented
        return hash(other) == hash(self)

    def __hash__(self) -> int:
        return hash(self.channel_id)

    def __str__(self) -> str:
        return f"CacheRecordFullChannel of {self.channel_id}"

    def __repr__(self) -> str:
        return f"CacheRecordFullChannel(channel_id={self.channel_id}, exp={self._exp})"


class CacheRecordFullUser:
    """Cache record for full user information"""

    def __init__(self, user_id: int, full_user: UserFull, exp: int) -> None:
        self.user_id = user_id
        self.full_user = full_user
        self._exp = round(time.time() + exp)
        self.ts = time.time()

    @property
    def expired(self) -> bool:
        """Check if cache record is expired"""
        return self._exp < time.time()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CacheRecordFullUser):
            return NotImplemented
        return hash(other) == hash(self)

    def __hash__(self) -> int:
        return hash(self.user_id)

    def __str__(self) -> str:
        return f"CacheRecordFullUser of {self.user_id}"

    def __repr__(self) -> str:
        return f"CacheRecordFullUser(user_id={self.user_id}, exp={self._exp})"


def get_commands(mod: Module) -> dict[str, Command]:
    """Introspect module to get its command handlers"""
    return _get_members(mod, "cmd", "is_command")


def get_inline_handlers(mod: Module) -> dict[str, Command]:
    """Introspect module to get its inline handlers"""
    return _get_members(mod, "_inline_handler", "is_inline_handler")


def get_callback_handlers(mod: Module) -> dict[str, Command]:
    """Introspect module to get its callback handlers"""
    return _get_members(mod, "_callback_handler", "is_callback_handler")


def get_watchers(mod: Module) -> dict[str, Command]:
    """Introspect module to get its watchers"""
    return _get_members(mod, "watcher", "is_watcher", strict=True)
