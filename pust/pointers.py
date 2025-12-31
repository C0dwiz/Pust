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

from __future__ import annotations

import collections.abc
import typing
from collections.abc import Iterable, Iterator, KeysView
from typing import (
    Any,
    Optional,
    SupportsIndex,
    Type,
    TypeVar,
    Union,
    overload,
)

if typing.TYPE_CHECKING:
    from .database import Database
    from .types import JSONSerializable

T = TypeVar("T")
KT = TypeVar("KT")  # Key type
VT = TypeVar("VT")  # Value type
NT = TypeVar("NT")  # NamedTuple type


class PointerList(list):
    """Mutable list that automatically persists changes to database"""

    def __init__(
        self,
        db: Database,
        module: str,
        key: str,
        default: Optional[Any] = None,
    ) -> None:
        self._db = db
        self._module = module
        self._key = key
        self._default: list = default if default is not None else []
        
        initial_data = db.get(module, key, self._default)
        if not isinstance(initial_data, list):
            raise TypeError(
                f"Database value for {module}.{key} is not a list, "
                f"got {type(initial_data).__name__}"
            )
        
        super().__init__(initial_data)

    @property
    def data(self) -> list:
        """Get a copy of the underlying list"""
        return list(self)

    @data.setter
    def data(self, value: list) -> None:
        """Replace the entire list"""
        if not isinstance(value, list):
            raise TypeError(f"Expected list, got {type(value).__name__}")
        
        self.clear()
        self.extend(value)
        self._save()

    def __repr__(self) -> str:
        return f"PointerList({super().__repr__()})"

    def __str__(self) -> str:
        return f"PointerList({list(self)})"

    def __delitem__(self, index: Union[SupportsIndex, slice]) -> None:
        super().__delitem__(index)
        self._save()

    def __setitem__(
        self,
        index: Union[SupportsIndex, slice],
        value: Any,
    ) -> None:
        super().__setitem__(index, value)
        self._save()

    def __iadd__(self, other: Iterable) -> PointerList:
        result = super().__iadd__(other)
        self._save()
        return result

    def __imul__(self, n: int) -> PointerList:
        result = super().__imul__(n)
        self._save()
        return result

    def append(self, value: Any) -> None:
        super().append(value)
        self._save()

    def extend(self, iterable: Iterable) -> None:
        super().extend(iterable)
        self._save()

    def insert(self, index: int, value: Any) -> None:
        super().insert(index, value)
        self._save()

    def remove(self, value: Any) -> None:
        super().remove(value)
        self._save()

    def pop(self, index: int = -1) -> Any:
        result = super().pop(index)
        self._save()
        return result

    def clear(self) -> None:
        super().clear()
        self._save()

    def sort(self, *, key: Any = None, reverse: bool = False) -> None:
        super().sort(key=key, reverse=reverse)
        self._save()

    def reverse(self) -> None:
        super().reverse()
        self._save()

    def _save(self) -> None:
        """Persist current state to database"""
        self._db.set(self._module, self._key, list(self))

    def tolist(self) -> list:
        """Get raw list from database"""
        return self._db.get(self._module, self._key, self._default)


