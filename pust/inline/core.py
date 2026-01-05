"""Inline buttons, galleries and other Telegram-Bot-API stuff"""

# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

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

import asyncio
import logging
import time
from enum import StrEnum, IntEnum
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from functools import wraps
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError, TelegramUnauthorizedError
from aiogram.client.default import DefaultBotProperties
from telethon.errors.rpcerrorlist import InputUserDeactivatedError, YouBlockedUserError
from telethon.tl.functions.contacts import UnblockRequest
from telethon.tl.functions.messages import (
    GetDialogFiltersRequest,
    UpdateDialogFilterRequest,
)
from telethon.tl.types import DialogFilter, Message, InputPeerUser
from telethon.utils import get_display_name

from .. import utils
from ..database import Database
from ..tl_cache import CustomTelegramClient
from ..translations import Translator
from .bot_pm import BotPM
from .events import Events
from .form import Form
from .gallery import Gallery
from .list import List
from .query_gallery import QueryGallery
from .token_obtainment import TokenObtainment
from .utils import Utils

logger = logging.getLogger(__name__)


class InlineStatus(StrEnum):
    """Inline manager status enumeration"""

    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"
    STOPPING = "stopping"
    STOPPED = "stopped"


class InlineFeature(StrEnum):
    """Inline feature flags"""

    FORMS = "forms"
    GALLERIES = "galleries"
    LIST = "list"
    BOT_PM = "bot_pm"
    TOKEN_OBTAINMENT = "token_obtainment"
    QUERY_GALLERY = "query_gallery"
    WEB_AUTH = "web_auth"
    ERROR_HANDLING = "error_handling"
    RATE_LIMITING = "rate_limiting"
    STATISTICS = "statistics"
    HOT_RELOAD = "hot_reload"


