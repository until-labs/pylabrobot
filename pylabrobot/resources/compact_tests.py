"""Tests for the compact serialization module.

Round-trip tests for each factory we expect to be compact-serializable, plus
a full-deck fixture and the MFXCarrier-with-modules edge case.
"""

import unittest
from typing import cast

from pylabrobot.resources.carrier import MFXCarrier
from pylabrobot.resources.compact import compact_factory
from pylabrobot.resources.corning.costar.plates import Cor_Cos_12_wellplate_6900ul_Fb
from pylabrobot.resources.corning.plates import Cor_96_wellplate_2mL_Vb
from pylabrobot.resources.eppendorf.plates import (
  Eppendorf_96_wellplate_250ul_Vb_semiskirted,
  Eppendorf_96_wellplate_250ul_Vb_semiskirted_waste,
)
from pylabrobot.resources.hamilton.hamilton_decks import STARDeck
from pylabrobot.resources.hamilton.mfx_carriers import MFX_CAR_L4_SHAKER
from pylabrobot.resources.hamilton.mfx_modules import MFX_DWP_module_flat
from pylabrobot.resources.hamilton.plate_carriers import PLT_CAR_L5AC_A00, PLT_CAR_L5PCR
from pylabrobot.resources.hamilton.plates import Hamilton_1_troughplate_300ml
from pylabrobot.resources.hamilton.tip_carriers import TIP_CAR_480_A00, TIP_CAR_NTR_A00
from pylabrobot.resources.hamilton.tip_racks import (
  hamilton_96_tiprack_50uL_filter,
  hamilton_96_tiprack_50uL_NTR,
  hamilton_96_tiprack_300uL_filter,
  hamilton_96_tiprack_1000uL_filter,
)
from pylabrobot.resources.nest.plates import nest_12_troughplate_15000uL_Vb
from pylabrobot.resources.nested_resource import NestedResource
from pylabrobot.resources.resource import Resource
from pylabrobot.resources.tip_rack import TipSpot
from pylabrobot.resources.thermo_fisher.plates import Thermo_Nunc_96_wellplate_400uL_Fb


# All labeled factories we expect to round-trip. Each entry is a
# zero-arg-after-name builder; the test loops over them.
_LEAF_BUILDERS = [
  lambda n: Eppendorf_96_wellplate_250ul_Vb_semiskirted(name=n),
  lambda n: Eppendorf_96_wellplate_250ul_Vb_semiskirted_waste(name=n),
  lambda n: hamilton_96_tiprack_50uL_filter(name=n),
  lambda n: hamilton_96_tiprack_50uL_NTR(name=n),
  lambda n: hamilton_96_tiprack_300uL_filter(name=n),
  lambda n: hamilton_96_tiprack_1000uL_filter(name=n),
  lambda n: nest_12_troughplate_15000uL_Vb(name=n),
  lambda n: Hamilton_1_troughplate_300ml(name=n),
  lambda n: Cor_Cos_12_wellplate_6900ul_Fb(name=n),
  lambda n: Cor_96_wellplate_2mL_Vb(name=n),
  lambda n: Thermo_Nunc_96_wellplate_400uL_Fb(name=n),
  lambda n: MFX_DWP_module_flat(name=n),
]

_CARRIER_BUILDERS = [
  lambda n: PLT_CAR_L5AC_A00(name=n),
  lambda n: PLT_CAR_L5PCR(name=n),
  lambda n: TIP_CAR_480_A00(name=n),
  lambda n: TIP_CAR_NTR_A00(name=n),
]


@compact_factory
def _fixed_assembly_mfx(name: str) -> MFXCarrier:
  """A self-assembling MFX carrier: modules baked in, factory takes only ``name``.

  Mirrors the until-data ``until_mfx_cooling_dwp`` pattern — the whole carrier is
  one resource, so its compact blob records only the qualified name plus any
  plate assignments, never a ``modules`` block.
  """
  # ``compact_factory`` erases the wrapped return type to ``Callable``, so the
  # factory call is typed ``Any``; cast back to the annotated return type.
  return cast(
    MFXCarrier,
    MFX_CAR_L4_SHAKER(
      name=name,
      modules={
        0: MFX_DWP_module_flat(name=f"{name}_m0"),
        2: MFX_DWP_module_flat(name=f"{name}_m2"),
      },
    ),
  )


