# ruff: noqa: F811
# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportArgumentType=false
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
    """Test that default_factory works correctly.

    Edge case: Each read of an unset default_factory field calls the factory again.
    This is consistent with dataclass semantics but may be surprising. The freezing
    only prevents writes, not re-evaluation of defaults.
    """
    call_count = 0

    def counting_factory() -> list[int]:
        nonlocal call_count
        call_count += 1
        return []

    @chz.chz
    class Config:
        items: list[int] = chz.field(default_factory=counting_factory)

    bp = chz.Blueprint(Config)
    m = bp.mud()

    # First read calls factory
    items1 = m.items
    assert items1 == []
    assert call_count == 1

    # Second read calls factory again (stateless design - no caching of defaults)
    items2 = m.items
    assert items2 == []
    assert call_count == 2

    # The lists are different instances
    assert items1 is not items2

    # Field is frozen after first read, so writes fail
    with pytest.raises(FrozenPropertyError):
        m.items = [1, 2, 3]

    # make() uses the default (calls factory one more time)
    result = bp.make()
    assert result.items == []


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
    # Both logical name and raw name should work
    assert bp.is_mud_frozen("base")
    assert bp.is_mud_frozen("X_base")  # Raw name also accepted


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


def test_mud_assign_instance_before_freeze():
    """Test that assigning a chz instance works before freezing."""

    @chz.chz
    class Inner:
        x: int
        y: str = "default"

    @chz.chz
    class Outer:
        inner: Inner

    bp = chz.Blueprint(Outer)
    m = bp.mud()

    # Assign a complete instance (before any reads)
    m.inner = Inner(x=42, y="assigned")

    result = bp.make()
    assert result.inner.x == 42
    assert result.inner.y == "assigned"


def test_mud_polymorphic_assign_child_instance():
    """Test assigning a child instance to a polymorphic field."""

    @chz.chz
    class Parent:
        x: int

    @chz.chz
    class Child(Parent):
        y: int

    @chz.chz
    class Main:
        field: Parent = chz.field(blueprint_unspecified=Child)

    bp = chz.Blueprint(Main)
    m = bp.mud()

    # Assign a Child instance to a Parent-typed field
    m.field = Child(x=10, y=20)

    result = bp.make()
    assert isinstance(result.field, Child)
    assert result.field.x == 10
    assert result.field.y == 20


def test_mud_polymorphic_subcomponents():
    """Test that subcomponent access works for polymorphic fields."""

    @chz.chz
    class Parent:
        x: int

    @chz.chz
    class Child(Parent):
        y: int = 0

    @chz.chz
    class Main:
        field: Parent = chz.field(blueprint_unspecified=Child)

    bp = chz.Blueprint(Main)
    m = bp.mud()

    # Setting parent field via MudView works
    m.field.x = 10

    # Blueprint constructs Child at make() time
    result = bp.make()
    assert isinstance(result.field, Child)
    assert result.field.x == 10
    assert result.field.y == 0  # default


def test_mud_polymorphic_child_only_field_error():
    """Document limitation: child-only fields raise AttributeError via MudView."""

    @chz.chz
    class Parent:
        x: int

    @chz.chz
    class Child(Parent):
        y: int

    @chz.chz
    class Main:
        field: Parent = chz.field(blueprint_unspecified=Child)

    bp = chz.Blueprint(Main)
    m = bp.mud()

    # MudView thinks field is Parent, so y is not accessible
    with pytest.raises(AttributeError, match="has no field"):
        m.field.y = 20

    # Note: Accessing m.field above freezes "field", so we need a fresh Blueprint
    # to demonstrate the workaround
    bp2 = chz.Blueprint(Main)
    m2 = bp2.mud()

    # Workaround 1: assign a complete instance
    m2.field = Child(x=10, y=20)
    result = bp2.make()
    assert result.field.y == 20

    # Workaround 2: use mud(path, child_type) for polymorphic access
    bp3 = chz.Blueprint(Main)
    field = bp3.mud("field", Child)
    field.x = 10
    field.y = 20  # Now accessible!
    result = bp3.make()
    assert result.field.x == 10
    assert result.field.y == 20


def test_mud_polymorphic_nested_access():
    """Test mud(path, child_type) for polymorphic nested field access."""

    @chz.chz
    class Parent:
        x: int

    @chz.chz
    class Child(Parent):
        y: int
        z: str = "default"

    @chz.chz
    class Main:
        field: Parent = chz.field(blueprint_unspecified=Child)
        name: str = "main"

    bp = chz.Blueprint(Main)

    # Access root mud for non-polymorphic fields
    m = bp.mud()
    m.name = "test"

    # Access polymorphic field with child type
    field = bp.mud("field", Child)
    field.x = 10
    field.y = 20
    field.z = "custom"

    result = bp.make()
    assert result.name == "test"
    assert isinstance(result.field, Child)
    assert result.field.x == 10
    assert result.field.y == 20
    assert result.field.z == "custom"


