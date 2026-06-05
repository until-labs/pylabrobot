import unittest

from .coordinate import Coordinate
from .nested_resource import NestedResource
from .resource import Resource


class _NestedBox(NestedResource):
  """Minimal concrete host for the mixin — proves the nesting behavior is host-agnostic and not
  tied to ``NestedTipRack``."""

  def __init__(self, name: str, stacking_z_height: float = 10, size: float = 20):
    super().__init__(name, size_x=size, size_y=size, size_z=size)
    self.stacking_z_height = stacking_z_height


class NestedResourceTests(unittest.TestCase):
  def test_get_default_child_location(self):
    box = _NestedBox("box", stacking_z_height=16)
    child = _NestedBox("child")
    # single-level nest: pitch in z, nothing in x/y for an unrotated child.
    self.assertEqual(box.get_default_child_location(child), Coordinate(0, 0, 16))

  def test_assign_nests_at_stacking_z_height(self):
    bottom = _NestedBox("bottom", stacking_z_height=16)
    top = _NestedBox("top", stacking_z_height=16)
    bottom.assign_child_resource(top)  # build path defaults the location
    self.assertEqual(top.location, Coordinate(0, 0, 16))
    self.assertIs(top.parent, bottom)

  def test_assign_explicit_location_respected(self):
    bottom = _NestedBox("bottom", stacking_z_height=16)
    top = _NestedBox("top")
    bottom.assign_child_resource(top, location=Coordinate(0, 0, 5))
    self.assertEqual(top.location, Coordinate(0, 0, 5))

  def test_assign_non_nested_requires_location(self):
    bottom = _NestedBox("bottom", stacking_z_height=16)
    plain = Resource("plain", size_x=1, size_y=1, size_z=1)
    with self.assertRaises(AssertionError):
      bottom.assign_child_resource(plain)
    # but works with an explicit location
    bottom.assign_child_resource(plain, location=Coordinate(1, 2, 3))
    self.assertEqual(plain.location, Coordinate(1, 2, 3))

  def test_get_stack_top_one_high(self):
    bottom = _NestedBox("bottom")
    self.assertIs(bottom.get_stack_top(), bottom)

  def test_get_stack_top_two_and_three_high(self):
    bottom = _NestedBox("bottom", stacking_z_height=16)
    mid = _NestedBox("mid", stacking_z_height=16)
    top = _NestedBox("top", stacking_z_height=16)
    bottom.assign_child_resource(mid)
    self.assertIs(bottom.get_stack_top(), mid)
    mid.assign_child_resource(top)
    self.assertIs(bottom.get_stack_top(), top)
    self.assertIs(mid.get_stack_top(), top)

  def test_get_stack_top_ignores_non_nested_children(self):
    bottom = _NestedBox("bottom", stacking_z_height=16)
    # a non-nested child (e.g. a tip spot on a rack) must not be mistaken for the stack top.
    bottom.assign_child_resource(
      Resource("plain", size_x=1, size_y=1, size_z=1), location=Coordinate(0, 0, 0)
    )
    self.assertIs(bottom.get_stack_top(), bottom)

  def test_serialize_carries_stacking_z_height(self):
    box = _NestedBox("box", stacking_z_height=16)
    self.assertEqual(box.serialize()["stacking_z_height"], 16)


class NestedTipRackIsNestedResourceTests(unittest.TestCase):
  """NestedTipRack is the first concrete implementor; its public API and factories are unchanged."""

  def test_ntr_is_a_nested_resource(self):
    from pylabrobot.resources.tip_rack import NestedTipRack

    self.assertTrue(issubclass(NestedTipRack, NestedResource))

  def test_factory_api_and_nesting_unchanged(self):
    from pylabrobot.resources.hamilton import hamilton_96_tiprack_50uL_NTR

    bottom = hamilton_96_tiprack_50uL_NTR(name="bottom")
    top = hamilton_96_tiprack_50uL_NTR(name="top")
    self.assertEqual(bottom.stacking_z_height, 16.0)
    self.assertEqual(bottom.get_size_z(), 56.0)

    bottom.assign_child_resource(top)  # NTR auto-stacks via the mixin
    self.assertEqual(top.location, Coordinate(0, 0, 16))
    self.assertIs(bottom.get_stack_top(), top)

  def test_ntr_verbose_serialization_round_trips(self):
    from pylabrobot.resources.hamilton import hamilton_96_tiprack_50uL_NTR

    bottom = hamilton_96_tiprack_50uL_NTR(name="bottom")
    bottom.assign_child_resource(hamilton_96_tiprack_50uL_NTR(name="top"))
    self.assertEqual(bottom.serialize()["stacking_z_height"], 16.0)
    self.assertEqual(Resource.deserialize(bottom.serialize()), bottom)


if __name__ == "__main__":
  unittest.main()
