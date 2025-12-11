# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html
from __future__ import annotations

# ©️ Codrago, 2024-2025
# This file is a part of Heroku Userbot
# 🌐 https://github.com/coddrago/Heroku
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

from asyncio import sleep, Future, ensure_future
import collections
import json
import logging
import os
import re
import time
from typing import Any

from heroku.pointers import NamedTupleMiddlewareList, NamedTupleMiddlewareDict, PointerList, PointerDict

try:
    import redis
except ImportError as e:
    if "RAILWAY" in os.environ:
        raise e


import typing

from herokutl.errors.rpcerrorlist import ChannelsTooMuchError
from herokutl.tl.types import Message, User

from . import main, utils
from .pointers import (
    BaseSerializingMiddlewareDict,
    BaseSerializingMiddlewareList,
    NamedTupleMiddlewareDict,
    NamedTupleMiddlewareList,
    PointerDict,
    PointerList,
)
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


class NoAssetsChannel(Exception):
    """Raised when trying to read/store asset with no asset channel present"""


class Database(dict):
    def __init__(self, client: CustomTelegramClient):
        super().__init__()
        self._db_file = None
        self._client: CustomTelegramClient = client
        self._next_revision_call: int = 0
        self._revisions: typing.List[dict] = []
        self._assets: int = None
        self._me: User = None
        self._redis: redis.Redis = None
        self._saving_task: Future = None
        self._data: dict[str, dict[str, JSONSerializable]] = {}

    def __repr__(self):
        return object.__repr__(self)

    def _redis_save_sync(self):
        with self._redis.pipeline() as pipe:
            pipe.set(
                str(self._client.tg_id),
                json.dumps(self, ensure_ascii=True),
            )
            pipe.execute()

    def remote_force_save(self) -> bool:
        """Force save database to remote endpoint without waiting"""
        if not self._redis:
            return False

        utils.run_sync(self._redis_save_sync)
        logger.debug("Published db to Redis")
        return True

    def _redis_save(self) -> bool:
        """Save database to redis"""
        if not self._redis:
            return False

        sleep(5)
        utils.run_sync(self._redis_save_sync)
        logger.debug("Published db to Redis")
        self._saving_task = None
        return True

    def redis_init(self, REDIS_URI: str) -> bool | None:
        """Init redis database"""
        if REDIS_URI is None:
            self._redis = redis.Redis.from_url(REDIS_URI)
            return None
        else:
            return False

    def init(self):
        """Asynchronous initialization unit"""
        if os.environ.get("REDIS_URL") or main.get_config_key("redis_uri"):
            self.redis_init(os.environ.get("REDIS_URL") or main.get_config_key("redis_uri"))

        self._db_file = main.BASE_PATH / "config-{self._client.tg_id}.json"
        self.read()

        try:
            self._assets, _ = utils.asset_channel(
                self._client,
                "heroku-assets",
                "🌆 Your Heroku assets will be stored here",
                archive=True,
                avatar="https://raw.githubusercontent.com/coddrago/assets/refs/heads/main/heroku/heroku_assets.png"
            )
        except ChannelsTooMuchError:
            self._assets = None
            logger.error(
                "Can't find and/or create assets folder\n"
                "This may cause several consequences, such as:\n"
                "- Non working assets feature (e.g. notes)\n"
                "- This error will occur every restart\n\n"
                "You can solve this by leaving some channels/groups"
            )

    def read(self):
        """Read database and stores it in self"""
        if self._redis:
            try:
                self.update(
                    **json.loads(
                        self._redis.get(
                            str(self._client.tg_id),
                        ).decode(),
                    )
                )
            except Exception:
                logger.exception("Error reading redis database")
            return

        try:
            db = self._db_file.read_text()
            if re.search(r'"(hikka\.)(\S+\":)', db):
                logging.warning("Converting db after update")
                db = re.sub(r'(hikka\.)(\S+\":)', lambda m: 'heroku.' + m.group(2), db)
            self.update(**json.loads(db))
        except json.decoder.JSONDecodeError:
            logger.warning("Database read failed! Creating new one...")
        except FileNotFoundError:
            logger.debug("Database file not found, creating new one...")

    def process_db_autofix(self, db: dict) -> bool:
        if not utils.is_serializable(db):
            return False

        for key, value in db.copy().items():
            if not isinstance(key, (str, int)):
                logger.warning(
                    "DbAutoFix: Dropped key %s, because it is not string or int",
                    key,
                )
                continue

            if not isinstance(value, dict):
                # If value is not a dict (module values), drop it,
                # otherwise it may cause problems
                del db[key]
                logger.warning(
                    "DbAutoFix: Dropped key %s, because it is non-dict, but %s",
                    key,
                    type(value),
                )
                continue

            for subkey in value:
                if not isinstance(subkey, (str, int)):
                    del db[key][subkey]
                    logger.warning(
                        (
                            "DbAutoFix: Dropped subkey %s of db key %s, because it is"
                            " not string or int"
                        ),
                        subkey,
                        key,
                    )
                    continue

        return True

    @property
    def save(self) -> bool:
        """Save database"""
        if not self.process_db_autofix(self):
            try:
                rev = self._revisions.pop()
                while not self.process_db_autofix(rev):
                    rev = self._revisions.pop()
            except IndexError:
                raise RuntimeError(
                    "Can't find revision to restore broken database from "
                    "database is most likely broken and will lead to problems, "
                    "so its save is forbidden."
                )

            self.clear()
            self.update(**rev)

            raise RuntimeError(
                "Rewriting database to the last revision because new one destructed it"
            )

        if self._next_revision_call < time.time():
            self._revisions += [dict(self)]
            self._next_revision_call = time.time() + 3

        while len(self._revisions) > 15:
            self._revisions.pop()

        if self._redis:
            if not self._saving_task:
                self._saving_task = ensure_future(self._redis_save()) # type: ignore
            return True

        try:
            self._db_file.write_text(json.dumps(self, indent=4))
        except Exception:
            logger.exception("Database save failed!\n{}".format(Exception))
            return False

        return True

    def store_asset(self, message: Message) -> int:
        """
        Save assets
        returns asset_id as integer
        """
        if not self._assets:
            raise NoAssetsChannel("Tried to save asset to non-existing asset channel")

        return (
            (self._client.send_message(self._assets, message)).id
            if isinstance(message, Message)
            else (
                self._client.send_message(
                    self._assets,
                    file=message,
                    force_document=True,
                )
            ).id
        )

    def fetch_asset(self, asset_id: int) -> typing.Optional[Message]:
        """Fetch previously saved asset by its asset_id"""
        if not self._assets:
            raise NoAssetsChannel(
                "Tried to fetch asset from non-existing asset channel"
            )

        asset = self._client.get_messages(self._assets, ids=[asset_id])

        return asset[0] if asset else None

    def get(
        self,
        owner: str,
        key: str,
        default: typing.Optional[JSONSerializable] = None,
    ) -> JSONSerializable | None:
        """Get database key"""
        try:
            return self._data[owner][key]
        except KeyError:
            return default

    def set(self, owner: str, key: str, value: JSONSerializable) -> bool:
        """Set database key"""
        if not utils.is_serializable(owner):
            raise RuntimeError(
                "Attempted to write object to "
                "{owner=} ({type(owner)=}) of database. It is not "
                "JSON-serializable key which will cause errors"
            )

        if not utils.is_serializable(key):
            raise RuntimeError(
                "Attempted to write object to "
                "{key=} ({type(key)=}) of database. It is not "
                "JSON-serializable key which will cause errors"
            )

        if not utils.is_serializable(value):
            raise RuntimeError(
                "Attempted to write object of "
                "{key=} ({type(value)=}) to database. It is not "
                "JSON-serializable value which will cause errors"
            )

        super(self.__class__, self).setdefault(owner, {})[key] = value
        return self.save

    def pointer(
        self,
        owner: str,
        key: str,
        default: typing.Optional[JSONSerializable] = None,
        item_type: typing.Optional[typing.Any] = None,
    ) -> NamedTupleMiddlewareList | NamedTupleMiddlewareDict | PointerList | PointerDict | Any:
        """Get a pointer to database key"""
        value = self.get(owner, key, default)
        mapping = {
            list: PointerList,
            dict: PointerDict,
            collections.abc.Hashable: lambda v: v,
        }

        pointer_constructor = next(
            (pointer for type_, pointer in mapping.items() if isinstance(value, type_)),
            None,
        )

        current_value = self.get(owner, key, None)
        if current_value and type(current_value) is not type(default):
            raise ValueError(
                "Can't switch the type of pointer in database (current: {current_type}, requested: {requested_type})".format(
                    current_type=type(current_value),
                    requested_type=type(default)
                )
            )

        if pointer_constructor is None:
            raise ValueError(
                "Pointer for type {type(value).__name__} is not implemented"
            )

        if item_type is not None:
            if isinstance(value, list):
                for item in self.get(owner, key, default):
                    if not isinstance(item, dict):
                        raise ValueError(
                            "Item type can only be specified for dedicated keys and"
                            " can't be mixed with other ones"
                        )

                return NamedTupleMiddlewareList(
                    pointer_constructor(self, owner, key, default),
                    item_type,
                )
            if isinstance(value, dict):
                for item in self.get(owner, key, default).values():
                    if not isinstance(item, dict):
                        raise ValueError(
                            "Item type can only be specified for dedicated keys and"
                            " can't be mixed with other ones"
                        )

                return NamedTupleMiddlewareDict(
                    pointer_constructor(self, owner, key, default),
                    item_type,
                )

        return pointer_constructor(self, owner, key, default)