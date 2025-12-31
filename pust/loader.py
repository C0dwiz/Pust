"""Registers modules"""

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
import builtins
import contextlib
import copy
import importlib
import importlib.machinery
import importlib.util
import inspect
import logging
import os
import re
import sys
import typing
from functools import wraps
from pathlib import Path
from types import FunctionType
from uuid import uuid4

from Pusttl.tl.tlobject import TLObject

from . import security, utils, validators
from .database import Database
from .inline.core import InlineManager
from .translations import Strings, Translator
from .types import (
    Command,
    ConfigValue,
    CoreOverwriteError,
    CoreUnloadError,
    InlineMessage,
    JSONSerializable,
    Library,
    LibraryConfig,
    LoadError,
    Module,
    ModuleConfig,
    SelfSuspend,
    SelfUnload,
    StopLoop,
    StringLoader,
    get_callback_handlers,
    get_commands,
    get_inline_handlers,
)

if typing.TYPE_CHECKING:
    from .tl_cache import CustomTelegramClient

__all__ = [
    "Modules",
    "InfiniteLoop",
    "Command",
    "CoreOverwriteError",
    "CoreUnloadError",
    "InlineMessage",
    "JSONSerializable",
    "Library",
    "LibraryConfig",
    "LoadError",
    "Module",
    "SelfSuspend",
    "SelfUnload",
    "StopLoop",
    "StringLoader",
    "get_commands",
    "get_inline_handlers",
    "get_callback_handlers",
    "validators",
    "Database",
    "InlineManager",
    "Strings",
    "Translator",
    "ConfigValue",
    "ModuleConfig",
    "owner",
    "group_owner",
    "group_admin_add_admins",
    "group_admin_change_info",
    "group_admin_ban_users",
    "group_admin_delete_messages",
    "group_admin_pin_messages",
    "group_admin_invite_users",
    "group_admin",
    "group_member",
    "pm",
    "unrestricted",
    "inline_everyone",
    "loop",
]

logger = logging.getLogger(__name__)

# Security decorators
owner = security.owner

# Deprecated decorators
sudo = security.sudo
support = security.support
# /deprecated

group_owner = security.group_owner
group_admin_add_admins = security.group_admin_add_admins
group_admin_change_info = security.group_admin_change_info
group_admin_ban_users = security.group_admin_ban_users
group_admin_delete_messages = security.group_admin_delete_messages
group_admin_pin_messages = security.group_admin_pin_messages
group_admin_invite_users = security.group_admin_invite_users
group_admin = security.group_admin
group_member = security.group_member
pm = security.pm
unrestricted = security.unrestricted
inline_everyone = security.inline_everyone

# Constants
MODULES_NAME = "modules"
BASE_DIR = (
    "/data"
    if "DOCKER" in os.environ
    else os.path.normpath(os.path.join(utils.get_base_dir(), ".."))
)
LOADED_MODULES_DIR = os.path.join(BASE_DIR, "loaded_modules")
LOADED_MODULES_PATH = Path(LOADED_MODULES_DIR)
LOADED_MODULES_PATH.mkdir(parents=True, exist_ok=True)

VALID_PIP_PACKAGES = re.compile(
    r"^\s*# ?requires:(?: ?)((?:{url} )*(?:{url}))\s*$".format(
        url=r"[-[\]_.~:/?#@!$&'()*+,;%<=>a-zA-Z0-9]+"
    ),
    re.MULTILINE,
)

USER_INSTALL = "PIP_TARGET" not in os.environ and "VIRTUAL_ENV" not in os.environ


async def _stop_placeholder() -> bool:
    """Placeholder function for stopping loops."""
    return True


class Placeholder:
    """Placeholder class."""


class _ImportPatcher:
    """Patches built-in import to handle library renames."""
    
    def __init__(self):
        self._original_import = builtins.__import__
        self._mappings = [
            ("telethon", "Pusttl"),
            ("hikkatl", "Pusttl"),
            ("hikka", "Pust"),
        ]
        
    def _patch(self, name: str, *args, **kwargs) -> typing.Any:
        """Patch import to redirect old library names to new ones."""
        for old_prefix, new_prefix in self._mappings:
            if name.startswith(old_prefix):
                new_name = new_prefix + name[len(old_prefix):]
                return self._original_import(new_name, *args, **kwargs)
        
        return self._original_import(name, *args, **kwargs)
    
    def install(self):
        """Install the import patcher."""
        builtins.__import__ = self._patch
    
    def uninstall(self):
        """Uninstall the import patcher."""
        builtins.__import__ = self._original_import


_import_patcher = _ImportPatcher()
_import_patcher.install()


