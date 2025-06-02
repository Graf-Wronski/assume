from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

import pypsa

import logging
from datetime import timedelta, datetime

import pandas as pd
from dateutil import rrule as rr

from assume import World
from assume.common.forecasts import NaiveForecast
from assume.common.market_objects import MarketConfig, MarketProduct

from dateutil.relativedelta import relativedelta

import seaborn as sns
import matplotlib.dates as mdates

# Suppres pypsa deprecation warnings.
logging.getLogger("pypsa").setLevel(logging.ERROR)


class CongestionManagementAsRedispatch:
    def __init__(self, demand_input: pd.DataFrame):

        self.name = "00_congestion_management_as_redispatch"

        self.demand_index = demand_input.index
        self.demand_input = demand_input  # kW to MW for pypsa
        self.n = self.build_network()

        self.assume_world = self.create_assume_world()

    @property
    def data_root(self) -> Path:
        return Path(f"/home/carl-wanninger/data/assume/{self.name}")

    @property
    def simulation_steps(self)  -> rr.rrule:
        """ Simulations starts one day before demand. """
        sim_start = self.demand_index.min() - timedelta(days=1)
        sim_end = self.demand_index.max()
        return rr.rrule(freq=rr.HOURLY, dtstart=sim_start, until=sim_end)

    @property
    def eom_market_steps(self) -> rr.rrule:
        """ EOM starts with simualation and ends 24 hrs before demand ends. """
        eom_start = self.simulation_steps[0]
        eom_end = self.demand_index.max() - timedelta(days=1)
        return rr.rrule(freq=rr.HOURLY, dtstart=eom_start, until=eom_end)

    @property
    def rd_market_steps(self) -> rr.rrule:
        """ Redispatch is possible one hour before each demand. """
        rd_start = self.demand_index.min() - timedelta(hours=1)
        rd_end = self.demand_index.max() - timedelta(hours=1)
        return rr.rrule(freq=rr.HOURLY, dtstart=rd_start, until=rd_end)

    def build_network(self) -> pypsa.Network():
        """ Build a star shaped low-voltage grid. """

        n = pypsa.Network(snapshots=self.demand_index)

        # LV grid.
        n.add("Bus", "LV bus", v_nom=0.4)

        for prosumer in self.demand_input.columns:
            bus_name = f"{prosumer} bus"
            n.add("Bus", bus_name, v_nom=0.4)

        for prosumer in self.demand_input.columns:
            name = f"{prosumer} load"
            bus = f"{prosumer} bus"
            p_set = self.demand_input[prosumer]
            n.add("Load", name, bus=bus, p_set=p_set)

        for prosumer in self.demand_input.columns:
            bus0, bus1 = f"{prosumer} bus", "LV bus"
            params = {"type": "NAYY 4x150 SE", "s_nom": 4., "length": 0.2}
            name = f"Feeder {len(n.lines)}"
            n.add("Line", name, bus0=bus0, bus1=bus1, **params)

        # MV grid (represented by slack bus).
        name = "MV bus"
        n.add("Bus", name, v_nom=10.0, control="Slack")

        # Transformer
        bus0, bus1 = "MV bus", "LV bus"
        name = "MV/LV Transformer"
        trafo_type = "0.25 MVA 10/0.4 kV"
        n.add("Transformer", name, bus0=bus0, bus1=bus1, type=trafo_type)

        path_grid = self.data_root / "network"
        n.generators.to_csv(path_grid / "powerplant_units.csv")
        n.loads.to_csv(path_grid / "demand_units.csv")
        n.export_to_csv_folder(path_grid)

        return n

    def plot_network(self) -> None:
        # Increase size of MV grid buses and add some colors.
        bus_sizes = {b: 0.001 for b in self.n.buses.index}
        bus_colors = {b: "grey" for b in self.n.buses.index}
        bus_colors["Prosumer 1"], bus_colors["Prosumer 2"] = "green", "green"
        self.n.plot.map(
            bus_sizes=bus_sizes,
            bus_colors=bus_colors,
            margin=0.2)
        plt.show()

    def create_assume_world(self) -> World:
        db_uri = "sqlite:///local_db/assume_db.db"

        world = World(database_uri=db_uri, export_csv_path=str(self.data_root))

        simulation_id = "sim_00"

        world.setup(
            start=self.simulation_steps[0],
            end=self.simulation_steps[-1],
            save_frequency_hours=1,
            simulation_id=simulation_id)

        # Create a simple market.
        eom_product = MarketProduct(
            duration=relativedelta(hours=1),
            count=24,
            first_delivery=relativedelta(hours=24))

        eom_market = MarketConfig(
            market_id="EOM",
            opening_hours=self.eom_market_steps,
            opening_duration=timedelta(hours=1),
            market_mechanism="pay_as_clear",
            market_products=[eom_product],
            additional_fields=["block_id", "link", "exclusive_id"])

        mo_id = "market_operator"
        world.add_market_operator(id=mo_id)
        world.add_market(market_operator_id=mo_id, market_config=eom_market)


        grid_data = dict()
        grid_data["buses"] = self.n.buses
        grid_data["lines"] = self.n.lines
        loads = self.n.loads
        loads["node"] = loads["bus"]
        loads.drop("bus", axis=1, inplace=True)
        grid_data["loads"] = loads

        # n.add("Bus", name, v_nom=10.0, control="Slack")
        generators = {"node": "MV bus", "max_power": 10.0}
        grid_data["generators"] = pd.DataFrame(
            index=self.demand_index,
            data=generators)

        param_dict = dict()
        param_dict["grid_data"] = grid_data

        rd_product = MarketProduct(
            duration=relativedelta(hours=1),
            count=1,
            first_delivery=relativedelta(hours=1))

        redispatch_market = MarketConfig(
                market_id="REDISPATCH",
                opening_hours=self.rd_market_steps,
                opening_duration=timedelta(hours=1),
                market_mechanism="redispatch",
                market_products=[rd_product],
                additional_fields=["node", "max_power", "min_power"],
                maximum_bid_volume=1e9,
                maximum_bid_price=1e9,
                param_dict=param_dict,
            )

        world.add_market(market_operator_id=mo_id, market_config=redispatch_market)

        # Create consumers.
        for load_name, load_data in self.n.loads.iterrows():
            load = self.n.loads_t["p_set"][load_name]
            demand_forecast = NaiveForecast(self.demand_index, demand=load)
            world.add_unit_operator(f"demand_operator_{load_name}")

            world.add_unit(
                id=f"demand_unit_{load_name}",
                unit_type="demand",
                unit_operator_id=f"demand_operator_{load_name}",
                unit_params={
                    "min_power": 0,
                    "max_power": 1000,
                    "bidding_strategies": {
                        "EOM": "naive_eom",
                        "REDISPATCH": "naive_eom"},
                    "technology": "demand",
                    "price": 2.5,
                },
                forecaster=demand_forecast)

        for i in range(1):
            world.add_unit_operator(f"plant_operator_{i}")

            nuclear_forecast = NaiveForecast(self.demand_index, availability=1,
                                             fuel_price=2.5 + i)

            world.add_unit(
                id=f"nucular_unit_{i}",
                unit_type="power_plant",
                unit_operator_id=f"plant_operator_{i}",
                unit_params={
                    "min_power": 0.000,
                    "max_power": 500.0,
                    "bidding_strategies": {
                        "EOM": "naive_eom",
                        "REDISPATCH": "naive_eom"},
                    "technology": "nuclear",
                },
                forecaster=nuclear_forecast)

            return world

    def plot_market_orders(self) -> None:
        p = self.data_root / "sim_00" / "market_orders.csv"
        market_orders = pd.read_csv(p)
        x = pd.DatetimeIndex(market_orders["start_time"])

        ax = sns.scatterplot(market_orders, x=x, y="accepted_volume",
                             hue="unit_id")

        ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
        plt.show()

    def main(self):
        self.assume_world.run()
        self.plot_market_orders()


if __name__ == '__main__':
    np.random.seed(65537)

    load_start = datetime(2023, 1, 13, hour=0, minute=0)
    load_end = datetime(2023, 1, 14, hour=0, minute=0)
    index = pd.date_range(load_start, load_end, freq="60min")

    prosumers ={"Prosumer 1": np.random.normal(2.0, .5 , len(index)),
                "Prosumer 2": np.random.normal(4.0, .5 , len(index)),
    }

    load_data = pd.DataFrame(prosumers, index=index)

    model = CongestionManagementAsRedispatch(load_data)
    model.main()