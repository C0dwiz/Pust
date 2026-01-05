"""Main script, where all the fun starts"""

#    Friendly Telegram (telegram userbot)
#    Copyright (C) 2018-2021 The Authors

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.

#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.

#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.

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

import argparse
import asyncio
import collections
import contextlib
import importlib
import json
import logging
import os
import random
import signal
import socket
import sqlite3
import sys
from enum import StrEnum
from getpass import getpass
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Union

import aiohttp
import telethon
from telethon import events
from telethon.errors import (
    ApiIdInvalidError,
    AuthKeyDuplicatedError,
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
    YouBlockedUserError,
)
from telethon.network.connection import (
    ConnectionTcpFull,
    ConnectionTcpMTProxyRandomizedIntermediate,
)
from telethon.password import compute_check
from telethon.sessions import MemorySession, SQLiteSession
from telethon.tl.functions.account import GetPasswordRequest
from telethon.tl.functions.auth import CheckPasswordRequest
from telethon.tl.functions.contacts import UnblockRequest

from . import database, loader, utils, version
from ._internal import print_banner, restart
from .dispatcher import CommandDispatcher
from .qr import QRCode
from .secure import patcher
from .tl_cache import CustomTelegramClient
from .translations import Translator
from .version import __version__

if TYPE_CHECKING:
    pass


class ConnectionType(StrEnum):
    """Connection type enumeration"""

    FULL = "full"
    MT_PROXY = "mtproxy"
    OBFUSCATED = "obfuscated"


class AuthMethod(StrEnum):
    """Authentication method enumeration"""

    PHONE = "phone"
    QR = "qr"
    BOT_TOKEN = "bot_token"


try:
    from .web import core
except ImportError:
    web_available = False
    logging.exception("Unable to import web")
else:
    web_available = True

BASE_DIR = (
    "/data"
    if "DOCKER" in os.environ
    else os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)
BASE_PATH = Path(BASE_DIR)
CONFIG_PATH = BASE_PATH / "config.json"
DEFAULT_CACHE_EXPIRY = 5 * 60  # 5 minutes

# fmt: off
LATIN_MOCK = [
    "Amor", "Arbor", "Astra", "Aurum", "Bellum", "Caelum",
    "Calor", "Candor", "Carpe", "Celer", "Certo", "Cibus",
    "Civis", "Clemens", "Coetus", "Cogito", "Conexus",
    "Consilium", "Cresco", "Cura", "Cursus", "Decus",
    "Deus", "Dies", "Digitus", "Discipulus", "Dominus",
    "Donum", "Dulcis", "Durus", "Elementum", "Emendo",
    "Ensis", "Equus", "Espero", "Fidelis", "Fides",
    "Finis", "Flamma", "Flos", "Fortis", "Frater", "Fuga",
    "Fulgeo", "Genius", "Gloria", "Gratia", "Gravis",
    "Habitus", "Honor", "Hora", "Ignis", "Imago",
    "Imperium", "Inceptum", "Infinitus", "Ingenium",
    "Initium", "Intra", "Iunctus", "Iustitia", "Labor",
    "Laurus", "Lectus", "Legio", "Liberi", "Libertas",
    "Lumen", "Lux", "Magister", "Magnus", "Manus",
    "Memoria", "Mens", "Mors", "Mundo", "Natura",
    "Nexus", "Nobilis", "Nomen", "Novus", "Nox",
    "Oculus", "Omnis", "Opus", "Orbis", "Ordo", "Os",
    "Pax", "Perpetuus", "Persona", "Petra", "Pietas",
    "Pons", "Populus", "Potentia", "Primus", "Proelium",
    "Pulcher", "Purus", "Quaero", "Quies", "Ratio",
    "Regnum", "Sanguis", "Sapientia", "Sensus", "Serenus",
    "Sermo", "Signum", "Sol", "Solus", "Sors", "Spes",
    "Spiritus", "Stella", "Summus", "Teneo", "Terra",
    "Tigris", "Trans", "Tribuo", "Tristis", "Ultimus",
    "Unitas", "Universus", "Uterque", "Valde", "Vates",
    "Veritas", "Verus", "Vester", "Via", "Victoria",
    "Vita", "Vox", "Vultus", "Zephyrus", "Hewoku", "Bimbalas", "Nywuctuu",
    "Sodrago", "Anyone"
]
# fmt: on

ApiToken = collections.namedtuple("ApiToken", ("ID", "HASH"))