def test_mud_polymorphic_deeply_nested():
    """Test mud(path, child_type) for deeply nested polymorphic fields."""

    @chz.chz
    class Base:
        a: int

    @chz.chz
    class Derived(Base):
        b: int

    @chz.chz
    class Container:
        item: Base = chz.field(blueprint_unspecified=Derived)

    @chz.chz
    class Root:
        container: Container

    bp = chz.Blueprint(Root)

    # Access deeply nested polymorphic field
    item = bp.mud("container.item", Derived)
    item.a = 1
    item.b = 2

    result = bp.make()
    assert isinstance(result.container.item, Derived)
    assert result.container.item.a == 1
    assert result.container.item.b == 2


def test_mud_polymorphic_freezing():
    """Test that mud(path, child_type) respects freezing semantics."""

    @chz.chz
    class Parent:
        x: int

    @chz.chz
    class Child(Parent):
        y: int

    @chz.chz
    class Main:
        field: Parent = chz.field(blueprint_unspecified=Child)

    bp = chz.Blueprint(Main)

    field = bp.mud("field", Child)
    field.x = 10
    field.y = 20

    # Reading freezes the field
    _ = field.x

    # Can't write to frozen field
    with pytest.raises(FrozenPropertyError):
        field.x = 100

    # But can still write to non-frozen field
    field.y = 30

    result = bp.make()
    assert result.field.x == 10
    assert result.field.y == 30


# =============================================================================
# Edge case tests for cache invalidation, consolidation, and freeze semantics
# =============================================================================


def test_consolidation_invalidated_by_mud_write():
    """Test that writing via mud invalidates consolidation."""

    @chz.chz
    class Config:
        a: int
        b: int = 0

    bp = chz.Blueprint(Config)
    m = bp.mud()

    # Force consolidation
    bp._arg_map.consolidate()
    assert bp._arg_map.consolidated

    # Write via mud should invalidate consolidation
    m.a = 1
    assert not bp._arg_map.consolidated

    # Re-consolidate
    bp._arg_map.consolidate()
    assert bp._arg_map.consolidated

    # Another write should invalidate again
    m.b = 2
    assert not bp._arg_map.consolidated

    # Final make should work
    result = bp.make()
    assert result.a == 1
    assert result.b == 2


def test_consolidation_invalidated_by_polymorphic_mud():
    """Test that mud(path, child_type) invalidates consolidation."""

    @chz.chz
    class Parent:
        x: int

    @chz.chz
    class Child(Parent):
        y: int

    @chz.chz
    class Main:
        field: Parent = chz.field(blueprint_unspecified=Child)

    bp = chz.Blueprint(Main)

    # Force consolidation
    bp._arg_map.consolidate()
    assert bp._arg_map.consolidated

    # Polymorphic mud should invalidate (applies type to Blueprint)
    field = bp.mud("field", Child)
    assert not bp._arg_map.consolidated

    # Write should also invalidate
    bp._arg_map.consolidate()
    field.y = 20
    assert not bp._arg_map.consolidated


def test_frozen_shared_between_root_and_polymorphic_mud():
    """Test that frozen state is shared between root mud and polymorphic mud views."""

    @chz.chz
    class Parent:
        x: int

    @chz.chz
    class Child(Parent):
        y: int

    @chz.chz
    class Main:
        field: Parent = chz.field(blueprint_unspecified=Child)

    bp = chz.Blueprint(Main)

    # Get polymorphic mud view and set + freeze a field
    field = bp.mud("field", Child)
    field.x = 10
    _ = field.x  # Freeze "field.x"

    # Frozen state should be visible via Blueprint
    assert bp.is_mud_frozen("field.x")

    # Get another polymorphic mud view - should see same frozen state
    field2 = bp.mud("field", Child)
    with pytest.raises(FrozenPropertyError):
        field2.x = 20

    # Root mud view accessing nested field should also respect frozen state
    m = bp.mud()
    # Note: m.field creates a MudView for Parent, but frozen paths are shared
    # Accessing m.field freezes "field" but "field.x" is already frozen
    nested = m.field
    with pytest.raises(FrozenPropertyError):
        nested.x = 30


