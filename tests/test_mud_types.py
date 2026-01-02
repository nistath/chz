# Type checking tests for mud module
# This file is checked by pyright to verify type annotations are correct
#
# Run: uv run pyright tests/test_mud_types.py
#
# Note: Blueprint.mud() returns T for type checkers (MudView[T] at runtime).
# chz uses frozen_default=False in @dataclass_transform so assignments are allowed
# by the type checker, even though chz instances are frozen at runtime.

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
    """Test that Blueprint.mud() returns T for type checker."""
    bp = chz.Blueprint(TypedConfig)
    # Type checker sees m as TypedConfig (for field autocomplete)
    m = bp.mud()

    # Field assignment works without type: ignore
    m.name = "hello"
    m.count = 42

    # make() returns the correct type
    result: TypedConfig = bp.make()
    assert result.name == "hello"


def test_blueprint_frozen_methods() -> None:
    """Test that frozen state methods are on Blueprint, not MudView."""
    bp = chz.Blueprint(TypedConfig)
    m = bp.mud()
    m.name = "hello"

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
    m.label = "test"

    # Access nested field - type checker sees TypedConfig
    inner = m.inner
    inner.name = "nested"
    inner.count = 5

    result = bp.make()
    assert result.inner.name == "nested"
