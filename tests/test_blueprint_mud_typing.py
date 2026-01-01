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


def test_blueprint_mud_typing() -> None:
    view = chz.Blueprint(Parent).mud()
    view.value = 1
    assert_type(view.value, int)
    assert_type(view.child, Child)