class InfiniteLoop:
    """Infinite loop for running periodic tasks in modules.
    
    Attributes:
        status: Boolean indicating whether the loop is running.
        module_instance: Reference to the module instance (set later).
    """
    
    def __init__(
        self,
        func: FunctionType,
        interval: int,
        autostart: bool,
        wait_before: bool,
        stop_clause: typing.Optional[str],
    ):
        self.func = func
        self.interval = interval
        self.autostart = autostart
        self._wait_before = wait_before
        self._stop_clause = stop_clause
        self.module_instance: typing.Optional[Module] = None
        self._task: typing.Optional[asyncio.Task] = None
        self.status = False
        self._stop_event: typing.Optional[asyncio.Event] = None
    
    def _set_logging_tag(self) -> None:
        """Set logging tag for debugging."""
        if self.module_instance and hasattr(self.module_instance.allmodules, 'client'):
            _Pust_client_id_logging_tag = copy.copy(
                self.module_instance.allmodules.client.tg_id
            )  # noqa: F841
    
    def stop(self, *args, **kwargs) -> asyncio.Future:
        """Stop the infinite loop.
        
        Returns:
            Future that completes when the loop has stopped.
        """
        self._set_logging_tag()
        
        if self._task and not self._task.done():
            logger.debug("Stopping loop for method %s", self.func.__name__)
            self.status = False
            self._stop_event = asyncio.Event()
            self._task.cancel()
            return asyncio.ensure_future(self._stop_event.wait())
        
        logger.debug("Loop is not running")
        return asyncio.ensure_future(_stop_placeholder())
    
    def start(self, *args, **kwargs) -> None:
        """Start the infinite loop."""
        self._set_logging_tag()
        
        if not self._task or self._task.done():
            logger.debug("Starting loop for method %s", self.func.__name__)
            self._task = asyncio.ensure_future(
                self._actual_loop(*args, **kwargs)
            )
        else:
            logger.debug("Attempted to start already running loop")
    
    async def _actual_loop(self, *args, **kwargs) -> None:
        """Actual loop implementation."""
        # Wait for loader to set module_instance
        while not self.module_instance:
            await asyncio.sleep(0.01)
        
        self._set_logging_tag()
        
        # Set stop clause if specified
        if self._stop_clause:
            self.module_instance.set(self._stop_clause, True)
        
        self.status = True
        
        while self.status:
            if self._wait_before:
                await asyncio.sleep(self.interval)
            
            # Check stop clause
            if self._stop_clause and not self.module_instance.get(self._stop_clause, False):
                break
            
            try:
                await self.func(self.module_instance, *args, **kwargs)
            except StopLoop:
                break
            except Exception:
                logger.exception("Error running loop in %s", self.func.__name__)
            
            if not self._wait_before:
                await asyncio.sleep(self.interval)
        
        # Signal stop
        if self._stop_event:
            self._stop_event.set()
        
        self.status = False
    
    def __del__(self):
        """Cleanup on deletion."""
        self.stop()


def loop(
    interval: int = 5,
    autostart: typing.Optional[bool] = False,
    wait_before: typing.Optional[bool] = False,
    stop_clause: typing.Optional[str] = None,
) -> typing.Callable:
    """Decorator to create an infinite loop from a class method.
    
    Args:
        interval: Delay between loop iterations in seconds.
        autostart: Start loop automatically when module is loaded.
        wait_before: Insert delay before iteration rather than after.
        stop_clause: Database key that controls loop execution.
                     Loop runs while this key is True.
    
    Returns:
        Decorated function wrapped in an InfiniteLoop instance.
    """
    def decorator(func: FunctionType) -> InfiniteLoop:
        return InfiniteLoop(func, interval, autostart, wait_before, stop_clause)
    
    return decorator


def translatable_docstring(cls: typing.Type) -> typing.Type:
    """Decorator that makes triple-quote docstrings translatable.
    
    Args:
        cls: Module class to decorate.
    
    Returns:
        Decorated class with translatable docstrings.
    """
    
    @wraps(cls.config_complete)
    def config_complete(self, *args, **kwargs) -> bool:
        """Process docstring decorators and set up translations."""
        
        def _process_docstrings(mark: str, obj: str, func: typing.Callable) -> None:
            """Process docstring decorators for a function."""
            for attr in dir(func):
                if (attr.endswith("_doc") and len(attr) == 6 and 
                    isinstance(getattr(func, attr), str)):
                    
                    var_name = f"strings_{attr.split('_')[0]}"
                    if not hasattr(self, var_name):
                        setattr(self, var_name, {})
                    
                    strings_dict = getattr(self, var_name)
                    strings_dict.setdefault(f"{mark}{obj}", getattr(func, attr))
        
        # Process command docstrings
        for command_name, command_func in get_commands(cls).items():
            _process_docstrings("_cmd_doc_", command_name, command_func)
            try:
                command_func.__doc__ = self.strings[f"_cmd_doc_{command_name}"]
            except (AttributeError, KeyError):
                pass
        
        # Process inline handler docstrings
        for handler_name, handler_func in get_inline_handlers(cls).items():
            _process_docstrings("_ihandle_doc_", handler_name, handler_func)
            try:
                handler_func.__doc__ = self.strings[f"_ihandle_doc_{handler_name}"]
            except (AttributeError, KeyError):
                pass
        
        # Set class docstring
        self.__doc__ = self.strings.get("_cls_doc", "")
        
        # Call original config_complete if not reloading dynamic translations
        if not kwargs.pop("reload_dynamic_translate", None):
            return config_complete._original(self, *args, **kwargs)
        
        return True
    
    # Store original method and replace it
    config_complete._original = cls.config_complete
    cls.config_complete = config_complete
    
    # Store original docstrings
    cls.strings = getattr(cls, "strings", {})
    
    for command_name, command_func in get_commands(cls).items():
        cls.strings[f"_cmd_doc_{command_name}"] = inspect.getdoc(command_func) or ""
    
    for handler_name, handler_func in get_inline_handlers(cls).items():
        cls.strings[f"_ihandle_doc_{handler_name}"] = inspect.getdoc(handler_func) or ""
    
    cls.strings["_cls_doc"] = inspect.getdoc(cls) or ""
    
    return cls


