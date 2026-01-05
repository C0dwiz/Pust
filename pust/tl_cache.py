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
# This file is a part of Pust Userbot.
#
# Copyright (C) 2026 CodWiz

import copy
import inspect
import logging
import time
from contextlib import suppress
from enum import StrEnum, IntEnum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Union

from telethon import TelegramClient, helpers
from telethon._updates import (
    ChannelState,
    EntityType,
    SessionState,
)
from telethon._updates import (
    Entity as TL_Entity,
)
from telethon.errors.rpcerrorlist import TopicDeletedError
from telethon.hints import EntityLike
from telethon.network import MTProtoSender
from telethon.tl import functions
from telethon.tl.alltlobjects import LAYER
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.tlobject import TLRequest
from telethon.tl.types import (
    ChannelFull,
    Message,
    Updates,
    UpdatesCombined,
    UpdateShort,
    UserFull,
)
from telethon.utils import is_list_like

from .types import (
    CacheRecordEntity,
    CacheRecordFullChannel,
    CacheRecordFullUser,
    CacheRecordPerms,
    Module,
)

logger = logging.getLogger(__name__)


class CacheType(StrEnum):
    """Cache type enumeration"""

    ENTITY = "entity"
    FULL_CHANNEL = "full_channel"
    FULL_USER = "full_user"
    PERMISSIONS = "permissions"
    MESSAGE = "message"


class CacheStatus(IntEnum):
    """Cache status enumeration"""

    ACTIVE = 1
    EXPIRED = 2
    INVALID = 3
    UPDATING = 4


_ID_ATTRIBUTES = {"user_id", "channel_id", "chat_id", "id"}
_CACHE_EXPIRY = 5 * 60  # 5 minutes


def _is_hashable(value: Any) -> bool:
    """Check if a value can be used as a dictionary key.

    Args:
        value: Value to check

    Returns:
        True if the value is hashable, False otherwise
    """
    try:
        hash(value)
        return True
    except TypeError:
        return False


def _get_hashable_entity(entity: Any) -> Optional[Union[int, str]]:
    """Extract a hashable identifier from an entity object.

    Args:
        entity: Entity object or identifier

    Returns:
        Hashable identifier or None if cannot be extracted
    """
    if _is_hashable(entity):
        return entity

    for attr in _ID_ATTRIBUTES:
        if hasattr(entity, attr):
            value = getattr(entity, attr, None)
            if value is not None:
                return value

    return None


def _normalize_entity_id(entity_id: Union[str, int]) -> Union[str, int]:
    """Normalize entity ID by removing prefixes for negative IDs.

    Args:
        entity_id: Entity ID to normalize

    Returns:
        Normalized entity ID
    """
    if isinstance(entity_id, str) and entity_id.isdigit() and int(entity_id) < 0:
        return int(entity_id[4:])
    return entity_id


