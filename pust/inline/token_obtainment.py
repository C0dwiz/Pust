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

import asyncio
import logging
import re
import os
import random
from contextlib import suppress
from typing import Optional, Tuple

from Pusttl.errors.rpcerrorlist import YouBlockedUserError
from Pusttl.tl.functions.contacts import UnblockRequest

from .. import utils
from .. import main
from .._internal import fw_protect
from .types import InlineUnit

logger = logging.getLogger(__name__)


class TokenObtainment(InlineUnit):
    async def _send_botfather_message(
        self,
        message: str,
        expect_response: bool = True,
        delete_messages: bool = True,
        max_attempts: int = 3,
    ) -> Optional[str]:
        """
        Helper method to send message to BotFather and get response
        :param message: Message to send
        :param expect_response: Whether to expect a response
        :param delete_messages: Whether to delete messages after
        :param max_attempts: Maximum number of retry attempts
        :return: Response text or None
        """
        for attempt in range(max_attempts):
            try:
                async with self._client.conversation(
                    "@BotFather", exclusive=False
                ) as conv:
                    await fw_protect()

                    if attempt == 0:
                        with suppress(YouBlockedUserError):
                            await self._client(UnblockRequest(id="@BotFather"))

                    sent_msg = await conv.send_message(message)
                    if not expect_response:
                        return None

                    response = await conv.get_response(timeout=30)

                    logger.debug(f"BotFather attempt {attempt + 1} >> {message}")
                    logger.debug(
                        f"BotFather attempt {attempt + 1} << {response.raw_text}"
                    )

                    if delete_messages:
                        with suppress(Exception):
                            await sent_msg.delete()
                        with suppress(Exception):
                            await response.delete()

                    return response.raw_text

            except asyncio.TimeoutError:
                logger.warning(
                    f"Timeout waiting for BotFather response (attempt {attempt + 1})"
                )
                if attempt == max_attempts - 1:
                    raise
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(
                    f"Error communicating with BotFather (attempt {attempt + 1}): {e}"
                )
                if attempt == max_attempts - 1:
                    raise
                await asyncio.sleep(1)

        return None

    async def _create_bot(self) -> bool:
        """
        Create a new bot via BotFather
        :return: True if bot was created successfully, False otherwise
        """
        logger.info("User doesn't have bot, attempting to create a new one")

        try:
            response = await self._send_botfather_message("/newbot")
            if not response:
                return False

            if "20" in response:
                logger.error("BotFather limit reached (20 bots maximum)")
                return False

            if self._db.get("Pust.inline", "custom_bot", False):
                custom_username = self._db.get("Pust.inline", "custom_bot").strip("@")

                try:
                    await self._client.get_entity(f"@{custom_username}")
                    logger.warning(
                        f"Custom username @{custom_username} is already taken"
                    )

                    custom_username = None
                except ValueError:
                    pass

                if custom_username:
                    username = f"@{custom_username}"
                else:
                    uid = utils.rand(6)
                    genran = "".join(random.choice(main.LATIN_MOCK))
                    username = f"@{genran}_{uid}_bot"
            else:
                uid = utils.rand(6)
                genran = "".join(random.choice(main.LATIN_MOCK))
                username = f"@{genran}_{uid}_bot"

            bot_name = f"🪐 Pust {utils.get_version_raw}"[:64]
            await self._send_botfather_message(bot_name)

            await self._send_botfather_message(username)

            await self._send_botfather_message("/setuserpic")
            await self._send_botfather_message(username)

            avatar_path = f"{os.getcwd()}/assets/Pust.png"
            if os.path.exists(avatar_path):
                try:
                    async with self._client.conversation(
                        "@BotFather", exclusive=False
                    ) as conv:
                        await fw_protect()
                        await conv.send_file(avatar_path)
                        await conv.get_response()
                except Exception as e:
                    logger.warning(f"Failed to set bot avatar: {e}")

            else:
                logger.warning(f"Bot avatar not found at {avatar_path}")

            logger.info("Bot created successfully, obtaining token...")
            return await self._assert_token(
                create_new_if_needed=False, revoke_token=False
            )

        except Exception as e:
            logger.error(f"Failed to create bot: {e}", exc_info=True)
            return False

    async def _process_botfather_bot_list(
        self, response_text: str, revoke_token: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """
        Process BotFather response with list of bots
        :param response_text: Response text from BotFather
        :param revoke_token: Whether to revoke token
        :return: Tuple of (success, token)
        """

        bot_patterns = [r"@([a-zA-Z0-9_]{5,32})", r"@Pust_[0-9a-zA-Z]{6}_bot"]

        found_bots = []
        for pattern in bot_patterns:
            found_bots.extend(re.findall(pattern, response_text))

        if not found_bots:
            logger.debug("No bots found in BotFather response")
            return False, None

        custom_bot = self._db.get("Pust.inline", "custom_bot", False)
        target_bots = []

        for bot_username in found_bots:
            bot_username = f"@{bot_username}"

            if custom_bot:
                if bot_username == custom_bot:
                    target_bots.append(bot_username)
            else:
                if re.match(r"@Pust_[0-9a-zA-Z]{6}_bot", bot_username):
                    target_bots.append(bot_username)

        if not target_bots:
            logger.debug(f"No matching bots found. Custom bot: {custom_bot}")
            return False, None

        for bot_username in target_bots:
            try:
                logger.info(f"Attempting to get token for {bot_username}")

                response = await self._send_botfather_message(bot_username)
                if not response:
                    continue

                lines = response.splitlines()
                if len(lines) < 2:
                    logger.warning(f"Unexpected response format for {bot_username}")
                    continue

                token = lines[1].strip()
                if not token or len(token) < 20:
                    logger.warning(f"Invalid token format for {bot_username}")
                    continue

                if revoke_token:
                    logger.info(f"Revoking token for {bot_username}")
                    await self._send_botfather_message("/revoke")
                    revoke_response = await self._send_botfather_message(bot_username)
                    if revoke_response:
                        lines = revoke_response.splitlines()
                        if len(lines) >= 2:
                            token = lines[1].strip()

                config_steps = [
                    ("/setinline", "Setting inline mode..."),
                    (bot_username, "Providing bot username..."),
                    ("user@Pust:~$", "Setting inline placeholder..."),
                    ("/setinlinefeedback", "Setting feedback mode..."),
                    (bot_username, "Providing bot username for feedback..."),
                    ("Enabled", "Enabling inline feedback..."),
                ]

                for step_text, step_log in config_steps:
                    logger.debug(step_log)
                    await self._send_botfather_message(step_text)
                    await asyncio.sleep(0.5)

                return True, token

            except Exception as e:
                logger.error(f"Failed to process bot {bot_username}: {e}")
                continue

        return False, None

    async def _assert_token(
        self,
        create_new_if_needed: bool = True,
        revoke_token: bool = False,
    ) -> bool:
        """
        Assert that bot token exists and is valid
        :param create_new_if_needed: Create new bot if token not found
        :param revoke_token: Revoke existing token and get new one
        :return: True if token was obtained, False otherwise
        """

        if self._token and not revoke_token:
            logger.debug("Token already exists in memory")
            return True

        logger.info("Bot token not found in db, attempting to search in BotFather")

        if not self._db.get(__name__, "no_mute", False):
            try:
                await utils.dnd(
                    self._client,
                    await self._client.get_entity("@BotFather"),
                    True,
                )
                self._db.set(__name__, "no_mute", True)
            except Exception as e:
                logger.warning(f"Failed to mute BotFather: {e}")

        try:
            response = await self._send_botfather_message("/token")
            if not response:
                logger.error("Failed to get response from BotFather")
                if create_new_if_needed:
                    return await self._create_bot()
                return False

            success, token = await self._process_botfather_bot_list(
                response, revoke_token
            )

            if success and token:
                self._db.set("Pust.inline", "bot_token", token)
                self._token = token
                logger.info("Token successfully obtained and stored")
                return True
            else:
                logger.info("No suitable bot found in BotFather")
                if create_new_if_needed:
                    return await self._create_bot()
                return False

        except Exception as e:
            logger.error(f"Error asserting token: {e}", exc_info=True)
            if create_new_if_needed:
                logger.info("Attempting to create new bot due to error")
                return await self._create_bot()
            return False

    async def _reassert_token(self) -> bool:
        """
        Reassert token (revoke old and get new)
        :return: True if successful, False otherwise
        """
        logger.info("Reasserting bot token...")
        is_token_asserted = await self._assert_token(revoke_token=True)

        if not is_token_asserted:
            self.init_complete = False
            logger.error("Failed to reassert token")
            return False
        else:
            logger.info("Token reasserted successfully, re-registering manager")
            await self.register_manager(ignore_token_checks=True)
            return True

    async def _dp_revoke_token(
        self, already_initialised: bool = True
    ) -> Optional[bool]:
        """
        Revoke bot token and get new one
        :param already_initialised: Whether inline manager is already initialized
        :return: True if successful, None if async operation started
        """
        if already_initialised:
            await self._stop()
            logger.error("Got polling conflict. Attempting token revocation...")

        self._db.set("Pust.inline", "bot_token", None)
        self._token = None

        if already_initialised:
            asyncio.ensure_future(self._reassert_token())
            return None
        else:
            return await self._reassert_token()

    async def _validate_token(self, token: str) -> bool:
        """
        Validate bot token format and availability
        :param token: Token to validate
        :return: True if token appears valid
        """
        if not token or len(token) < 20:
            return False

        token_pattern = r"^\d+:[a-zA-Z0-9_-]{35}$"
        return bool(re.match(token_pattern, token))

    async def _get_bot_info(self, token: str) -> Optional[dict]:
        """
        Get bot info using token
        :param token: Bot token
        :return: Bot info dict or None
        """

        return None
