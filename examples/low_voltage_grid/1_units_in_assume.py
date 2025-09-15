#%% md
# # Small steps on a small scale: Integrating low-voltage DNs in ASSUME
#%% md
# ## Notebook 1: Units as implemented in ASSUME and their ability to participate on a lokal market.
#%% md
# This notebook displays LV units as implemented in ASSUME and their ability to participate on a lokal market.
# 
# Deliverables:
# 1. Define a small test distribution network.
# 2. Define a local EOM market, where units can trade.
# 3. Subsequently add BASE, PV, HP, BSS and EV to the market.
# 4. Display resulting trading activity and ask yourself, if transactions make sense.
#%%
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

import matplotlib.dates as mdates

import pypsa

import logging
from datetime import datetime, timedelta

import pandas as pd
from dateutil import rrule as rr

from assume import World
from assume.common.forecasts import NaiveForecast, CsvForecaster
from assume.common.market_objects import MarketConfig, MarketProduct

from assume.units.dst_components import HeatPump
from assume.units.building import Building
from assume.strategies.naive_strategies import NaiveDADSMStrategy


#%% md
# ### Deliverable 1: Definition of a small test distribution network.
# 
# Define a test distribution network with:
# - Five households with BASELOAD.
# - An infinite supplier / buyer of power.
# - Topology might be neglectable for the moment.
#%% md
# ### Deliverable 2: Definition of a local EOM market.
# 
# Define a local EOM market such that:
# - Units can buy energy from each other and from infinite supplier / buyer.
# - Trading locally is preferred over buying remotely.
#%%
def get_random_demand(n_steps):
    """ A load profile (MW) peaking in morning and evening hours. """

    demand_series = []
    for i in range(n_steps):
        if i / n_steps < 0.25:
            demand = np.random.normal(0.5, 0.1)
        elif 0.25 <= (i / n_steps) and (i / n_steps) < 0.35:
            demand = np.random.normal(1.5, 0.3)
        elif 0.35 <= (i / n_steps) and (i / n_steps) < 0.7:
            demand = np.random.normal(0.7, 0.1)
        elif 0.7 <= (i / n_steps) and (i / n_steps) < 0.85:
            demand = np.random.normal(1.5, 0.3)
        elif 0.85 <= (i / n_steps):
            demand = np.random.normal(0.5, 0.1)

        demand_series.append(abs(demand) / 1000)

    return demand_series

data_root = Path("/home/carl-wanninger/data/assume/simulations")

start = datetime(2023, 1, 13, hour=0)
end = datetime(2023, 1, 13, hour=17)
temporal_resolution = "60min"
index = pd.date_range(start, end, freq=temporal_resolution)
n_steps = len(index)

# Create ASSUME World.
simulation_id = "lv_units_in_assume"
db_uri = "sqlite:///local_db/assume_db.db"
world = World(database_uri=db_uri, export_csv_path=data_root)
world.setup(
    start=start,
    end=end,
    save_frequency_hours=1,
    simulation_id=simulation_id,
    index=index)

n_users = 2
p_low, p_mid, p_high = 0.5, 1.0, 1.5
baseload_prices_accepted = [p_mid, p_mid, p_high, p_high, p_high]
np.random.seed(65537)

market_product = MarketProduct(
    duration=timedelta(hours=1),
    count=24,
    first_delivery=timedelta(hours=1))

market_config = MarketConfig(
    market_id="EOM",
    opening_hours=rr.rrule(rr.HOURLY, interval=1, dtstart=start, until=end),
    opening_duration=timedelta(hours=1),
    market_mechanism="pay_as_clear",
    market_products=[market_product],
    additional_fields=["block_id", "link", "exclusive_id"])

mo_id = "market_operator"
world.add_market_operator(id=mo_id)

world.add_market(market_operator_id=mo_id, market_config=market_config)

world.add_unit_operator("infinity_operator")

nuclear_forecast = NaiveForecast(index, availability=1, fuel_price=p_mid)
world.add_unit(
    id="infinity_supply",
    unit_type="power_plant",
    unit_operator_id="infinity_operator",
    unit_params={
        "min_power": 0.0,
        "max_power": 2000,
        "bidding_strategies": {"EOM": "naive_eom"},
        "technology": "nuclear"},
    forecaster=nuclear_forecast)


for i in range(n_users):
    # Add households.

    demand = get_random_demand(n_steps)
    # demand = pd.Series(index=index, data=demand)
    demand_forecast = NaiveForecast(index, demand=demand)
    # demand_forecast = NaiveForecast(index, demand=100)

    world.add_unit_operator(f"household_{i}_HEMS")

    world.add_unit(
        id=f"demand_household_{i}",
        unit_type="demand",
        unit_operator_id=f"household_{i}_HEMS",
        unit_params={
            "min_power": 0,
            "max_power": 1000,
            "bidding_strategies": {}, # {"EOM": "naive_eom"},
            "technology": "demand"},
        forecaster=demand_forecast)
#%%

try:
    world.add_unit_operator("building_operator")
except ValueError:
    pass

price_profile = [50, 45, 55, 40, 1000, 55, 1000, 65, 45, 70,
                 55, 32, 1000, 30, 10, 25, 40, 45]

forecaster = CsvForecaster(
    index,
    powerplants_units=[],  # Add appropriate values
    demand_units=[],
    market_configs=[])
forecaster.forecasts["price_EOM"] = price_profile
forecaster.forecasts["fuel_price_natural gas"] = pd.Series([30] * n_steps, index=index)
forecaster.forecasts["building_heat_demand"] = pd.Series([50] * n_steps, index=index)
forecaster.forecasts["ev_load_profile"] = pd.Series([5] * n_steps, index=index)
forecaster.forecasts["battery_load_profile"] = pd.Series([3] * n_steps, index=index)
forecaster.forecasts["building_load_profile"] = pd.Series([20] * n_steps, index=index)
forecaster.forecasts["availability_solar"] = pd.Series([0.25] * n_steps, index=index)
forecaster.forecasts["building_pv_power_profile"] = pd.Series([10] * n_steps, index=index)
forecaster.forecasts["building_heat_demand"] = pd.Series([50] * n_steps, index=index)
forecaster.convert_forecasts_to_fast_series()

heat_pump_config = {
    "max_power": 80,
    "cop": 3.5,
    "min_power": 10,
    "ramp_up": 20,
    "ramp_down": 20,
    "min_operating_steps": 2,
    "min_down_steps": 2,
    "initial_operational_status": 1}

building_config = {
    "components": {"heat_pump": heat_pump_config},
    "bidding_strategies": {"EOM": "naive_eom"}}

# hp = HeatPump(max_power=7*10e-3, cop=0.7, time_steps=[0, 1])
b = Building(
    id="building",
    unit_operator="building_operator",
    bidding_strategies={"EOM": "naive_eom"},
    components={"heat_pump": heat_pump_config},
    forecaster=forecaster)

# Perform optimization
b.determine_optimal_operation_without_flex()
world.add_unit(
    b,
    unit_type="building",
    unit_operator_id="building_operator",
    unit_params=building_config,
    forecaster=forecaster)

try:
    world.run()
except RuntimeError:
    pass

market_orders = pd.read_csv(data_root / "lv_units_in_assume" / "market_orders.csv")
market_orders

#%% md
# ### Deliverable 4: Display Transactions.
# 
# Displayed Transactions make sense, if:
# - Demand meets supply.
# - Lower prices when buying are preferred.
# - Higher prices when selling are preferred.