class CustomTelegramClient(TelegramClient):
    """Extended Telegram client with entity caching and update processing enhancements.

    This class extends the base TelegramClient with additional caching capabilities
    for entities, permissions, and full channel/user information. It also provides
    protection against unwanted constructor calls and enhanced update processing.

    Attributes:
        Pustntity_cache: Cache for entity objects
        Pusterms_cache: Cache for user permissions in entities
        Pustullchannel_cache: Cache for full channel information
        Pustulluser_cache: Cache for full user information
        forbidden_constructors: List of forbidden constructor IDs
        raw_updates_processor: Optional callback for processing raw updates
    """

    def __init__(self, *args, **kwargs):
        """Initialize the extended Telegram client.

        Args:
            *args: Arguments passed to the parent TelegramClient
            **kwargs: Keyword arguments passed to the parent TelegramClient
        """
        super().__init__(*args, **kwargs)

        self._Pustntity_cache: Dict[
            Union[str, int],
            CacheRecordEntity,
        ] = {}

        self._Pusterms_cache: Dict[
            Union[str, int],
            Dict[Union[str, int], CacheRecordPerms],
        ] = {}

        self._Pustullchannel_cache: Dict[
            Union[str, int],
            CacheRecordFullChannel,
        ] = {}

        self._Pustulluser_cache: Dict[
            Union[str, int],
            CacheRecordFullUser,
        ] = {}

        self._forbidden_constructors: Set[int] = set()
        self._raw_updates_processor: Optional[
            Callable[[Union[Updates, UpdatesCombined, UpdateShort]], None]
        ] = None

    async def connect(self, unix_socket_path: Optional[str] = None) -> None:
        """Connect the client to Telegram servers.

        Args:
            unix_socket_path: Optional path to Unix socket for connection

        Raises:
            ValueError: If the client instance cannot be reused
            RuntimeError: If the asyncio event loop changes during connection
        """
        if self.session is None:
            raise ValueError(
                "TelegramClient instance cannot be reused after logging out"
            )

        if self._loop is None:
            self._loop = helpers.get_running_loop()
        elif self._loop != helpers.get_running_loop():
            raise RuntimeError(
                "The asyncio event loop must not change after connection"
            )

        connection = self._connection(
            self.session.server_address,
            self.session.port,
            self.session.dc_id,
            loggers=self._log,
            proxy=self._proxy,
            local_addr=self._local_addr,
        )

        if unix_socket_path is not None:
            connection.set_unix_socket(unix_socket_path)

        if not await self._sender.connect(connection):
            return

        self.session.auth_key = self._sender.auth_key
        with suppress(AttributeError):
            self.session.save()

        if self._catch_up:
            await self._catch_up_updates()

        self._init_request.query = functions.help.GetConfigRequest()

        req = self._init_request
        if self._no_updates:
            req = functions.InvokeWithoutUpdatesRequest(req)

        await self._sender.send(functions.InvokeWithLayerRequest(LAYER, req))

        if self._message_box.is_empty():
            me = await self.get_me()
            if me:
                await self._on_login(me)

        self._updates_handle = self.loop.create_task(self._update_loop())
        self._keepalive_handle = self.loop.create_task(self._keepalive_loop())

    async def _catch_up_updates(self) -> None:
        """Process pending updates when connecting to the server."""
        ss = SessionState(0, 0, False, 0, 0, 0, 0, None)
        cs = []

        for entity_id, state in self.session.get_update_states():
            if entity_id == 0:
                ss = SessionState(
                    0,
                    0,
                    False,
                    state.pts,
                    state.qts,
                    int(state.date.timestamp()),
                    state.seq,
                    None,
                )
            else:
                cs.append(ChannelState(entity_id, state.pts))

        self._message_box.load(ss, cs)

        for state in cs:
            try:
                entity = self.session.get_input_entity(state.channel_id)
            except ValueError:
                logger.warning(
                    "No access_hash in cache for channel %s, will not catch up",
                    state.channel_id,
                )
            else:
                self._mb_entity_cache.put(
                    TL_Entity(
                        EntityType.CHANNEL,
                        entity.channel_id,
                        entity.access_hash,
                    )
                )

    @property
    def raw_updates_processor(
        self,
    ) -> Optional[Callable[[Union[Updates, UpdatesCombined, UpdateShort]], None]]:
        """Get the raw updates processor callback.

        Returns:
            Optional callback function for processing raw updates
        """
        return self._raw_updates_processor

    @raw_updates_processor.setter
    def raw_updates_processor(
        self,
        value: Callable[[Union[Updates, UpdatesCombined, UpdateShort]], None],
    ) -> None:
        """Set the raw updates processor callback.

        Args:
            value: Callback function to process raw updates

        Raises:
            ValueError: If processor is already set or value is not callable
        """
        if self._raw_updates_processor is not None:
            raise ValueError("raw_updates_processor is already set")

        if not callable(value):
            raise ValueError("raw_updates_processor must be callable")

        self._raw_updates_processor = value

    @property
    def Pustntity_cache(self) -> Dict[int, CacheRecordEntity]:
        """Get the entity cache.

        Returns:
            Dictionary mapping entity IDs to cache records
        """
        return self._Pustntity_cache

    @property
    def Pusterms_cache(
        self,
    ) -> Dict[int, Dict[int, CacheRecordPerms]]:
        """Get the permissions cache.

        Returns:
            Nested dictionary mapping entity IDs to user IDs to permission cache records
        """
        return self._Pusterms_cache

    @property
    def Pustullchannel_cache(self) -> Dict[int, CacheRecordFullChannel]:
        """Get the full channel cache.

        Returns:
            Dictionary mapping channel IDs to full channel cache records
        """
        return self._Pustullchannel_cache

    @property
    def Pustulluser_cache(self) -> Dict[int, CacheRecordFullUser]:
        """Get the full user cache.

        Returns:
            Dictionary mapping user IDs to full user cache records
        """
        return self._Pustulluser_cache

    @property
    def forbidden_constructors(self) -> List[int]:
        """Get the list of forbidden constructor IDs.

        Returns:
            List of constructor IDs that are forbidden
        """
        return list(self._forbidden_constructors)

    async def force_get_entity(self, *args, **kwargs) -> Any:
        """Forcefully fetch an entity from Telegram, bypassing cache.

        Args:
            *args: Arguments passed to get_entity
            **kwargs: Keyword arguments passed to get_entity

        Returns:
            Entity object
        """
        return await self.get_entity(*args, force=True, **kwargs)

    async def get_entity(
        self,
        entity: EntityLike,
        exp: int = _CACHE_EXPIRY,
        force: bool = False,
    ) -> Any:
        """Fetch an entity and cache it for future use.

        Args:
            entity: Entity to fetch (can be ID, username, or entity object)
            exp: Cache expiration time in seconds (0 for no expiration)
            force: Force refresh cache by making API request

        Returns:
            Entity object
        """
        hashable_entity = _get_hashable_entity(entity)
        if hashable_entity is None:
            logger.debug(
                "Cannot parse hashable from entity %s, using legacy resolve",
                entity,
            )
            return await super().get_entity(entity)

        hashable_entity = _normalize_entity_id(hashable_entity)

        if not force and hashable_entity in self._Pustntity_cache:
            cache_record = self._Pustntity_cache[hashable_entity]
            if exp == 0 or cache_record.ts + exp > time.time():
                logger.debug(
                    "Using cached entity %s (%s)",
                    entity,
                    type(cache_record.entity).__name__,
                )
                return copy.deepcopy(cache_record.entity)

        resolved_entity = await super().get_entity(entity)

        if resolved_entity:
            await self._cache_entity(resolved_entity, hashable_entity, exp)

        return copy.deepcopy(resolved_entity)

    async def _cache_entity(
        self,
        entity: Any,
        hashable_id: Union[str, int],
        exp: int,
    ) -> None:
        """Cache an entity with multiple lookup keys.

        Args:
            entity: Entity object to cache
            hashable_id: Primary hashable identifier
            exp: Cache expiration time in seconds
        """
        cache_record = CacheRecordEntity(hashable_id, entity, exp)

        self._Pustntity_cache[hashable_id] = cache_record
        logger.debug("Saved entity %s to cache", hashable_id)

        if hasattr(entity, "id"):
            self._Pustntity_cache[entity.id] = cache_record
            logger.debug("Saved entity id %s to cache", entity.id)

        if hasattr(entity, "username") and entity.username:
            username_key = f"@{entity.username}"
            self._Pustntity_cache[username_key] = cache_record
            self._Pustntity_cache[entity.username] = cache_record
            logger.debug("Saved entity username @%s to cache", entity.username)

    async def get_perms_cached(
        self,
        entity: EntityLike,
        user: Optional[EntityLike] = None,
        exp: int = _CACHE_EXPIRY,
        force: bool = False,
    ) -> Any:
        """Fetch user permissions in an entity and cache them.

        Args:
            entity: Entity (chat/channel) to check permissions in
            user: User to check permissions for
            exp: Cache expiration time in seconds (0 for no expiration)
            force: Force refresh cache by making API request

        Returns:
            ChatPermissions object
        """
        entity_obj = await self.get_entity(entity)
        user_obj = await self.get_entity(user) if user else None

        hashable_entity = _get_hashable_entity(entity_obj)
        hashable_user = _get_hashable_entity(user_obj)

        if not hashable_entity or not hashable_user:
            logger.debug(
                "Cannot parse hashable from entity %s or user %s, using legacy method",
                entity_obj,
                user_obj,
            )
            return await self.get_permissions(entity_obj, user_obj)

        hashable_entity = _normalize_entity_id(hashable_entity)
        hashable_user = _normalize_entity_id(hashable_user)

        entity_cache = self._Pusterms_cache.get(hashable_entity, {})

        if not force and hashable_user in entity_cache:
            cache_record = entity_cache[hashable_user]
            if exp == 0 or cache_record.ts + exp > time.time():
                logger.debug(
                    "Using cached perms for entity %s, user %s",
                    hashable_entity,
                    hashable_user,
                )
                return copy.deepcopy(cache_record.perms)

        resolved_perms = await self.get_permissions(entity_obj, user_obj)

        if resolved_perms:
            await self._cache_perms(
                entity_obj,
                user_obj,
                hashable_entity,
                hashable_user,
                resolved_perms,
                exp,
            )

        return copy.deepcopy(resolved_perms)

    async def _cache_perms(
        self,
        entity_obj: Any,
        user_obj: Any,
        hashable_entity: Union[str, int],
        hashable_user: Union[str, int],
        perms: Any,
        exp: int,
    ) -> None:
        """Cache permissions with multiple lookup keys.

        Args:
            entity_obj: Entity object
            user_obj: User object
            hashable_entity: Hashable entity identifier
            hashable_user: Hashable user identifier
            perms: Permissions object to cache
            exp: Cache expiration time in seconds
        """
        cache_record = CacheRecordPerms(hashable_entity, hashable_user, perms, exp)

        self._Pusterms_cache.setdefault(hashable_entity, {})[hashable_user] = (
            cache_record
        )
        logger.debug("Saved permissions for entity %s to cache", hashable_entity)

        def _add_to_cache(key: Union[str, int]) -> None:
            if hasattr(user_obj, "id"):
                self._Pusterms_cache.setdefault(key, {})[user_obj.id] = cache_record

            if hasattr(user_obj, "username") and user_obj.username:
                username_key = f"@{user_obj.username}"
                self._Pusterms_cache.setdefault(key, {})[username_key] = cache_record
                self._Pusterms_cache.setdefault(key, {})[user_obj.username] = (
                    cache_record
                )

        if hasattr(entity_obj, "id"):
            _add_to_cache(entity_obj.id)
            logger.debug("Saved permissions for entity id %s to cache", entity_obj.id)

        if hasattr(entity_obj, "username") and entity_obj.username:
            username_key = f"@{entity_obj.username}"
            _add_to_cache(username_key)
            _add_to_cache(entity_obj.username)
            logger.debug(
                "Saved permissions for entity username @%s to cache",
                entity_obj.username,
            )

    async def get_fullchannel(
        self,
        entity: EntityLike,
        exp: int = 300,
        force: bool = False,
    ) -> ChannelFull:
        """Fetch full channel information and cache it.

        Args:
            entity: Channel to fetch information for
            exp: Cache expiration time in seconds (0 for no expiration)
            force: Force refresh cache by making API request

        Returns:
            ChannelFull object
        """
        hashable_entity = _get_hashable_entity(entity)
        if hashable_entity is None:
            logger.debug(
                "Cannot parse hashable from entity %s, using legacy fullchannel request",
                entity,
            )
            return await self(GetFullChannelRequest(channel=entity))

        hashable_entity = _normalize_entity_id(hashable_entity)

        cache_record = self._Pustullchannel_cache.get(hashable_entity)

        if not force and cache_record and not cache_record.expired:
            if exp == 0 or cache_record.ts + exp > time.time():
                return cache_record.full_channel

        result = await self(GetFullChannelRequest(channel=entity))
        self._Pustullchannel_cache[hashable_entity] = CacheRecordFullChannel(
            hashable_entity,
            result,
            exp,
        )
        return result

    async def get_fulluser(
        self,
        entity: EntityLike,
        exp: int = 300,
        force: bool = False,
    ) -> UserFull:
        """Fetch full user information and cache it.

        Args:
            entity: User to fetch information for
            exp: Cache expiration time in seconds (0 for no expiration)
            force: Force refresh cache by making API request

        Returns:
            UserFull object
        """
        hashable_entity = _get_hashable_entity(entity)
        if hashable_entity is None:
            logger.debug(
                "Cannot parse hashable from entity %s, using legacy fulluser request",
                entity,
            )
            return await self(GetFullUserRequest(entity))

        hashable_entity = _normalize_entity_id(hashable_entity)

        cache_record = self._Pustulluser_cache.get(hashable_entity)

        if not force and cache_record and not cache_record.expired:
            if exp == 0 or cache_record.ts + exp > time.time():
                return cache_record.full_user

        result = await self(GetFullUserRequest(entity))
        self._Pustulluser_cache[hashable_entity] = CacheRecordFullUser(
            hashable_entity,
            result,
            exp,
        )
        return result

    @staticmethod
    def _find_message_in_frame(
        chat_id: int,
        frame: inspect.FrameInfo,
    ) -> Optional[Message]:
        """Find a message object in a stack frame.

        Args:
            chat_id: Chat ID to match
            frame: Stack frame to search

        Returns:
            Message object if found, None otherwise
        """
        logger.debug("Searching for message object in frame %s", frame)

        for obj in frame.frame.f_locals.values():
            if not isinstance(obj, Message):
                continue

            reply_to = getattr(obj, "reply_to", None)
            if not reply_to or not getattr(reply_to, "forum_topic", False):
                continue

            peer_id = getattr(obj, "peer_id", None)
            if peer_id and getattr(peer_id, "channel_id", None) == chat_id:
                return obj

        return None

    async def _find_message_in_stack(
        self,
        chat: EntityLike,
        stack: List[inspect.FrameInfo],
    ) -> Optional[Message]:
        """Find a message object in the call stack.

        Args:
            chat: Chat to search in
            stack: Call stack to search

        Returns:
            Message object if found, None otherwise
        """
        chat_entity = await self.get_entity(chat, exp=0)
        chat_id = getattr(chat_entity, "id", None)

        if not chat_id:
            logger.debug("Cannot get chat id for %s", chat)
            return None

        logger.debug("Searching for message in stack for chat %s", chat_id)

        for frame_info in stack:
            message = self._find_message_in_frame(chat_id, frame_info)
            if message:
                return message

        return None

    async def _find_topic_in_stack(
        self,
        chat: EntityLike,
        stack: List[inspect.FrameInfo],
    ) -> Optional[int]:
        """Find topic ID in the call stack.

        Args:
            chat: Chat to search in
            stack: Call stack to search

        Returns:
            Topic ID if found, None otherwise
        """
        message = await self._find_message_in_stack(chat, stack)
        if not message or not hasattr(message, "reply_to"):
            return None

        reply_to = message.reply_to
        return getattr(reply_to, "reply_to_top_id", None) or getattr(
            reply_to, "reply_to_msg_id", None
        )

    async def _topic_guesser(
        self,
        native_method: Callable[..., Awaitable[Message]],
        stack: List[inspect.FrameInfo],
        *args,
        **kwargs,
    ) -> Message:
        """Attempt to guess topic ID when TopicDeletedError occurs.

        Args:
            native_method: Original send method
            stack: Call stack for finding topic context
            *args: Arguments for the native method
            **kwargs: Keyword arguments for the native method

        Returns:
            Sent message

        Raises:
            TopicDeletedError: If topic cannot be guessed
        """
        no_retry = kwargs.pop("_topic_no_retry", False)

        try:
            return await native_method(*args, **kwargs)
        except TopicDeletedError:
            if no_retry:
                raise

            logger.debug("Topic deleted, attempting to guess topic id")

            if not args:
                raise

            topic = await self._find_topic_in_stack(args[0], stack)
            logger.debug("Guessed topic id: %s", topic)

            if not topic:
                raise

            kwargs["reply_to"] = topic
            kwargs["_topic_no_retry"] = True
            return await self._topic_guesser(native_method, stack, *args, **kwargs)

    async def send_file(self, *args, **kwargs) -> Message:
        """Send a file with topic guessing support.

        Returns:
            Sent message
        """
        return await self._topic_guesser(
            super().send_file,
            inspect.stack(),
            *args,
            **kwargs,
        )

    async def send_message(self, *args, **kwargs) -> Message:
        """Send a message with topic guessing support.

        Returns:
            Sent message
        """
        return await self._topic_guesser(
            super().send_message,
            inspect.stack(),
            *args,
            **kwargs,
        )

    async def _call(
        self,
        sender: MTProtoSender,
        request: TLRequest,
        ordered: bool = False,
        flood_sleep_threshold: Optional[int] = None,
    ) -> Any:
        """Execute a request with forbidden constructor protection.

        ⚠️ WARNING! If you are a module developer and try to bypass this protection
        to force users to join your channel, your module will be added to the SCAM
        module list and you will be banned from the Pustederation.

        Args:
            sender: MTProto sender to use
            request: Request to send
            ordered: Whether to send the request ordered
            flood_sleep_threshold: Flood sleep threshold

        Returns:
            Request result
        """
        if not is_list_like(request):
            requests = [request]
            single_request = True
        else:
            requests = list(request)
            single_request = False

        filtered_requests = []

        for req in requests:
            if req.CONSTRUCTOR_ID in self._forbidden_constructors:
                if self._is_module_request():
                    logger.debug(
                        "🎉 Protected from unintended %s (%s)!",
                        req.__class__.__name__,
                        req,
                    )
                    continue

            filtered_requests.append(req)

        if not filtered_requests:
            return

        return await super()._call(
            sender,
            filtered_requests[0] if single_request else tuple(filtered_requests),
            ordered,
            flood_sleep_threshold,
        )

    def _is_module_request(self) -> bool:
        """Check if a request originates from a module (not core).

        Returns:
            True if request is from a non-core module, False otherwise
        """
        for frame_info in inspect.stack():
            frame = frame_info.frame
            locals_dict = frame.f_locals

            if "self" in locals_dict:
                obj = locals_dict["self"]
                if isinstance(obj, Module):
                    module_origin = getattr(obj, "__origin__", "")
                    if not module_origin.startswith("<core"):
                        return True

        return False

    def _internal_forbid_ctor(self, constructors: List[int]) -> None:
        """Internal method to forbid constructor IDs.

        Args:
            constructors: List of constructor IDs to forbid
        """
        self._forbidden_constructors.update(constructors)

    def forbid_constructor(self, constructor: int) -> None:
        """Forbid a specific constructor from being called.

        Args:
            constructor: Constructor ID to forbid
        """
        self._internal_forbid_ctor([constructor])

    def forbid_constructors(self, constructors: List[int]) -> None:
        """Forbid multiple constructors from being called.

        Args:
            constructors: List of constructor IDs to forbid
        """
        self._internal_forbid_ctor(constructors)

    def _handle_update(
        self,
        update: Union[Updates, UpdatesCombined, UpdateShort],
    ) -> None:
        """Handle update with custom processor.

        Args:
            update: Update to handle
        """
        if self._raw_updates_processor is not None:
            self._raw_updates_processor(update)

        super()._handle_update(update)
