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
import atexit as _atexit
import contextlib
import functools
import logging
import random
import signal
import time
from enum import StrEnum, IntEnum
from typing import Any, Awaitable, Callable, Optional, Dict, List
from dataclasses import dataclass, field
from functools import wraps

import telethon
from telethon import hints
from telethon.tl.functions.channels import (
    EditAdminRequest,
    InviteToChannelRequest,
)
from telethon.tl.types import (
    ChatAdminRights,
)

from ..tl_cache import CustomTelegramClient
from ..types import ListLike

parser = telethon.utils.sanitize_parse_mode("html")
logger = logging.getLogger(__name__)


class BotPermission(StrEnum):
    """Bot permission enumeration"""

    BAN_USERS = "ban_users"
    INVITE_USERS = "invite_users"
    CHANGE_INFO = "change_info"
    ADMIN = "admin"


class ExecutionMode(StrEnum):
    """Execution mode enumeration"""

    SYNC = "sync"
    ASYNC = "async"
    THREAD = "thread"


def rand(size: int, /) -> str:
    """
    Return random string of len `size`

    :param size: Length of string
    :return: Random string
    """
    if size <= 0:
        return ""

    match size:
        case 1:
            return random.choice("abcdefghijklmnopqrstuvwxyz1234567890")
        case 2:
            return random.choice("abcdefghijklmnopqrstuvwxyz1234567890") * 2
        case _:
            return "".join(
                random.choice("abcdefghijklmnopqrstuvwxyz1234567890")
                for _ in range(size)
            )


async def invite_inline_bot(
    client: CustomTelegramClient,
    peer: hints.EntityLike,
    permissions: BotPermission = BotPermission.ADMIN,
) -> None:
    """
    Invites inline bot to a chat with specified permissions

    :param client: Client to use
    :param peer: Peer to invite bot to
    :param permissions: Permission level to grant
    :return: None
    :raise RuntimeError: If error occurred while inviting bot
    """
    try:
        await client(InviteToChannelRequest(peer, [client.loader.inline.bot_username]))
    except Exception as e:
        raise RuntimeError(
            "Can't invite inline bot to old asset chat, which is required by module"
        ) from e

    with contextlib.suppress(Exception):
        match permissions:
            case BotPermission.ADMIN:
                await client(
                    EditAdminRequest(
                        channel=peer,
                        user_id=client.loader.inline.bot_username,
                        admin_rights=ChatAdminRights(
                            ban_users=True,
                            invite_users=True,
                            change_info=True,
                            post_messages=True,
                            edit_messages=True,
                            delete_messages=True,
                        ),
                        rank="Pust",
                    )
                )
            case BotPermission.BAN_USERS:
                await client(
                    EditAdminRequest(
                        channel=peer,
                        user_id=client.loader.inline.bot_username,
                        admin_rights=ChatAdminRights(ban_users=True),
                        rank="Pust",
                    )
                )
            case BotPermission.INVITE_USERS:
                await client(
                    EditAdminRequest(
                        channel=peer,
                        user_id=client.loader.inline.bot_username,
                        admin_rights=ChatAdminRights(invite_users=True),
                        rank="Pust",
                    )
                )
            case _:
                await client(
                    EditAdminRequest(
                        channel=peer,
                        user_id=client.loader.inline.bot_username,
                        admin_rights=ChatAdminRights(ban_users=True),
                        rank="Pust",
                    )
                )


def run_sync(func, *args, **kwargs):
    """
    Run a non-async function in a new thread and return an awaitable
    :param func: Sync-only function to execute
    :return: Awaitable coroutine
    """
    return asyncio.get_event_loop().run_in_executor(
        None,
        functools.partial(func, *args, **kwargs),
    )


def run_async(loop: asyncio.AbstractEventLoop, coro: Awaitable) -> Any:
    """
    Run an async function as a non-async function, blocking till it's done
    :param loop: Event loop to run the coroutine in
    :param coro: Coroutine to run
    :return: Result of the coroutine
    """
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


