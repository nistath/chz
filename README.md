# 🪤 chz

*(pronounced "चीज़")*

`chz` helps you manage configuration, particularly from the command line.

`chz` is available on [PyPI](https://pypi.org/project/chz/).

To click the links below, please visit [Github](https://github.com/openai/chz).

Overview:
- [Quickstart](docs/01_quickstart.md)
- [Declarative object model](docs/02_object_model.md)
- [Immutability](docs/02_object_model.md#immutability)
- [Validation](docs/03_validation.md)
- [Type checking](docs/03_validation.md#type-checking)
- [Command line parsing](docs/04_command_line.md)
- [Discoverability](docs/04_command_line.md#discoverability---help-and-errors)
- [Partial application](docs/05_blueprint.md)
- [Mutable Blueprint views (mud)](#mutable-blueprint-views-mud)
- [Presets or shared configuration](docs/05_blueprint.md#presets-or-shared-configuration)
- [Serialisation and deserialisation](docs/06_serialisation.md)

More details:
- [Post init](docs/21_post_init.md)
- [Field API](docs/22_field_api.md)
- [Philosophy](docs/91_philosophy.md)
- [Alternatives](docs/92_alternatives.md)
- [Testimonials](docs/93_testimonials.md)

Please let @shantanu know if you have feedback!

## Mutable Blueprint views (mud)

Mud gives you a mutable, dataclass-like view over a Blueprint. Every assignment appends a Blueprint
layer, and every read freezes that path (and any dependencies) so it cannot be rewritten later.
This lets you build configurations ergonomically while keeping the reproducibility and layering
benefits of Blueprints.

Basic usage:

```python
@chz.chz
class Model:
    n_layers: int

@chz.chz
class Experiment:
    model: Model
    seed: int

bp = chz.Blueprint(Experiment)
view = bp.mud()
view.seed = 123
view.model.n_layers = 12

experiment = bp.make()
```

Read-freeze behavior (and the escape hatch):

```python
view = bp.mud()
view.seed = 1
_ = view.seed
view.seed = 2  # FrozenInstanceError

thaw = bp.mud(thaw=True)
thaw.seed = 1
thaw.seed = 2  # allowed, but can invalidate other views
```

Polymorphic nested fields are best handled via `mud_view`, which both selects a subclass and
returns a view of that subclass:

```python
@chz.chz
class Base:
    a: int

@chz.chz
class Child(Base):
    b: int

@chz.chz
class Parent:
    child: Base = chz.field(meta_factory=chz.factories.subclass(Base))

bp = chz.Blueprint(Parent)
child = bp.mud_view("child", Child)
child.a = 1
child.b = 2
```

Notes and limitations:
- Methods and properties on the original class work on mud views, but they can read unset fields,
  which raises MissingBlueprintArg, and their reads will freeze the paths they touch.
- When you access a polymorphic field through the parent view, it is typed as the base class.
  Use `mud_view` if you need a view typed as the concrete subclass.
- `thaw=True` disables freezing, which is useful for exploration but can surprise other views on
  the same Blueprint.
- Path strings are used for `mud_view` today; there is no typed path helper yet.

Directions for future work:
- Improve typing so parent views can reflect selected subclasses where practical.
- Add ergonomic path helpers or path objects for `mud_view`.
- Improve diagnostics around frozen paths and read dependencies.
- Consider more explicit caching semantics for properties in thaw mode.
