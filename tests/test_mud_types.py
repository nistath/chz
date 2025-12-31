# Type checking tests for mud module
# This file is checked by pyright to verify type annotations are correct
#
# Run: uv run pyright tests/test_mud_types.py

import chz
from chz.mud import MudView


@chz.chz
class TypedConfig:
    name: str
    count: int = 0


@chz.chz
class NestedConfig:
    inner: TypedConfig
    label: str = "default"


def test_blueprint_mud_types() -> None:
    """Test that Blueprint.mud() returns MudView[T] with proper typing."""
    bp = chz.Blueprint(TypedConfig)
    m: MudView[TypedConfig] = bp.mud()

    # Field assignment (type checker sees these as field assignments)
    m.name = "hello"  # type: ignore[assignment]  # Dynamic assignment
    m.count = 42  # type: ignore[assignment]

    # make() returns the correct type
    result: TypedConfig = bp.make()
    assert result.name == "hello"


def test_mudview_methods_typed() -> None:
    """Test that MudView methods are properly typed."""
    bp = chz.Blueprint(TypedConfig)
    m = bp.mud()

    # is_frozen returns bool
    frozen: bool = m.is_frozen("name")

    # get_frozen_fields returns set[str]
    fields: set[str] = m.get_frozen_fields()

    _ = (frozen, fields)


def test_nested_mud_types() -> None:
    """Test type checking for nested chz fields."""
    bp = chz.Blueprint(NestedConfig)
    m = bp.mud()
    m.label = "test"  # type: ignore[assignment]

    # Access nested field - returns MudView at runtime
    inner = m.inner
    inner.name = "nested"  # type: ignore[misc]
    inner.count = 5  # type: ignore[misc]

    result = bp.make()
    assert result.inner.name == "nested"


# NOTE: Field assignment type checking has limitations due to dynamic __getattr__.
# The following would NOT be caught as errors by pyright:
#
# m.name = 123      # Wrong type - NOT caught by pyright
# m.count = "hello" # Wrong type - NOT caught by pyright
#
# This is a fundamental limitation of Python's type system with dynamic __getattr__.
# Runtime type checking happens via chz's validators when make() is called.