class TestLeafRoundTrip(unittest.TestCase):
  """Every leaf resource (plate, tip rack, module) round-trips by itself."""

  def test_leaf_round_trip(self):
    for builder in _LEAF_BUILDERS:
      resource = builder("test_name")
      blob = resource.serialize_compact()
      self.assertTrue(blob["_compact_v1"])
      self.assertEqual(blob["name"], "test_name")
      # Round-trip
      restored = Resource.deserialize_compact(blob)
      self.assertEqual(resource, restored)


class TestCarrierRoundTrip(unittest.TestCase):
  """Carriers round-trip empty and with assignments."""

  def test_empty_carrier_round_trip(self):
    for builder in _CARRIER_BUILDERS:
      carrier = builder("test_carrier")
      blob = carrier.serialize_compact()
      # Empty carriers have no assignments block
      self.assertNotIn("assignments", blob)
      restored = Resource.deserialize_compact(blob)
      self.assertEqual(carrier, restored)

  def test_plate_carrier_with_plate_round_trip(self):
    carrier = PLT_CAR_L5AC_A00(name="plate_car")
    carrier[0] = Eppendorf_96_wellplate_250ul_Vb_semiskirted(name="cell_plate")
    carrier[2] = nest_12_troughplate_15000uL_Vb(name="reservoir")
    blob = carrier.serialize_compact()
    self.assertEqual(set(blob["assignments"].keys()), {"0", "2"})
    restored = Resource.deserialize_compact(blob)
    self.assertEqual(carrier, restored)

  def test_tip_carrier_with_tip_rack_round_trip(self):
    carrier = TIP_CAR_480_A00(name="tips_car")
    carrier[0] = hamilton_96_tiprack_1000uL_filter(name="tips_1")
    carrier[3] = hamilton_96_tiprack_300uL_filter(name="tips_2")
    blob = carrier.serialize_compact()
    self.assertEqual(set(blob["assignments"].keys()), {"0", "3"})
    restored = Resource.deserialize_compact(blob)
    self.assertEqual(carrier, restored)


class TestMFXCarrierRoundTrip(unittest.TestCase):
  """MFXCarrier needs ``modules=`` at construction — verify the special-case."""

  def test_mfx_carrier_with_modules_only(self):
    mfx = MFX_CAR_L4_SHAKER(
      name="mfx_carrier",
      modules={
        0: MFX_DWP_module_flat(name="module_0"),
        2: MFX_DWP_module_flat(name="module_2"),
      },
    )
    blob = mfx.serialize_compact()
    self.assertIn("modules", blob)
    self.assertNotIn("assignments", blob)
    self.assertEqual(set(blob["modules"].keys()), {"0", "2"})
    restored = Resource.deserialize_compact(blob)
    self.assertEqual(mfx, restored)

  def test_mfx_carrier_with_modules_and_plates(self):
    mfx = MFX_CAR_L4_SHAKER(
      name="mfx_carrier",
      modules={
        0: MFX_DWP_module_flat(name="module_0"),
        1: MFX_DWP_module_flat(name="module_1"),
      },
    )
    mfx[0] = nest_12_troughplate_15000uL_Vb(name="reservoir_1")
    blob = mfx.serialize_compact()
    self.assertIn("modules", blob)
    self.assertIn("assignments", blob)
    self.assertEqual(set(blob["assignments"].keys()), {"0"})
    restored = Resource.deserialize_compact(blob)
    self.assertEqual(mfx, restored)


class TestMFXFixedAssemblyRoundTrip(unittest.TestCase):
  """A fixed-assembly MFX factory (takes only ``name``) serializes like a
  standard carrier: no ``modules`` block, modules rebuilt by the factory."""

  def test_no_modules_block_emitted(self):
    mfx = _fixed_assembly_mfx(name="mfx_fixed")
    blob = mfx.serialize_compact()
    self.assertNotIn("modules", blob)  # the factory bakes them in
    restored = Resource.deserialize_compact(blob)
    self.assertEqual(mfx, restored)
    # The modules are reconstructed by re-calling the factory, not from the blob.
    assert isinstance(restored, MFXCarrier)
    self.assertEqual(sorted(restored.sites), [0, 2])

  def test_plate_assignment_round_trips(self):
    mfx = _fixed_assembly_mfx(name="mfx_fixed")
    mfx[0] = nest_12_troughplate_15000uL_Vb(name="reservoir_1")
    blob = mfx.serialize_compact()
    self.assertNotIn("modules", blob)
    self.assertEqual(set(blob["assignments"].keys()), {"0"})
    restored = Resource.deserialize_compact(blob)
    self.assertEqual(mfx, restored)

  def test_fixed_assembly_on_full_deck(self):
    deck = STARDeck()
    mfx = _fixed_assembly_mfx(name="mfx_fixed")
    mfx[0] = nest_12_troughplate_15000uL_Vb(name="reservoir_1")
    deck.assign_child_resource(mfx, rails=14)
    blob = deck.serialize_compact()
    self.assertNotIn("modules", blob["children"][0])
    restored = Resource.deserialize_compact(blob)
    self.assertEqual(deck, restored)


