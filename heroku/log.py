"""Main logging module for Heroku Userbot"""

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
# This file is a part of Heroku Userbot.
#
# Copyright (C) 2026 CodWiz

from __future__ import annotations

import asyncio
import contextlib
import inspect
import io
import linecache
import logging
import re
import sys
import traceback
from collections.abc import Callable, Iterable
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING, Any, Optional, Union

import herokutl
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from herokutl.errors import PersistentTimestampOutdatedError
from herokutl.errors.rpcbaseerrors import RPCError, ServerError

from . import utils
from .types import BotInlineCall, CoreOverwriteError

if TYPE_CHECKING:
    from .tl_cache import CustomTelegramClient
    from .types import Module

INTERNET_ERRORS = (
    TelegramNetworkError,
    asyncio.exceptions.TimeoutError,
    ServerError,
    PersistentTimestampOutdatedError,
)


_original_getlines = linecache.getlines


def _patched_getlines(filename: str, module_globals=None) -> list[str]:
    """
    Get the lines for a Python source file from the cache.
    
    Modified version of original `linecache.getlines`, which returns the
    source code of Heroku modules properly. This is needed for
    interactive line debugger in werkzeug web debugger.
    """
    try:
        if filename.startswith("<") and filename.endswith(">"):
            module_name = filename[1:-1].split(maxsplit=1)[-1]
            if (
                module_name.startswith("heroku.modules")
                and module_name in sys.modules
            ):
                module = sys.modules[module_name]
                if hasattr(module, "__loader__") and hasattr(
                    module.__loader__, "get_source"
                ):
                    source = module.__loader__.get_source()
                    return [f"{line}\n" for line in source.splitlines()]
    except Exception as e:
        logging.debug("Can't get lines for %s: %s", filename, e, exc_info=True)

    return _original_getlines(filename, module_globals)


linecache.getlines = _patched_getlines


def override_text(exception: Exception) -> Optional[str]:
    """Returns error-specific description if available, else `None`"""
    if isinstance(exception, (TelegramNetworkError, asyncio.exceptions.TimeoutError)):
        return "✈️ <b>You have problems with internet connection on your server.</b>"

    if isinstance(exception, PersistentTimestampOutdatedError):
        return "✈️ <b>Telegram has problems with their datacenters.</b>"

    if isinstance(exception, CoreOverwriteError):
        return f"⚠️ {exception}"

    if isinstance(exception, ServerError):
        return (
            "📡 <b>Telegram servers are currently experiencing issues. "
            "Please try again later.</b>"
        )

    if isinstance(exception, RPCError) and "TRANSLATION_TIMEOUT" in str(exception):
        return (
            "🕓 <b>Telegram translation service timed out. "
            "Please try again later.</b>"
        )

    if isinstance(exception, ModuleNotFoundError):
        exc_text = "".join(traceback.format_exception_only(type(exception), exception))
        return f"📦 {exc_text.split(':', 1)[1].strip()}"

    if isinstance(exception, TelegramRetryAfter):
        return (
            f"✋ <b>Bot is hitting limits on {type(exception.method).__name__!r} "
            f"method and got {exception.retry_after} seconds floodwait</b>"
        )

    return None


