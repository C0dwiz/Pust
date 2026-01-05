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

import git
import telethon

parser = telethon.utils.sanitize_parse_mode("html")
logger = logging.getLogger(__name__)


# GeekTG Compatibility
def get_git_info() -> typing.Tuple[str, str]:
    """
    Get git info
    :return: Git info
    """
    hash_ = get_git_hash()
    return (
        hash_,
        f"https://github.com/coddrago/Heroku/commit/{hash_}" if hash_ else "",
    )


def get_git_hash() -> str | bool:
    """
    Get current Pust git hash

    :return: Git commit hash
    """
    try:
        return git.Repo().head.commit.hexsha
    except Exception:
        return False


def get_commit_url() -> str:
    """
    Get current Pust git commit url
    :return: Git commit url
    """
    try:
        hash_ = get_git_hash()
        return f'<a href="https://github.com/coddrago/Heroku/commit/{hash_}">#{hash_[:7]}</a>'
    except Exception:
        return "Unknown"