def test_frozen_path_prefixing_correct():
    """Test that frozen paths are correctly prefixed for nested views."""

    @chz.chz
    class Inner:
        a: int
        b: int

    @chz.chz
    class Outer:
        inner: Inner
        c: int

    bp = chz.Blueprint(Outer)
    m = bp.mud()

    # Set values
    m.inner.a = 1
    m.inner.b = 2
    m.c = 3

    # Freeze inner.a by reading it
    _ = m.inner.a

    # Check correct path is frozen
    assert bp.is_mud_frozen("inner.a")
    assert not bp.is_mud_frozen("inner.b")
    assert not bp.is_mud_frozen("c")

    # Can't write to frozen path
    with pytest.raises(FrozenPropertyError):
        m.inner.a = 100

    # Can still write to non-frozen paths
    m.inner.b = 20
    m.c = 30

    result = bp.make()
    assert result.inner.a == 1
    assert result.inner.b == 20
    assert result.c == 30


def test_polymorphic_mud_multiple_calls_same_type():
    """Test calling mud(path, type) multiple times with same type."""

    @chz.chz
    class Parent:
        x: int

    @chz.chz
    class Child(Parent):
        y: int

    @chz.chz
    class Main:
        field: Parent = chz.field(blueprint_unspecified=Child)

    bp = chz.Blueprint(Main)

    # First call
    field1 = bp.mud("field", Child)
    field1.x = 10
    field1.y = 20

    # Second call - should get fresh MudView but same Blueprint state
    field2 = bp.mud("field", Child)
    # Values should be visible (not cached in MudView)
    bp._arg_map.consolidate()
    assert bp._arg_map.get_kv("field.x").value == 10
    assert bp._arg_map.get_kv("field.y").value == 20

    # Overwrite via second view
    field2.y = 30

    result = bp.make()
    assert result.field.x == 10
    assert result.field.y == 30


def test_polymorphic_mud_different_types_override():
    """Test that calling mud(path, type) with different types overrides.

    When switching types, old type-specific fields become extraneous.
    This test documents the correct behavior.
    """
    from chz.blueprint._entrypoint import ExtraneousBlueprintArg

    @chz.chz
    class Parent:
        x: int

    @chz.chz
    class Child1(Parent):
        y: int = 0

    @chz.chz
    class Child2(Parent):
        z: int = 0

    @chz.chz
    class Main:
        field: Parent

    bp = chz.Blueprint(Main)

    # First call selects Child1 and sets a Child1-specific field
    field1 = bp.mud("field", Child1)
    field1.x = 10
    field1.y = 20  # Child1-specific

    # Second call selects Child2 - the type override works
    field2 = bp.mud("field", Child2)
    field2.x = 100
    field2.z = 200  # Child2-specific

    # BUT: field.y from Child1 is now extraneous (Child2 doesn't have y)
    # This correctly raises an error at make() time
    with pytest.raises(ExtraneousBlueprintArg, match="field.y"):
        bp.make()


def test_polymorphic_mud_type_switch_clean():
    """Test switching types when no type-specific fields are set."""

    @chz.chz
    class Parent:
        x: int

    @chz.chz
    class Child1(Parent):
        y: int = 0

    @chz.chz
    class Child2(Parent):
        z: int = 0

    @chz.chz
    class Main:
        field: Parent

    bp = chz.Blueprint(Main)

    # First call selects Child1, only set shared field
    field1 = bp.mud("field", Child1)
    field1.x = 10
    # Don't set y

    # Second call selects Child2
    field2 = bp.mud("field", Child2)
    field2.x = 100  # Override shared field
    field2.z = 200  # Set Child2-specific

    # This works because we didn't set any Child1-specific fields
    result = bp.make()
    assert isinstance(result.field, Child2)
    assert result.field.x == 100
    assert result.field.z == 200


def test_root_mud_after_polymorphic_mud():
    """Test that root mud still works after polymorphic mud."""

    @chz.chz
    class Parent:
        x: int

    @chz.chz
    class Child(Parent):
        y: int

    @chz.chz
    class Main:
        field: Parent = chz.field(blueprint_unspecified=Child)
        name: str = "default"

    bp = chz.Blueprint(Main)

    # Use polymorphic mud first
    field = bp.mud("field", Child)
    field.x = 10
    field.y = 20

    # Root mud should still work
    m = bp.mud()
    m.name = "test"

    # Root mud's nested view is for Parent type (can't access y)
    nested = m.field
    with pytest.raises(AttributeError, match="has no field"):
        nested.y = 30  # Can't access Child-only field via Parent view

    result = bp.make()
    assert result.name == "test"
    assert result.field.x == 10
    assert result.field.y == 20


