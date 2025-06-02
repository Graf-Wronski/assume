import pypsa
import numpy as np
from datetime import datetime
import pandas as pd
from pathlib import Path


def build_network_1(data_root: Path) -> pypsa.Network():
    """ Build a star shaped low-voltage grid. """

    np.random.seed(65537)

    load_start = datetime(2023, 1, 13, hour=0, minute=0)
    load_end = datetime(2023, 1, 14, hour=0, minute=0)
    index = pd.date_range(load_start, load_end, freq="60min")

    prosumers = {"Prosumer 1": np.random.normal(2.0, .5, len(index)),
                 "Prosumer 2": np.random.normal(4.0, .5, len(index))}

    demand = pd.DataFrame(prosumers, index=index)


    n = pypsa.Network(snapshots=index)

    # LV grid.
    n.add("Bus", "LV bus", v_nom=0.4)

    for prosumer in demand.columns:
        bus_name = f"{prosumer} bus"
        n.add("Bus", bus_name, v_nom=0.4)

    for prosumer in demand.columns:
        name = f"{prosumer} load"
        bus = f"{prosumer} bus"
        p_set = demand[prosumer]
        n.add("Load", name, bus=bus, p_set=p_set)

    for prosumer in demand.columns:
        bus0, bus1 = f"{prosumer} bus", "LV bus"
        params = {"type": "NAYY 4x150 SE", "s_nom": 4., "length": 0.2}
        name = f"Feeder {len(n.lines)}"
        n.add("Line", name, bus0=bus0, bus1=bus1, **params)

    # MV grid (represented by slack bus).
    bus_name = "MV bus"
    n.add("Bus", bus_name, v_nom=10.0)
    params = {"control": "PQ", "p_set": 7.0}
    gen_name = "nucular_unit_0"
    n.add("Generator", name=gen_name, bus=bus_name, **params)

    # Transformer
    bus0, bus1 = "MV bus", "LV bus"
    name = "MV/LV Transformer"
    trafo_type = "0.25 MVA 10/0.4 kV"
    n.add("Transformer", name, bus0=bus0, bus1=bus1, type=trafo_type)

    path_grid = data_root / "network"
    n.generators.to_csv(path_grid / "powerplant_units.csv")
    n.loads.to_csv(path_grid / "demand_units.csv")
    n.export_to_csv_folder(path_grid)

    return n


def check_congestion(n: pypsa.Network, data_root: Path):
    # ToDo: Congestion only sets values for loads, not for generatos.

    n.loads["bus"] = n.loads["node"]

    path = data_root / "sim_00" / "market_orders.csv"
    market_orders = pd.read_csv(path)
    market_orders["start_time"] = pd.DatetimeIndex(
        market_orders["start_time"])
    p_set = market_orders.groupby(["start_time", "unit_id"])[
                                   "accepted_volume"].sum()
    # P_set in pypsa format.
    p_set = p_set.reset_index().pivot(
        index="start_time",
        columns="unit_id",
        values="accepted_volume")

    p_set.index = pd.DatetimeIndex(p_set.index)
    # ToDo Debug the following line.
    n.loads_t["p_set"] = p_set.loc[n.snapshots, n.loads_t["p_set"].columns]
    n.lpf()

    line_loading = n.lines_t.p0.abs() / n.lines.s_nom

    # if any line is congested, perform redispatch
    if line_loading.max().max() > 1:
        print("Congestion detected")
    else:
        print("No Congestion detected")
