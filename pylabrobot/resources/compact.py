"""Compact serialization for pylabrobot resources.

The built-in ``Resource.serialize()`` is exhaustive — every well, every
coordinate, every attribute. For a typical Hamilton deck with 90 plates that
produces around 11 MB of JSON.

The compact format records only:

- The fully-qualified factory function path (e.g.
  ``pylabrobot.resources.eppendorf.plates.Eppendorf_96_wellplate_250ul_Vb_semiskirted``).
- Variable per-instance state (``name``, child assignments, deck-rail
  placement).

Geometry and class-default attributes are reconstructed by calling the
factory. Both producer and consumer must have the same pylabrobot installed
— the qualified name *is* the API contract; there is no in-band schema to
translate.

Usage::

    @compact_factory
    def Eppendorf_96_wellplate_250ul_Vb_semiskirted(name, with_lid=False):
        ...

    plate = Eppendorf_96_wellplate_250ul_Vb_semiskirted(name="cell_plate_1")
    blob = plate.serialize_compact()
    plate2 = Resource.deserialize_compact(blob)
    assert plate == plate2

Carriers and decks have special handling:

- A :class:`~pylabrobot.resources.deck.Deck` serializes its top-level
  children (carriers) with each child's ``rails`` placement inline.
- A regular :class:`~pylabrobot.resources.carrier.Carrier` serializes the
  resources *assigned* to its sites (the sites themselves are reconstructed
  by the factory). Empty sites are omitted.
- A :class:`~pylabrobot.resources.carrier.MFXCarrier` is special: its
  factory requires ``modules=`` at construction time. The compact format
  serializes the modules in a separate ``modules`` block so the deserializer
  can rebuild them first, then call the factory, then assign plates onto
  the resulting sites.

Per-instance attribute overrides (a plate with a custom ``max_volume_uL``,
etc.) are intentionally **out of scope for v1** — the compact format
assumes resources are pure class-default identity, and per-runfile policy
lives in the caller's own structures (e.g. until-data's ``ResourceUsage``).
"""

from __future__ import annotations

import functools
import importlib
import inspect
from typing import TYPE_CHECKING, Any, Callable, Dict

if TYPE_CHECKING:
  from .resource import Resource


COMPACT_VERSION_KEY = "_compact_v1"


def compact_factory(func: Callable) -> Callable:
  """Mark a factory function as compact-serializable.

  Wraps a factory so the produced resource carries its factory's
  fully-qualified import path on ``_factory_qn``. :meth:`Resource.serialize_compact`
  reads this attribute; :meth:`Resource.deserialize_compact` resolves it back to
  the factory via :mod:`importlib`. Resources built through unlabeled factories
  (or constructed directly via class) fail to serialize via the compact path
  with a clear error.

  The wrapper preserves the original signature via :func:`functools.wraps`, so
  the labeled factory is a drop-in replacement.
  """
  qn = f"{func.__module__}.{func.__qualname__}"

  @functools.wraps(func)
  def wrapper(*args, **kwargs):
    instance = func(*args, **kwargs)
    instance._factory_qn = qn
    return instance

  # Mark the wrapper itself so callers (e.g. catalog generators) can
  # introspect which factories are compact-serializable.
  wrapper._is_compact_factory = True  # type: ignore[attr-defined]
  wrapper._factory_qn = qn  # type: ignore[attr-defined]
  return wrapper


def _import_qualified(qn: str) -> Callable:
  """Resolve a fully-qualified Python import path to its target callable."""
  module_path, _, attr = qn.rpartition(".")
  if not module_path:
    raise ValueError(f"Not a qualified name: {qn!r}")
  module = importlib.import_module(module_path)
  try:
    return getattr(module, attr)
  except AttributeError as exc:
    raise ImportError(
      f"Could not resolve {qn!r}: attribute {attr!r} not found on {module_path!r}"
    ) from exc


def _factory_qn_or_raise(resource: "Resource") -> str:
  qn = getattr(resource, "_factory_qn", None)
  if qn is None:
    raise ValueError(
      f"Resource {resource.name!r} ({type(resource).__name__}) was not built "
      f"via a @compact_factory-labeled factory. Compact serialization is only "
      f"supported for resources constructed through labeled factories — label "
      f"the factory or fall back to the verbose `Resource.serialize()`."
    )
  return qn