class HerokuException:
    """Container for exception information with rich formatting capabilities"""

    def __init__(
        self,
        message: str,
        full_stack: str,
        sysinfo: Optional[tuple[object, Exception, traceback.TracebackException]] = None,
    ):
        self.message = message
        self.full_stack = full_stack
        self.sysinfo = sysinfo
        self.debug_url: Optional[str] = None

    @classmethod
    def from_exc_info(
        cls,
        exc_type: type[BaseException],
        exc_value: BaseException,
        tb: traceback.TracebackException,
        stack: Optional[list[inspect.FrameInfo]] = None,
        comment: Optional[Any] = None,
    ) -> HerokuException:
        """Create HerokuException from exception info"""
       
        full_traceback = traceback.format_exc().replace(
            "Traceback (most recent call last):\n",
            "",
        )

     
        line_regex = re.compile(r'  File "(.*?)", line ([0-9]+), in (.+)')

        def format_line(line: str) -> str:
            """Format a traceback line for HTML output"""
            match = line_regex.search(line)
            if not match:
                return f"<code>{utils.escape_html(line)}</code>"
            
            filename_, lineno_, name_ = match.groups()
            return (
                f"👉 <code>{utils.escape_html(filename_)}:{lineno_}</code> "
                f"<b>in</b> <code>{utils.escape_html(name_)}</code>"
            )

       
        formatted_traceback = "\n".join(
            format_line(line) for line in full_traceback.splitlines()
        )

       
        last_frame = next(
            (
                line_regex.search(line).groups()
                for line in reversed(full_traceback.splitlines())
                if line_regex.search(line)
            ),
            (None, None, None),
        )

        filename, lineno, name = last_frame
        caller = utils.find_caller(stack or inspect.stack())

       
        if custom_message := override_text(exc_value):
            message = custom_message
        else:
           
            caller_info = ""
            if caller and hasattr(caller, "__self__") and hasattr(caller, "__name__"):
                caller_info = (
                    "🔮 <b>Cause: method </b>"
                    f"<code>{utils.escape_html(caller.__name__)}</code>"
                    "<b> of </b>"
                    f"<code>{utils.escape_html(caller.__self__.__class__.__name__)}</code>\n\n"
                )

           
            error_text = "".join(
                traceback.format_exception_only(exc_type, exc_value)
            ).strip()

          
            comment_text = ""
            if comment:
                comment_text = (
                    "\n💭 <b>Message:</b> "
                    f"<code>{utils.escape_html(str(comment))}</code>"
                )

            message = (
                f"{caller_info}"
                f"<b>🎯 Source:</b> <code>{utils.escape_html(filename)}:{lineno}</code> "
                f"<b>in</b> <code>{utils.escape_html(name)}</code>\n"
                f"<b>❓ Error:</b> <code>{utils.escape_html(error_text)}</code>"
                f"{comment_text}"
            )

        return cls(
            message=message,
            full_stack=formatted_traceback,
            sysinfo=(exc_type, exc_value, tb),
        )