@dataclass
class InlineStats:
    """Enhanced inline statistics with Python 3.12+ features"""

    units_created: int = 0
    units_destroyed: int = 0
    forms_created: int = 0
    galleries_created: int = 0
    bot_messages_sent: int = 0
    errors_handled: int = 0
    rate_limits_hit: int = 0
    web_auth_tokens_created: int = 0
    start_time: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    feature_usage: Dict[str, int] = field(default_factory=dict)

    def update_activity(self) -> None:
        """Update last activity timestamp"""
        self.last_activity = time.time()

    def update_feature_usage(self, feature: str) -> None:
        """Update feature usage statistics"""
        if feature not in self.feature_usage:
            self.feature_usage[feature] = 0
        self.feature_usage[feature] += 1

    def get_uptime(self) -> str:
        """Get formatted uptime"""
        uptime = time.time() - self.start_time
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        seconds = int(uptime % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def inline_context(feature: str):
    """Context manager for inline operations with Python 3.12+ features"""

    @asynccontextmanager
    async def context_manager(self):
        start_time = time.time()
        logger.debug(f"Starting inline operation: {feature}")

        try:
            yield
        except Exception as e:
            logger.error(f"Inline operation {feature} failed: {e}")
            raise
        finally:
            duration = time.time() - start_time
            logger.debug(f"Inline operation {feature} completed in {duration:.2f}s")

    return context_manager


def inline_error_handler(
    exceptions: type[Exception] | tuple[type[Exception], ...] = Exception,
    fallback_message: str = "Inline operation failed",
    log_errors: bool = True,
):
    """Enhanced error handling decorator for inline operations"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except exceptions as e:
                if log_errors:
                    logger.error(
                        f"Error in inline operation {func.__name__}: {e}", exc_info=True
                    )

                if hasattr(args[0], "_error_events") and hasattr(args[0], "_units"):
                    try:
                        await args[0]._send_error_message(fallback_message)
                    except Exception:
                        pass

                raise

        return wrapper

    return decorator


class FormType(StrEnum):
    """Form type enumeration"""

    TEXT = "text"
    NUMBER = "number"
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    PHOTO = "photo"
    FILE = "file"
    LOCATION = "location"


class ButtonType(IntEnum):
    """Button type enumeration"""

    CALLBACK = 0
    URL = 1
    SWITCH_INLINE = 2
    SWITCH_INLINE_CURRENT = 3
    GAME = 4
    PAY = 5


class InlineManager(
    Utils,
    Events,
    TokenObtainment,
    Form,
    Gallery,
    QueryGallery,
    List,
    BotPM,
):
    """
    Enhanced Inline buttons, galleries and other Telegram-Bot-API stuff
    with modern Python 3.12+ features

    :param client: Telegram client
    :param db: Database instance
    :param allmodules: All modules
    :type client: Pust.tl_cache.CustomTelegramClient
    :type db: Pust.database.Database
    :type allmodules: Pust.loader.Modules
    """

    def __init__(
        self,
        client: CustomTelegramClient,
        db: Database,
        allmodules: "Modules",  # type: ignore  # noqa: F821
    ):
        """Initialize enhanced InlineManager with modern features"""
        self._client = client
        self._db = db
        self._allmodules = allmodules
        self.translator: Translator = allmodules.translator

        self._units: Dict[str, dict] = {}
        self._custom_map: Dict[str, callable] = {}
        self.fsm: Dict[str, str] = {}
        self._web_auth_tokens: List[str] = []
        self._error_events: Dict[str, asyncio.Event] = {}

        self._status: InlineStatus = InlineStatus.UNINITIALIZED
        self._stats = InlineStats()
        self._features: set[InlineFeature] = set()

        self._markup_ttl = 60 * 60 * 24
        self.init_complete = False

        self._token = db.get("Pust.inline", "bot_token", False)
        self._me: int = None
        self._name: str = None
        self._dp: Dispatcher = None
        self._task: asyncio.Future = None
        self._cleaner_task: asyncio.Future = None
        self.bot: Bot = None
        self.bot_id: int = None
        self.bot_username: str = None

        self._initialize_features()

    def _initialize_features(self) -> None:
        """Initialize available features"""
        self._features.update(
            {
                InlineFeature.FORMS,
                InlineFeature.GALLERIES,
                InlineFeature.LIST,
                InlineFeature.BOT_PM,
                InlineFeature.TOKEN_OBTAINMENT,
                InlineFeature.QUERY_GALLERY,
                InlineFeature.WEB_AUTH,
                InlineFeature.ERROR_HANDLING,
                InlineFeature.STATISTICS,
            }
        )

    def has_feature(self, feature: InlineFeature) -> bool:
        """Check if inline manager has specific feature"""
        return feature in self._features

    def get_status(self) -> InlineStatus:
        """Get current inline manager status"""
        return self._status

    def get_stats(self) -> InlineStats:
        """Get inline statistics"""
        return self._stats

    def update_stats(self, **kwargs) -> None:
        """Update statistics with modern Python 3.12+ features"""
        for key, value in kwargs.items():
            if hasattr(self._stats, key):
                setattr(self._stats, key, value)

        self._stats.update_activity()

    @inline_context("cleaner")
    async def _cleaner(self):
        """Enhanced cleaner with modern Python 3.12+ features"""
        while True:
            units_to_remove = []

            for unit_id, unit in self._units.copy().items():
                if (unit.get("ttl") or (time.time() + self._markup_ttl)) < time.time():
                    units_to_remove.append(unit_id)
                    self._stats.units_destroyed += 1

            for unit_id in units_to_remove:
                del self._units[unit_id]
                self._stats.update_activity()

            if units_to_remove:
                logger.debug(f"Cleaned up {len(units_to_remove)} outdated inline units")

            await asyncio.sleep(5)

    async def register_manager(
        self,
        after_break: bool = False,
        ignore_token_checks: bool = False,
    ):
        """
        Register manager
        :param after_break: Loop marker
        :param ignore_token_checks: If `True`, will not check for token
        :type after_break: bool
        :type ignore_token_checks: bool
        :return: None
        :rtype: None
        """
        self._me = self._client.tg_id
        self._name = get_display_name(self._client.Pust_me)

        if not ignore_token_checks:
            is_token_asserted = await self._assert_token()
            if not is_token_asserted:
                self.init_complete = False
                return

        self.init_complete = True

        self.bot = Bot(
            token=self._token, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        self._bot = self.bot
        self._dp = Dispatcher()

        try:
            bot_me = await self.bot.get_me()
            self.bot_username = bot_me.username
            self.bot_id = bot_me.id
        except TelegramUnauthorizedError:
            logger.critical("Token expired, revoking...")
            return await self._dp_revoke_token(False)

        try:
            m = await self._client.send_message(self.bot_username, "/start Pust init")
        except (InputUserDeactivatedError, ValueError):
            self._db.set("Pust.inline", "bot_token", None)
            self._token = False

            if not after_break:
                return await self.register_manager(True)

            self.init_complete = False
            return False
        except YouBlockedUserError:
            await self._client(UnblockRequest(id=self.bot_username))
            try:
                m = await self._client.send_message(
                    self.bot_username, "/start Pust init"
                )
            except Exception:
                logger.critical("Can't unblock users bot", exc_info=True)
                return False
        except Exception:
            self.init_complete = False
            logger.critical("Initialization of inline manager failed!", exc_info=True)
            return False

        _folders = await self._client(GetDialogFiltersRequest())
        for folder in _folders.filters:
            if getattr(folder, "title", None) == "Pust":
                if any(
                    [
                        isinstance(peer, InputPeerUser) and peer.user_id == self.bot_id
                        for peer in folder.include_peer
                    ]
                ):
                    break

                pinned = [await self._client.get_input_entity(self.bot_id)]
                include = folder.include_peers
                exclude = folder.exclude_peers
                emoticon = folder.emoticon
                color = folder.color

                await self._client(
                    UpdateDialogFilterRequest(
                        folder.id,
                        DialogFilter(
                            folder.id,
                            pinned_peers=pinned,
                            include_peers=include,
                            exclude_peers=exclude,
                            emoticon=emoticon,
                            color=color,
                        ),
                    )
                )
                break

        await self._client.delete_messages(self.bot_username, m)

        self._dp.inline_query.register(
            self._inline_handler,
            lambda _: True,
        )

        self._dp.callback_query.register(
            self._callback_query_handler,
            lambda _: True,
        )

        self._dp.chosen_inline_result.register(
            self._chosen_inline_handler,
            lambda _: True,
        )

        self._dp.message.register(
            self._message_handler,
            lambda *_: True,
        )

        old = self.bot.get_updates
        revoke = self._dp_revoke_token

        async def new(*args, **kwargs):
            nonlocal revoke, old
            try:
                return await old(*args, **kwargs)
            except TelegramConflictError:
                await revoke()
            except TelegramUnauthorizedError:
                logger.critical("Got Unauthorized")
                await self._stop()

        self.bot.get_updates = new

        self._task = asyncio.ensure_future(
            self._dp.start_polling(self._bot, handle_signals=False)
        )
        self._cleaner_task = asyncio.ensure_future(self._cleaner())

    async def _stop(self):
        """Stop the bot"""
        self._task.cancel()
        await self._dp.stop_polling()
        self._cleaner_task.cancel()

    def pop_web_auth_token(self, token: str) -> bool:
        """
        Check if web confirmation button was pressed
        :param token: Token to check
        :type token: str
        :return: `True` if token was found, `False` otherwise
        :rtype: bool
        """
        if token not in self._web_auth_tokens:
            return False

        self._web_auth_tokens.remove(token)
        return True

    async def _invoke_unit(self, unit_id: str, message: Message) -> Message:
        """Invoke inline unit"""
        if not self.bot_username:
            raise Exception(
                "InlineManager is not initialized. Bot username is not set."
            )

        event = asyncio.Event()
        self._error_events[unit_id] = event

        q: "InlineResults" = None  # type: ignore  # noqa: F821
        exception: Exception = None

        async def result_getter():
            nonlocal unit_id, q
            try:
                q = await self._client.inline_query(self.bot_username, unit_id)
            except Exception as e:
                logger.error(f"Failed to execute inline query: {e}")
                if unit_id in self._error_events:
                    self._error_events[unit_id] = e
                    event.set()

        async def event_poller():
            nonlocal exception
            try:
                await asyncio.wait_for(event.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass

            if self._error_events.get(unit_id) and isinstance(
                self._error_events[unit_id], Exception
            ):
                exception = self._error_events[unit_id]

        result_getter_task = asyncio.ensure_future(result_getter())
        event_poller_task = asyncio.ensure_future(event_poller())

        _, pending = await asyncio.wait(
            [result_getter_task, event_poller_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

        self._error_events.pop(unit_id, None)

        if exception:
            raise exception

        if not q or not q.results:
            raise Exception(
                f"No query results for unit_id: {unit_id}. Bot: @{self.bot_username}"
            )

        return await q[0].click(
            utils.get_chat_id(message) if isinstance(message, Message) else message,
            reply_to=(
                message.reply_to_msg_id if isinstance(message, Message) else None
            ),
        )
