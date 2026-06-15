import unittest

from pylabrobot.resources.errors import (
  TooLittleLiquidError,
  TooLittleVolumeError,
)
from pylabrobot.resources.liquid import Liquid
from pylabrobot.resources.volume_tracker import VolumeTracker


class TestVolumeTracker(unittest.TestCase):
  """Test for the tip volume tracker"""

  def test_init(self):
    tracker = VolumeTracker(thing="test", max_volume=100)
    self.assertEqual(tracker.get_free_volume(), 100)
    self.assertEqual(tracker.get_used_volume(), 0)

    tracker.set_liquids([(None, 20)])
    self.assertEqual(tracker.get_free_volume(), 80)
    self.assertEqual(tracker.get_used_volume(), 20)

  def test_add_liquid(self):
    tracker = VolumeTracker(thing="test", max_volume=100)

    tracker.add_liquid(liquid=None, volume=20)
    self.assertEqual(tracker.get_used_volume(), 20)
    self.assertEqual(tracker.get_free_volume(), 80)

    tracker.commit()
    self.assertEqual(tracker.get_used_volume(), 20)
    self.assertEqual(tracker.get_free_volume(), 80)

    with self.assertRaises(TooLittleVolumeError):
      tracker.add_liquid(liquid=None, volume=100)

  def test_remove_liquid(self):
    tracker = VolumeTracker(thing="test", max_volume=100)
    tracker.add_liquid(liquid=None, volume=60)
    tracker.commit()

    self.assertEqual(tracker.get_used_volume(), 60)
    tracker.remove_liquid(volume=20)
    tracker.commit()
    self.assertEqual(tracker.get_used_volume(), 40)

    with self.assertRaises(TooLittleLiquidError):
      tracker.remove_liquid(volume=100)

  def test_get_liquids(self):
    tracker = VolumeTracker(thing="test", max_volume=200)
    tracker.add_liquid(liquid=None, volume=60)
    tracker.add_liquid(liquid=Liquid.WATER, volume=60)
    tracker.commit()

    liquids = tracker.get_liquids(top_volume=100)
    self.assertEqual(liquids, [(Liquid.WATER, 60), (None, 40)])

    liquids = tracker.get_liquids(top_volume=50)
    self.assertEqual(liquids, [(Liquid.WATER, 50)])

    liquids = tracker.get_liquids(top_volume=60)
    self.assertEqual(liquids, [(Liquid.WATER, 60)])

    with self.assertRaises(TooLittleLiquidError):
      tracker.get_liquids(top_volume=600)

  def test_set_liquids_does_not_alias_pending_into_committed(self):
    """Regression: set_liquids must not alias pending_liquids to the committed
    `liquids` list. If it does, remove_liquid (which pops/appends pending in
    place) also mutates committed, so rollback restores from corrupted state and
    a faulted aspirate is never undone."""
    tracker = VolumeTracker(thing="reservoir", max_volume=300)
    tracker.set_liquids([(None, 200)])
    self.assertIsNot(tracker.liquids, tracker.pending_liquids)

    # Pending-only removals (as a faulted aspirate leaves before rollback)...
    tracker.remove_liquid(volume=50)
    tracker.remove_liquid(volume=50)
    self.assertEqual(tracker.get_used_volume(), 100)
    # ...must NOT have touched the committed volume.
    self.assertEqual(sum(v for _, v in tracker.liquids), 200)

    # rollback (the aspirate96 except-block path) fully restores pending.
    tracker.rollback()
    self.assertEqual(tracker.get_used_volume(), 200)
