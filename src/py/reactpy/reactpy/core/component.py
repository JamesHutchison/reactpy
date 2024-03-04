from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Callable

from reactpy.core.types import ComponentType, VdomDict


def component(
    function: Callable[..., ComponentType | VdomDict | str | None] | None = None,
    *,
    priority: int = 0,
) -> Callable[..., Component]:
    """A decorator for defining a new component.

    Parameters:
        priority: The rendering priority. Lower numbers are higher priority.
    """

    def _component(
        function: Callable[..., ComponentType | VdomDict | str | None]
    ) -> Callable[..., Component]:
        sig = inspect.signature(function)

        if "key" in sig.parameters and sig.parameters["key"].kind in (
            inspect.Parameter.KEYWORD_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            msg = f"Component render function {function} uses reserved parameter 'key'"
            raise TypeError(msg)

        @wraps(function)
        def constructor(*args: Any, key: Any | None = None, **kwargs: Any) -> Component:
            return Component(function, key, args, kwargs, sig, priority)

        return constructor

    if function:
        return _component(function)
    return _component


class Component:
    """An object for rending component models."""

    __slots__ = "__weakref__", "_func", "_args", "_kwargs", "_sig", "key", "type"

    def __init__(
        self,
        function: Callable[..., ComponentType | VdomDict | str | None],
        key: Any | None,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        sig: inspect.Signature,
        priority: int = 0,
    ) -> None:
        self.key = key
        self.type = function
        self._args = args
        self._kwargs = kwargs
        self._sig = sig
        self.priority = priority

    def render(self) -> ComponentType | VdomDict | str | None:
        return self.type(*self._args, **self._kwargs)

    def __repr__(self) -> str:
        try:
            args = self._sig.bind(*self._args, **self._kwargs).arguments
        except TypeError:
            return f"{self.type.__name__}(...)"
        else:
            items = ", ".join(f"{k}={v!r}" for k, v in args.items())
            if items:
                return f"{self.type.__name__}({id(self):02x}, {items})"
            else:
                return f"{self.type.__name__}({id(self):02x})"
