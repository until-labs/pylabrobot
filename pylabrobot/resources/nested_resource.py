from __future__ import annotations

from typing import Optional

from pylabrobot.resources.coordinate import Coordinate
from pylabrobot.resources.resource import Resource
from pylabrobot.resources.resource_holder import get_child_location


class NestedResource(Resource):
  """A mixin for self-stacking labware: resources that nest directly onto another resource of
  the same kind at a fixed pitch (``stacking_z_height``), which is typically much smaller than
  the resource's full ``size_z`` (e.g. a nested tip rack with ``stacking_z_height=16`` but
  ``size_z=56``).

  A stack of nested resources is a parent->child *chain* — each resource is nested on the one
  below it, and every item remains a full resource at its nested position (which is exactly why
  picking the top off a stack already works). This is unlike :class:`~.ResourceStack`, whose
  single ``get_size_z`` doubles as both "where the next item goes" and "how tall the stack is";
  for nesting those two differ (pitch != height), so nestable labware must not be modeled as a
  ``ResourceStack``.

  Mix this into a concrete :class:`~.Resource` subclass and set ``stacking_z_height``; the nesting
  offset reuses :func:`~.get_child_location` — the same rotation-aware helper
  :class:`~.ResourceHolder` and :class:`~.ResourceStack` use — so nesting handles rotated children.
  """

  stacking_z_height: float

  def get_default_child_location(self, resource: Resource) -> Coordinate:
    """The location, relative to ``self``, where ``resource`` nests directly on top of ``self``
    (a single level up). Mirrors :meth:`ResourceHolder.get_default_child_location`."""
    return get_child_location(resource) + Coordinate(0, 0, self.stacking_z_height)

  def get_stack_top(self) -> NestedResource:
    """Walk the chain of nested children to the current top of the stack, returning ``self`` if
    nothing is nested on it. Depth-agnostic."""
    top: NestedResource = self
    while True:
      nested = next((c for c in top.children if isinstance(c, NestedResource)), None)
      if nested is None:
        return top
      top = nested

  def assign_child_resource(
    self,
    resource: Resource,
    location: Optional[Coordinate] = None,
    reassign: bool = True,
  ):
    if isinstance(resource, NestedResource):
      location = location or self.get_default_child_location(resource)
    else:
      assert location is not None, "Location must be specified if resource is not a NestedResource."
    return super().assign_child_resource(resource, location=location, reassign=reassign)

  def serialize(self) -> dict:
    return {**super().serialize(), "stacking_z_height": self.stacking_z_height}