def generate_app_name() -> str:
    """Generate a random app name consisting of three Latin words.

    Returns:
        Random app name like "Cresco Cibus Consilium"
    """
    return " ".join(random.choices(LATIN_MOCK, k=3))


def get_app_name() -> str:
    """Get the saved app name or generate a new one if not present.

    Returns:
        App name string
    """
    if not (app_name := get_config_key("app_name")):
        app_name = generate_app_name()
        save_config_key("app_name", app_name)

    return app_name


def generate_random_system_version() -> str:
    """Generate a random system version string similar to OS version strings.

    Returns:
        Random system version string like "Windows 10.0.19042.1234"
    """
    os_choices = [
        ("Windows", "Vista"),
        ("Windows", "XP"),
        ("Windows", "7"),
        ("Windows", "8"),
        ("Windows", "10"),
        ("Ubuntu", "20.04"),
        ("Debian", "10"),
        ("Fedora", "33"),
        ("Arch Linux", "2021.05"),
        ("CentOS", "8"),
        ("NixOS", "23.05"),
        ("Puppy Linux", "9.5"),
        ("Alpine Linux", "3.18.0"),
        ("Android", "14"),
        ("Android", "15"),
        ("Android", "13"),
        ("Solus", "4.4"),
        ("Gentoo", "2023.0"),
        ("Void Linux", "2023-07-01"),
        ("IOS", "18.0.1"),
    ]

    os_name, os_version = random.choice(os_choices)
    return f"{os_name} {os_version}"


def run_config() -> None:
    """Load and run the configurator module."""
    from . import configurator

    return configurator.api_config(None)


def get_config_key(key: str) -> Union[str, bool, int]:
    """Get a configuration value by key.

    Args:
        key: Configuration key name

    Returns:
        Configuration value or False if key doesn't exist
    """
    try:
        config = json.loads(CONFIG_PATH.read_text())
        return config.get(key, False)
    except (FileNotFoundError, json.JSONDecodeError):
        return False


def save_config_key(key: str, value: Any) -> bool:
    """Save a key-value pair to the configuration file.

    Args:
        key: Configuration key name
        value: Value to save

    Returns:
        True on success
    """
    try:
        config = json.loads(CONFIG_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        config = {}

    config[key] = value
    CONFIG_PATH.write_text(json.dumps(config, indent=4))
    return True


def gen_port(cfg: str = "port", no8080: bool = False) -> int:
    """Generate a random free port or return 8080 for Docker.

    Args:
        cfg: Configuration key for port
        no8080: Force generation even in Docker environment

    Returns:
        Port number
    """
    if "DOCKER" in os.environ and not no8080:
        return 8080

    if port := get_config_key(cfg):
        return int(port)

    while port := random.randint(1024, 65536):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if sock.connect_ex(("localhost", port)):
            sock.close()
            break
        sock.close()

    return port


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--port",
        dest="port",
        action="store",
        default=gen_port(),
        type=int,
    )
    parser.add_argument("--phone", "-p", action="append")
    parser.add_argument("--no-web", dest="disable_web", action="store_true")
    parser.add_argument(
        "--qr-login",
        dest="qr_login",
        action="store_true",
        help=(
            "Use QR code login instead of phone number (will only work if scanned from"
            " another device)"
        ),
    )
    parser.add_argument(
        "--data-root",
        dest="data_root",
        default="",
        help="Root path to store session files in",
    )
    parser.add_argument(
        "--no-auth",
        dest="no_auth",
        action="store_true",
        help="Disable authentication and API token input, exitting if needed",
    )
    parser.add_argument(
        "--proxy-host",
        dest="proxy_host",
        action="store",
        help="MTProto proxy host, without port",
    )
    parser.add_argument(
        "--proxy-port",
        dest="proxy_port",
        action="store",
        type=int,
        help="MTProto proxy port",
    )
    parser.add_argument(
        "--proxy-secret",
        dest="proxy_secret",
        action="store",
        help="MTProto proxy secret",
    )
    parser.add_argument(
        "--root",
        dest="disable_root_check",
        action="store_true",
        help="Disable `force_insecure` warning",
    )
    parser.add_argument(
        "--sandbox",
        dest="sandbox",
        action="store_true",
        help="Die instead of restart",
    )
    parser.add_argument(
        "--proxy-pass",
        dest="proxy_pass",
        action="store_true",
        help="Open proxy pass tunnel on start (not needed on setup)",
    )
    parser.add_argument(
        "--no-tty",
        dest="tty",
        action="store_false",
        default=True,
        help="Do not print colorful output using ANSI escapes",
    )

    return parser.parse_args()


