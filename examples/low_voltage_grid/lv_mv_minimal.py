from pathlib import Path

import pandas as pd
import pypsa
from assume.scenario.loader_csv import read_grid

minimal_grid = pypsa.Network()

# Time-series data
start, end = '2016-01-13 11:00', '2016-01-13 12:00'
index = pd.date_range(start, end, freq="15T")
prosumer_1_load_ts = [5.0, 7.0, 3.0, -2.0]
prosumer_2_load_ts = [5.0, 7.0, 3.0, -2.0]

generator = ...
trafo = ...
prosumer_1 = ...
prosumer_2 = ...

minimal_grid.add(generator, trafo, prosumer_1, prosumer_2)

grid_path = Path(...)
minimal_grid.export_to_csv_folder(grid_path)

assume_grid = read_grid(grid_path)

# Scenario 1:
# Generator produces sufficient energy.
# Market clearing: Willingness-to pay

# Scenario 2:
# Generator produces less energy than required.
# Market clearing: Willingness-to pay

# Scenario 3:
# Generator produces less energy than required.
# Market clearing: Willingness-to pay but a minimal demand is always covered.

