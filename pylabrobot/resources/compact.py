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
- A :class:`~pylabrobot.resources.carrier.MFXCarrier` whose factory declares
  ``modules=`` (a generic carrier — the caller chooses which modules sit in
  which slots) serializes the modules in a separate ``modules`` block, so the
  deserializer rebuilds them first, then calls the factory, then assigns plates
  onto the resulting sites. A fixed-assembly MFX factory that bakes its modules
  in and takes only ``name`` serializes like a standard carrier (assignments
  only) — it reconstructs its own modules by re-calling the factory, so
  recording them would be redundant and could silently drift from what the
  factory produces.

Per-instance attribute overrides (a plate with a custom ``max_volume_uL``,
etc.) are intentionally **out of scope for v1** — the compact format
assumes resources are pure class-default identity, and per-runfile policy
lives in the caller's own structures (e.g. until-data's ``ResourceUsage``).
"""

from __future__ import annotations

import functools
import importlib
import inspect
from typing import TYPE_CHECKING, Any, Callable, Dict, cast

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
    return cast(Callable[..., Any], getattr(module, attr))
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
  # ``_factory_qn`` is always the string the decorator set; getattr returns Any.
  return cast(str, qn)


def _factory_declares_modules(qn: str) -> bool:
  """Whether the factory at ``qn`` takes a ``modules=`` parameter.

  A generic MFXCarrier factory (e.g. ``MFX_CAR_L4_SHAKER``) declares
  ``modules=`` — its modules are caller-chosen, so they must be recorded in the
  blob. A fixed-assembly factory bakes its modules in and takes only ``name``;
  it rebuilds them itself on deserialize, so the blob omits them and the carrier
  serializes like a standard one. Introspecting the signature keeps this a
  property of the factory, not a hand-maintained list.
  """
  sig = inspect.signature(inspect.unwrap(_import_qualified(qn)))
  return "modules" in sig.parameters


def serialize_compact(resource: "Resource") -> Dict[str, Any]:
  """Emit a compact JSON blob describing this resource and its children.

  Records factory qualified name + variable per-instance state. Class
  defaults are NOT included — the receiver reconstructs them by calling
  the factory.
  """
  # Local imports to avoid circulars with resource.py loading order.
  from .carrier import Carrier, MFXCarrier, ResourceHolder
  from .deck import Deck
  from .tip_rack import TipRack, TipSpot

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
      # them; the deck factory will recreate them on deserialize. But a
      # *user-placed carrier* with no labeled factory is NOT recreated by the
      # deck factory — silently skipping it would drop the carrier (and
      # everything on it) from the blob with no error. Refuse loudly: a carrier
      # on the deck must come from a @compact_factory.
      if getattr(child, "_factory_qn", None) is None:
        if isinstance(child, Carrier):
          raise ValueError(
            f"Carrier {child.name!r} on deck {resource.name!r} was not built via a "
            f"@compact_factory-labeled factory, so it cannot be compact-serialized "
            f"and would be silently dropped. Build it through a labeled factory (or "
            f"fall back to the verbose Resource.serialize())."
          )
        continue
      child_blob = serialize_compact(child)
      child_blob["rails"] = _rails_for_child(child, resource)
      children.append(child_blob)
    if children:
      blob["children"] = children
    return blob

  if isinstance(resource, MFXCarrier):
    # Plates assigned onto the modules' holders are recorded for every MFX
    # carrier. The modules themselves are recorded ONLY when the factory takes
    # ``modules=`` (a generic carrier whose modules are caller-chosen); a
    # fixed-assembly factory rebuilds its own modules, so emitting them would be
    # redundant — it serializes like a standard carrier.
    assignments: Dict[str, Any] = {}
    for slot_idx, site in resource.sites.items():
      if site.resource is not None:
        assignments[str(slot_idx)] = serialize_compact(site.resource)
    if _factory_declares_modules(blob["factory"]):
      modules: Dict[str, Any] = {
        str(slot_idx): serialize_compact(site)
        for slot_idx, site in resource.sites.items()
      }
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

  # Generic resources (Plate, TipRack, MFX module, ResourceStack): factory + name
  # rebuilds the geometry. But a resource *stacked on top* of this one — a
  # NestedTipRack on another NTR, a Lid on a Plate — is a child the factory does
  # NOT recreate, so record those (and only those), each with its placement. The
  # factory's own sub-parts (a rack's TipSpots, a plate's Wells) carry no
  # ``_factory_qn``; a stacked resource built through a labeled factory does — the
  # same marker the deck branch keys on. Recorded under ``stacked`` with each
  # child's ``location`` (mirroring how the deck records ``rails``) so the format
  # spans the whole ``NestedResource`` family (stacked at any depth, by build or by
  # move) and lids alike, not one concrete rack type.
  #
  # A ResourceHolder is excluded: its single held resource is already recorded by
  # the owning carrier / MFXCarrier via ``assignments`` (e.g. a plate on an MFX
  # module's holder), so recording it here too would double-assign it on rebuild.
  #
  # A TipRack's per-instance tip state is the one piece the factory does not
  # reconstruct from ``name`` alone: the factory defaults to ``with_tips=True``
  # (a full rack), so an empty rack built ``with_tips=False`` must record that
  # override or it round-trips back to full. ``with_tips`` is inferred from the
  # observable tip presence — exact for the only two states the factory knob can
  # produce (all-full / all-empty) — and replayed into the factory on deserialize,
  # mirroring how ``modules`` is recorded and replayed for a generic MFXCarrier.
  if isinstance(resource, TipRack):
    # Read the TipSpot children directly rather than ``get_all_items()``: a rack
    # with a stacked child (an NTR on an NTR) counts that child in ``num_items``,
    # so ``get_all_items()`` would include the non-spot stacked rack.
    have = [c.has_tip() for c in resource.children if isinstance(c, TipSpot)]
    if have and not any(have):
      # All spots empty: factory default is with_tips=True, so record the override.
      blob["with_tips"] = False
    elif have and not all(have):
      # Non-uniform tip presence is runtime consumption state, out of scope for the
      # compact format (see module docstring). Fail visibly rather than emit a blob
      # that silently won't round-trip.
      raise ValueError(
        f"TipRack {resource.name!r} has non-uniform tip presence "
        f"({sum(have)}/{len(have)} spots filled), which is runtime consumption state, "
        f"not class-default identity. The compact format records only all-full "
        f"(default) or all-empty (with_tips=False) racks; use serialize_all_state for "
        f"per-spot runtime state."
      )
    # All spots full → omit; factory default with_tips=True round-trips.

  stacked = []
  if not isinstance(resource, ResourceHolder):
    for child in resource.children:
      if getattr(child, "_factory_qn", None) is None:
        continue
      if child.location is None:
        raise ValueError(
          f"Stacked resource {child.name!r} on {resource.name!r} has no location; "
          f"cannot compact-serialize the stack."
        )
      child_blob = serialize_compact(child)
      child_blob["location"] = [child.location.x, child.location.y, child.location.z]
      stacked.append(child_blob)
  if stacked:
    blob["stacked"] = stacked
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
  from .carrier import Carrier, MFXCarrier
  from .deck import Deck

  if not blob.get(COMPACT_VERSION_KEY):
    raise ValueError(
      f"Blob is not a compact_v1 serialization (missing {COMPACT_VERSION_KEY!r} marker)"
    )

  factory = _import_qualified(blob["factory"])
  if not getattr(factory, "_is_compact_factory", False):
    raise ValueError(
      f"Refusing to deserialize via {blob['factory']!r}: it does not resolve to a "
      f"@compact_factory-labeled factory. A compact blob may only instantiate "
      f"resources through labeled factories — the symmetric guard to "
      f"serialize_compact's _factory_qn requirement, so a hostile/garbled blob "
      f"cannot invoke an arbitrary imported callable."
    )
  name = blob["name"]

  # Replay the caller-chosen construction arguments the blob recorded. A generic
  # MFXCarrier records its ``modules`` (rebuilt here); an empty TipRack records
  # ``with_tips=False``. ``_invoke_factory`` filters by signature, so each kwarg
  # reaches only the factories that declare it (a fixed-assembly MFX factory bakes
  # its own modules and is built with just ``name``).
  factory_kwargs: Dict[str, Any] = {"name": name}
  if "modules" in blob:
    factory_kwargs["modules"] = {
      int(slot): deserialize_compact(mod_blob)
      for slot, mod_blob in blob["modules"].items()
    }
  if "with_tips" in blob:
    factory_kwargs["with_tips"] = blob["with_tips"]
  resource = _invoke_factory(factory, **factory_kwargs)

  if isinstance(resource, Deck):
    # Deck children are placed by ``rails``, which only ``HamiltonDeck`` accepts
    # (the serialize side records rails via the Hamilton rail math). The deck
    # factory always produces a HamiltonDeck here.
    from .hamilton.hamilton_decks import HamiltonDeck

    hamilton_deck = cast(HamiltonDeck, resource)
    for child_blob in blob.get("children", []):
      child = deserialize_compact(child_blob)
      hamilton_deck.assign_child_resource(child, rails=child_blob["rails"])
    return resource

  if isinstance(resource, MFXCarrier):
    # Plates were recorded in ``assignments``; drop them onto the modules'
    # holders (the modules came either from the blob or the factory itself).
    for slot, plate_blob in blob.get("assignments", {}).items():
      resource[int(slot)].assign_child_resource(deserialize_compact(plate_blob))
    return resource

  # Standard carriers and leaf resources: assignments go via __setitem__. Only a
  # Carrier is ever recorded with an ``assignments`` block (see serialize_compact),
  # so the target here is always a Carrier.
  for slot, child_blob in blob.get("assignments", {}).items():
    child = deserialize_compact(child_blob)
    cast(Carrier, resource)[int(slot)] = child

  # Replay any stacked-on resources (a NestedTipRack on an NTR, a Lid on a Plate),
  # each at its recorded location — the inverse of the ``stacked`` block above.
  if blob.get("stacked"):
    from .coordinate import Coordinate

    for child_blob in blob["stacked"]:
      child = deserialize_compact(child_blob)
      resource.assign_child_resource(
        child, location=Coordinate(*child_blob["location"])
      )

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
  return cast("Resource", factory(**accepted))


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