class TestFullDeckRoundTrip(unittest.TestCase):
  """Full deck with multiple carrier types — the realistic case."""

  def test_full_deck_round_trip(self):
    deck = STARDeck()

    tips_car = TIP_CAR_480_A00(name="tips_carrier")
    tips_car[0] = hamilton_96_tiprack_1000uL_filter(name="tips_1")
    tips_car[1] = hamilton_96_tiprack_1000uL_filter(name="tips_2")
    deck.assign_child_resource(tips_car, rails=1)

    plate_car = PLT_CAR_L5AC_A00(name="plate_carrier")
    plate_car[0] = Eppendorf_96_wellplate_250ul_Vb_semiskirted(name="cell_plate")
    deck.assign_child_resource(plate_car, rails=7)

    mfx = MFX_CAR_L4_SHAKER(
      name="mfx_carrier",
      modules={
        0: MFX_DWP_module_flat(name="dwp_module_0"),
        1: MFX_DWP_module_flat(name="dwp_module_1"),
      },
    )
    mfx[0] = nest_12_troughplate_15000uL_Vb(name="reservoir_1")
    deck.assign_child_resource(mfx, rails=14)

    blob = deck.serialize_compact()
    restored = Resource.deserialize_compact(blob)
    self.assertEqual(deck, restored)

  def test_ntr_carrier_with_nested_tip_rack_round_trips(self):
    """A TIP_CAR_NTR_A00 holding a nested tip rack now round-trips: both the carrier
    and the NTR factory are @compact_factory-labeled, so the carrier no longer
    silently vanishes from the deck blob. (A *stack* of NTRs on one site round-trips
    too — see TestStackedResourceRoundTrip.)"""
    deck = STARDeck()
    carrier = TIP_CAR_NTR_A00(name="tip_car_ntr")
    carrier[0] = hamilton_96_tiprack_50uL_NTR(name="ntr_bottom")
    deck.assign_child_resource(carrier, rails=25)

    blob = deck.serialize_compact()
    self.assertIn("tip_car_ntr", [c["name"] for c in blob["children"]])
    restored = Resource.deserialize_compact(blob)
    self.assertEqual(deck, restored)
    self.assertEqual(restored.get_resource("ntr_bottom").name, "ntr_bottom")

  def test_compact_blob_is_orders_of_magnitude_smaller_than_verbose(self):
    """Sanity check: the whole point of the compact format is size reduction."""
    import json

    deck = STARDeck()
    plate_car = PLT_CAR_L5AC_A00(name="plate_carrier")
    for i in range(5):
      plate_car[i] = Eppendorf_96_wellplate_250ul_Vb_semiskirted(name=f"plate_{i}")
    deck.assign_child_resource(plate_car, rails=7)

    compact = json.dumps(deck.serialize_compact())
    verbose = json.dumps(deck.serialize())
    # Expect at least a 50x reduction. In practice we see ~140x for typical decks.
    self.assertGreater(len(verbose) / len(compact), 50)


