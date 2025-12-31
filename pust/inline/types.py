# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

# ©️ Codrago, 2024-2025
# This file is a part of Pust Userbot
# 🌐 https://github.com/coddrago/Pust
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

# SPDX-License-Identifier: GNU AGPL v3.0
#
# This file is a part of Pust Userbot.
#
# Copyright (C) 2026 CodWiz

import logging
import typing
from contextlib import suppress
from datetime import datetime

from aiogram.types import CallbackQuery
from aiogram.types import InlineQuery as AiogramInlineQuery
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from aiogram.types import Message as AiogramMessage
from pydantic import ConfigDict

from .. import utils

logger = logging.getLogger(__name__)

if typing.TYPE_CHECKING:
    from ..inline.core import InlineManager


class InlineMessage:
    """Aiogram message, sent via inline bot"""

    def __init__(
        self,
        inline_manager: "InlineManager",  # type: ignore  # noqa: F821
        unit_id: str,
        inline_message_id: str,
    ):
        self.inline_message_id = inline_message_id
        self.unit_id = unit_id
        self.inline_manager = inline_manager
        self._units = inline_manager._units
        self._created_at = datetime.now()
        self._update_count = 0

        self._form_cache = None
        self._form_cache_timestamp = None

    def _get_form(self, force_refresh: bool = False) -> dict:
        """Get up-to-date form data with caching"""
        current_time = datetime.now()

        # Update the cache if:
        # 1. There is no cache
        # 2. Cache is outdated (older than 5 seconds)
        # 3. Forced update
        if (
            force_refresh
            or self._form_cache is None
            or (current_time - self._form_cache_timestamp).total_seconds() > 5
        ):
            if self.unit_id in self._units:
                unit_data = self._units[self.unit_id]
                self._form_cache = {"id": self.unit_id, **unit_data}
            else:
                self._form_cache = {}

            self._form_cache_timestamp = current_time

        return self._form_cache

    @property
    def form(self) -> dict:
        """Property for getting cached form data"""
        return self._get_form()

    def _clear_cache(self):
        """Clear the form cache"""
        self._form_cache = None
        self._form_cache_timestamp = None

    def _validate_operation(self) -> bool:
        """Check whether the operation can be performed with the message"""
        if self.unit_id not in self._units:
            logger.warning(f"Unit {self.unit_id} not found in units")
            return False

        unit = self._units[self.unit_id]
        if "ttl" in unit and unit["ttl"] < datetime.now().timestamp():
            logger.warning(f"Unit {self.unit_id} has expired (TTL)")
            return False

        return True

    async def edit(self, *args, **kwargs) -> "InlineMessage":
        """Edit inline message"""
        if not self._validate_operation():
            logger.error(f"Cannot edit unit {self.unit_id} - invalid or expired")
            return self

        kwargs.pop("unit_id", None)
        kwargs.pop("inline_message_id", None)

        self._clear_cache()

        try:
            result = await self.inline_manager._edit_unit(
                *args,
                unit_id=self.unit_id,
                inline_message_id=self.inline_message_id,
                **kwargs,
            )
            self._update_count += 1
            return result
        except Exception as e:
            logger.error(f"Failed to edit unit {self.unit_id}: {e}")
            raise

    async def delete(self) -> bool:
        """Delete inline message"""
        entity = self._units.get(self.unit_id)
        if not entity:
            logger.warning(f"Unit {self.unit_id} not found for deletion")

            if hasattr(self, "original_call"):
                with suppress(Exception):
                    await self.original_call.answer(
                        "Message not found", show_alert=True
                    )
            return False

        msgid = entity.get("message_id")
        cid = entity.get("chat")

        if not msgid or not cid:
            logger.error(f"Incomplete data for deletion: cid={cid}, msgid={msgid}")
            return False

        try:
            await self.inline_manager._client.delete_messages(cid, msgid)
            self._clear_cache()

            if hasattr(self, "original_call"):
                with suppress(Exception):
                    await self.original_call.answer("")

            return True
        except Exception as e:
            logger.error(f"Failed to delete message: {e}")
            return False

    async def unload(self) -> bool:
        """Unload inline unit"""
        try:
            result = await self.inline_manager._unload_unit(unit_id=self.unit_id)
            self._clear_cache()
            return result
        except Exception as e:
            logger.error(f"Failed to unload unit {self.unit_id}: {e}")
            return False

    def __str__(self) -> str:
        """String representation for debugging"""
        return f"InlineMessage(unit_id={self.unit_id}, updates={self._update_count})"

    def __repr__(self) -> str:
        """Detailed representation for debugging"""
        return f"InlineMessage(unit_id={self.unit_id}, inline_message_id={self.inline_message_id}, created={self._created_at})"


