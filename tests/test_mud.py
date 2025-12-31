# ruff: noqa: F811
import pytest

import chz
from chz.mud import FrozenPropertyError, MudView


def test_blueprint_mud_basic():
    """Test basic Blueprint.mud() usage."""

    @chz.chz
    class Config:
        name: str
        count: int = 0

    bp = chz.Blueprint(Config)
    m = bp.mud()

    assert isinstance(m, MudView)

    m.name = "hello"
    m.count = 42

    config = bp.make()
    assert config.name == "hello"
    assert config.count == 42


def test_blueprint_mud_read_freezing():
    """Test that reads freeze values."""

    @chz.chz
    class Config:
        a: int
        b: str = "default"

    bp = chz.Blueprint(Config)
    m = bp.mud()
    m.a = 1
    m.b = "hello"

    # Read a - should freeze it
    _ = m.a

    # Now writing to a should fail
    with pytest.raises(FrozenPropertyError, match="already been read"):
        m.a = 2

    # But we can still write to b (not read yet)
    m.b = "world"

    config = bp.make()
    assert config.a == 1
    assert config.b == "world"


def test_is_frozen():
    """Test the is_frozen method."""

    @chz.chz
    class Config:
        a: int
        b: str = "default"

    bp = chz.Blueprint(Config)
    m = bp.mud()
    m.a = 1

    assert not m.is_frozen("a")
    assert not m.is_frozen("b")

    _ = m.a

    assert m.is_frozen("a")
    assert not m.is_frozen("b")


def test_get_frozen_fields():
    """Test getting all frozen fields."""

    @chz.chz
    class Config:
        a: int
        b: str = "default"
        c: float = 1.0

    bp = chz.Blueprint(Config)
    m = bp.mud()
    m.a = 1
    m.b = "test"
    m.c = 2.0

    assert m.get_frozen_fields() == set()

    _ = m.a
    _ = m.c

    assert m.get_frozen_fields() == {"a", "c"}


def test_nested_mud():
    """Test recursive mud for nested chz classes."""

    @chz.chz
    class Inner:
        x: int
        y: str = "default"

    @chz.chz
    class Outer:
        inner: Inner
        name: str = "outer"

    bp = chz.Blueprint(Outer)
    m = bp.mud()
    m.inner.x = 42
    m.inner.y = "hello"
    m.name = "my_outer"

    result = bp.make()
    assert result.inner.x == 42
    assert result.inner.y == "hello"
    assert result.name == "my_outer"


def test_nested_mud_freezing():
    """Test that nested field access freezes the parent field."""

    @chz.chz
    class Inner:
        x: int

    @chz.chz
    class Outer:
        inner: Inner

    bp = chz.Blueprint(Outer)
    m = bp.mud()

    # Accessing inner should freeze it
    _ = m.inner

    # We can still set properties on the nested mud
    m.inner.x = 42

    # But we can't replace inner itself
    with pytest.raises(FrozenPropertyError):
        m.inner = Inner(x=100)

    assert bp.make().inner.x == 42


def test_deeply_nested_mud():
    """Test deeply nested chz structures."""

    @chz.chz
    class Level3:
        value: int

    @chz.chz
    class Level2:
        level3: Level3

    @chz.chz
    class Level1:
        level2: Level2

    bp = chz.Blueprint(Level1)
    m = bp.mud()
    m.level2.level3.value = 123

    result = bp.make()
    assert result.level2.level3.value == 123


def test_defaults():
    """Test that defaults work correctly with mud."""

    @chz.chz
    class Config:
        a: int
        b: str = "default"
        c: list[int] = chz.field(default_factory=list)

    bp = chz.Blueprint(Config)
    m = bp.mud()
    m.a = 1
    # Don't set b or c

    config = bp.make()
    assert config.a == 1
    assert config.b == "default"
    assert config.c == []


def test_mud_singleton():
    """Test that bp.mud() returns the same view."""

    @chz.chz
    class Config:
        x: int

    bp = chz.Blueprint(Config)
    m1 = bp.mud()
    m2 = bp.mud()

    assert m1 is m2