class TestStackedResourceRoundTrip(unittest.TestCase):
  """A resource stacked directly on another (NestedTipRack on an NTR) round-trips:
  the stacked child is recorded under ``stacked`` with its location, not dropped."""

  def test_two_high_ntr_stack_round_trips(self):
    bottom = hamilton_96_tiprack_50uL_NTR(name="ntr_bottom")
    top = hamilton_96_tiprack_50uL_NTR(name="ntr_top")
    bottom.assign_child_resource(top)  # NestedTipRack auto-stacks via stacking_z_height
    blob = bottom.serialize_compact()
    self.assertEqual([s["name"] for s in blob["stacked"]], ["ntr_top"])
    self.assertEqual(blob["stacked"][0]["location"], [0.0, 0.0, top.location.z])
    restored = Resource.deserialize_compact(blob)
    self.assertEqual(bottom, restored)

  def test_stacked_ntr_on_carrier_on_deck(self):
    """The full scenario: two NTRs stacked at slot 0 of a TIP_CAR_NTR_A00 on a deck.
    The stack survives the carrier->site->stacked recursion end to end."""
    deck = STARDeck()
    carrier = TIP_CAR_NTR_A00(name="tip_car_ntr")
    bottom = hamilton_96_tiprack_50uL_NTR(name="ntr_bottom")
    top = hamilton_96_tiprack_50uL_NTR(name="ntr_top")
    carrier[0] = bottom
    bottom.assign_child_resource(top)
    deck.assign_child_resource(carrier, rails=25)

    blob = deck.serialize_compact()
    slot0 = blob["children"][0]["assignments"]["0"]
    self.assertEqual([s["name"] for s in slot0["stacked"]], ["ntr_top"])
    restored = Resource.deserialize_compact(blob)
    self.assertEqual(deck, restored)
    self.assertEqual(restored.get_resource("ntr_top").name, "ntr_top")

  def test_three_high_ntr_stack_round_trips(self):
    """Depth-agnostic: a 3-high chain is recorded as nested ``stacked`` blobs and rebuilt as a
    proper bottom -> mid -> top chain."""
    bottom = hamilton_96_tiprack_50uL_NTR(name="ntr_bottom")
    mid = hamilton_96_tiprack_50uL_NTR(name="ntr_mid")
    top = hamilton_96_tiprack_50uL_NTR(name="ntr_top")
    bottom.assign_child_resource(mid)
    mid.assign_child_resource(top)
    blob = bottom.serialize_compact()
    self.assertEqual([s["name"] for s in blob["stacked"]], ["ntr_mid"])
    self.assertEqual([s["name"] for s in blob["stacked"][0]["stacked"]], ["ntr_top"])
    restored = Resource.deserialize_compact(blob)
    self.assertEqual(bottom, restored)
    assert isinstance(restored, NestedResource)
    self.assertIs(restored.get_stack_top(), restored.get_resource("ntr_top"))


def _spot_states(rack) -> list:
  """has_tip() for each TipSpot child of ``rack``. Filters to TipSpots because a
  rack with a stacked child counts that child in num_items, so get_all_items()
  would include the non-spot stacked rack."""
  return [c.has_tip() for c in rack.children if isinstance(c, TipSpot)]


class TestTipRackTipStateRoundTrip(unittest.TestCase):
  """A tip rack's ``with_tips`` state round-trips: an empty rack records
  ``with_tips=False`` and comes back empty, a full rack omits the key and comes
  back full. ``Resource.__eq__`` ignores tip-tracker state, so every assertion
  checks ``has_tip()`` explicitly rather than relying on ``==``."""

  def test_empty_tip_rack_round_trips_standalone(self):
    rack = hamilton_96_tiprack_1000uL_filter(name="empty_rack", with_tips=False)
    blob = rack.serialize_compact()
    self.assertIs(blob["with_tips"], False)
    restored = Resource.deserialize_compact(blob)
    self.assertTrue(not any(_spot_states(restored)))

  def test_full_tip_rack_omits_with_tips_and_round_trips(self):
    rack = hamilton_96_tiprack_1000uL_filter(name="full_rack")  # default with_tips=True
    blob = rack.serialize_compact()
    self.assertNotIn("with_tips", blob)
    restored = Resource.deserialize_compact(blob)
    self.assertTrue(all(_spot_states(restored)))

  def test_empty_tip_rack_on_carrier_round_trips(self):
    carrier = TIP_CAR_480_A00(name="tips_car")
    carrier[0] = hamilton_96_tiprack_1000uL_filter(name="empty_on_carrier", with_tips=False)
    blob = carrier.serialize_compact()
    self.assertIs(blob["assignments"]["0"]["with_tips"], False)
    restored = Resource.deserialize_compact(blob)
    rack = restored.get_resource("empty_on_carrier")
    self.assertTrue(not any(_spot_states(rack)))

  def test_empty_tip_rack_on_full_deck_round_trips(self):
    deck = STARDeck()
    carrier = TIP_CAR_480_A00(name="tips_carrier")
    carrier[0] = hamilton_96_tiprack_1000uL_filter(name="empty_deck_rack", with_tips=False)
    deck.assign_child_resource(carrier, rails=1)
    blob = deck.serialize_compact()
    restored = Resource.deserialize_compact(blob)
    rack = restored.get_resource("empty_deck_rack")
    self.assertTrue(not any(_spot_states(rack)))

  def test_nested_stack_full_bottom_empty_top_round_trips(self):
    """Each rack in a stack records its own ``with_tips`` independently: a full
    bottom omits the key, an empty top stacked on it records ``with_tips=False``."""
    bottom = hamilton_96_tiprack_50uL_NTR(name="ntr_bottom")  # full (default)
    top = hamilton_96_tiprack_50uL_NTR(name="ntr_top", with_tips=False)  # empty
    bottom.assign_child_resource(top)  # NestedTipRack auto-stacks
    blob = bottom.serialize_compact()
    self.assertNotIn("with_tips", blob)
    self.assertIs(blob["stacked"][0]["with_tips"], False)
    restored = Resource.deserialize_compact(blob)
    self.assertTrue(all(_spot_states(restored)))
    restored_top = restored.get_resource("ntr_top")
    self.assertTrue(not any(_spot_states(restored_top)))

  def test_partial_tip_rack_raises(self):
    """Non-uniform tip presence is runtime consumption state, out of scope for the
    compact format — serialize must refuse loudly, pointing to serialize_all_state."""
    rack = hamilton_96_tiprack_1000uL_filter(name="partial_rack")  # full
    rack.set_tip_state([False] + [True] * (rack.num_items - 1))  # empty one spot
    with self.assertRaises(ValueError) as cm:
      rack.serialize_compact()
    self.assertIn("serialize_all_state", str(cm.exception))


