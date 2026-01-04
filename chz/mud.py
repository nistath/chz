from __future__ import annotations

import functools
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generic,
    TypeVar,
    cast,
    get_args,
    get_origin,
)

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


class MudView(Generic[_T]):
    """Mutable view of a Blueprint that acts like a chz instance.

    MudView is a thin stateless wrapper - all state lives on Blueprint.
    - Writes immediately apply to the Blueprint
    - Reads consolidate the Blueprint and freeze the accessed field
    - Methods and properties work by binding to MudView
    - Nested MudViews are created fresh on each access (stateless)

    Example:
        bp = Blueprint(Config)
        m = bp.mud()
        m.name = "hello"
        m.model.n_layers = 10
        print(m.name)  # Freezes 'name'
        config = bp.make()

    Freezing Semantics:
        Reading a field freezes it - subsequent writes raise FrozenPropertyError.
        For nested chz fields, accessing the field freezes the *parent path*, not
        the nested fields. You can still modify nested fields through the returned
        MudView.

        Example:
            m.inner        # Freezes "inner"
            m.inner.x = 5  # Still works - sets "inner.x"
            m.inner = X()  # Raises FrozenPropertyError

        The frozen set is stored on the Blueprint (not MudView) and is shared
        across all mud() calls on the same Blueprint. Use bp.is_mud_frozen(path)
        and bp.get_mud_frozen_fields() to inspect frozen state.

    Polymorphic Fields:
        For fields with blueprint_unspecified or meta_factory, MudView uses the
        declared base type. Child-only fields are not accessible via the root
        MudView. Use bp.mud(path, child_type) to get a MudView with the child type:

            field = bp.mud("field", Child)
            field.child_only_attr = 42

        Alternatively, assign a complete instance: m.field = Child(x=1, y=2).

    Default Factory:
        Fields with default_factory call the factory on each read (stateless design).
        This is consistent with dataclass semantics but may be surprising. Freezing
        only prevents writes, not re-evaluation of defaults.
    """

    __slots__ = (
        "_mv_blueprint",
        "_mv_target_class",
        "_mv_fields",
        "_mv_path",
        # Note: _mv_frozen is a property that accesses Blueprint._mud_frozen
        # All other caches removed - stateless design
    )

    def __init__(
        self,
        blueprint: Blueprint[_T],
        target_class: type[_T],
        path: str = "",
    ) -> None:
        object.__setattr__(self, "_mv_blueprint", blueprint)
        object.__setattr__(self, "_mv_target_class", target_class)
        object.__setattr__(self, "_mv_fields", chz.chz_fields(target_class))
        object.__setattr__(self, "_mv_path", path)

    @property
    def _mv_frozen(self) -> set[str]:
        """Access the frozen set stored on Blueprint."""
        return self._mv_blueprint._mud_frozen

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
                    # Evaluate fresh each time (stateless design)
                    return attr.func(self)

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

        # Read from Blueprint
        self._mv_blueprint._arg_map.consolidate()
        found = self._mv_blueprint._arg_map.get_kv(full_path)

        field_type = field.final_type

        # Handle nested chz classes - always return fresh nested MudView
        # (stateless design - created on each access)
        if _is_chz_type(field_type):
            chz_class = _get_chz_class(field_type)
            if chz_class is not None:
                # Mark frozen before creating nested view
                self._mv_frozen.add(full_path)
                # Create fresh MudView - shares frozen set via Blueprint
                return MudView(
                    blueprint=self._mv_blueprint,
                    target_class=chz_class,
                    path=full_path,
                )

        # For non-nested fields, check if set or has default
        if found is None:
            # Check for default value
            if field._default is not MISSING:
                self._mv_frozen.add(full_path)
                return field._default
            elif field._default_factory is not MISSING:
                self._mv_frozen.add(full_path)
                factory = cast(Callable[[], Any], field._default_factory)
                return factory()
            else:
                raise AttributeError(
                    f"Field '{name}' has not been set and has no default. "
                    f"Set it first with `mud.{name} = value`."
                )

        # Mark frozen
        self._mv_frozen.add(full_path)

        return found.value

    def _evaluate_init_property(self, name: str, prop: chz_init_property) -> Any:  # type: ignore[type-arg]
        """Evaluate an init_property (fresh each time - stateless design)."""
        # Evaluate: accessing fields via self freezes them
        return prop.func(self)

    def __repr__(self) -> str:
        path_str = f" at '{self._mv_path}'" if self._mv_path else ""
        return f"MudView[{self._mv_target_class.__qualname__}]{path_str}"
