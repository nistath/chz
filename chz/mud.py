from __future__ import annotations

import functools
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    TypeVar,
    get_args,
    get_origin,
)

from typing_extensions import dataclass_transform

import chz
from chz.blueprint._argmap import join_arg_path
from chz.data_model import init_property as chz_init_property
from chz.util import MISSING

if TYPE_CHECKING:
    from chz.blueprint import Blueprint
    from chz.field import Field

_T = TypeVar("_T")


class FrozenPropertyError(Exception):
    """Raised when attempting to write to a property that has been read."""

    pass


def _is_chz_type(tp: Any) -> bool:
    """Check if a type annotation represents a chz class."""
    origin = get_origin(tp)
    if origin is not None:
        # Handle Optional, Union, etc - check args
        args = get_args(tp)
        if args:
            return any(_is_chz_type(arg) for arg in args if arg is not type(None))
        return False
    return chz.is_chz(tp)


def _get_chz_class(tp: Any) -> type | None:
    """Extract the chz class from a type annotation."""
    origin = get_origin(tp)
    if origin is not None:
        args = get_args(tp)
        for arg in args:
            if arg is not type(None):
                result = _get_chz_class(arg)
                if result is not None:
                    return result
        return None
    if chz.is_chz(tp):
        return tp
    return None


@dataclass_transform(frozen_default=False, kw_only_default=True, field_specifiers=(chz.field,))
class MudView(Generic[_T]):
    """Mutable view of a Blueprint that acts like a chz instance.

    MudView provides chz-instance-like access while editing the Blueprint:
    - Writes immediately apply to the Blueprint
    - Reads consolidate the Blueprint and freeze the accessed field
    - Methods and properties work by binding to MudView

    Example:
        bp = Blueprint(Config)
        m = bp.mud()
        m.name = "hello"
        m.model.n_layers = 10
        print(m.name)  # Freezes 'name'
        config = bp.make()
    """

    __slots__ = (
        "_mv_blueprint",
        "_mv_target_class",
        "_mv_fields",
        "_mv_path",
        "_mv_frozen",
        "_mv_init_property_cache",
        "_mv_nested",
    )

    def __init__(
        self,
        blueprint: Blueprint[_T],
        target_class: type[_T],
        path: str = "",
        frozen: set[str] | None = None,
    ) -> None:
        object.__setattr__(self, "_mv_blueprint", blueprint)
        object.__setattr__(self, "_mv_target_class", target_class)
        object.__setattr__(self, "_mv_fields", chz.chz_fields(target_class))
        object.__setattr__(self, "_mv_path", path)
        object.__setattr__(self, "_mv_frozen", frozen if frozen is not None else set())
        object.__setattr__(self, "_mv_init_property_cache", {})
        object.__setattr__(self, "_mv_nested", {})

    def _get_field_by_logical_name(self, name: str) -> Field | None:
        """Get field by logical name (handles X_ prefix)."""
        fields = self._mv_fields
        # Try direct match first (fields are keyed by logical name)
        if name in fields:
            return fields[name]
        # If name starts with X_, check if it's an x_name of some field
        if name.startswith("X_"):
            logical = name[2:]  # Remove X_ prefix
            if logical in fields and fields[logical].x_name == name:
                return fields[logical]
        return None

    def _full_path(self, name: str) -> str:
        """Get the full path for a field name."""
        return join_arg_path(self._mv_path, name)

    def __setattr__(self, name: str, value: Any) -> None:
        # Handle internal attributes
        if name.startswith("_mv_"):
            object.__setattr__(self, name, value)
            return

        field = self._get_field_by_logical_name(name)
        if field is None:
            raise AttributeError(
                f"'{self._mv_target_class.__qualname__}' has no field '{name}'"
            )

        logical = field.logical_name
        full_path = self._full_path(logical)

        if full_path in self._mv_frozen:
            raise FrozenPropertyError(
                f"Cannot modify field '{name}' - it has already been read"
            )

        # Apply immediately to Blueprint
        self._mv_blueprint.apply({full_path: value}, layer_name="mud")

        # Clear nested view if exists
        self._mv_nested.pop(logical, None)

    def __getattr__(self, name: str) -> Any:
        # Handle internal attributes
        if name.startswith("_mv_"):
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

        # FIRST check for init_property on target class (before field check)
        # This is important because fields and init_properties can share the same name
        target = self._mv_target_class
        for cls in target.__mro__:
            if name in cls.__dict__:
                attr = cls.__dict__[name]

                if isinstance(attr, chz_init_property):
                    return self._evaluate_init_property(name, attr)

                elif isinstance(attr, property):
                    if attr.fget is None:
                        raise AttributeError(f"property '{name}' has no getter")
                    return attr.fget(self)

                elif isinstance(attr, functools.cached_property):
                    # Treat like init_property - cache result
                    cache = self._mv_init_property_cache
                    if name in cache:
                        return cache[name]
                    result = attr.func(self)
                    cache[name] = result
                    return result

                elif callable(attr) and not isinstance(attr, type):
                    # Regular method - bind to this MudView
                    return attr.__get__(self, type(self))

                # If it's something else (like a field descriptor), continue to field handling
                break

        # Check if it's a field access (including X_ prefixed raw access)
        field = self._get_field_by_logical_name(name)
        if field is not None:
            return self._get_field_value(name, field)

        raise AttributeError(
            f"'{self._mv_target_class.__qualname__}' has no field or method '{name}'"
        )

    def _get_field_value(self, name: str, field: Field) -> Any:
        """Get a field value, freezing it and returning nested MudView for chz fields."""
        logical = field.logical_name
        full_path = self._full_path(logical)

        # Check if we already have a nested view
        if logical in self._mv_nested:
            return self._mv_nested[logical]

        # Read from Blueprint
        self._mv_blueprint._arg_map.consolidate()
        found = self._mv_blueprint._arg_map.get_kv(full_path)
        value = found.value if found else MISSING

        # Mark frozen
        self._mv_frozen.add(full_path)

        field_type = field.final_type

        # Handle nested chz classes - return nested MudView
        if _is_chz_type(field_type):
            chz_class = _get_chz_class(field_type)
            if chz_class is not None:
                nested = MudView(
                    blueprint=self._mv_blueprint,
                    target_class=chz_class,
                    path=full_path,
                    frozen=self._mv_frozen,  # Share frozen set
                )
                self._mv_nested[logical] = nested
                return nested

        return value

    def _evaluate_init_property(self, name: str, prop: chz_init_property) -> Any:
        """Lazily evaluate and cache an init_property."""
        cache = self._mv_init_property_cache
        if name in cache:
            return cache[name]

        # Evaluate: accessing fields via self freezes them
        result = prop.func(self)
        cache[name] = result
        return result

    def is_frozen(self, name: str) -> bool:
        """Check if a field has been read (frozen)."""
        field = self._get_field_by_logical_name(name)
        if field is None:
            raise AttributeError(
                f"'{self._mv_target_class.__qualname__}' has no field '{name}'"
            )
        full_path = self._full_path(field.logical_name)
        return full_path in self._mv_frozen

    def get_frozen_fields(self) -> set[str]:
        """Return set of all frozen field paths."""
        return set(self._mv_frozen)

    def __repr__(self) -> str:
        path_str = f" at '{self._mv_path}'" if self._mv_path else ""
        return f"MudView[{self._mv_target_class.__qualname__}]{path_str}"
