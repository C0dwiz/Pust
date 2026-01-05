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

import logging
import typing
from contextlib import suppress

from .types import InlineUnit

logger = logging.getLogger(__name__)


class BotPM(InlineUnit):
    def set_fsm_state(
        self,
        user: typing.Union[str, int],
        state: typing.Union[str, bool, None],
    ) -> bool:
        """
        Set FSM state for user
        :param user: user id
        :param state: state to set. If None, False or empty string - removes state
        :return: True if operation successful, False otherwise
        :rtype: bool
        """

        if not isinstance(user, (str, int)):
            logger.error(
                "Invalid type for `user` in `set_fsm_state`. Expected `str` or `int`, got %s",
                type(user),
            )
            return False

        if not isinstance(state, (str, bool, type(None))):
            logger.error(
                "Invalid type for `state` in `set_fsm_state`. Expected `str`, `bool` or `None`, got %s",
                type(state),
            )
            return False

        user_id = str(user)

        if (
            state is None
            or state is False
            or (isinstance(state, str) and not state.strip())
        ):
            with suppress(KeyError):
                del self.fsm[user_id]
        else:
            if isinstance(state, bool):
                self.fsm[user_id] = str(state).lower()
            else:
                self.fsm[user_id] = (
                    state.strip() if isinstance(state, str) else str(state)
                )

        logger.debug(
            "FSM state updated for user %s: %s",
            user_id,
            self.fsm.get(user_id, "REMOVED"),
        )
        return True

    ss = set_fsm_state

    def get_fsm_state(self, user: typing.Union[str, int]) -> typing.Union[bool, str]:
        """
        Get FSM state for user
        :param user: user id
        :return: FSM state or False if user has no FSM state
        :rtype: typing.Union[bool, str]
        """

        if not isinstance(user, (str, int)):
            logger.error(
                "Invalid type for `user` in `get_fsm_state`. Expected `str` or `int`, got %s",
                type(user),
            )
            return False

        user_id = str(user)
        state = self.fsm.get(user_id)

        if state is None:
            return False
        elif isinstance(state, str):
            if state.lower() == "true":
                return True
            elif state.lower() == "false":
                return False

        return state

    gs = get_fsm_state

    def clear_fsm_states(
        self, user_ids: typing.Optional[typing.List[typing.Union[str, int]]] = None
    ) -> int:
        """
        Clear FSM states for specified users or all users
        :param user_ids: List of user IDs to clear. If None, clears all states
        :return: Number of states cleared
        :rtype: int
        """
        cleared_count = 0

        if user_ids is None:
            cleared_count = len(self.fsm)
            self.fsm.clear()
            logger.debug("Cleared all FSM states (%d total)", cleared_count)
        else:
            for user in user_ids:
                user_id = str(user)
                if user_id in self.fsm:
                    del self.fsm[user_id]
                    cleared_count += 1
            logger.debug("Cleared FSM states for %d users", cleared_count)

        return cleared_count

    def list_fsm_users(self) -> typing.List[str]:
        """
        Get list of all users with FSM states
        :return: List of user IDs
        :rtype: typing.List[str]
        """
        return list(self.fsm.keys())

    def has_fsm_state(self, user: typing.Union[str, int]) -> bool:
        """
        Check if user has any FSM state
        :param user: user id
        :return: True if user has state, False otherwise
        :rtype: bool
        """
        if not isinstance(user, (str, int)):
            return False

        return str(user) in self.fsm
