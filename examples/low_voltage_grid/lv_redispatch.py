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

from examples.low_voltage_grid.util.networks import build_network_1, \
    check_congestion

# Suppres pypsa deprecation warnings.
logging.getLogger("pypsa").setLevel(logging.ERROR)


class CongestionManagementAsRedispatch:
    def __init__(self):

        self.name = "00_congestion_management_as_redispatch"

        self.start = datetime(2023, 1, 12, 0, 0)
        self.end = datetime(2023, 1, 14, 0, 0)

        self.n = build_network_1(self.data_root)
        self.demand_index = self.n.snapshots
        self.demand_input = self.n.loads_t
        self.assume_world = self.create_assume_world()

    @property
    def data_root(self) -> Path:
        return Path(f"/home/carl-wanninger/data/assume/{self.name}")

    @property
    def index(self):
        """ End +24 hours as in assume examples. """
        return pd.date_range(
            start=self.start,
            end=self.end + timedelta(hours=24),
            freq="h")

    @property
    def eom_market_steps(self) -> rr.rrule:
        """ EOM starts with simualation and ends 24 hrs before demand ends. """
        return rr.rrule(freq=rr.HOURLY, dtstart=self.start, until=self.end)

    @property
    def rd_market_steps(self) -> rr.rrule:
        """ Redispatch is possible one hour before each demand. """
        return rr.rrule(freq=rr.HOURLY, dtstart=self.start + timedelta(
            hours=21), until=self.end)

    @property
    def bidding_strategies(self):
        return {"EOM": "naive_eom", "REDISPATCH": "naive_eom"}

    def plot_topology(self) -> None:
        # Increase size of MV grid buses and add some colors.
        bus_sizes = {b: 0.001 for b in self.n.buses.index}
        bus_colors = {b: "grey" for b in self.n.buses.index}
        bus_colors["Prosumer 1"], bus_colors["Prosumer 2"] = "green", "green"
        self.n.plot.map(bus_sizes=bus_sizes, bus_colors=bus_colors, margin=0.2)
        plt.show()

    def create_assume_world(self) -> World:
        db_uri = "sqlite:///local_db/assume_db.db"

        world = World(database_uri=db_uri, export_csv_path=str(self.data_root))

        simulation_id = "sim_00"

        world.setup(
            start=self.start,
            end=self.end,
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
            additional_fields=["node", "max_power", "min_power"])

        mo_id = "market_operator"
        world.add_market_operator(id=mo_id)
        world.add_market(market_operator_id=mo_id, market_config=eom_market)

        param_dict = dict()
        param_dict["grid_data"] = self.grid_data

        rd_product = MarketProduct(
            duration=relativedelta(hours=1),
            count=24,
            first_delivery=relativedelta(hours=3))

        redispatch_market = MarketConfig(
                market_id="REDISPATCH",
                opening_hours=self.rd_market_steps,
                opening_duration=timedelta(hours=1),
                market_mechanism="redispatch",
                market_products=[rd_product],
                additional_fields=["node", "max_power", "min_power"],
                param_dict=param_dict)

        world.add_market(
            market_operator_id=mo_id,
            market_config=redispatch_market)

        # Create consumers.
        for load_name, load_data in self.n.loads.iterrows():
            load = self.n.loads_t["p_set"][load_name]

            demand_forecast = NaiveForecast(self.demand_index, demand=load)

            world.add_unit_operator(f"demand_operator_{load_name}")
            world.add_unit(
                id=f"demand_unit_{load_name}",  # demand_unit is required
                                                # for assume
                unit_type="demand",
                unit_operator_id=f"demand_operator_{load_name}",
                unit_params={
                    "max_power": 200.,
                    "min_power": 0.,
                    "bidding_strategies": self.bidding_strategies,
                    "technology": "demand",
                    "price": 2.5},
                forecaster=demand_forecast)

        world.add_unit_operator(f"plant_operator_{0}")

        nuclear_forecast = NaiveForecast(
            self.demand_index,
            availability=1,
            fuel_price=2.5)

        world.add_unit(
            id=f"nucular_unit_{0}",
            unit_type="power_plant",
            unit_operator_id=f"plant_operator_{0}",
            unit_params={
                "min_power": 0.,
                "max_power": 5.,
                "bidding_strategies": self.bidding_strategies,
                "technology": "nuclear"},
            forecaster=nuclear_forecast)

        return world

    @property
    def grid_data(self) -> dict:
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

        return grid_data

    def plot_market_orders(self) -> None:
        path = self.data_root / "sim_00" / "market_orders.csv"
        market_orders = pd.read_csv(path)
        x = pd.DatetimeIndex(market_orders["start_time"])

        ax = sns.scatterplot(market_orders, x=x, y="accepted_volume",
                             hue="unit_id")

        ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H'))
        plt.show()

    def run(self):
        self.assume_world.run()
        check_congestion(self.n, self.data_root)
        # self.plot_market_orders()


if __name__ == '__main__':
    model = CongestionManagementAsRedispatch()
    model.run()