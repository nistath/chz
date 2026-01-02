from __future__ import annotations

import collections
import functools
import typing
from dataclasses import dataclass
from typing import Any, Iterable

import chz
from chz.blueprint._argmap import join_arg_path
from chz.blueprint._entrypoint import MissingBlueprintArg
from chz.blueprint._lazy import ParamRef, Thunk, Value
from chz.data_model import FrozenInstanceError, init_property, is_chz


@dataclass(frozen=True)
class _ReadLayer:
    paths: tuple[str, ...]
    layer_name: str | None


def _iter_prefixes(path: str) -> Iterable[str]:
    if path == "":
        yield ""
        return
    prefix = ""
    for part in path.split("."):
        prefix = part if not prefix else f"{prefix}.{part}"
        yield prefix


def _add_frozen_path(blueprint, path: str) -> None:
    blueprint._mud_frozen_paths.add(path)
    for prefix in _iter_prefixes(path):
        blueprint._mud_frozen_prefixes.add(prefix)


def _record_read_layer(blueprint, path: str, *, layer_name: str | None) -> None:
    blueprint._mud_read_layers.append(_ReadLayer(paths=(path,), layer_name=layer_name))


def _freeze_paths(blueprint, paths: Iterable[str]) -> None:
    for path in paths:
        _add_frozen_path(blueprint, path)


def _is_frozen(blueprint, path: str) -> bool:
    if "" in blueprint._mud_frozen_paths:
        return True
    if path in blueprint._mud_frozen_prefixes:
        return True
    if path:
        prefix = ""
        for part in path.split(".")[:-1]:
            prefix = part if not prefix else f"{prefix}.{part}"
            if prefix in blueprint._mud_frozen_paths:
                return True
    return False


def _is_chz_type(obj: Any) -> bool:
    origin = getattr(obj, "__origin__", None)
    if origin is not None:
        obj = origin
    return is_chz(obj)


def _normalize_chz_type(obj: Any) -> Any:
    origin = getattr(obj, "__origin__", None)
    return origin if origin is not None else obj


def _evaluate_path(
    path: str,
    *,
    value_mapping: dict[str, Any],
    all_params: dict[str, Any],
) -> Any:
    cache: dict[str, Any] = {}
    refs_in_progress = collections.OrderedDict[str, None]()

    def resolve(ref: str) -> Any:
        if ref in cache:
            return cache[ref]
        if ref in refs_in_progress:
            cycle = " -> ".join(list(refs_in_progress.keys())[1:] + [ref])
            raise RecursionError(f"Detected cyclic reference: {cycle}")

        refs_in_progress[ref] = None
        try:
            if ref in value_mapping:
                value = value_mapping[ref]
                if isinstance(value, Value):
                    result = value.value
                elif isinstance(value, ParamRef):
                    result = resolve(value.ref)
                elif isinstance(value, Thunk):
                    kwargs = {k: resolve(v.ref) for k, v in value.kwargs.items()}
                    result = value.fn(**kwargs)
                else:
                    raise AssertionError(f"Unexpected evaluatable: {value!r}")
            else:
                param = all_params.get(ref)
                if param is None or param.default is None:
                    raise MissingBlueprintArg(
                        f"Missing required arguments for parameter(s): {ref}"
                    )
                if param.default.value is typing.NotRequired:
                    raise MissingBlueprintArg(
                        f"Missing required arguments for parameter(s): {ref}"
                    )
                result = param.default.instantiate()
            cache[ref] = result
            return result
        finally:
            item = refs_in_progress.popitem()
            assert item[0] == ref

    return resolve(path)


def _dependencies_for_path(path: str, value_mapping: dict[str, Any]) -> set[str]:
    deps: set[str] = set()
    visited: set[str] = set()

    def walk(ref: str) -> None:
        if ref in visited:
            return
        visited.add(ref)
        value = value_mapping.get(ref)
        if isinstance(value, ParamRef):
            deps.add(value.ref)
            walk(value.ref)
        elif isinstance(value, Thunk):
            for param_ref in value.kwargs.values():
                deps.add(param_ref.ref)
                walk(param_ref.ref)

    walk(path)
    deps.discard(path)
    return deps


class _MudInitProperty:
    def __init__(self, prop: init_property[Any]) -> None:
        self._prop = prop
        self.func = prop.func
        self.name = getattr(prop, "name", None)

    def __get__(self, obj: Any, cls: Any) -> Any:
        if obj is None:
            return self
        if getattr(obj, "_mud_thaw", False):
            return self.func(obj)
        return self._prop.__get__(obj, cls)


def _chz_type_from_factory(factory: Any) -> type | None:
    if isinstance(factory, functools.partial):
        factory = factory.func
    if isinstance(factory, type) and is_chz(factory):
        return factory
    return None


def _resolve_mud_view_type(obj: Any, path: str, field: Any) -> type:
    base_type = _normalize_chz_type(field.x_type)
    meta_factory = field.meta_factory
    if meta_factory is None:
        return base_type

    make_result = obj._mud_state.blueprint._make_lazy()
    factory = make_result.meta_factory_value.get(path)
    if factory is None:
        factory = meta_factory.unspecified_factory()
    if factory is None:
        return base_type

    target_cls = _chz_type_from_factory(factory)
    if target_cls is None:
        raise TypeError(
            f"Cannot create mud view for {path!r}; factory {factory!r} is not a chz class"
        )
    return target_cls