class TelegramLogsHandler(logging.Handler):
    """
    Logging handler that buffers logs and sends them to Telegram.
    
    Maintains two buffers:
    - One for dispatched messages
    - One for unused messages
    
    When total capacity is exceeded, trims handled buffer first.
    """

    _TG_MESSAGE_LIMIT = 4096
    _MAX_QUEUE_SIZE = 5
    _SENDER_INTERVAL = 3

    def __init__(self, targets: Iterable[logging.Handler], capacity: int):
        super().__init__(0)
        self.buffer: list[logging.LogRecord] = []
        self.handled_buffer: list[logging.LogRecord] = []
        self._queue: dict[int, list[str]] = {}
        self._modules: dict[int, Module] = {}
        self._tg_buffer: list[tuple[Union[str, HerokuException], Optional[int]]] = []
        self.force_send_all = False
        self.tg_level = 20
        self.ignore_common = False
        self.targets = list(targets)
        self.capacity = capacity
        self._send_lock = asyncio.Lock()
        self._sender_task: Optional[asyncio.Task] = None

    def install_tg_log(self, mod: Module) -> None:
        """Install Telegram logging for a module"""
        if self._sender_task:
            self._sender_task.cancel()

        self._modules[mod.tg_id] = mod
        self._sender_task = asyncio.create_task(self._queue_poller())

    async def _queue_poller(self) -> None:
        """Poll queue and send logs periodically"""
        while True:
            try:
                await self._sender()
            except Exception as e:
                logging.error("Error in queue poller: %s", e, exc_info=True)
            await asyncio.sleep(self._SENDER_INTERVAL)

    def dump(self) -> list[logging.LogRecord]:
        """Return all logging entries"""
        return self.handled_buffer + self.buffer

    def dumps(
        self,
        level: int = 0,
        client_id: Optional[int] = None,
    ) -> list[str]:
        """Return all entries of minimum level as list of strings"""
        result = []
        for record in self.buffer + self.handled_buffer:
            if record.levelno < level:
                continue
            if record.heroku_caller and client_id != record.heroku_caller:
                continue
           
            if self.targets:
                result.append(self.targets[0].format(record))
        
        return result

    async def _show_full_trace(
        self,
        call: BotInlineCall,
        bot: "aiogram.Bot",  # noqa: F821
        exception: HerokuException,
    ) -> None:
        """Show full traceback in Telegram messages"""
        try:
           
            import herokutl.extensions.html
            
            chunks_text = (
                f"{exception.message}\n\n"
                "<b>🪐 Full traceback:</b>\n"
                f"{exception.full_stack}"
            )
            
            parsed_chunks = herokutl.extensions.html.parse(chunks_text)
            chunks = list(utils.smart_split(*parsed_chunks, self._TG_MESSAGE_LIMIT))

            if chunks:
                await call.edit(chunks[0])

                for chunk in chunks[1:]:
                    await bot.send_message(
                        chat_id=call.chat_id,
                        text=chunk,
                        disable_web_page_preview=True,
                    )
        except Exception as e:
            logging.error("Failed to show full trace: %s", e, exc_info=True)

    def get_logid_by_client(self, client_id: int) -> int:
        """Get log chat ID for a client"""
        return self._modules[client_id].logchat

    async def _sender(self) -> None:
        """Send buffered logs to Telegram"""
        async with self._send_lock:
            if not self._modules:
                return

            await self._prepare_and_send_logs()

    async def _prepare_and_send_logs(self) -> None:
        """Prepare logs for sending and dispatch them"""
        
        self._queue = {}
        for client_id, module in self._modules.items():
            client_logs = []
            for item in self._tg_buffer:
                if isinstance(item[0], str) and (
                    not item[1] or item[1] == client_id or self.force_send_all
                ):
                    client_logs.append(item[0])

            if client_logs:
                log_text = utils.escape_html("".join(client_logs))
                self._queue[client_id] = list(utils.chunks(log_text, self._TG_MESSAGE_LIMIT))

     
        exception_tasks = []
        for client_id, module in self._modules.items():
            for item in self._tg_buffer:
                if isinstance(item[0], HerokuException) and (
                    not item[1] or item[1] == client_id or self.force_send_all
                ):
                    
                    exception = item[0]
                    if (
                        exception.sysinfo
                        and isinstance(exception.sysinfo[1], INTERNET_ERRORS)
                    ):
                        tester_module = module.lookup("tester")
                        if tester_module and getattr(
                            tester_module.config, "disable_internet_warn", False
                        ):
                            continue

                   
                    task = self._send_exception(module, exception)
                    exception_tasks.append(task)

       
        self._tg_buffer.clear()

        
        for task in exception_tasks:
            asyncio.create_task(task)

       
        for client_id, chunks in self._queue.items():
            if client_id not in self._modules:
                continue

            module = self._modules[client_id]
            await self._send_text_logs(module, chunks)

    async def _send_exception(
        self,
        module: Module,
        exception: HerokuException,
    ) -> None:
        """Send exception to Telegram"""
        try:
            await module.inline.bot.send_message(
                module.logchat,
                exception.message,
                reply_markup=module.inline.generate_markup(
                    [
                        {
                            "text": "🪐 Full traceback",
                            "callback": self._show_full_trace,
                            "args": (module.inline.bot, exception),
                            "disable_security": True,
                        },
                    ]
                ),
                disable_web_page_preview=True,
            )
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
            await self._send_exception(module, exception)
        except Exception as e:
            logging.error("Failed to send exception: %s", e, exc_info=True)

    async def _send_text_logs(self, module: Module, chunks: list[str]) -> None:
        """Send text logs to Telegram"""
        if len(chunks) > self._MAX_QUEUE_SIZE:
            
            log_content = "".join(chunks)
            log_file = io.BytesIO(log_content.encode("utf-8"))
            log_file.name = "heroku-logs.txt"
            log_file.seek(0)

            try:
                await module.inline.bot.send_document(
                    module.logchat,
                    log_file,
                    caption="<b>🧳 Logs are too big to be sent as separate messages</b>",
                )
            except Exception as e:
                logging.error("Failed to send log file: %s", e, exc_info=True)
            return

      
        for chunk in chunks:
            if not chunk.strip():
                continue

            try:
                await module.inline.bot.send_message(
                    module.logchat,
                    f"<code>{chunk}</code>",
                    disable_notification=True,
                    disable_web_page_preview=True,
                )
            except Exception as e:
                logging.error("Failed to send log chunk: %s", e, exc_info=True)

    def emit(self, record: logging.LogRecord) -> None:
        """Process a log record"""
        try:
            
            caller_id = None
            for frame_info in inspect.stack():
                frame_locals = getattr(frame_info.frame, "f_locals", {})
                candidate = frame_locals.get("_heroku_client_id_logging_tag")
                if isinstance(candidate, int):
                    caller_id = candidate
                    break

            record.heroku_caller = caller_id
        except Exception as e:
            logging.debug("Failed to determine caller: %s", e)
            record.heroku_caller = None

       
        if record.levelno >= self.tg_level:
            self._process_telegram_log(record, caller_id)

        
        self._manage_buffers(record)

   
        if record.levelno >= self.level:
            self._dispatch_to_targets(record)

    def _process_telegram_log(self, record: logging.LogRecord, caller_id: Optional[int]) -> None:
        """Process log record for Telegram output"""
        if record.exc_info:
            try:
                comment = record.msg % record.args if record.args else str(record.msg)
            except Exception:
                comment = f"{record.msg} {record.args}"

            exception = HerokuException.from_exc_info(
                *record.exc_info,
                stack=record.__dict__.get("stack"),
                comment=comment,
            )

            # Filter common errors if ignore_common is True
            if not self.ignore_common or all(
                field not in exception.message
                for field in [
                    "InputPeerEmpty() does not have any entity type",
                    "https://docs.telethon.dev/en/stable/concepts/entities.html",
                ]
            ):
                self._tg_buffer.append((exception, caller_id))
        else:
            formatted = _TG_FORMATTER.format(record)
            self._tg_buffer.append((formatted, caller_id))

    def _manage_buffers(self, record: logging.LogRecord) -> None:
        """Manage log buffers with capacity limits"""
        total_length = len(self.buffer) + len(self.handled_buffer)
        if total_length >= self.capacity:
            if self.handled_buffer:
                self.handled_buffer.pop(0)
            else:
                self.buffer.pop(0)

        self.buffer.append(record)

    def _dispatch_to_targets(self, record: logging.LogRecord) -> None:
        """Dispatch log record to all targets"""
        self.acquire()
        try:
            for target in self.targets:
                if record.levelno >= target.level:
                    target.handle(record)

           
            self.handled_buffer.extend(self.buffer)
            self.handled_buffer = self.handled_buffer[-(self.capacity - len(self.buffer)):]
            self.buffer.clear()
        finally:
            self.release()

    def close(self) -> None:
        """Clean up handler resources"""
        if self._sender_task:
            self._sender_task.cancel()
        super().close()


class NoFetchUpdatesFilter(logging.Filter):
    """Filter out common aiogram noise messages"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return (
            "Failed to fetch updates" not in message
            and "Sleep" not in message
        )



_MAIN_FORMATTER = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_TG_FORMATTER = logging.Formatter(
    fmt="[%(levelname)s] %(name)s: %(message)s\n",
    datefmt=None,
)


_ROTATING_HANDLER = RotatingFileHandler(
    filename="heroku.log",
    mode="a",
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=1,
    encoding="utf-8",
    delay=False,
)
_ROTATING_HANDLER.setFormatter(_MAIN_FORMATTER)


def init() -> None:
    """Initialize logging configuration"""
    
    aiogram_logger = logging.getLogger("aiogram.dispatcher")
    aiogram_logger.addFilter(NoFetchUpdatesFilter())
    
   
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(_MAIN_FORMATTER)
    
    
    root_logger = logging.getLogger()

    root_logger.handlers.clear()
    
   
    main_handler = TelegramLogsHandler((stream_handler, _ROTATING_HANDLER), 7000)
    root_logger.addHandler(main_handler)
    root_logger.setLevel(logging.NOTSET)
    
   
    logging.getLogger("herokutl").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.WARNING)

    logging.captureWarnings(True)