class PointerDict(dict):
    """Mutable dict that automatically persists changes to database"""

    def __init__(
        self,
        db: Database,
        module: str,
        key: str,
        default: Optional[Any] = None,
    ) -> None:
        self._db = db
        self._module = module
        self._key = key
        self._default: dict = default if default is not None else {}
        
        initial_data = db.get(module, key, self._default)
        if not isinstance(initial_data, dict):
            raise TypeError(
                f"Database value for {module}.{key} is not a dict, "
                f"got {type(initial_data).__name__}"
            )
        
        super().__init__(initial_data)

    @property
    def data(self) -> dict:
        """Get a copy of the underlying dict"""
        return dict(self)

    @data.setter
    def data(self, value: dict) -> None:
        """Replace the entire dict"""
        if not isinstance(value, dict):
            raise TypeError(f"Expected dict, got {type(value).__name__}")
        
        self.clear()
        self.update(value)
        self._save()

    def __repr__(self) -> str:
        return f"PointerDict({super().__repr__()})"

    def __bool__(self) -> bool:
        return bool(self._db.get(self._module, self._key, self._default))

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        self._save()

    def __delitem__(self, key: str) -> None:
        super().__delitem__(key)
        self._save()

    def __str__(self) -> str:
        return f"PointerDict({dict(self)})"

    def update(self, other: dict = None, **kwargs: Any) -> None:  # type: ignore
        if other:
            super().update(other)
        if kwargs:
            super().update(kwargs)
        if other or kwargs:
            self._save()

    def setdefault(self, key: str, default: Any = None) -> Any:
        result = super().setdefault(key, default)
        self._save()
        return result

    def pop(self, key: str, default: Any = None) -> Any:
        result = super().pop(key, default)
        self._save()
        return result

    def popitem(self) -> tuple[Any, Any]:
        result = super().popitem()
        self._save()
        return result

    def clear(self) -> None:
        super().clear()
        self._save()

    def _save(self) -> None:
        """Persist current state to database"""
        self._db.set(self._module, self._key, dict(self))

    def todict(self) -> dict:
        """Get raw dict from database"""
        return self._db.get(self._module, self._key, self._default)


class BaseSerializingMiddlewareDict(collections.abc.MutableMapping):
    """Base class for dict-like structures with custom serialization"""
    
    def __init__(self, pointer: PointerDict) -> None:
        if not isinstance(pointer, PointerDict):
            raise TypeError(f"Expected PointerDict, got {type(pointer).__name__}")
        self._pointer = pointer

    def serialize(self, item: Any) -> JSONSerializable:
        """Convert object to JSON-serializable format"""
        raise NotImplementedError

    def deserialize(self, item: JSONSerializable) -> Any:
        """Convert JSON-serializable format back to object"""
        raise NotImplementedError

    @overload
    def __getitem__(self, key: KT) -> VT: ...

    @overload
    def __getitem__(self, key: Any) -> Any: ...

    def __getitem__(self, key: Any) -> Any:
        return self.deserialize(self._pointer[key])

    def __setitem__(self, key: Any, value: Any) -> None:
        self._pointer[key] = self.serialize(value)

    def __delitem__(self, key: Any) -> None:
        del self._pointer[key]

    def __iter__(self) -> Iterator[Any]:
        for key, value in self._pointer.items():
            yield key, self.deserialize(value)

    def __len__(self) -> int:
        return len(self._pointer)

    def __contains__(self, key: Any) -> bool:
        return key in self._pointer

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.todict()})"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._pointer})"

    def pop(self, key: Any, default: Any = None) -> Any:
        if key in self._pointer:
            return self.deserialize(self._pointer.pop(key))
        return default

    def popitem(self) -> tuple[Any, Any]:
        key, value = self._pointer.popitem()
        return key, self.deserialize(value)

    def get(self, key: Any, default: Any = None) -> Any:
        if key in self._pointer:
            return self.deserialize(self._pointer[key])
        return default

    def setdefault(self, key: Any, default: Any = None) -> Any:
        if key in self._pointer:
            return self.deserialize(self._pointer[key])
        self._pointer[key] = self.serialize(default)
        return default

    def clear(self) -> None:
        self._pointer.clear()

    def todict(self) -> dict:
        """Convert to plain dict with deserialized values"""
        return {k: self.deserialize(v) for k, v in self._pointer.data.items()}

    def keys(self) -> KeysView:
        return self._pointer.keys()

    def values(self) -> Iterator[Any]:
        return (self.deserialize(v) for v in self._pointer.values())

    def items(self) -> Iterator[tuple[Any, Any]]:
        return ((k, self.deserialize(v)) for k, v in self._pointer.items())


