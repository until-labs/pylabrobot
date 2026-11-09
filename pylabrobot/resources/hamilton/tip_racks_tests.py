"""Unit test validating center-center coordinates of Hamilton
tip spots across all PLR-integrated Hamilton tip racks.

These tests instantiate Hamilton tip rack models, compute each
rack's representative H1 tip spot position relative to the tip rack origin
and verify that the reported center-center coordinates match
expected reference values.
"""

import json
import unittest

from pylabrobot.liquid_handling import LiquidHandler
from pylabrobot.liquid_handling.backends.hamilton.STAR_chatterbox import STARChatterboxBackend
from pylabrobot.resources.carrier import Coordinate
from pylabrobot.resources.deck import Deck
from pylabrobot.resources.hamilton import (
  TIP_CAR_480_A00,
  STARDeck,
  hamilton_96_tiprack_10uL,
  hamilton_96_tiprack_10uL_filter,
  hamilton_96_tiprack_50uL,
  hamilton_96_tiprack_50uL_filter,
  hamilton_96_tiprack_50uL_NTR,
  hamilton_96_tiprack_300uL,
  hamilton_96_tiprack_300uL_filter,
  hamilton_96_tiprack_300uL_filter_182040,
  hamilton_96_tiprack_300uL_filter_slim,
  hamilton_96_tiprack_1000uL,
  hamilton_96_tiprack_1000uL_filter,
  hamilton_96_tiprack_1000uL_filter_ultrawide,
  hamilton_96_tiprack_1000uL_filter_wide,
)
from pylabrobot.resources.resource import Resource
from pylabrobot.resources.tip_rack import TipRack
from pylabrobot.resources.tip_tracker import does_tip_tracking, set_tip_tracking


class HamiltonTipSpotTests(unittest.TestCase):
  def test_tipspot_h1_cc(self):
    """Tests for PLR-integrated Hamilton TipRacks' accurate TipSpot center-center coordinates."""

    def check_tip_spot_h1(tr: TipRack, expect: Coordinate):
      h1_loc = tr.get_item("H1").get_absolute_location("c", "c")
      assert h1_loc.x == expect.x and h1_loc.y == expect.y, f"{h1_loc} != {expect}"

    common_tip_rack_loc = Coordinate(x=11.7, y=9.8, z=-22.5)
    check_tip_spot_h1(hamilton_96_tiprack_10uL_filter("tr"), common_tip_rack_loc)
    check_tip_spot_h1(hamilton_96_tiprack_10uL(name="tr"), common_tip_rack_loc)
    check_tip_spot_h1(hamilton_96_tiprack_50uL_filter(name="tr"), common_tip_rack_loc)
    check_tip_spot_h1(hamilton_96_tiprack_50uL(name="tr"), common_tip_rack_loc)
    check_tip_spot_h1(hamilton_96_tiprack_300uL_filter(name="tr"), common_tip_rack_loc)
    check_tip_spot_h1(hamilton_96_tiprack_300uL(name="tr"), common_tip_rack_loc)
    check_tip_spot_h1(hamilton_96_tiprack_300uL_filter_slim(name="tr"), common_tip_rack_loc)
    check_tip_spot_h1(hamilton_96_tiprack_1000uL_filter(name="tr"), common_tip_rack_loc)
    check_tip_spot_h1(hamilton_96_tiprack_1000uL(name="tr"), common_tip_rack_loc)
    check_tip_spot_h1(hamilton_96_tiprack_1000uL_filter_wide(name="tr"), common_tip_rack_loc)
    check_tip_spot_h1(hamilton_96_tiprack_1000uL_filter_ultrawide(name="tr"), common_tip_rack_loc)

    ntr_loc = Coordinate(x=13.525, y=11.625, z=13.5)
    check_tip_spot_h1(hamilton_96_tiprack_50uL_NTR(name="tr"), ntr_loc)


class HamiltonTipAdapterTests(unittest.IsolatedAsyncioTestCase):
  async def test_adapter_reseat_and_discard_after_compact_round_trip(self):
    deck = STARDeck()
    carrier = TIP_CAR_480_A00("tips_rail_7")
    deck.assign_child_resource(carrier, rails=7)
    carrier[0] = hamilton_96_tiprack_300uL_filter_182040("adapter", with_tips=False)
    carrier[1] = hamilton_96_tiprack_300uL_filter("source")
    deck = Resource.deserialize_compact(json.loads(json.dumps(deck.serialize_compact())))
    adapter = deck.get_resource("adapter")
    source = deck.get_resource("source")
    assert isinstance(deck, Deck)
    assert isinstance(adapter, TipRack)
    assert isinstance(source, TipRack)
    self.assertTrue(all(not spot.has_tip() for spot in adapter.get_all_items()))

    a1 = adapter.get_item("A1")
    h12 = adapter.get_item("H12")
    tip = a1.make_tip()
    self.assertTrue(tip.has_filter)
    self.assertEqual(tip.total_tip_length, 59.9)
    for spot, expected in (
      (a1, Coordinate(252.9, 145.8, 227.45)),
      (h12, Coordinate(351.9, 82.8, 227.45)),
    ):
      position = spot.get_absolute_location("c", "c")
      position.z += tip.total_tip_length - tip.fitting_depth
      for axis in ("x", "y", "z"):
        self.assertAlmostEqual(getattr(position, axis), getattr(expected, axis))

    lh = LiquidHandler(STARChatterboxBackend(), deck)
    await lh.setup()
    self.addCleanup(set_tip_tracking, does_tip_tracking())
    set_tip_tracking(True)
    try:
      await lh.pick_up_tips96(source)
      tips = [tracker.get_tip() for tracker in lh.head96.values()]
      await lh.drop_tips96(adapter)
      self.assertEqual([spot.get_tip() for spot in adapter.get_all_items()], tips)
      await lh.pick_up_tips96(adapter)
      self.assertEqual([tracker.get_tip() for tracker in lh.head96.values()], tips)
      await lh.discard_tips96()
      self.assertTrue(all(not tracker.has_tip for tracker in lh.head96.values()))
      self.assertTrue(all(not spot.has_tip() for spot in adapter.get_all_items()))
      self.assertTrue(all(not spot.has_tip() for spot in source.get_all_items()))
    finally:
      await lh.stop()
