"""Represents current userbot version"""
# ©️ Dan Gazizullin, 2021-2023
# This file is a part of Hikka Userbot
# 🌐 https://github.com/hikariatama/Hikka
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

# ©️ Codrago, 2024-2025
# This file is a part of Pustrbot
# 🌐 https://github.com/coddrago/Pust
# You can redistribute it and/or modify it under the terms of the GNU AGPLv3
# 🔑 https://www.gnu.org/licenses/agpl-3.0.html

# SPDX-License-Identifier: GNU AGPL v3.0
#
# This file is a part of Pust Userbot.
#
# Copyright (C) 2026 CodWiz

import os

import git
from Pustternal import restart

# Version constants
__version__ = (2, 0, 0)
MASTER_BRANCH: str = "master"


def get_repo_path() -> str:
    """Get absolute path to the repository root."""
    current_dir = os.path.dirname(__file__)
    parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
    return parent_dir


def get_active_branch() -> str:
    """Get current git branch name."""
    try:
        repo = git.Repo(path=get_repo_path())
        return repo.active_branch.name
    except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError, AttributeError):
        return MASTER_BRANCH


branch: str = get_active_branch()


async def check_branch(me_id: int, allowed_ids: list[int]) -> None:
    """
    Check if current branch is allowed for the user.

    Args:
        me_id: Current user ID
        allowed_ids: List of user IDs allowed to use non-master branches
    """
    if branch == MASTER_BRANCH or me_id in allowed_ids:
        return

    try:
        repo = git.Repo(path=get_repo_path())
        repo.git.reset("--hard", "HEAD")
        repo.git.checkout(MASTER_BRANCH, force=True)
        restart()
    except (git.exc.GitCommandError, git.exc.InvalidGitRepositoryError) as e:
        print(f"Failed to switch branch: {e}")