class SuperList(list):
    """Enhanced list that allows calling methods on all contained objects.

    Enables syntax like: await self.allclients.send_message("foo", "bar")
    """

    def __getattribute__(self, attr: str) -> Any:
        """Override attribute access to handle method calls on all items.

        Args:
            attr: Attribute name to access

        Returns:
            Combined result from all items or list of attribute values
        """
        if hasattr(list, attr):
            return list.__getattribute__(self, attr)

        for obj in self:
            attribute = getattr(obj, attr)
            if callable(attribute):
                if asyncio.iscoroutinefunction(attribute):

                    async def async_wrapper(*args, **kwargs):
                        return [await getattr(_, attr)(*args, **kwargs) for _ in self]

                    return async_wrapper

                def sync_wrapper(*args, **kwargs):
                    return [getattr(_, attr)(*args, **kwargs) for _ in self]

                return sync_wrapper

            return [getattr(x, attr) for x in self]


class InteractiveAuthRequired(Exception):
    """Raised when interactive authentication (phone input) is required."""


class Pust:
    """Main Pust userbot instance capable of handling multiple clients."""

    def __init__(self) -> None:
        """Initialize the Pust instance."""
        global BASE_DIR, BASE_PATH, CONFIG_PATH

        self.omit_log = False
        self.arguments = parse_arguments()

        if self.arguments.data_root:
            BASE_DIR = self.arguments.data_root
            BASE_PATH = Path(BASE_DIR)
            CONFIG_PATH = BASE_PATH / "config.json"

        self.loop = None
        self.clients = SuperList()
        self.ready = asyncio.Event()

        self._read_sessions()
        self._get_api_token()
        self._get_proxy()
        self.web = None

    @property
    def loop(self):
        """Get current event loop"""
        return asyncio.get_running_loop()

    def _read_sessions(self) -> None:
        """Read session files from environment and data directory."""
        self.sessions = []

        for filename in os.listdir(BASE_DIR):
            if (
                filename.startswith("Pust-") or filename.startswith("hikka-")
            ) and filename.endswith(".session"):
                session_path = os.path.join(BASE_DIR, filename.rsplit(".session", 1)[0])
                self.sessions.append(SQLiteSession(session_path))

    def _get_api_token(self) -> None:
        """Retrieve API credentials from config, environment, or file."""
        api_id = get_config_key("api_id")
        api_hash = get_config_key("api_hash")

        if api_id and api_hash:
            self.api_token = ApiToken(api_id, api_hash)
            return

        token_file = BASE_PATH / "api_token.txt"
        if token_file.exists():
            try:
                lines = token_file.read_text().splitlines()
                if len(lines) >= 2:
                    api_id, api_hash = lines[0].strip(), lines[1].strip()
                    save_config_key("api_id", int(api_id))
                    save_config_key("api_hash", api_hash)
                    token_file.unlink()
                    logging.debug("Migrated api_token.txt to config.json")
                    self.api_token = ApiToken(int(api_id), api_hash)
                    return
            except (ValueError, IndexError, OSError) as e:
                logging.warning(f"Failed to migrate api_token.txt: {e}")

        match (os.environ.get("api_id"), os.environ.get("api_hash")):
            case (str(id_str), str(hash_str)):
                try:
                    self.api_token = ApiToken(int(id_str), hash_str)
                    return
                except ValueError:
                    pass
            case _:
                pass

        try:
            from . import api_token

            self.api_token = ApiToken(api_token.ID, api_token.HASH)
            return
        except ImportError:
            pass

        self.api_token = None

    def _get_proxy(self) -> None:
        """Configure proxy settings from command-line arguments."""
        if (
            self.arguments.proxy_host
            and self.arguments.proxy_port
            and self.arguments.proxy_secret
        ):
            logging.debug(
                "Using proxy: %s:%s",
                self.arguments.proxy_host,
                self.arguments.proxy_port,
            )

            self.proxy = (
                self.arguments.proxy_host,
                self.arguments.proxy_port,
                self.arguments.proxy_secret,
            )
            self.conn = ConnectionTcpMTProxyRandomizedIntermediate
        else:
            self.proxy = None
            self.conn = ConnectionTcpFull

    def _init_web(self) -> None:
        """Initialize web interface if available."""
        if not web_available or self.arguments.disable_web:
            self.web = None
            return

        self.web = core.Web(
            data_root=BASE_DIR,
            api_token=self.api_token,
            proxy=self.proxy,
            connection=self.conn,
        )

    async def _get_token(self) -> None:
        """Obtain API credentials from user or web interface."""
        while self.api_token is None:
            if self.arguments.no_auth:
                return

            if self.web:
                await self.web.start(self.arguments.port, proxy_pass=True)
                await self._web_banner()
                await self.web.wait_for_api_token_setup()
                self.api_token = self.web.api_token
            else:
                run_config()
                importlib.invalidate_caches()
                self._get_api_token()

    async def save_client_session(
        self,
        client: CustomTelegramClient,
        *,
        delay_restart: bool = False,
    ) -> None:
        """Save client session and optionally restart.

        Args:
            client: Telegram client to save
            delay_restart: If True, delay restart for web setup
        """
        if not hasattr(client, "tg_id"):
            me = await client.get_me()
            if not me:
                raise RuntimeError("Attempted to save non-initialized session")

            telegram_id = me.id
            client._tg_id = telegram_id
            client.tg_id = telegram_id
            client.hikka_me = me
            client.Pust_me = me
        else:
            telegram_id = client.tg_id

        session = SQLiteSession(os.path.join(BASE_DIR, f"Pust-{telegram_id}"))
        session.set_dc(
            client.session.dc_id,
            client.session.server_address,
            client.session.port,
        )
        session.auth_key = client.session.auth_key

        with contextlib.suppress(AttributeError):
            session.save()

        if not delay_restart:
            client.disconnect()
            restart()

        client.session = session

        client.Pust_db = database.Database(client)
        await client.Pust_db.init()

        if delay_restart:
            client.disconnect()
            await asyncio.sleep(3600)

    async def _web_banner(self) -> None:
        """Display web interface information."""
        if not self.web:
            return

        logging.info("🔎 Web mode ready for configuration")

        url = await self.web.get_url(proxy_pass=False)
        logging.info("🔗 Please visit %s", url)

    async def wait_for_web_auth(self, token: str) -> bool:
        """Wait for web authentication confirmation.

        Args:
            token: Authentication token to wait for

        Returns:
            True if authentication succeeded
        """
        timeout = 5 * 60  # 5 minutes
        polling_interval = 1

        for _ in range(timeout):
            await asyncio.sleep(polling_interval)

            for client in self.clients:
                if client.loader.inline.pop_web_auth_token(token):
                    return True

        return False

    async def _phone_login(self, client: CustomTelegramClient) -> bool:
        """Handle phone-based login flow.

        Args:
            client: Telegram client to authenticate

        Returns:
            True if login succeeded
        """
        prompt = (
            "\033[0;96mEnter phone: \033[0m" if self.arguments.tty else "Enter phone: "
        )
        phone = input(prompt)

        await client.start(phone)

        me = await client.get_me()
        telegram_id = me.id
        client._tg_id = telegram_id
        client.tg_id = telegram_id
        client.hikka_me = me
        client.Pust_me = me

        db = database.Database(client)
        await db.init()

        while True:
            bot_username = input(
                "You can enter a custom bot username or leave it empty "
                "and Pust will generate a random one: "
            )

            if not bot_username:
                break

            try:
                if await self._check_bot(client, bot_username):
                    db.set("Pust.inline", "custom_bot", bot_username)
                    print("Bot username saved!")
                    break
                else:
                    print("Bot username is occupied. Try again or leave it empty")
            except Exception as e:
                print(f"Something went wrong: {e}")

        await self.save_client_session(client)
        self.clients.append(client)
        return True

    async def _check_bot(
        self,
        client: CustomTelegramClient,
        username: str,
    ) -> bool:
        """Check if a bot username is available.

        Args:
            client: Telegram client
            username: Bot username to check

        Returns:
            True if username is available
        """

        async with client.conversation("@BotFather", exclusive=False) as conv:
            try:
                message = await conv.send_message("/token")
            except YouBlockedUserError:
                await client(UnblockRequest(id="@BotFather"))
                message = await conv.send_message("/token")

            response = await conv.get_response()

            await message.delete()
            await response.delete()

            if hasattr(response, "reply_markup") and hasattr(
                response.reply_markup, "rows"
            ):
                for row in response.reply_markup.rows:
                    for button in row.buttons:
                        if username == button.text.strip("@"):
                            message = await conv.send_message("/cancel")
                            response = await conv.get_response()

                            await message.delete()
                            await response.delete()
                            return False

        try:
            await client.get_entity(username)
            return False
        except Exception:
            return True

    async def _initial_setup(self) -> bool:
        """Handle initial userbot setup and authentication.

        Returns:
            True if setup completed successfully
        """
        if self.arguments.no_auth:
            return False

        if not self.web:
            return await self._cli_setup()

        if not self.web.running.is_set():
            await self.web.start(self.arguments.port, proxy_pass=True)
            await self._web_banner()

        await self.web.wait_for_clients_setup()
        return True

    async def _cli_setup(self) -> bool:
        """Handle command-line interface setup.

        Returns:
            True if CLI setup completed successfully
        """
        if not self.api_token:
            logging.error("API token not available for CLI setup")
            return False

        client = CustomTelegramClient(
            MemorySession(),
            self.api_token.ID,
            self.api_token.HASH,
            connection=self.conn,
            proxy=self.proxy,
            connection_retries=None,
            device_model=get_app_name(),
            system_version=generate_random_system_version(),
            app_version=".".join(map(str, __version__)) + " x64",
            lang_code="en",
            system_lang_code="en-US",
        )

        await client.connect()

        print(
            "\033[0;96m{}\033[0m".format(
                "You can use QR-code to login from another device "
                "(your friend's phone, for example)."
            )
            if self.arguments.tty
            else (
                "You can use QR-code to login from another device "
                "(your friend's phone, for example)."
            )
        )

        use_qr = (
            input(
                "\033[0;96mUse QR code? [y/N]: \033[0m"
                if self.arguments.tty
                else "Use QR code? [y/N]: "
            ).lower()
            == "y"
        )

        if not use_qr:
            return await self._phone_login(client)

        print("\033[0;96mLoading QR code...\033[0m")
        return await self._qr_login_flow(client)

    async def _qr_login_flow(self, client: CustomTelegramClient) -> bool:
        """Handle QR code authentication flow.

        Args:
            client: Telegram client to authenticate

        Returns:
            True if QR login succeeded
        """
        try:
            qr_login = await client.qr_login()
        except Exception as e:
            logging.error(f"Failed to start QR login: {e}")
            return await self._phone_login(client)

        def print_qr() -> None:
            """Display QR code in terminal."""
            qr = QRCode()
            qr.add_data(qr_login.url)
            print("\033[2J\033[3;1f")
            qr.print_ascii(invert=True)
            print("\033[0;96mScan the QR code above to log in.\033[0m")
            print("\033[0;96mPress Ctrl+C to cancel.\033[0m")

        print_qr()

        try:
            await qr_login.wait(timeout=300)  # 5 minutes timeout
            print_banner("success.txt")
            print("\033[0;92mLogged in successfully!\033[0m")

        except asyncio.TimeoutError:
            print("\033[0;91mQR login timed out.\033[0m")
            return await self._phone_login(client)

        except SessionPasswordNeededError:
            if not await self._handle_2fa(client):
                return False

        except KeyboardInterrupt:
            print("\033[2J\033[3;1f")
            return await self._phone_login(client)

        except Exception as e:
            logging.error(f"QR login failed: {e}")
            return await self._phone_login(client)

        await self.save_client_session(client)
        self.clients.append(client)
        return True

    async def _handle_2fa(self, client: CustomTelegramClient) -> bool:
        """Handle two-factor authentication.

        Args:
            client: Telegram client

        Returns:
            True if 2FA succeeded
        """
        print_banner("2fa.txt")

        try:
            password_info = await client(GetPasswordRequest())
        except Exception as e:
            logging.error(f"Failed to get password info: {e}")
            return False

        hint = getattr(password_info, "hint", "No hint provided")

        while True:
            prompt = (
                f"\033[0;96mEnter 2FA password ({hint}): \033[0m"
                if self.arguments.tty
                else f"Enter 2FA password ({hint}): "
            )
            password = getpass(prompt)

            try:
                check = compute_check(password_info, password.strip())
                await client(CheckPasswordRequest(check))
                return True

            except PasswordHashInvalidError:
                print("\033[0;91mInvalid 2FA password!\033[0m")

            except FloodWaitError as e:
                hours, remainder = divmod(e.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)

                time_parts = []
                if hours:
                    time_parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
                if minutes:
                    time_parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
                if seconds:
                    time_parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

                wait_time = ", ".join(time_parts)
                print(
                    f"\033[0;91mYou got FloodWait error! Please wait {wait_time}\033[0m"
                )
                return False

    async def _init_clients(self) -> bool:
        """Initialize clients from saved sessions.

        Returns:
            True if at least one client started successfully
        """
        for session in self.sessions.copy():
            try:
                client = await self._create_client_from_session(session)
                self.clients.append(client)

            except sqlite3.OperationalError:
                logging.error(
                    "Check that this is the only instance running. "
                    "If that doesn't help, delete the file '%s'",
                    session.filename,
                )
                continue

            except (TypeError, AuthKeyDuplicatedError):
                Path(session.filename).unlink(missing_ok=True)
                self.sessions.remove(session)

            except (ValueError, ApiIdInvalidError):
                run_config()
                return False

            except PhoneNumberInvalidError:
                logging.error(
                    "Phone number is incorrect. Use international format (+XX...) "
                    "and don't put spaces in it."
                )
                self.sessions.remove(session)

            except InteractiveAuthRequired:
                logging.error(
                    "Session %s was terminated and re-auth is required",
                    session.filename,
                )
                self.sessions.remove(session)

        return bool(self.sessions)

    async def _create_client_from_session(
        self, session: SQLiteSession
    ) -> CustomTelegramClient:
        """Create a Telegram client from a session.

        Args:
            session: SQLite session object

        Returns:
            Initialized Telegram client
        """
        client = CustomTelegramClient(
            session,
            self.api_token.ID,
            self.api_token.HASH,
            connection=self.conn,
            proxy=self.proxy,
            connection_retries=None,
            device_model=get_app_name(),
            system_version=generate_random_system_version(),
            app_version=".".join(map(str, __version__)) + " x64",
            lang_code="en",
            system_lang_code="en-US",
        )

        await client.connect()

        if session.server_address == "0.0.0.0":
            patcher.patch(client, session)

        client.phone = "None"
        return client

    async def amain_wrapper(self, client: CustomTelegramClient) -> None:
        """Wrapper around main client loop.

        Args:
            client: Telegram client to run
        """
        async with client:
            first = True
            me = await client.get_me()
            client._tg_id = me.id
            client.tg_id = me.id
            client.hikka_me = me
            client.Pust_me = me

            allowed_ids = await self._load_allowed_ids()

            await version.check_branch(me.id, allowed_ids)

            while await self.amain(first, client):
                first = False

    async def _load_allowed_ids(self) -> List[int]:
        """Load allowed beta tester IDs from GitHub.

        Returns:
            List of allowed user IDs
        """
        url = "https://raw.githubusercontent.com/coddrago/modules-web/main/mods/ids/allowed_ids.txt"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.text()
                        return [
                            int(line.strip())
                            for line in content.split("\n")
                            if line.strip() and line.strip().isdigit()
                        ]
                    else:
                        logging.error(f"Failed to load allowed IDs: {response.status}")
        except Exception as e:
            logging.error(f"Exception loading allowed beta tester IDs: {e}")

        return []

    async def _badge(self, client: CustomTelegramClient) -> None:
        """Display startup badge and send notification.

        Args:
            client: Telegram client
        """
        try:
            import git

            repo = git.Repo()
            build = utils.get_git_hash()

            diff = repo.git.log([f"HEAD..origin/{version.branch}", "--oneline"])
            update_status = "Update required" if diff else "Up-to-date"

            logo = (
                "🪐 Pust Userbot\n"
                f"• Build: {build[:7]}\n"
                f"• Version: {'.'.join(map(str, __version__))}\n"
                f"• {update_status}\n"
            )

            if not self.omit_log:
                print(logo)

                if self.web and hasattr(self.web, "url"):
                    web_url = f"🔗 Web url: {self.web.url}"
                    logging.debug(
                        "\n🪐 Pust %s #%s (%s) started\n%s",
                        ".".join(map(str, __version__)),
                        build[:7],
                        update_status,
                        web_url,
                    )
                    self.omit_log = True

            caption = (
                "🪐 <b>Pust {} started!</b>\n\n"
                "⚙ <b>GitHub commit SHA: <a href='https://github.com/C0dWiz/Pust/commit/{}'>{}</a></b>\n"
                "🔎 <b>Update status: {}</b>\n"
                "<b>{}</b>".format(
                    ".".join(map(str, __version__)),
                    build,
                    build[:7],
                    update_status,
                    web_url if self.web and hasattr(self.web, "url") else "",
                )
            )

            await client.Pust_inline.bot.send_photo(
                logging.getLogger().handlers[0].get_logid_by_client(client.tg_id),
                "https://raw.githubusercontent.com/coddrago/assets/refs/heads/main/Pust/Pust_started.png",
                caption=caption,
            )

            prefix = client.Pust_db.get(__name__, "command_prefix", False) or "."
            logging.debug(
                "· Started for %s · Prefix: «%s» ·",
                client.tg_id,
                prefix,
            )

        except Exception as e:
            logging.exception("Badge error: %s", e)

    async def _add_dispatcher(
        self,
        client: CustomTelegramClient,
        modules: loader.Modules,
        db: database.Database,
    ) -> None:
        """Initialize and add command dispatcher to client.

        Args:
            client: Telegram client
            modules: Loaded modules
            db: Database instance
        """
        dispatcher = CommandDispatcher(modules, client, db)
        client.dispatcher = dispatcher
        modules.check_security = dispatcher.check_security

        client.add_event_handler(
            dispatcher.handle_incoming,
            events.NewMessage,
        )

        client.add_event_handler(
            dispatcher.handle_incoming,
            events.ChatAction,
        )

        client.add_event_handler(
            dispatcher.handle_command,
            events.NewMessage(forwards=False),
        )

        client.add_event_handler(
            dispatcher.handle_command,
            events.MessageEdited(),
        )

        client.add_event_handler(
            dispatcher.handle_raw,
            events.Raw(),
        )

    async def amain(self, first: bool, client: CustomTelegramClient) -> bool:
        """Main async initialization for each client.

        Args:
            first: Whether this is the first run
            client: Telegram client

        Returns:
            True if should reconnect, False otherwise
        """
        client.parse_mode = "HTML"
        await client.start()

        db = database.Database(client)
        client.Pust_db = db
        await db.init()

        logging.debug("Database initialized")

        translator = Translator(client, db)
        await translator.init()

        modules = loader.Modules(client, db, self.clients, translator)
        client.loader = modules

        if self.web:
            await self.web.add_loader(client, modules, db)
            await self.web.start_if_ready(
                len(self.clients),
                self.arguments.port,
                proxy_pass=self.arguments.proxy_pass,
            )

        await self._add_dispatcher(client, modules, db)

        await modules.register_all(None)
        modules.send_config()
        await modules.send_ready()

        if first:
            await self._badge(client)

        await client.run_until_disconnected()
        return True

    async def _main(self) -> None:
        """Main entrypoint for async execution."""
        self._init_web()
        inital_web = False

        save_config_key("port", self.arguments.port)

        await self._get_token()

        if (
            not self.clients and not self.sessions or not await self._init_clients()
        ) and not (inital_web := await self._initial_setup()):
            return

        if inital_web:

            async def scheduled_web_stop() -> None:
                await asyncio.sleep(120)
                if self.web:
                    await self.web.stop()
                    logging.debug("Initial web was stopped for security reasons")

            asyncio.create_task(scheduled_web_stop())

        self.loop.set_exception_handler(
            lambda loop, context: logging.error(
                "Exception on event loop! %s",
                context.get("message", "No message"),
                exc_info=context.get("exception", None),
            )
        )

        await asyncio.gather(*[self.amain_wrapper(client) for client in self.clients])

    async def _shutdown_handler(self) -> None:
        """Handle graceful shutdown."""

        for client in self.clients:
            inline = getattr(client.loader, "inline", None)
            if inline:
                for task in (inline._task, inline._cleaner_task):
                    if task:
                        task.cancel()

                with contextlib.suppress(Exception):
                    await inline._dp.stop_polling()
                    await inline.bot.session.close()

        for client in self.clients:
            await client.disconnect()

        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()

    def main(self) -> None:
        """Main entrypoint for the application."""

        logging.info("Starting Pust Userbot with asyncio.run()")

        try:
            asyncio.run(self._main())
        except KeyboardInterrupt:
            logging.info("KeyboardInterrupt received.")

        except Exception as e:
            logging.exception("Unexpected exception in main loop: %s", e)
        finally:
            logging.info("Bye!")


CUSTOM_EMOJIS = not get_config_key("disable_custom_emojis")

Pust = Pust()
