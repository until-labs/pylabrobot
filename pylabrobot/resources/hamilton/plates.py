from pylabrobot.resources.compact import compact_factory
from pylabrobot.resources.height_volume_functions import (
  compute_height_from_volume_rectangle,
  compute_volume_from_height_rectangle,
)
from pylabrobot.resources.plate import Plate
from pylabrobot.resources.utils import create_ordered_items_2d
from pylabrobot.resources.well import (
  CrossSectionType,
  Well,
  WellBottomType,
)
@compact_factory
def Hamilton_1_troughplate_300ml(name: str) -> Plate:
  """
  Part # 56669-01 (slightly modified to allow dispensing with 96 head)
  - Material: Polypropylene
  - Max. volume: 300 mL
  """
  INNER_WELL_WIDTH = 108.1  # hot fix to allow dispensing with 96 head (real measured is 107.3)
  INNER_WELL_HEIGHT = 70.9  # measured

  well_kwargs = {
    "size_x": INNER_WELL_WIDTH,  # measured
    "size_y": INNER_WELL_HEIGHT,  # measured
    "size_z": 37.1,  # measured to bottom of well
    "bottom_type": WellBottomType.FLAT,
    "cross_section_type": CrossSectionType.RECTANGLE,
    "compute_height_from_volume": lambda liquid_volume: compute_height_from_volume_rectangle(
      liquid_volume,
      INNER_WELL_HEIGHT,
      INNER_WELL_WIDTH,
    ),
    "compute_volume_from_height": lambda liquid_height: compute_volume_from_height_rectangle(
      liquid_height,
      INNER_WELL_HEIGHT,
      INNER_WELL_WIDTH,
    ),
    "material_z_thickness": 1,
  }

  return Plate(
    name=name,
    size_x=127.76,  # from spec
    size_y=85.48,  # from spec
    size_z=44.2,  # measured
    model=Hamilton_1_troughplate_300ml.__name__,
    ordered_items=create_ordered_items_2d(
      Well,
      num_items_x=1,
      num_items_y=1,
      dx=10.3, # measured
      dy=7.3, # measured
      dz=6.9, # measured
      item_dx=INNER_WELL_WIDTH,
      item_dy=INNER_WELL_HEIGHT,
      **well_kwargs,
    ),
  )