class TestErrorHandling(unittest.TestCase):
  """Resources built outside a labeled factory raise a clear error."""

  def test_unlabeled_resource_raises(self):
    # Direct construction of a base Resource, not via a labeled factory.
    r = Resource("unlabeled", size_x=10, size_y=10, size_z=10)
    with self.assertRaises(ValueError) as cm:
      r.serialize_compact()
    self.assertIn("@compact_factory", str(cm.exception))

  def test_unlabeled_carrier_on_deck_raises(self):
    # A carrier placed on the deck without a labeled factory would otherwise be
    # silently dropped (it and everything on it) — serialize_compact must refuse
    # loudly rather than emit a deck blob that's quietly missing the carrier.
    deck = STARDeck()
    carrier = TIP_CAR_480_A00(name="orphan_carrier")
    carrier._factory_qn = None  # simulate a carrier built outside a labeled factory
    deck.assign_child_resource(carrier, rails=25)
    with self.assertRaises(ValueError) as cm:
      deck.serialize_compact()
    self.assertIn("@compact_factory", str(cm.exception))
    self.assertIn("orphan_carrier", str(cm.exception))

  def test_deserialize_rejects_missing_marker(self):
    blob = {"factory": "pylabrobot.resources.resource.Resource", "name": "x"}
    with self.assertRaises(ValueError) as cm:
      Resource.deserialize_compact(blob)
    self.assertIn("_compact_v1", str(cm.exception))

  def test_deserialize_rejects_unresolvable_factory(self):
    blob = {
      "_compact_v1": True,
      "factory": "nonexistent.module.Factory",
      "name": "x",
    }
    with self.assertRaises((ImportError, ModuleNotFoundError)):
      Resource.deserialize_compact(blob)

  def test_deserialize_rejects_non_compact_factory(self):
    # Importable and callable, but NOT @compact_factory-labeled: deserialize must
    # refuse to invoke it (symmetric with serialize's labeling requirement), so a
    # blob can't be turned into a call to an arbitrary imported callable.
    blob = {
      "_compact_v1": True,
      "factory": "pylabrobot.resources.resource.Resource",
      "name": "x",
    }
    with self.assertRaises(ValueError) as cm:
      Resource.deserialize_compact(blob)
    self.assertIn("@compact_factory", str(cm.exception))


class TestCompactFactoryDecorator(unittest.TestCase):
  """The decorator itself: introspection + labeling."""

  def test_decorator_sets_factory_qn_on_wrapper(self):
    self.assertTrue(
      getattr(Eppendorf_96_wellplate_250ul_Vb_semiskirted, "_is_compact_factory", False)
    )
    self.assertEqual(
      getattr(Eppendorf_96_wellplate_250ul_Vb_semiskirted, "_factory_qn"),
      "pylabrobot.resources.eppendorf.plates.Eppendorf_96_wellplate_250ul_Vb_semiskirted",
    )

  def test_decorator_sets_factory_qn_on_instance(self):
    p = Eppendorf_96_wellplate_250ul_Vb_semiskirted(name="x")
    self.assertEqual(
      p._factory_qn,
      "pylabrobot.resources.eppendorf.plates.Eppendorf_96_wellplate_250ul_Vb_semiskirted",
    )

  def test_decorator_preserves_signature(self):
    import inspect

    sig = inspect.signature(Eppendorf_96_wellplate_250ul_Vb_semiskirted)
    self.assertIn("name", sig.parameters)
    self.assertIn("with_lid", sig.parameters)


if __name__ == "__main__":
  unittest.main()
