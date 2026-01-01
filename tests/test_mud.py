# ruff: noqa: F811
import pytest

import chz
from chz.mud import FrozenPropertyError


def test_blueprint_mud_basic():
    """Test basic Blueprint.mud() usage."""

    @chz.chz
    class Config:
        name: str
        count: int = 0

    bp = chz.Blueprint(Config)
    m = bp.mud()

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
    """Test the is_mud_frozen method on Blueprint."""

    @chz.chz
    class Config:
        a: int
        b: str = "default"

    bp = chz.Blueprint(Config)
    m = bp.mud()
    m.a = 1

    assert not bp.is_mud_frozen("a")
    assert not bp.is_mud_frozen("b")

    _ = m.a

    assert bp.is_mud_frozen("a")
    assert not bp.is_mud_frozen("b")


def test_get_frozen_fields():
    """Test getting all frozen fields via Blueprint."""

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

    assert bp.get_mud_frozen_fields() == set()

    _ = m.a
    _ = m.c

    assert bp.get_mud_frozen_fields() == {"a", "c"}


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


def test_error_on_unset_field():
    """Test that accessing unset fields raises AttributeError."""

    @chz.chz
    class Config:
        a: int
        b: str = "default"

    bp = chz.Blueprint(Config)
    m = bp.mud()

    # Field with default returns default
    assert m.b == "default"

    # Accessing unset required field raises
    with pytest.raises(AttributeError, match="has not been set"):
        _ = m.a

    # After setting, it works
    m.a = 42
    assert m.a == 42


def test_default_factory():
    """Test that default_factory works correctly."""

    @chz.chz
    class Config:
        items: list[int] = chz.field(default_factory=list)

    bp = chz.Blueprint(Config)
    m = bp.mud()

    # Should return a new list from factory
    items = m.items
    assert items == []

    # Each call should return a new list (factory is called each time before freeze)
    # But reading freezes, so we can't modify via mud anymore


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

    # Access the optional field - should create nested mud view
    inner = m.inner
    # Can set nested fields through the view
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
    assert bp.is_mud_frozen("x")
    assert bp.is_mud_frozen("y")


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
    """Test init_property is lazy on mud (evaluated fresh each access - stateless design)."""
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

    # Second access re-evaluates (stateless - no caching)
    assert m.base == 10
    assert call_count == 2

    # X_base is frozen (accessed by init_property)
    # Note: frozen paths use logical field names, so "X_base" becomes "base"
    assert bp.is_mud_frozen("base")


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


def test_external_blueprint_modification():
    """Test that external Blueprint.apply() works correctly with mud (stateless design)."""

    @chz.chz
    class Config:
        a: int
        b: str = "default"

    bp = chz.Blueprint(Config)
    m = bp.mud()
    m.a = 1

    # External modification via Blueprint.apply()
    bp.apply({"b": "external"})

    # MudView should see the updated value (stateless - reads from Blueprint)
    assert m.b == "external"

    config = bp.make()
    assert config.a == 1
    assert config.b == "external"


def test_frozen_shared_across_mud_calls():
    """Test that frozen state is shared across all mud() calls."""

    @chz.chz
    class Config:
        a: int
        b: str = "default"

    bp = chz.Blueprint(Config)
    m1 = bp.mud()
    m2 = bp.mud()  # Same view (singleton)

    m1.a = 1
    _ = m1.a  # Freeze 'a'

    # Frozen state lives on Blueprint
    assert bp.is_mud_frozen("a")

    # Both should fail to modify 'a'
    with pytest.raises(FrozenPropertyError):
        m2.a = 2


def test_clone_preserves_frozen_state():
    """Test that Blueprint.clone() preserves frozen state."""

    @chz.chz
    class Config:
        a: int
        b: str = "default"

    bp = chz.Blueprint(Config)
    m = bp.mud()
    m.a = 1
    m.b = "hello"
    _ = m.a  # Freeze 'a'

    # Clone the blueprint
    bp2 = bp.clone()

    # Frozen state should be preserved
    assert bp2.is_mud_frozen("a")
    assert not bp2.is_mud_frozen("b")

    # Can't modify frozen field in clone
    m2 = bp2.mud()
    with pytest.raises(FrozenPropertyError):
        m2.a = 2

    # Can still modify non-frozen field
    m2.b = "world"

    # Both blueprints should make valid configs
    config1 = bp.make()
    config2 = bp2.make()
    assert config1.a == 1
    assert config1.b == "hello"
    assert config2.a == 1
    assert config2.b == "world"
