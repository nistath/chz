# Type checking tests for mud module
# This file is checked by pyright to verify type annotations are correct
#
# Run: uv run pyright tests/test_mud_types.py
#
# Type Checking Trade-offs:
#   Blueprint.mud() returns T for type checkers (MudView[T] at runtime).
#   This gives field autocomplete but requires # type: ignore[misc] for assignments
#   because chz classes are frozen dataclasses.
#
#   Alternative approaches were considered but have worse trade-offs:
#   - Return MudView[T]: Loses field types (everything becomes Any)
#   - Generate Protocols: Not supported at type-check time
#   - Intersection types: Not supported in Python
#
#   The current approach prioritizes IDE autocomplete over assignment type safety.

import chz


@chz.chz
class TypedConfig:
    name: str
    count: int = 0


@chz.chz
class NestedConfig:
    inner: TypedConfig
    label: str = "default"


def test_blueprint_mud_types() -> None:
    """Test that Blueprint.mud() returns T for type checker (TYPE_CHECKING trick)."""
    bp = chz.Blueprint(TypedConfig)
    # Type checker sees m as TypedConfig (for field autocomplete)
    m = bp.mud()

    # Field assignment - needs type: ignore because chz classes are frozen
    # The trade-off: autocomplete works, but assignment errors need suppression
    m.name = "hello"  # type: ignore[misc]
    m.count = 42  # type: ignore[misc]

    # make() returns the correct type
    result: TypedConfig = bp.make()
    assert result.name == "hello"


def test_blueprint_frozen_methods() -> None:
    """Test that frozen state methods are on Blueprint, not MudView."""
    bp = chz.Blueprint(TypedConfig)
    m = bp.mud()
    m.name = "hello"  # type: ignore[misc]

    _ = m.name  # Freeze it

    # Frozen state methods are on Blueprint (properly typed)
    frozen: bool = bp.is_mud_frozen("name")
    fields: set[str] = bp.get_mud_frozen_fields()

    assert frozen is True
    assert "name" in fields


def test_nested_mud_types() -> None:
    """Test type checking for nested chz fields."""
    bp = chz.Blueprint(NestedConfig)
    m = bp.mud()
    m.label = "test"  # type: ignore[misc]

    # Access nested field - type checker sees TypedConfig
    inner = m.inner
    inner.name = "nested"  # type: ignore[misc]
    inner.count = 5  # type: ignore[misc]

    result = bp.make()
    assert result.inner.name == "nested"


# NOTE: With TYPE_CHECKING trick:
# - Field access has proper autocomplete (type checker sees T)
# - Field assignment needs type: ignore (chz classes are frozen)
# - Frozen state methods are on Blueprint, not MudView (properly typed)