def test_mud_with_existing_apply():
    """Test mud works with existing Blueprint.apply()."""

    @chz.chz
    class Config:
        a: int
        b: str = "default"

    bp = chz.Blueprint(Config)
    bp.apply({"a": 10})

    m = bp.mud()
    m.b = "from_mud"

    config = bp.make()
    assert config.a == 10
    assert config.b == "from_mud"


def test_error_on_non_chz():
    """Test that mud() raises for non-chz classes."""

    class NotChz:
        pass

    bp = chz.Blueprint(NotChz)
    with pytest.raises(TypeError, match="requires a chz class"):
        bp.mud()


def test_error_on_unknown_field():
    """Test that accessing unknown fields raises AttributeError."""

    @chz.chz
    class Config:
        a: int

    bp = chz.Blueprint(Config)
    m = bp.mud()

    with pytest.raises(AttributeError, match="has no field"):
        m.unknown_field = 1

    with pytest.raises(AttributeError, match="has no field"):
        _ = m.unknown_field


def test_optional_field():
    """Test handling of Optional[ChzClass] fields."""

    @chz.chz
    class Inner:
        x: int

    @chz.chz
    class Outer:
        inner: Inner | None = None

    bp = chz.Blueprint(Outer)
    m = bp.mud()

    # Access the optional field - should create nested mud
    inner = m.inner
    assert isinstance(inner, MudView)
    inner.x = 42

    result = bp.make()
    assert result.inner is not None
    assert result.inner.x == 42


def test_x_field_handling():
    """Test handling of X_ prefixed fields (mungers)."""

    @chz.chz
    class Config:
        # When you have X_ prefix with a munger, chz auto-generates the value init_property
        X_value: int = chz.field(munger=lambda self, v: v * 2)

    bp = chz.Blueprint(Config)
    m = bp.mud()
    # Should be able to set via logical name "value"
    m.value = 5

    config = bp.make()
    # The raw value should be stored in X_value
    assert config.X_value == 5
    # The munger is applied to create the computed "value"
    assert config.value == 10


def test_mud_method():
    """Test calling methods on mud."""

    @chz.chz
    class Config:
        x: int
        y: int

        def sum(self):
            return self.x + self.y

    bp = chz.Blueprint(Config)
    m = bp.mud()
    m.x = 3
    m.y = 5

    assert m.sum() == 8
    # x and y are now frozen (accessed by method)
    assert m.is_frozen("x")
    assert m.is_frozen("y")


def test_mud_property():
    """Test @property on mud."""

    @chz.chz
    class Config:
        x: int

        @property
        def doubled(self):
            return self.x * 2

    bp = chz.Blueprint(Config)
    m = bp.mud()
    m.x = 5

    assert m.doubled == 10


def test_mud_init_property_lazy():
    """Test init_property is lazy on mud."""
    call_count = 0

    @chz.chz
    class Config:
        X_base: int

        @chz.init_property
        def base(self):
            nonlocal call_count
            call_count += 1
            return self.X_base * 2

    bp = chz.Blueprint(Config)
    m = bp.mud()
    m.X_base = 5

    # Not evaluated yet
    assert call_count == 0

    # First access evaluates
    assert m.base == 10
    assert call_count == 1

    # Second access uses cache
    assert m.base == 10
    assert call_count == 1

    # X_base is frozen (accessed by init_property)
    assert m.is_frozen("X_base")


def test_mud_method_uses_init_property():
    """Test method that uses init_property."""

    @chz.chz
    class Config:
        X_value: int

        @chz.init_property
        def value(self):
            return self.X_value * 2

        def compute(self):
            return self.value + 10

    bp = chz.Blueprint(Config)
    m = bp.mud()
    m.X_value = 5

    assert m.compute() == 20  # (5*2) + 10


def test_repr():
    """Test string representation."""

    @chz.chz
    class Config:
        a: int
        b: str = "default"

    bp = chz.Blueprint(Config)
    m = bp.mud()

    repr_str = repr(m)
    assert "MudView" in repr_str
    assert "Config" in repr_str
