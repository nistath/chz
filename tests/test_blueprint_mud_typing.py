from __future__ import annotations

from typing_extensions import assert_type

import chz


@chz.chz
class Child:
    x: int


@chz.chz
class Parent:
    child: Child
    value: int


@chz.chz
class PolyBase:
    a: int


@chz.chz
class PolyChild(PolyBase):
    b: int


@chz.chz
class PolyParent:
    child: PolyBase = chz.field(
        meta_factory=chz.factories.subclass(PolyBase, default_cls=PolyBase)
    )


def _int_value() -> int:
    return 1


def test_blueprint_mud_typing() -> None:
    view = chz.Blueprint[Parent](Parent).mud()
    view.value = _int_value()
    assert_type(view.value, int)
    assert_type(view.child, Child)


def test_blueprint_mud_polymorphic_typing() -> None:
    child_view = chz.Blueprint[PolyParent](PolyParent).mud_view("child", PolyChild)
    child_view.a = _int_value()
    assert_type(child_view.a, int)
    assert_type(child_view, PolyChild)
    child_view.b = _int_value()
    assert_type(child_view.b, int)
