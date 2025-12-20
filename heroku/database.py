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
# This file is a part of Pust Userbot.
#
# Copyright (C) 2026 CodWiz

from __future__ import annotations

import asyncio
import collections.abc
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional, TypeVar, cast

from heroku.pointers import (
    NamedTupleMiddlewareList,
    NamedTupleMiddlewareDict,
    PointerList,
    PointerDict,
    BaseSerializingMiddlewareDict,
    BaseSerializingMiddlewareList,
)
from herokutl.errors.rpcerrorlist import ChannelsTooMuchError
from herokutl.tl.types import Message

from . import main, utils
from .tl_cache import CustomTelegramClient
from .types import JSONSerializable

__all__ = [
    "Database",
    "PointerList",
    "PointerDict",
    "NamedTupleMiddlewareDict",
    "NamedTupleMiddlewareList",
    "BaseSerializingMiddlewareDict",
    "BaseSerializingMiddlewareList",
]

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=JSONSerializable)


class NoAssetsChannel(Exception):
    """Raised when trying to read/store asset with no asset channel present"""


class Database(dict):
    """Database manager for Heroku Userbot"""
    
    _MAX_REVISIONS = 15
    _REVISION_INTERVAL = 3

    def __init__(self, client: CustomTelegramClient):
        super().__init__()
        self._db_file: Optional[Path] = None
        self._client: CustomTelegramClient = client
        self._next_revision_call: float = 0.0
        self._revisions: list[dict[str, Any]] = []
        self._assets: Optional[int] = None
        self._redis = None
        self._saving_task: Optional[asyncio.Future] = None
        self._data: dict[str, dict[str, JSONSerializable]] = {}

        try:
            import redis
            self._redis_client = redis
        except ImportError:
            self._redis_client = None
            if "RAILWAY" in os.environ:
                raise

    def __repr__(self) -> str:
        return object.__repr__(self)

    def _redis_save_sync(self) -> None:
        """Synchronously save database to Redis"""
        if not self._redis:
            return

        with self._redis.pipeline() as pipe:
            pipe.set(
                str(self._client.tg_id),
                json.dumps(self, ensure_ascii=True, separators=(",", ":")),
            )
            pipe.execute()

    def remote_force_save(self) -> bool:
        """Force save database to remote endpoint without waiting"""
        if not self._redis:
            return False

        try:
            utils.run_sync(self._redis_save_sync)
            logger.debug("Published database to Redis")
            return True
        except Exception as e:
            logger.error("Failed to force save database to Redis: %s", e)
            return False

    async def _redis_save(self) -> bool:
        """Save database to Redis asynchronously"""
        if not self._redis:
            return False

        await asyncio.sleep(5)
        
        try:
            utils.run_sync(self._redis_save_sync)
            logger.debug("Published database to Redis")
            return True
        except Exception as e:
            logger.error("Failed to save database to Redis: %s", e)
            return False
        finally:
            self._saving_task = None

    def redis_init(self, redis_uri: Optional[str]) -> bool:
        """Initialize Redis database connection"""
        if not redis_uri or self._redis_client is None:
            return False

        try:
            self._redis = self._redis_client.Redis.from_url(redis_uri)
            logger.info("Redis connection established")
            return True
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            return False

    async def init(self) -> None:
        """Asynchronous initialization unit"""
        redis_uri = os.environ.get("REDIS_URL") or main.get_config_key("redis_uri")
        if redis_uri:
            self.redis_init(redis_uri)

        self._db_file = main.BASE_PATH / f"config-{self._client.tg_id}.json"
        self.read()

        try:
            self._assets, _ = await utils.asset_channel(
                self._client,
                "heroku-assets",
                "🌆 Your Heroku assets will be stored here",
                archive=True,
                avatar=(
                    "https://raw.githubusercontent.com/coddrago/assets/refs/heads/main/"
                    "heroku/heroku_assets.png"
                )
            )
        except ChannelsTooMuchError:
            self._assets = None
            logger.error(
                "Cannot find and/or create assets folder\n"
                "This may cause several consequences, such as:\n"
                "- Non-working assets feature (e.g., notes)\n"
                "- This error will occur on every restart\n\n"
                "You can solve this by leaving some channels/groups"
            )

    def read(self) -> None:
        """Read database and store it in self"""
        if self._redis:
            try:
                data = self._redis.get(str(self._client.tg_id))
                if data:
                    self.update(**json.loads(data.decode()))
                    logger.debug("Database loaded from Redis")
                else:
                    logger.debug("No database found in Redis")
            except json.JSONDecodeError as e:
                logger.error("Failed to decode JSON from Redis: %s", e)
            except Exception as e:
                logger.exception("Error reading Redis database: %s", e)
            return

        if not self._db_file or not self._db_file.exists():
            logger.debug("Database file not found, creating new one...")
            return

        try:
            db_content = self._db_file.read_text()
            # Convert legacy Hikka keys to Heroku
            if re.search(r'"(hikka\.)(\S+\":)', db_content):
                logger.warning("Converting database after update")
                db_content = re.sub(
                    r'(hikka\.)(\S+\":)',
                    lambda m: 'heroku.' + m.group(2),
                    db_content
                )
            self.update(**json.loads(db_content))
            logger.debug("Database loaded from file")
        except json.JSONDecodeError as e:
            logger.error("Database JSON decode failed: %s", e)
        except Exception as e:
            logger.exception("Unexpected error reading database: %s", e)

    def process_db_autofix(self, db: dict) -> bool:
        """Validate and fix database structure"""
        if not utils.is_serializable(db):
            return False

        for key, value in db.copy().items():
            if not isinstance(key, (str, int)):
                logger.warning(
                    "DbAutoFix: Dropped key %s because it is not string or int",
                    key,
                )
                del db[key]
                continue

            if not isinstance(value, dict):
                logger.warning(
                    "DbAutoFix: Dropped key %s because it is non-dict, but %s",
                    key,
                    type(value).__name__,
                )
                del db[key]
                continue

            for subkey in list(value.keys()):
                if not isinstance(subkey, (str, int)):
                    logger.warning(
                        "DbAutoFix: Dropped subkey %s of key %s (not string or int)",
                        subkey,
                        key,
                    )
                    del db[key][subkey]

        return True

    @property
    def save(self) -> bool:
        """Save database to persistent storage"""
        if not self.process_db_autofix(self):
            try:
                rev = self._revisions.pop()
                while not self.process_db_autofix(rev):
                    rev = self._revisions.pop()
            except IndexError:
                raise RuntimeError(
                    "Cannot find revision to restore broken database from. "
                    "Database is most likely broken and will lead to problems, "
                    "so its save is forbidden."
                )

            self.clear()
            self.update(**rev)
            
            logger.error("Database restored from previous revision due to corruption")
            raise RuntimeError(
                "Rewriting database to the last revision because new one destructed it"
            )

        if self._next_revision_call < time.time():
            self._revisions.append(dict(self))
            self._next_revision_call = time.time() + self._REVISION_INTERVAL

        while len(self._revisions) > self._MAX_REVISIONS:
            self._revisions.pop(0)

        if self._redis:
            if not self._saving_task or self._saving_task.done():
                self._saving_task = asyncio.ensure_future(self._redis_save())
            return True

        try:
            if self._db_file:
                self._db_file.write_text(json.dumps(self, indent=4))
                logger.debug("Database saved to file")
                return True
        except Exception as e:
            logger.exception("Database save failed: %s", e)
            return False

        return False

    async def store_asset(self, message: Message) -> int:
        """
        Save asset to Telegram channel
        
        Returns:
            Asset ID as integer
        """
        if not self._assets:
            raise NoAssetsChannel(
                "Tried to save asset to non-existing asset channel"
            )

        try:
            if isinstance(message, Message):
                sent = await self._client.send_message(self._assets, message)
            else:
                sent = await self._client.send_message(
                    self._assets,
                    file=message,
                    force_document=True,
                )
            return sent.id
        except Exception as e:
            logger.error("Failed to store asset: %s", e)
            raise

    async def fetch_asset(self, asset_id: int) -> Optional[Message]:
        """Fetch previously saved asset by its asset_id"""
        if not self._assets:
            raise NoAssetsChannel(
                "Tried to fetch asset from non-existing asset channel"
            )

        try:
            assets = await self._client.get_messages(self._assets, ids=[asset_id])
            return assets[0] if assets else None
        except Exception as e:
            logger.error("Failed to fetch asset %s: %s", asset_id, e)
            return None

    def get(
        self,
        owner: str,
        key: str,
        default: Optional[T] = None,
    ) -> Optional[T]:
        """Get database key"""
        try:
            return cast(T, self._data[owner][key])
        except KeyError:
            return default

    def set(self, owner: str, key: str, value: JSONSerializable) -> bool:
        """Set database key"""
        for name, val, val_type in [
            ("owner", owner, str),
            ("key", key, str),
            ("value", value, JSONSerializable),
        ]:
            if not utils.is_serializable(val):
                raise RuntimeError(
                    f"Attempted to write non-JSON-serializable {name} "
                    f"({val_type.__name__}) to database"
                )

        self.setdefault(owner, {})[key] = value
        return self.save

    def pointer(
        self,
        owner: str,
        key: str,
        default: Optional[JSONSerializable] = None,
        item_type: Optional[type] = None,
    ) -> Any:
        """Get a pointer to database key"""
        value = self.get(owner, key, default)
        
        current_value = self.get(owner, key, None)
        if current_value is not None and default is not None:
            if type(current_value) is not type(default):
                raise ValueError(
                    f"Cannot switch pointer type in database "
                    f"(current: {type(current_value).__name__}, "
                    f"requested: {type(default).__name__})"
                )

        if isinstance(value, list):
            if item_type is not None:
                for item in value:
                    if not isinstance(item, dict):
                        raise ValueError(
                            "Item type can only be specified for dedicated keys "
                            "and cannot be mixed with other ones"
                        )
                return NamedTupleMiddlewareList(
                    PointerList(self, owner, key, default or []),
                    item_type,
                )
            return PointerList(self, owner, key, default or [])

        if isinstance(value, dict):
            if item_type is not None:
                for item in value.values():
                    if not isinstance(item, dict):
                        raise ValueError(
                            "Item type can only be specified for dedicated keys "
                            "and cannot be mixed with other ones"
                        )
                return NamedTupleMiddlewareDict(
                    PointerDict(self, owner, key, default or {}),
                    item_type,
                )
            return PointerDict(self, owner, key, default or {})

        if isinstance(value, collections.abc.Hashable):
            return value

        raise ValueError(
            f"Pointer for type {type(value).__name__} is not implemented"
        )