def test_polymorphic_mud_preserves_prior_writes():
    """Test that polymorphic mud preserves writes made before type selection."""

    @chz.chz
    class Parent:
        x: int

    @chz.chz
    class Child(Parent):
        y: int

    @chz.chz
    class Main:
        field: Parent = chz.field(blueprint_unspecified=Child)

    bp = chz.Blueprint(Main)

    # Write via root mud first (uses Parent view)
    m = bp.mud()
    m.field.x = 10

    # Then get polymorphic view and add child-specific field
    field = bp.mud("field", Child)
    field.y = 20

    # Both writes should be preserved
    result = bp.make()
    assert result.field.x == 10
    assert result.field.y == 20


def test_apply_after_mud_freeze():
    """Test that Blueprint.apply() respects frozen state from mud."""

    @chz.chz
    class Config:
        a: int
        b: int = 0

    bp = chz.Blueprint(Config)
    m = bp.mud()
    m.a = 1
    _ = m.a  # Freeze 'a'

    # Direct apply should still work (apply doesn't check frozen)
    # But mud writes after reading should fail
    with pytest.raises(FrozenPropertyError):
        m.a = 2

    # Blueprint.apply bypasses mud frozen checks (it's a different API)
    bp.apply({"b": 10})

    result = bp.make()
    assert result.a == 1
    assert result.b == 10


def test_clone_after_polymorphic_mud():
    """Test that clone preserves state from polymorphic mud."""

    @chz.chz
    class Parent:
        x: int

    @chz.chz
    class Child(Parent):
        y: int

    @chz.chz
    class Main:
        field: Parent = chz.field(blueprint_unspecified=Child)

    bp = chz.Blueprint(Main)

    # Use polymorphic mud
    field = bp.mud("field", Child)
    field.x = 10
    field.y = 20
    _ = field.x  # Freeze field.x

    # Clone
    bp2 = bp.clone()

    # Clone should have the values
    result2 = bp2.make()
    assert result2.field.x == 10
    assert result2.field.y == 20

    # Clone should preserve frozen state
    assert bp2.is_mud_frozen("field.x")
    field2 = bp2.mud("field", Child)
    with pytest.raises(FrozenPropertyError):
        field2.x = 100


def test_deeply_nested_polymorphic_freezing():
    """Test freezing in deeply nested polymorphic structures."""

    @chz.chz
    class Base:
        a: int

    @chz.chz
    class Derived(Base):
        b: int

    @chz.chz
    class Middle:
        item: Base = chz.field(blueprint_unspecified=Derived)

    @chz.chz
    class Root:
        middle: Middle
        name: str = "root"

    bp = chz.Blueprint(Root)

    # Access deeply nested polymorphic field
    item = bp.mud("middle.item", Derived)
    item.a = 1
    item.b = 2

    # Freeze a
    _ = item.a
    assert bp.is_mud_frozen("middle.item.a")

    # Can't modify frozen field
    with pytest.raises(FrozenPropertyError):
        item.a = 100

    # Can still modify non-frozen field
    item.b = 20

    # Root mud should work
    m = bp.mud()
    m.name = "test"

    result = bp.make()
    assert result.name == "test"
    assert result.middle.item.a == 1
    assert result.middle.item.b == 20


def test_mud_read_value_consistency():
    """Test that reading via mud returns consistent values."""

    @chz.chz
    class Config:
        a: int
        b: str = "default"

    bp = chz.Blueprint(Config)
    m = bp.mud()

    # Set a value
    m.a = 42

    # Reading should return the set value
    assert m.a == 42

    # Reading default should return default
    assert m.b == "default"

    # After reading, values are frozen
    with pytest.raises(FrozenPropertyError):
        m.a = 100

    # But we should still be able to read
    assert m.a == 42


def test_mud_error_on_invalid_arguments():
    """Test that mud() raises appropriate errors for invalid arguments."""

    @chz.chz
    class Config:
        a: int

    bp = chz.Blueprint(Config)

    # Only path without child_type should fail
    with pytest.raises(ValueError, match="both path and child_type"):
        bp.mud("a", None)

    # Only child_type without path should fail
    with pytest.raises(ValueError, match="both path and child_type"):
        bp.mud(None, Config)


def test_mud_error_on_non_chz_child_type():
    """Test that mud(path, child_type) requires child_type to be a chz class."""

    @chz.chz
    class Config:
        field: object

    class NotChz:
        pass

    bp = chz.Blueprint(Config)

    with pytest.raises(TypeError, match="requires child_type to be a chz class"):
        bp.mud("field", NotChz)

    with pytest.raises(TypeError, match="requires child_type to be a chz class"):
        bp.mud("field", str)
