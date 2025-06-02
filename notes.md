# Notes:Congestion management in Assume

## Current congestion management in assume.
### RedispatchMarketRole
The class `RedispatchMarketRole` is specifically designed to resolve 
congestions via redispatch.
*What exactly does 'redispatch' mean in the context of assume?*
The method `clear()` can be structured in three steps:
1. Calculate upwards and downwards potential of generators. That 
   is: Calculate the difference to minimal and maximal generation and 
   interprete it as upwards and downwards potential.  
2. Given these potentials: Run a redispatch market as an optimal linear power 
   flow. 
3. Process results of power flow, i.e. update the orderbook by accepted 
   orders and their prices.  

The redispatch market is a static optimization, i.e. the side conditions 
are met *per time step*. When optimizing a low-voltage grid however, 
rejecting an "order" (i.e. a load) at one time step incentivices an order 
at a later stage. That is, given a foreseeable congestion, instead of 
powerflow a central optimization with all relevant side conditions has to 
be performed. A potential objective function could be to minimize redispatch.

# Plan
## Redispatch Market modifizieren
## Step: 1 model 2 node net with negative generators and old re-dispatch.
## Step 2: Add constraints of e.g. heat pumps to pypsa optimization.


# Issues
## Issue with minimal example.
The exampe is not minimal as it contains non explained and non necessary
parameters such as save_frequency and db
"The whole code as a single cell" does not fit single cells (e.g index)
"demand_unit_" seems to be necessary for units to be recognized as demand unit
despite unit_type="demand" (and this is not explained)
Having both start,end and a diverging index in World is confusing.