tds = translatable_docstring  # Short alias for modules


def ratelimit(func: Command) -> Command:
    """Decorator that enforces stricter ratelimiting for a command.
    
    Args:
        func: Command function to decorate.
    
    Returns:
        Decorated command with ratelimit flag.
    """
    func.ratelimit = True
    return func


def tag(*tags: str, **kwarg_tags: typing.Any) -> typing.Callable:
    """Tag function (especially watchers) with specific tags.
    
    Available tags:
        • `no_commands` - Ignore all userbot commands
        • `only_commands` - Capture only userbot commands
        • `out` - Capture only outgoing events
        • `in` - Capture only incoming events
        • `only_messages` - Capture only messages (not join events)
        • `editable` - Capture only editable messages
        • `no_media` - Capture only messages without media
        • `only_media` - Capture only messages with media
        • `only_photos` - Capture only photos
        • `only_videos` - Capture only videos
        • `only_audios` - Capture only audios
        • `only_docs` - Capture only documents
        • `only_stickers` - Capture only stickers
        • `only_inline` - Capture only inline queries
        • `only_channels` - Capture only channel messages
        • `only_groups` - Capture only group messages
        • `only_pm` - Capture only private messages
        • `no_pm` - Exclude private messages
        • `no_channels` - Exclude channel messages
        • `no_groups` - Exclude group messages
        • `no_inline` - Exclude inline queries
        • `no_stickers` - Exclude stickers
        • `no_docs` - Exclude documents
        • `no_audios` - Exclude audios
        • `no_videos` - Exclude videos
        • `no_photos` - Exclude photos
        • `no_forwards` - Exclude forwarded messages
        • `no_reply` - Exclude replies
        • `no_mention` - Exclude mentions
        • `mention` - Capture only mentions
        • `only_reply` - Capture only replies
        • `only_forwards` - Capture only forwarded messages
        • `startswith` - Capture only messages starting with text
        • `endswith` - Capture only messages ending with text
        • `contains` - Capture only messages containing text
        • `regex` - Capture only messages matching regex
        • `filter` - Capture only messages passing function
        • `from_id` - Capture only messages from user
        • `chat_id` - Capture only messages from chat
        • `thumb_url` - For inline command handlers (shown in help)
        • `alias` - Single alias for command
        • `aliases` - Multiple aliases for command
    
    Args:
        *tags: Positional tag names.
        **kwarg_tags: Keyword tags with values.
    
    Returns:
        Decorator function.
    
    Example:
        @loader.tag("no_commands", "out")
        @loader.tag("only_messages", regex=r"^[.] ?Pust$")
    """
    def decorator(func: Command) -> Command:
        for tag_name in tags:
            setattr(func, tag_name, True)
        
        for tag_name, tag_value in kwarg_tags.items():
            setattr(func, tag_name, tag_value)
        
        return func
    
    return decorator


def _mark_method(
    mark: str, 
    *args: str, 
    **kwargs: typing.Any
) -> typing.Callable[..., Command]:
    """Mark a method with a specific attribute.
    
    Args:
        mark: Primary attribute name.
        *args: Additional attribute names (set to True).
        **kwargs: Additional attributes with values.
    
    Returns:
        Decorator function.
    """
    def decorator(func: Command) -> Command:
        setattr(func, mark, True)
        
        for arg in args:
            setattr(func, arg, True)
        
        for kwarg, value in kwargs.items():
            setattr(func, kwarg, value)
        
        return func
    
    return decorator


def command(*args: str, **kwargs: typing.Any) -> typing.Callable:
    """Decorator that marks a function as a userbot command.
    
    Returns:
        Decorator function.
    """
    return _mark_method("is_command", *args, **kwargs)


def debug_method(*args: str, **kwargs: typing.Any) -> typing.Callable:
    """Decorator that marks a function as an Internal Debug Method.
    
    Args:
        name: Name of the debug method.
    
    Returns:
        Decorator function.
    """
    return _mark_method("is_debug_method", *args, **kwargs)


def inline_handler(*args: str, **kwargs: typing.Any) -> typing.Callable:
    """Decorator that marks a function as an inline handler.
    
    Returns:
        Decorator function.
    """
    return _mark_method("is_inline_handler", *args, **kwargs)


def watcher(*args: str, **kwargs: typing.Any) -> typing.Callable:
    """Decorator that marks a function as a watcher.
    
    Returns:
        Decorator function.
    """
    return _mark_method("is_watcher", *args, **kwargs)


def callback_handler(*args: str, **kwargs: typing.Any) -> typing.Callable:
    """Decorator that marks a function as a callback handler.
    
    Returns:
        Decorator function.
    """
    return _mark_method("is_callback_handler", *args, **kwargs)


def raw_handler(*updates: TLObject) -> typing.Callable:
    """Decorator that marks a function as a raw Telethon event handler.
    
    Args:
        *updates: Update types to handle.
    
    Returns:
        Decorator function.
    
    Warning:
        Do not simulate this decorator dynamically!
        Feature won't work with dynamic method declaration.
    """
    def decorator(func: Command) -> Command:
        func.is_raw_handler = True
        func.updates = updates
        func.id = uuid4().hex
        return func
    
    return decorator