def merge(a: dict, b: dict, /) -> dict:
    """
    Merge with replace dictionary a to dictionary b
    :param a: Dictionary to merge
    :param b: Dictionary to merge to
    :return: Merged dictionary
    """
    for key in a:
        if key in b:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                b[key] = merge(a[key], b[key])
            elif isinstance(a[key], list) and isinstance(b[key], list):
                b[key] = list(set(b[key] + a[key]))
            else:
                b[key] = a[key]

        b[key] = a[key]

    return b


def chunks(_list: "ListLike", n: int, /) -> list[list[object]]:
    """
    Split provided `_list` into chunks of `n`

    :param _list: List to split
    :param n: Chunk size
    :return: List of chunks
    """
    return [_list[i : i + n] for i in range(0, len(_list), n)]


def atexit(
    func: "Callable",
    use_signal: int | None = None,
    *args,
    **kwargs,
) -> None:
    """
    Calls function on exit

    :param func: Function to call
    :param use_signal: If passed, `signal` will be used instead of `atexit`
    :param args: Arguments to pass to function
    :param kwargs: Keyword arguments to pass to function
    :return: None
    """
    if use_signal:
        signal.signal(use_signal, lambda *_: func(*args, **kwargs))
        return

    _atexit.register(functools.partial(func, *args, **kwargs))


def _copy_tl(o, **kwargs):
    d = o.to_dict()
    del d["_"]
    d.update(kwargs)
    return o.__class__(**d)


class TaskStatus(StrEnum):
    """Task status enumeration"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(IntEnum):
    """Task priority enumeration"""

    LOWEST = 0
    LOW = 25
    NORMAL = 50
    HIGH = 75
    HIGHEST = 100
    CRITICAL = 255


@dataclass
class TaskInfo:
    """Enhanced task information with Python 3.12+ features"""

    id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    result: Optional[Any] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def start(self) -> None:
        """Mark task as started"""
        self.status = TaskStatus.RUNNING
        self.started_at = time.time()

    def complete(self, result: Any = None) -> None:
        """Mark task as completed"""
        self.status = TaskStatus.COMPLETED
        self.completed_at = time.time()
        self.result = result

    def fail(self, error: str) -> None:
        """Mark task as failed"""
        self.status = TaskStatus.FAILED
        self.completed_at = time.time()
        self.error = error

    def cancel(self) -> None:
        """Mark task as cancelled"""
        self.status = TaskStatus.CANCELLED
        self.completed_at = time.time()

    def get_duration(self) -> Optional[float]:
        """Get task duration in seconds"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "priority": self.priority.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "result": self.result,
            "metadata": self.metadata,
        }