class BaseSerializingMiddlewareList(collections.abc.MutableSequence):
    """Base class for list-like structures with custom serialization"""
    
    def __init__(self, pointer: PointerList) -> None:
        if not isinstance(pointer, PointerList):
            raise TypeError(f"Expected PointerList, got {type(pointer).__name__}")
        self._pointer = pointer

    def serialize(self, item: Any) -> JSONSerializable:
        """Convert object to JSON-serializable format"""
        raise NotImplementedError

    def deserialize(self, item: JSONSerializable) -> Any:
        """Convert JSON-serializable format back to object"""
        raise NotImplementedError

    def remove(self, item: Any) -> None:
        self._pointer.remove(self.serialize(item))

    def pop(self, index: int = -1) -> Any:
        return self.deserialize(self._pointer.pop(index))

    def insert(self, index: int, item: Any) -> None:
        self._pointer.insert(index, self.serialize(item))

    def append(self, item: Any) -> None:
        self._pointer.append(self.serialize(item))

    def extend(self, items: Iterable[Any]) -> None:
        self._pointer.extend([self.serialize(item) for item in items])

    def __getitem__(self, index: Any) -> Any:
        return self.deserialize(self._pointer[index])

    def __setitem__(self, index: Any, value: Any) -> None:
        self._pointer[index] = self.serialize(value)

    def __delitem__(self, index: Any) -> None:
        del self._pointer[index]

    def __iter__(self) -> Iterator[Any]:
        return (self.deserialize(item) for item in self._pointer)

    def __len__(self) -> int:
        return len(self._pointer)

    def __contains__(self, item: Any) -> bool:
        return self.serialize(item) in self._pointer

    def __reversed__(self) -> Iterator[Any]:
        return (self.deserialize(item) for item in reversed(self._pointer))

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.tolist()})"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._pointer})"

    def tolist(self) -> list:
        """Convert to plain list with deserialized values"""
        return [self.deserialize(item) for item in self._pointer.data]

    def index(self, item: Any, start: int = 0, stop: int = None) -> int:  # type: ignore
        return self._pointer.index(self.serialize(item), start, stop or len(self._pointer))

    def count(self, item: Any) -> int:
        return self._pointer.count(self.serialize(item))

    def sort(self, *, key: Any = None, reverse: bool = False) -> None:
        # Sort by deserialized values using a custom key function
        if key is None:
            key = lambda x: self.serialize(x)  # noqa
        else:
            original_key = key
            key = lambda x: original_key(self.deserialize(x))  # noqa
        
        # Sort in-place by temporarily converting, sorting, and converting back
        deserialized = [self.deserialize(item) for item in self._pointer]
        deserialized.sort(key=key, reverse=reverse)
        self._pointer.clear()
        self._pointer.extend([self.serialize(item) for item in deserialized])
        self._save()

    def _save(self) -> None:
        """Ensure changes are persisted"""
        self._pointer._save()


class NamedTupleMiddlewareList(BaseSerializingMiddlewareList):
    """Middleware for lists of NamedTuple objects"""
    
    def __init__(self, pointer: PointerList, item_type: Type[Any]) -> None:
        super().__init__(pointer)
        self._item_type = item_type

    def serialize(self, item: Any) -> JSONSerializable:
        """Convert NamedTuple to dict"""
        if not hasattr(item, '_asdict'):
            raise TypeError(
                f"Expected NamedTuple with _asdict method, got {type(item).__name__}"
            )
        return item._asdict()

    def deserialize(self, item: JSONSerializable) -> Any:
        """Convert dict back to NamedTuple"""
        if not isinstance(item, dict):
            raise TypeError(f"Expected dict for NamedTuple, got {type(item).__name__}")
        return self._item_type(**item)


class NamedTupleMiddlewareDict(BaseSerializingMiddlewareDict):
    """Middleware for dicts of NamedTuple objects"""
    
    def __init__(self, pointer: PointerDict, item_type: Type[Any]) -> None:
        super().__init__(pointer)
        self._item_type = item_type

    def serialize(self, item: Any) -> JSONSerializable:
        """Convert NamedTuple to dict"""
        if not hasattr(item, '_asdict'):
            raise TypeError(
                f"Expected NamedTuple with _asdict method, got {type(item).__name__}"
            )
        return item._asdict()

    def deserialize(self, item: JSONSerializable) -> Any:
        """Convert dict back to NamedTuple"""
        if not isinstance(item, dict):
            raise TypeError(f"Expected dict for NamedTuple, got {type(item).__name__}")
        return self._item_type(**item)