class _MudField:
    def __init__(self, name: str, field: Any) -> None:
        self.name = name
        self.field = field
        self.field_type = field.x_type
        self.is_chz = _is_chz_type(self.field_type)

    def __get__(self, obj: Any, cls: Any) -> Any:
        if obj is None:
            return self
        path = join_arg_path(obj._mud_path, self.name)
        if self.is_chz:
            target_cls = _resolve_mud_view_type(obj, path, self.field)
            view_cls = _make_view_class(target_cls)
            return _make_view(obj._mud_state, path, thaw=obj._mud_thaw, view_cls=view_cls)
        return _mud_get_value(obj, path, thaw=obj._mud_thaw)

    def __set__(self, obj: Any, value: Any) -> None:
        path = join_arg_path(obj._mud_path, self.name)
        _mud_set_value(obj, path, value, thaw=obj._mud_thaw)


_MUD_VIEW_CACHE: dict[type, type] = {}


def _make_view_class(target_cls: type) -> type:
    if target_cls in _MUD_VIEW_CACHE:
        return _MUD_VIEW_CACHE[target_cls]

    fields = chz.chz_fields(target_cls)
    field_names = set(fields.keys())

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"_mud_state", "_mud_path", "_mud_thaw"}:
            object.__setattr__(self, name, value)
            return
        if name in field_names:
            path = join_arg_path(self._mud_path, name)
            _mud_set_value(self, path, value, thaw=self._mud_thaw)
            return
        descriptor = getattr(type(self), name, None)
        if descriptor is not None and hasattr(descriptor, "__set__"):
            descriptor.__set__(self, value)
            return
        raise FrozenInstanceError(f"Cannot modify field {name!r}")

    attrs: dict[str, Any] = {
        "__setattr__": __setattr__,
    }

    for name, field in fields.items():
        attrs[name] = _MudField(name, field)

    for name, obj in target_cls.__dict__.items():
        if isinstance(obj, init_property) and name not in field_names:
            attrs[name] = _MudInitProperty(obj)

    view_cls = type(f"Mud{target_cls.__name__}", (target_cls,), attrs)
    _MUD_VIEW_CACHE[target_cls] = view_cls
    return view_cls


class _MudState:
    def __init__(self, blueprint) -> None:
        self.blueprint = blueprint


def _make_view(state: _MudState, path: str, *, thaw: bool, view_cls: type) -> Any:
    obj: Any = object.__new__(view_cls)
    object.__setattr__(obj, "_mud_state", state)
    object.__setattr__(obj, "_mud_path", path)
    object.__setattr__(obj, "_mud_thaw", thaw)
    return obj


def _mud_get_value(obj: Any, path: str, *, thaw: bool) -> Any:
    make_result = obj._mud_state.blueprint._make_lazy()
    value = _evaluate_path(
        path,
        value_mapping=make_result.value_mapping,
        all_params=make_result.all_params,
    )
    if not thaw:
        deps = _dependencies_for_path(path, make_result.value_mapping)
        layer_name = f"mud:read#{obj._mud_state.blueprint._mud_read_index + 1}"
        _record_read_layer(obj._mud_state.blueprint, path, layer_name=layer_name)
        obj._mud_state.blueprint._mud_read_index += 1
        _freeze_paths(obj._mud_state.blueprint, {path, *deps})
    return value


def _mud_set_value_for_blueprint(
    blueprint: Any, path: str, value: Any, *, thaw: bool
) -> None:
    if not thaw and _is_frozen(blueprint, path):
        raise FrozenInstanceError(f"Cannot modify frozen field {path!r}")
    blueprint._mud_write_index += 1
    blueprint.apply({path: value}, layer_name=f"mud:set#{blueprint._mud_write_index}")


def _mud_set_value(obj: Any, path: str, value: Any, *, thaw: bool) -> None:
    _mud_set_value_for_blueprint(obj._mud_state.blueprint, path, value, thaw=thaw)


def make_mud_view(blueprint, *, thaw: bool) -> Any:
    target = blueprint.target
    if not isinstance(target, type) or not is_chz(target):
        raise TypeError("Blueprint.mud is only supported for chz classes")
    state = _MudState(blueprint)
    view_cls = _make_view_class(target)
    return _make_view(state, "", thaw=thaw, view_cls=view_cls)


def make_mud_view_at(
    blueprint, path: str, target_cls: type, *, thaw: bool
) -> Any:
    if not isinstance(target_cls, type) or not is_chz(target_cls):
        raise TypeError("Blueprint.mud_view requires a chz class")
    _mud_set_value_for_blueprint(blueprint, path, target_cls, thaw=thaw)
    state = _MudState(blueprint)
    view_cls = _make_view_class(target_cls)
    return _make_view(state, path, thaw=thaw, view_cls=view_cls)