class TaskManager:
    """Enhanced task manager with modern Python 3.12+ features"""

    def __init__(self) -> None:
        self._tasks: Dict[str, TaskInfo] = {}
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "cancelled_tasks": 0,
            "running_tasks": 0,
        }

    def create_task(
        self,
        name: str,
        coro: Awaitable[Any],
        priority: TaskPriority = TaskPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create and schedule a new task"""
        task_id = f"task_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"

        task_info = TaskInfo(
            id=task_id,
            name=name,
            priority=priority,
            metadata=metadata or {},
        )

        self._tasks[task_id] = task_info
        self._stats["total_tasks"] += 1

        async def task_wrapper():
            task_info.start()
            self._stats["running_tasks"] += 1

            try:
                result = await coro
                task_info.complete(result)
                self._stats["completed_tasks"] += 1
            except Exception as e:
                task_info.fail(str(e))
                self._stats["failed_tasks"] += 1
                logger.error(f"Task {task_id} failed: {e}")
            finally:
                self._stats["running_tasks"] -= 1
                if task_id in self._running_tasks:
                    del self._running_tasks[task_id]

        task = asyncio.create_task(task_wrapper())
        self._running_tasks[task_id] = task

        return task_id

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """Get task information"""
        return self._tasks.get(task_id)

    def get_tasks(self, status: Optional[TaskStatus] = None) -> List[TaskInfo]:
        """Get tasks by status"""
        tasks = list(self._tasks.values())
        if status:
            tasks = [task for task in tasks if task.status == status]
        return tasks

    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task"""
        if task_id in self._running_tasks:
            task = self._running_tasks[task_id]
            task.cancel()

            task_info = self._tasks.get(task_id)
            if task_info:
                task_info.cancel()
                self._stats["cancelled_tasks"] += 1

            return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get task manager statistics"""
        return self._stats.copy()

    def cleanup_completed_tasks(self, max_age: float = 3600) -> int:
        """Clean up completed tasks older than max_age seconds"""
        cutoff = time.time() - max_age
        tasks_to_remove = []

        for task_id, task_info in self._tasks.items():
            if (
                task_info.status
                in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
                and task_info.completed_at
                and task_info.completed_at < cutoff
            ):
                tasks_to_remove.append(task_id)

        for task_id in tasks_to_remove:
            del self._tasks[task_id]

        return len(tasks_to_remove)


task_manager = TaskManager()


def async_task(
    name: Optional[str] = None,
    priority: TaskPriority = TaskPriority.NORMAL,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Decorator to run function as async task"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            task_name = name or func.__name__
            coro = func(*args, **kwargs)
            return task_manager.create_task(task_name, coro, priority, metadata)

        return wrapper

    return decorator


def retry_on_failure(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
):
    """Enhanced retry decorator with exponential backoff"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            current_delay = delay

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt == max_attempts - 1:
                        break

                    logger.warning(
                        f"Attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying in {current_delay}s..."
                    )
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff_factor

            raise last_exception

        return wrapper

    return decorator


def timeout_handler(
    timeout: float,
    fallback: Optional[Any] = None,
    timeout_exception: type[Exception] = asyncio.TimeoutError,
):
    """Enhanced timeout decorator"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            except timeout_exception:
                logger.warning(f"Timeout in {func.__name__} after {timeout}s")
                if fallback is not None:
                    return fallback
                raise

        return wrapper

    return decorator


def performance_monitor(
    log_slow_calls: bool = True,
    slow_threshold: float = 1.0,
):
    """Enhanced performance monitoring decorator"""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time

                if log_slow_calls and duration > slow_threshold:
                    logger.warning(
                        f"Slow call to {func.__name__}: {duration:.2f}s (threshold: {slow_threshold}s)"
                    )
                elif logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Call to {func.__name__}: {duration:.2f}s")

        return wrapper

    return decorator


def safe_execute(
    func: Callable,
    *args,
    default: Any = None,
    log_errors: bool = True,
    **kwargs,
) -> Any:
    """Safely execute function with error handling"""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        if log_errors:
            logger.error(f"Error executing {func.__name__}: {e}")
        return default


def format_bytes(bytes_count: int) -> str:
    """Format bytes count in human readable format"""
    match bytes_count:
        case count if count < 1024:
            return f"{count} B"
        case count if count < 1024 * 1024:
            return f"{count / 1024:.1f} KB"
        case count if count < 1024 * 1024 * 1024:
            return f"{count / (1024 * 1024):.1f} MB"
        case count if count < 1024 * 1024 * 1024 * 1024:
            return f"{count / (1024 * 1024 * 1024):.1f} GB"
        case _:
            return f"{bytes_count / (1024 * 1024 * 1024 * 1024):.1f} TB"


def format_duration(seconds: float) -> str:
    """Format duration in human readable format"""
    match seconds:
        case s if s < 60:
            return f"{s:.1f}s"
        case s if s < 3600:
            minutes = int(s // 60)
            remaining = s % 60
            return f"{minutes}m {remaining:.1f}s"
        case s if s < 86400:
            hours = int(s // 3600)
            remaining = s % 3600
            minutes = int(remaining // 60)
            return f"{hours}h {minutes}m"
        case s:
            days = int(s // 86400)
            remaining = s % 86400
            hours = int(remaining // 3600)
            return f"{days}d {hours}h"


def generate_id(prefix: str = "id", length: int = 8) -> str:
    """Generate random ID with prefix"""
    import string

    chars = string.ascii_lowercase + string.digits
    random_part = "".join(random.choice(chars) for _ in range(length))
    return f"{prefix}_{random_part}"


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for safe file system usage"""
    import re

    filename = re.sub(r'[<>:"/\\|?*]', "_", filename)

    filename = re.sub(r"[\x00-\x1f\x7f]", "", filename)

    if len(filename) > 255:
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        max_name_length = 255 - len(ext) - 1
        filename = name[:max_name_length] + ("." + ext if ext else "")
    return filename.strip()
