from typing import Any, cast

import pytest

import chz
from chz.blueprint import MissingBlueprintArg


def test_blueprint_mud_read_write_freeze():
    @chz.chz
    class Foo:
        a: int
        b: int = 10

    bp = chz.Blueprint(Foo)
    view = bp.mud()

    view.a = 1
    assert view.a == 1
    with pytest.raises(chz.data_model.FrozenInstanceError):
        view.a = 2

    assert view.b == 10
    with pytest.raises(chz.data_model.FrozenInstanceError):
        view.b = 11

    assert len(bp._mud_read_layers) == 2


def test_blueprint_mud_missing_required():
    @chz.chz
    class Foo:
        a: int

    view = chz.Blueprint(Foo).mud()
    with pytest.raises(MissingBlueprintArg):
        _ = view.a


def test_blueprint_mud_nested_view():
    @chz.chz
    class Child:
        x: int

    @chz.chz
    class Parent:
        child: Child

    view = chz.Blueprint(Parent).mud()
    view.child.x = 1
    assert view.child.x == 1

    with pytest.raises(chz.data_model.FrozenInstanceError):
        view.child.x = 2


def test_blueprint_mud_polymorphic_default_subclass():
    @chz.chz
    class Base:
        a: int

    @chz.chz
    class Child(Base):
        b: int

    @chz.chz
    class Parent:
        child: Base = chz.field(
            meta_factory=chz.factories.subclass(Base, default_cls=Child)
        )

    view = chz.Blueprint(Parent).mud()
    child = cast(Child, view.child)
    child.a = 1
    child.b = 2
    assert child.a == 1
    assert child.b == 2


def test_blueprint_mud_polymorphic_select_subclass():
    @chz.chz
    class Base:
        a: int

    @chz.chz
    class Child(Base):
        b: int

    @chz.chz
    class Parent:
        child: Base = chz.field(
            meta_factory=chz.factories.subclass(Base, default_cls=Base)
        )

    bp = chz.Blueprint(Parent)
    view = bp.mud()
    with pytest.raises(chz.data_model.FrozenInstanceError):
        cast(Any, view.child).b = 1

    child = bp.mud_view("child", Child)
    child.b = 3
    assert child.b == 3


def test_blueprint_mud_polymorphic_castable():
    @chz.chz
    class Base:
        a: int

    @chz.chz
    class Child(Base):
        b: int

    @chz.chz
    class Parent:
        child: Base = chz.field(
            meta_factory=chz.factories.subclass(Base, default_cls=Base)
        )

    bp = chz.Blueprint(Parent)
    bp.apply({"child": chz.blueprint.Castable("Child")})
    view = bp.mud()
    child = cast(Child, view.child)
    child.b = 4
    assert child.b == 4


def test_blueprint_mud_polymorphic_non_chz_factory():
    @chz.chz
    class Base:
        a: int

    def make_child(a: int) -> Base:
        return Base(a=a)

    @chz.chz
    class Parent:
        child: Base = chz.field(meta_factory=chz.factories.function())

    bp = chz.Blueprint(Parent)
    bp.apply({"child": make_child})
    view = bp.mud()

    with pytest.raises(TypeError, match="mud view"):
        _ = view.child


def test_blueprint_mud_shared_freeze_and_thaw():
    @chz.chz
    class Foo:
        a: int

    bp = chz.Blueprint(Foo)
    view1 = bp.mud()
    view2 = bp.mud()

    view1.a = 1
    assert view1.a == 1

    with pytest.raises(chz.data_model.FrozenInstanceError):
        view2.a = 2

    thawed = bp.mud(thaw=True)
    thawed.a = 3
    assert view2.a == 3


def test_blueprint_mud_methods_and_properties():
    @chz.chz
    class Foo:
        a: int

        @property
        def doubled(self) -> int:
            return self.a * 2

        def plus(self, value: int) -> int:
            return self.a + value

    view = chz.Blueprint(Foo).mud()
    view.a = 2
    assert view.doubled == 4
    assert view.plus(3) == 5

    with pytest.raises(chz.data_model.FrozenInstanceError):
        view.a = 3


def test_blueprint_mud_thaw_init_property_no_cache():
    @chz.chz
    class Foo:
        a: int

        @chz.init_property
        def doubled(self) -> int:
            return self.a * 2

    view = chz.Blueprint(Foo).mud(thaw=True)
    view.a = 1
    assert view.doubled == 2
    view.a = 2
    assert view.doubled == 4


def test_blueprint_mud_freezes_reference_dependencies():
    @chz.chz
    class Foo:
        a: int
        b: int

    view = chz.Blueprint(Foo).mud()
    view.a = 1
    view.b = chz.blueprint.Reference("a")
    assert view.b == 1

    with pytest.raises(chz.data_model.FrozenInstanceError):
        view.a = 2


def test_blueprint_mud_requires_chz_class():
    def foo(a: int) -> int:
        return a

    with pytest.raises(TypeError, match="only supported for chz classes"):
        chz.Blueprint(foo).mud()