def serialize_compact(resource: "Resource") -> Dict[str, Any]:
  """Emit a compact JSON blob describing this resource and its children.

  Records factory qualified name + variable per-instance state. Class
  defaults are NOT included — the receiver reconstructs them by calling
  the factory.
  """
  # Local imports to avoid circulars with resource.py loading order.
  from .carrier import Carrier, MFXCarrier
  from .deck import Deck

  blob: Dict[str, Any] = {
    COMPACT_VERSION_KEY: True,
    "factory": _factory_qn_or_raise(resource),
    "name": resource.name,
  }

  if isinstance(resource, Deck):
    # Deck children are carriers placed by rails. Each child gets its own
    # compact blob plus a ``rails`` field; the deck factory is reconstructed
    # via the factory call and the children are then placed with
    # ``deck.assign_child_resource(child, rails=...)``.
    children = []
    for child in resource.children:
      # Trash / teaching-rack / autogenerated deck children don't carry a
      # ``_factory_qn`` (the deck factory creates them internally). Skip
      # them; the deck factory will recreate them on deserialize.
      if getattr(child, "_factory_qn", None) is None:
        continue
      child_blob = serialize_compact(child)
      child_blob["rails"] = _rails_for_child(child, resource)
      children.append(child_blob)
    if children:
      blob["children"] = children
    return blob

  if isinstance(resource, MFXCarrier):
    # MFXCarrier's factory takes ``modules=`` at construction. The modules
    # are the carrier's sites; plates assigned to those modules are the
    # post-construction additions.
    modules: Dict[str, Any] = {}
    assignments: Dict[str, Any] = {}
    for slot_idx, site in resource.sites.items():
      modules[str(slot_idx)] = serialize_compact(site)
      if site.resource is not None:
        assignments[str(slot_idx)] = serialize_compact(site.resource)
    if modules:
      blob["modules"] = modules
    if assignments:
      blob["assignments"] = assignments
    return blob

  if isinstance(resource, Carrier):
    # Standard carriers: sites are baked into the factory; only the
    # resources assigned to those sites need to be recorded.
    assignments = {}
    for slot_idx, site in resource.sites.items():
      if site.resource is not None:
        assignments[str(slot_idx)] = serialize_compact(site.resource)
    if assignments:
      blob["assignments"] = assignments
    return blob

  # Leaf resources (Plate, TipRack, MFX module on its own): factory + name
  # is enough. The factory rebuilds the full geometry.
  return blob


def deserialize_compact(blob: Dict[str, Any]) -> "Resource":
  """Materialize a compact blob into a Resource tree.

  Resolves ``blob["factory"]`` via :mod:`importlib`, calls it with the
  per-instance state recorded in the blob (``name``, ``modules`` for
  MFXCarrier), then recursively materializes children and assignments.

  Factory signatures are introspected — if a factory doesn't accept
  ``name=`` (e.g. ``STARDeck`` hard-codes ``name="deck"`` internally), the
  kwarg is omitted from the call. The round-trip still works as long as
  the factory always produces an instance with the recorded ``name``.
  """
  from .carrier import MFXCarrier
  from .deck import Deck

  if not blob.get(COMPACT_VERSION_KEY):
    raise ValueError(
      f"Blob is not a compact_v1 serialization (missing {COMPACT_VERSION_KEY!r} marker)"
    )

  factory = _import_qualified(blob["factory"])
  name = blob["name"]

  # MFXCarrier special case: factory needs ``modules=`` at construction.
  if "modules" in blob:
    modules = {
      int(slot): deserialize_compact(mod_blob)
      for slot, mod_blob in blob["modules"].items()
    }
    resource = _invoke_factory(factory, name=name, modules=modules)
    # Now assign plates onto the modules' holders.
    for slot, plate_blob in blob.get("assignments", {}).items():
      plate = deserialize_compact(plate_blob)
      resource[int(slot)].assign_child_resource(plate)
    return resource

  resource = _invoke_factory(factory, name=name)

  if isinstance(resource, Deck):
    for child_blob in blob.get("children", []):
      child = deserialize_compact(child_blob)
      resource.assign_child_resource(child, rails=child_blob["rails"])
    return resource

  # Standard carriers and leaf resources: assignments go via __setitem__.
  for slot, child_blob in blob.get("assignments", {}).items():
    child = deserialize_compact(child_blob)
    resource[int(slot)] = child

  return resource


def _invoke_factory(factory: Callable, **kwargs) -> "Resource":
  """Call ``factory`` with only the kwargs its signature accepts.

  Factories like :func:`STARDeck` don't take ``name=`` because they
  hard-code it; passing it would raise ``TypeError``. Introspecting the
  signature lets the deserializer be uniform while tolerating those
  factories. The deserialized instance's ``name`` will still match the
  blob because the factory bakes in the same value.
  """
  # Unwrap the decorator wrapper to get the real signature.
  real = inspect.unwrap(factory)
  sig = inspect.signature(real)
  accepted = {k: v for k, v in kwargs.items() if k in sig.parameters}
  return factory(**accepted)


def _rails_for_child(child: "Resource", deck: "Resource") -> int:
  """Recover the rails value for a deck child from its location."""
  from .hamilton.hamilton_decks import _rails_for_x_coordinate

  if child.location is None:
    raise ValueError(
      f"Child {child.name!r} on deck {deck.name!r} has no location; "
      f"cannot recover rails value for compact serialization."
    )
  deck_x = deck.location.x if deck.location is not None else 0.0
  return _rails_for_x_coordinate(child.location.x - deck_x)


__all__ = [
  "COMPACT_VERSION_KEY",
  "compact_factory",
  "deserialize_compact",
  "serialize_compact",
]