class Modules:
    """Manages all registered modules for the userbot.
    
    Attributes:
        commands: Dictionary of registered commands.
        inline_handlers: Dictionary of inline handlers.
        callback_handlers: Dictionary of callback handlers.
        aliases: Dictionary of command aliases.
        modules: List of loaded modules.
        libraries: List of loaded libraries.
        watchers: List of registered watchers.
        allclients: List of all connected clients.
        client: Current Telegram client.
        db: Database instance.
        translator: Translator instance.
        inline: Inline manager instance.
    """
    
    def __init__(
        self,
        client: "CustomTelegramClient",
        db: Database,
        allclients: typing.List["CustomTelegramClient"],
        translator: Translator,
    ):
        self._initial_registration = True
        self.commands: typing.Dict[str, Command] = {}
        self.inline_handlers: typing.Dict[str, typing.Callable] = {}
        self.callback_handlers: typing.Dict[str, typing.Callable] = {}
        self.aliases: typing.Dict[str, str] = {}
        self.modules: typing.List[Module] = []
        self.libraries: typing.List[Library] = []
        self.watchers: typing.List[typing.Callable] = []
        self._log_handlers: typing.List[typing.Callable] = []
        self._core_commands: typing.List[str] = []
        self.__approve: typing.List[str] = []
        
        self.allclients = allclients
        self.client = client
        self._db = db
        self.db = db
        self.translator = translator
        self.secure_boot = False
        
        self.inline = InlineManager(self.client, self._db, self)
        self.client.Pust_inline = self.inline
        
        # Start background tasks
        asyncio.ensure_future(self._junk_collector())
    
    async def _junk_collector(self) -> None:
        """Periodically reload handlers to prevent zombie handlers.
        
        Runs every 30 seconds to clean up stale references.
        """
        while True:
            await asyncio.sleep(30)
            
            commands = {}
            inline_handlers = {}
            callback_handlers = {}
            watchers = []
            
            for module in self.modules:
                commands.update(module.Pust_commands)
                inline_handlers.update(module.Pust_inline_handlers)
                callback_handlers.update(module.Pust_callback_handlers)
                watchers.extend(module.Pust_watchers.values())
            
            self.commands = commands
            self.inline_handlers = inline_handlers
            self.callback_handlers = callback_handlers
            self.watchers = watchers
            
            logger.debug(
                "Reloaded %s commands, %s inline handlers, %s callback handlers and %s watchers",
                len(self.commands),
                len(self.inline_handlers),
                len(self.callback_handlers),
                len(self.watchers),
            )
    
    async def register_all(
        self,
        mods: typing.Optional[typing.List[str]] = None,
        no_external: bool = False,
    ) -> typing.List[Module]:
        """Load all modules from the module directory.
        
        Args:
            mods: Specific modules to load (default: all).
            no_external: Skip external modules.
        
        Returns:
            List of loaded modules.
        """
        external_mods: typing.List[Path] = []
        
        if not mods:
            modules_dir = os.path.join(utils.get_base_dir(), MODULES_NAME)
            
            mods = [
                os.path.join(modules_dir, mod)
                for mod in os.listdir(modules_dir)
                if mod.endswith(".py") and not mod.startswith("_")
            ]
            
            self.secure_boot = self._db.get(__name__, "secure_boot", False)
            
            if not self.secure_boot:
                external_mods = [
                    (LOADED_MODULES_PATH / mod).resolve()
                    for mod in os.listdir(LOADED_MODULES_DIR)
                    if mod.endswith(f"{self.client.tg_id}.py") and not mod.startswith("_")
                ]
        
        loaded_modules = await self._register_modules(mods)
        
        if not no_external:
            loaded_modules += await self._register_modules(
                external_mods, 
                origin="<file>"
            )
        
        return loaded_modules
    
    async def _register_modules(
        self,
        modules: typing.List[typing.Union[str, Path]],
        origin: str = "<core>",
    ) -> typing.List[Module]:
        """Register multiple modules from a list of paths.
        
        Args:
            modules: List of module paths.
            origin: Origin identifier for modules.
        
        Returns:
            List of successfully loaded modules.
        """
        loaded: typing.List[Module] = []
        
        for mod_path in modules:
            try:
                mod_path_str = str(mod_path)
                mod_shortname = os.path.basename(mod_path_str).rsplit(".py", 1)[0]
                module_name = f"{__package__}.{MODULES_NAME}.{mod_shortname}"
                
                user_friendly_origin = (
                    "<core {}>" if origin == "<core>" else "<file {}>"
                ).format(module_name)
                
                logger.debug("Loading %s from filesystem", module_name)
                
                spec = importlib.machinery.ModuleSpec(
                    module_name,
                    StringLoader(
                        Path(mod_path_str).read_text(encoding='utf-8'),
                        user_friendly_origin,
                    ),
                    origin=user_friendly_origin,
                )
                
                module = await self.register_module(spec, module_name, origin)
                loaded.append(module)
                
            except Exception as e:
                logger.exception("Failed to load module %s: %s", mod_path, e)
        
        return loaded
    
    async def register_module(
        self,
        spec: importlib.machinery.ModuleSpec,
        module_name: str,
        origin: str = "<core>",
        save_fs: bool = False,
    ) -> Module:
        """Register a single module from an importlib spec.
        
        Args:
            spec: Module specification.
            module_name: Full module name.
            origin: Origin identifier.
            save_fs: Save to filesystem if from string.
        
        Returns:
            Loaded module instance.
        
        Raises:
            TypeError: If registered object is not a Module.
        """
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        
        # Find Module subclass
        module_instance = None
        
        for value in vars(module).values():
            if inspect.isclass(value) and issubclass(value, Module):
                module_instance = value()
                break
        
        # Try legacy register function
        if module_instance is None:
            if hasattr(module, "register"):
                module_instance = module.register(module_name)
            else:
                raise LoadError(f"No Module subclass found in {module_name}")
        
        if not isinstance(module_instance, Module):
            raise TypeError(f"Instance is not a Module, it is {type(module_instance)}")
        
        # Copy version if present
        if hasattr(module, "__version__"):
            module_instance.__version__ = module.__version__
        
        await self.complete_registration(module_instance)
        module_instance.__origin__ = origin
        
        # Save to filesystem if requested
        if save_fs and origin == "<string>":
            class_name = module_instance.__class__.__name__
            path = os.path.join(
                LOADED_MODULES_DIR,
                f"{class_name}_{self.client.tg_id}.py",
            )
            
            Path(path).write_text(spec.loader.data.decode())
            logger.debug("Saved class %s to path %s", class_name, path)
        
        return module_instance
    
    def add_aliases(self, aliases: typing.Dict[str, str]) -> None:
        """Add multiple aliases and apply them.
        
        Args:
            aliases: Dictionary mapping aliases to commands.
        """
        self.aliases.update(aliases)
        
        for alias, cmd in aliases.items():
            parts = cmd.split(maxsplit=1)
            self.add_alias(alias, parts[0], parts[1] if len(parts) > 1 else None)
    
    def register_raw_handlers(self, instance: Module) -> None:
        """Register raw event handlers for a module.
        
        Args:
            instance: Module instance.
        """
        for name, handler in utils.iter_attrs(instance):
            if getattr(handler, "is_raw_handler", False):
                self.client.dispatcher.raw_handlers.append(handler)
                logger.debug(
                    "Registered raw handler %s for %s. ID: %s",
                    name,
                    instance.__class__.__name__,
                    getattr(handler, "id", "unknown"),
                )
    
    @property
    def _remove_core_protection(self) -> bool:
        """Check if core module protection is disabled.
        
        Returns:
            True if core protection is disabled.
        """
        from . import main
        return self._db.get(main.__name__, "remove_core_protection", False)
    
    def register_commands(self, instance: Module) -> None:
        """Register commands from a module instance.
        
        Args:
            instance: Module instance.
        
        Raises:
            CoreOverwriteError: If trying to overwrite core command.
        """
        # Track core commands
        if instance.__origin__.startswith("<core"):
            self._core_commands.extend(
                cmd.lower() for cmd in instance.Pust_commands
            )
        
        # Register each command
        for command_name, command_func in instance.Pust_commands.items():
            command_name_lower = command_name.lower()
            
            # Check for core command overwrite
            if (not self._remove_core_protection and 
                command_name_lower in self._core_commands and 
                not instance.__origin__.startswith("<core")):
                
                with contextlib.suppress(ValueError):
                    self.modules.remove(instance)
                
                raise CoreOverwriteError(command=command_name)
            
            self.commands[command_name_lower] = command_func
        
        # Apply aliases
        for alias, cmd in self.aliases.copy().items():
            parts = cmd.split(maxsplit=1)
            if parts[0] in instance.Pust_commands:
                self.add_alias(alias, parts[0], parts[1] if len(parts) > 1 else None)
        
        self.register_inline_handlers(instance)
    
    def register_inline_handlers(self, instance: Module) -> None:
        """Register inline and callback handlers for a module.
        
        Args:
            instance: Module instance.
        """
        # Register inline handlers
        for name, handler in instance.Pust_inline_handlers.items():
            name_lower = name.lower()
            
            if name_lower in self.inline_handlers:
                existing = self.inline_handlers[name_lower]
                
                # Check if from different module
                if (hasattr(handler, "__self__") and 
                    hasattr(existing, "__self__") and
                    handler.__self__.__class__.__name__ != 
                    existing.__self__.__class__.__name__):
                    
                    logger.debug(
                        "Duplicate inline_handler %s from %s",
                        name,
                        instance.__class__.__name__,
                    )
                
                logger.debug(
                    "Replacing inline_handler %s with %s",
                    existing.__self__.__class__.__name__,
                    instance.__class__.__name__,
                )
            
            self.inline_handlers[name_lower] = handler
        
        # Register callback handlers
        for name, handler in instance.Pust_callback_handlers.items():
            name_lower = name.lower()
            
            if (name_lower in self.callback_handlers and
                hasattr(handler, "__self__") and
                hasattr(self.callback_handlers[name_lower], "__self__") and
                handler.__self__.__class__.__name__ != 
                self.callback_handlers[name_lower].__self__.__class__.__name__):
                
                logger.debug(
                    "Duplicate callback_handler %s from %s",
                    name,
                    instance.__class__.__name__,
                )
            
            self.callback_handlers[name_lower] = handler
    
    def unregister_inline_handlers(
        self, 
        instance: Module, 
        purpose: str
    ) -> None:
        """Unregister inline and callback handlers for a module.
        
        Args:
            instance: Module instance.
            purpose: Purpose of unregistration (for logging).
        """
        # Unregister inline handlers
        for name, handler in instance.Pust_inline_handlers.items():
            name_lower = name.lower()
            
            if (name_lower in self.inline_handlers and
                hasattr(handler, "__self__") and
                hasattr(self.inline_handlers[name_lower], "__self__") and
                handler.__self__.__class__.__name__ == 
                self.inline_handlers[name_lower].__self__.__class__.__name__):
                
                del self.inline_handlers[name_lower]
                logger.debug(
                    "Unregistered inline_handler %s of %s for %s",
                    name,
                    instance.__class__.__name__,
                    purpose,
                )
        
        # Unregister callback handlers
        for name, handler in instance.Pust_callback_handlers.items():
            name_lower = name.lower()
            
            if (name_lower in self.callback_handlers and
                hasattr(handler, "__self__") and
                hasattr(self.callback_handlers[name_lower], "__self__") and
                handler.__self__.__class__.__name__ == 
                self.callback_handlers[name_lower].__self__.__class__.__name__):
                
                del self.callback_handlers[name_lower]
                logger.debug(
                    "Unregistered callback_handler %s of %s for %s",
                    name,
                    instance.__class__.__name__,
                    purpose,
                )
    
    def register_watchers(self, instance: Module) -> None:
        """Register watchers from a module instance.
        
        Args:
            instance: Module instance.
        """
        # Remove existing watchers from same module
        self.watchers = [
            w for w in self.watchers
            if w.__self__.__class__.__name__ != instance.__class__.__name__
        ]
        
        # Add new watchers
        for watcher_func in instance.Pust_watchers.values():
            self.watchers.append(watcher_func)
    
    def lookup(
        self,
        modname: str,
    ) -> typing.Union[Module, Library, bool]:
        """Look up a module or library by name.
        
        Args:
            modname: Name to look up.
        
        Returns:
            Module/Library instance or False if not found.
        """
        # Check libraries
        for lib in self.libraries:
            if lib.name.lower() == modname.lower():
                return lib
        
        # Check modules
        for mod in self.modules:
            if (mod.__class__.__name__.lower() == modname.lower() or
                mod.name.lower() == modname.lower()):
                return mod
        
        return False
    
    @property
    def get_approved_channel(self) -> typing.Optional[str]:
        """Get the next approved channel from the queue.
        
        Returns:
            Channel name or None if queue is empty.
        """
        return self.__approve.pop(0) if self.__approve else None
    
    def get_prefix(self, ent_id: typing.Optional[int] = None) -> str:
        """Get command prefix for an entity.
        
        Args:
            ent_id: Entity ID (chat/user) for specific prefix.
        
        Returns:
            Command prefix.
        """
        from . import main
        
        default = "."
        key = main.__name__
        
        if ent_id:
            prefixes = self._db.get(key, "command_prefixes", {})
            return prefixes.get(str(ent_id), default)
        
        return self._db.get(key, "command_prefix", default)
    
    def get_prefixes(self) -> typing.Set[str]:
        """Get all command prefixes in use.
        
        Returns:
            Set of all prefixes.
        """
        from . import main
        
        key = main.__name__
        default = "."
        
        prefixes = set()
        
        # Add global prefix
        global_prefix = self._db.get(key, "command_prefix", default)
        if global_prefix:
            prefixes.add(global_prefix)
        
        # Add entity-specific prefixes
        entity_prefixes = self._db.get(key, "command_prefixes", {})
        prefixes.update(entity_prefixes.values())
        
        return prefixes
    
    async def complete_registration(self, instance: Module) -> None:
        """Complete registration of a module instance.
        
        Args:
            instance: Module instance.
        
        Raises:
            CoreOverwriteError: If trying to overwrite core module.
        """
        instance.allmodules = self
        instance.internal_init()
        
        # Check for existing module with same name
        for existing_module in self.modules:
            if existing_module.__class__.__name__ == instance.__class__.__name__:
                # Prevent overwriting core modules
                if (not self._remove_core_protection and 
                    existing_module.__origin__.startswith("<core")):
                    
                    raise CoreOverwriteError(
                        module=(
                            existing_module.__class__.__name__[:-3]
                            if existing_module.__class__.__name__.endswith("Mod")
                            else existing_module.__class__.__name__
                        )
                    )
                
                # Unload existing module
                logger.debug("Removing module %s for update", existing_module)
                await existing_module.on_unload()
                self.modules.remove(existing_module)
                
                # Stop loops in old module
                for _, method in utils.iter_attrs(existing_module):
                    if isinstance(method, InfiniteLoop):
                        method.stop()
                        logger.debug(
                            "Stopped loop in module %s, method %s",
                            existing_module.__class__.__name__,
                            method.func.__name__,
                        )
                
                break
        
        self.modules.append(instance)
    
    def find_alias(
        self,
        alias: str,
        include_legacy: bool = False,
    ) -> typing.Optional[str]:
        """Find command name for an alias.
        
        Args:
            alias: Alias to look up.
            include_legacy: Include legacy aliases.
        
        Returns:
            Command name or None.
        """
        if not alias:
            return None
        
        # Check command aliases
        for command_name, command_func in self.commands.items():
            aliases = []
            
            # Get aliases from command
            if hasattr(command_func, "alias"):
                aliases = [command_func.alias]
            
            if hasattr(command_func, "aliases"):
                aliases = command_func.aliases
            
            # Check if alias matches
            for cmd_alias in aliases:
                if (alias.lower() == cmd_alias.lower() and
                    alias.lower() not in self._core_commands):
                    return command_name
        
        # Check legacy aliases
        if include_legacy and alias in self.aliases:
            return self.aliases[alias]
        
        return None
    
    def dispatch(
        self, 
        command_input: str
    ) -> typing.Tuple[str, typing.Optional[Command]]:
        """Dispatch a command to the appropriate handler.
        
        Args:
            command_input: Raw command input.
        
        Returns:
            Tuple of (full_command, command_handler or None).
        """
        # Try direct command
        if command_input:
            first_word = command_input.split()[0].lower()
            if first_word in self.commands:
                return (command_input, self.commands[first_word])
        
        # Try alias resolution
        aliases_to_try = [
            command_input,
            self.aliases.get(command_input.lower()),
            self.find_alias(command_input),
        ]
        
        for alias in aliases_to_try:
            if alias:
                first_word = alias.split()[0].lower()
                if first_word in self.commands:
                    return (alias, self.commands[first_word])
        
        return (command_input, None)
    
    def send_config(self, skip_hook: bool = False) -> None:
        """Send configuration to all modules.
        
        Args:
            skip_hook: Skip config_complete hook.
        """
        for module in self.modules:
            self._send_config_to_module(module, skip_hook)
    
    def _send_config_to_module(self, module: Module, skip_hook: bool) -> None:
        """Send configuration to a single module.
        
        Args:
            module: Module instance.
            skip_hook: Skip config_complete hook.
        """
        # Configure module settings
        if hasattr(module, "config"):
            module_config = self._db.get(
                module.__class__.__name__,
                "__config__",
                {},
            )
            
            try:
                for config_key in module.config:
                    # Try database value
                    if config_key in module_config:
                        value = module_config[config_key]
                    # Try environment variable
                    elif env_value := os.environ.get(
                        f"{module.__class__.__name__}.{config_key}"
                    ):
                        value = env_value
                    # Use default
                    else:
                        value = module.config.getdef(config_key)
                    
                    module.config.set_no_raise(config_key, value)
            except AttributeError:
                logger.warning(
                    "Invalid config instance in %s. Expected ModuleConfig, got %s",
                    module.__class__.__name__,
                    type(module.config),
                )
        
        # Set module name
        if not hasattr(module, "name"):
            module.name = module.strings.get("name", module.__class__.__name__)
        
        if skip_hook:
            return
        
        # Initialize strings and translator
        if not hasattr(module, "strings"):
            module.strings = {}
        
        module.strings = Strings(module, self.translator)
        module.translator = self.translator
        
        # Call config_complete
        try:
            module.config_complete()
        except Exception as e:
            logger.exception(
                "Failed to send config_complete to %s: %s",
                module.__class__.__name__,
                e,
            )
            raise
    
    async def send_ready(self) -> None:
        """Initialize all modules and send ready signal."""
        await self.inline.register_manager()
        
        tasks = [
            self._send_ready_to_module(module)
            for module in self.modules
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _send_ready_to_module(
        self, 
        module: Module,
        no_self_unload: bool = False,
        from_dlmod: bool = False,
    ) -> None:
        """Send ready signal to a single module.
        
        Args:
            module: Module instance.
            no_self_unload: Don't allow self-unload.
            from_dlmod: Called from download module.
        """
        # Call on_dlmod if applicable
        if from_dlmod and hasattr(module, "on_dlmod"):
            try:
                sig = inspect.signature(module.on_dlmod)
                if len(sig.parameters) == 2:
                    await module.on_dlmod(self.client, self._db)
                else:
                    await module.on_dlmod()
            except Exception:
                logger.info(
                    "Can't process on_dlmod hook in %s",
                    module.__class__.__name__,
                    exc_info=True,
                )
        
        # Call client_ready
        try:
            if hasattr(module, "client_ready"):
                sig = inspect.signature(module.client_ready)
                if len(sig.parameters) == 2:
                    await module.client_ready(self.client, self._db)
                else:
                    await module.client_ready()
        except SelfUnload:
            if no_self_unload:
                raise
            
            logger.debug("Unloading %s due to SelfUnload", module.__class__.__name__)
            self.modules.remove(module)
            return
        except SelfSuspend:
            if no_self_unload:
                raise
            
            logger.debug("Suspending %s due to SelfSuspend", module.__class__.__name__)
            return
        except Exception as e:
            logger.exception(
                "Failed to initialize %s: %s",
                module.__class__.__name__,
                e,
            )
            self.modules.remove(module)
            raise
        
        # Initialize loops
        for _, method in utils.iter_attrs(module):
            if isinstance(method, InfiniteLoop):
                method.module_instance = module
                
                if method.autostart:
                    method.start()
                
                logger.debug(
                    "Initialized loop %s in module %s",
                    method.func.__name__,
                    module.__class__.__name__,
                )
        
        # Refresh handlers
        self.unregister_commands(module, "update")
        self.unregister_raw_handlers(module, "update")
        
        self.register_commands(module)
        self.register_watchers(module)
        self.register_raw_handlers(module)
    
    def get_classname(self, name: str) -> str:
        """Get full class name for a module.
        
        Args:
            name: Module name or class name.
        
        Returns:
            Full class name.
        """
        for module in reversed(self.modules):
            if name in (module.name, module.__class__.__module__):
                return module.__class__.__module__
        
        return name
    
    async def unload_module(self, classname: str) -> typing.List[str]:
        """Unload a module and clean up its resources.
        
        Args:
            classname: Module class name.
        
        Returns:
            List of unloaded module names.
        
        Raises:
            CoreUnloadError: If trying to unload core module.
        """
        unloaded: typing.List[str] = []
        
        for module in self.modules[:]:  # Copy for safe removal
            if classname.lower() in (
                module.name.lower(),
                module.__class__.__name__.lower(),
            ):
                # Prevent unloading core modules
                if (not self._remove_core_protection and 
                    module.__origin__.startswith("<core")):
                    
                    raise CoreUnloadError(module.__class__.__name__)
                
                unloaded.append(module.__class__.__name__)
                
                # Remove filesystem file
                path = os.path.join(
                    LOADED_MODULES_DIR,
                    f"{module.__class__.__name__}_{self.client.tg_id}.py",
                )
                
                if os.path.isfile(path):
                    os.remove(path)
                    logger.debug("Removed file %s", path)
                
                # Unload module
                logger.debug("Unloading module %s", module.__class__.__name__)
                self.modules.remove(module)
                
                await module.on_unload()
                
                # Clean up handlers
                self.unregister_raw_handlers(module, "unload")
                self.unregister_loops(module, "unload")
                self.unregister_commands(module, "unload")
                self.unregister_watchers(module, "unload")
                self.unregister_inline_handlers(module, "unload")
        
        logger.debug("Unloaded modules: %s", unloaded)
        return unloaded
    
    def unregister_loops(self, instance: Module, purpose: str) -> None:
        """Unregister loops from a module.
        
        Args:
            instance: Module instance.
            purpose: Purpose of unregistration.
        """
        for name, method in utils.iter_attrs(instance):
            if isinstance(method, InfiniteLoop):
                logger.debug(
                    "Stopping loop %s in module %s for %s",
                    name,
                    instance.__class__.__name__,
                    purpose,
                )
                method.stop()
    
    def unregister_commands(self, instance: Module, purpose: str) -> None:
        """Unregister commands from a module.
        
        Args:
            instance: Module instance.
            purpose: Purpose of unregistration.
        """
        for command_name, command_func in list(self.commands.items()):
            if command_func.__self__.__class__.__name__ == instance.__class__.__name__:
                del self.commands[command_name]
                logger.debug(
                    "Unregistered command %s from %s for %s",
                    command_name,
                    instance.__class__.__name__,
                    purpose,
                )
                
                # Remove related aliases
                for alias, cmd in list(self.aliases.items()):
                    if cmd == command_name:
                        del self.aliases[alias]
    
    def unregister_watchers(self, instance: Module, purpose: str) -> None:
        """Unregister watchers from a module.
        
        Args:
            instance: Module instance.
            purpose: Purpose of unregistration.
        """
        for watcher in list(self.watchers):
            if watcher.__self__.__class__.__name__ == instance.__class__.__name__:
                self.watchers.remove(watcher)
                logger.debug(
                    "Unregistered watcher from %s for %s",
                    instance.__class__.__name__,
                    purpose,
                )
    
    def unregister_raw_handlers(self, instance: Module, purpose: str) -> None:
        """Unregister raw handlers from a module.
        
        Args:
            instance: Module instance.
            purpose: Purpose of unregistration.
        """
        for handler in list(self.client.dispatcher.raw_handlers):
            if handler.__self__.__class__.__name__ == instance.__class__.__name__:
                self.client.dispatcher.raw_handlers.remove(handler)
                logger.debug(
                    "Unregistered raw handler from %s for %s (ID: %s)",
                    instance.__class__.__name__,
                    purpose,
                    getattr(handler, "id", "unknown"),
                )
    
    def add_alias(self, alias: str, cmd: str, args: typing.Optional[str] = None) -> bool:
        """Add a command alias.
        
        Args:
            alias: Alias name.
            cmd: Command name.
            args: Command arguments.
        
        Returns:
            True if alias was added.
        """
        if cmd not in self.commands:
            return False
        
        full_command = f"{cmd} {args}" if args else cmd
        self.aliases[alias.lower().strip()] = full_command
        return True
    
    def remove_alias(self, alias: str) -> bool:
        """Remove a command alias.
        
        Args:
            alias: Alias name.
        
        Returns:
            True if alias was removed.
        """
        return alias.lower().strip() in self.aliases.pop(alias.lower().strip(), {})
    
    async def log(self, *args, **kwargs) -> None:
        """Placeholder logging method."""
        pass
    
    async def reload_translations(self) -> bool:
        """Reload all translations.
        
        Returns:
            True if reload was successful.
        """
        if not await self.translator.init():
            return False
        
        for module in self.modules:
            try:
                module.config_complete(reload_dynamic_translate=True)
            except Exception as e:
                logger.debug(
                    "Can't reload translations for %s: %s",
                    module.__class__.__name__,
                    e,
                )
        
        return True