class BotInlineMessage:
    """Aiogram message, sent through inline bot itself"""

    def __init__(
        self,
        inline_manager: "InlineManager",  # type: ignore  # noqa: F821
        unit_id: str,
        chat_id: int,
        message_id: int,
    ):
        self.chat_id = chat_id
        self.unit_id = unit_id
        self.inline_manager = inline_manager
        self.message_id = message_id
        self._units = inline_manager._units
        self._created_at = datetime.now()
        self._update_count = 0
        self._form_cache = None
        self._form_cache_timestamp = None

    def _get_form(self, force_refresh: bool = False) -> dict:
        """Get up-to-date form data with caching"""
        current_time = datetime.now()

        if (
            force_refresh
            or self._form_cache is None
            or (current_time - self._form_cache_timestamp).total_seconds() > 5
        ):
            if self.unit_id in self._units:
                unit_data = self._units[self.unit_id]
                self._form_cache = {"id": self.unit_id, **unit_data}
            else:
                self._form_cache = {}

            self._form_cache_timestamp = current_time

        return self._form_cache

    @property
    def form(self) -> dict:
        """Property for getting cached form data"""
        return self._get_form()

    def _clear_cache(self):
        """Clear the form cache"""
        self._form_cache = None
        self._form_cache_timestamp = None

    def _validate_operation(self) -> bool:
        """Check whether the operation can be performed with the message"""
        if self.unit_id not in self._units:
            logger.warning(f"Unit {self.unit_id} not found in units")
            return False

        unit = self._units[self.unit_id]
        if "ttl" in unit and unit["ttl"] < datetime.now().timestamp():
            logger.warning(f"Unit {self.unit_id} has expired (TTL)")
            return False

        return True

    async def edit(self, *args, **kwargs) -> "BotMessage":
        """Edit bot message"""
        if not self._validate_operation():
            logger.error(f"Cannot edit unit {self.unit_id} - invalid or expired")
            return None

        kwargs.pop("unit_id", None)
        kwargs.pop("message_id", None)
        kwargs.pop("chat_id", None)

        self._clear_cache()

        try:
            result = await self.inline_manager._edit_unit(
                *args,
                unit_id=self.unit_id,
                chat_id=self.chat_id,
                message_id=self.message_id,
                **kwargs,
            )
            self._update_count += 1
            return result
        except Exception as e:
            logger.error(f"Failed to edit unit {self.unit_id}: {e}")
            raise

    async def delete(self) -> bool:
        """Delete bot message"""
        try:
            result = await self.inline_manager._delete_unit_message(
                self,
                unit_id=self.unit_id,
                chat_id=self.chat_id,
                message_id=self.message_id,
            )
            self._clear_cache()
            return result
        except Exception as e:
            logger.error(f"Failed to delete unit message: {e}")
            return False

    async def unload(self, *args, **kwargs) -> bool:
        """Unload bot message unit"""
        kwargs.pop("unit_id", None)

        try:
            result = await self.inline_manager._unload_unit(
                *args,
                unit_id=self.unit_id,
                **kwargs,
            )
            self._clear_cache()
            return result
        except Exception as e:
            logger.error(f"Failed to unload unit {self.unit_id}: {e}")
            return False

    def __str__(self) -> str:
        """String representation for debugging"""
        return f"BotInlineMessage(unit_id={self.unit_id}, chat_id={self.chat_id}, message_id={self.message_id})"


class InlineCall(CallbackQuery, InlineMessage):
    """Modified version of classic aiogram `CallbackQuery`"""

    model_config = ConfigDict(frozen=False)

    def __init__(
        self,
        call: CallbackQuery,
        inline_manager: "InlineManager",  # type: ignore  # noqa: F821
        unit_id: str,
    ):
        dump = call.model_dump()

        if "result_id" in dump:
            dump["id"] = dump.pop("result_id")

        dump.setdefault("chat_instance", "")

        CallbackQuery.__init__(self, **dump)

        InlineMessage.__init__(
            self,
            inline_manager,
            unit_id,
            call.inline_message_id if hasattr(call, "inline_message_id") else "",
        )

        self.original_call = call

        self._clear_cache()

    def __str__(self) -> str:
        """String representation for debugging"""
        base_info = f"InlineCall(unit_id={self.unit_id}, data={self.data})"
        if hasattr(self, "from_user") and self.from_user:
            return f"{base_info}, user_id={self.from_user.id}"
        return base_info


class BotInlineCall(CallbackQuery, BotInlineMessage):
    """Modified version of classic aiogram `CallbackQuery`"""

    model_config = ConfigDict(frozen=False)

    def __init__(
        self,
        call: CallbackQuery,
        inline_manager: "InlineManager",  # type: ignore  # noqa: F821
        unit_id: str,
    ):
        dump = call.model_dump()

        if "result_id" in dump:
            dump["id"] = dump.pop("result_id")

        dump.setdefault("chat_instance", "")

        CallbackQuery.__init__(self, **dump)

        if not hasattr(call.message, "chat"):
            raise ValueError("Call message has no chat attribute")

        BotInlineMessage.__init__(
            self,
            inline_manager,
            unit_id,
            call.message.chat.id,
            call.message.message_id,
        )

        self.original_call = call
        self._clear_cache()

    def __str__(self) -> str:
        """String representation for debugging"""
        base_info = f"BotInlineCall(unit_id={self.unit_id}, data={self.data})"
        if hasattr(self, "from_user") and self.from_user:
            return f"{base_info}, user_id={self.from_user.id}"
        return base_info


class InlineUnit:
    """InlineManager extension type. For internal use only"""

    def __init__(self):
        """Made just for type specification"""
        pass


class BotMessage(AiogramMessage):
    """Modified version of original Aiogram Message"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __str__(self) -> str:
        """Enhanced string representation"""
        if hasattr(self, "chat") and self.chat:
            return f"BotMessage(chat_id={self.chat.id}, message_id={self.message_id})"
        return "BotMessage(unknown)"


class InlineQuery(AiogramInlineQuery):
    """Modified version of original Aiogram InlineQuery"""

    model_config = ConfigDict(frozen=False)

    def __init__(self, inline_query: AiogramInlineQuery):
        super().__init__(**inline_query.model_dump())

        self.inline_query = inline_query

        try:
            query_parts = self.inline_query.query.split(maxsplit=1)
            self.args = query_parts[1] if len(query_parts) > 1 else ""
        except (AttributeError, IndexError):
            self.args = ""

        self._command = None

    @property
    def command(self) -> str:
        """Get the first word of the query (command)"""
        if self._command is None:
            try:
                self._command = (
                    self.inline_query.query.split()[0]
                    if self.inline_query.query
                    else ""
                )
            except (AttributeError, IndexError):
                self._command = ""
        return self._command

    @staticmethod
    def _get_res(title: str, description: str, thumbnail_url: str) -> list:
        """Create standardized error response"""
        return [
            InlineQueryResultArticle(
                id=utils.rand(20),
                title=title,
                description=description,
                input_message_content=InputTextMessageContent(
                    message_text="😶‍🌫️ <i>There is nothing here...</i>",
                    parse_mode="HTML",
                ),
                thumbnail_url=thumbnail_url,
                thumb_width=128,
                thumb_height=128,
            )
        ]

    async def e400(self):
        """Send 400 Bad Request error"""
        await self.answer(
            self._get_res(
                title="🚫 400",
                description=(
                    "Bad request. You need to pass right arguments, follow module's"
                    " documentation"
                ),
                thumbnail_url="https://img.icons8.com/color/344/swearing-male--v1.png",
            ),
            cache_time=0,
        )

    async def e403(self):
        """Send 403 Forbidden error"""
        await self.answer(
            self._get_res(
                title="🚫 403",
                description="You have no permissions to access this result",
                thumbnail_url="https://img.icons8.com/external-wanicon-flat-wanicon/344/external-forbidden-new-normal-wanicon-flat-wanicon.png",
            ),
            cache_time=0,
        )

    async def e404(self):
        """Send 404 Not Found error"""
        await self.answer(
            self._get_res(
                title="🚫 404",
                description="No results found",
                thumbnail_url="https://img.icons8.com/external-justicon-flat-justicon/344/external-404-error-responsive-web-design-justicon-flat-justicon.png",
            ),
            cache_time=0,
        )

    async def e426(self):
        """Send 426 Update Required error"""
        await self.answer(
            self._get_res(
                title="🚫 426",
                description="You need to update Pust before sending this request",
                thumbnail_url="https://img.icons8.com/fluency/344/approve-and-update.png",
            ),
            cache_time=0,
        )

    async def e500(self):
        """Send 500 Internal Server Error"""
        await self.answer(
            self._get_res(
                title="🚫 500",
                description="Internal userbot error while processing request. More info in logs",
                thumbnail_url="https://img.icons8.com/external-vitaliy-gorbachev-flat-vitaly-gorbachev/344/external-error-internet-security-vitaliy-gorbachev-flat-vitaly-gorbachev.png",
            ),
            cache_time=0,
        )

    def __str__(self) -> str:
        """String representation for debugging"""
        user_info = (
            f"user_id={self.from_user.id}"
            if hasattr(self, "from_user") and self.from_user
            else "unknown_user"
        )
        return f"InlineQuery({user_info}, query='{self.query[:50]}...')"
