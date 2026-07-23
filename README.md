# Toronto Safest Path

A walking-directions app for Toronto that scores routes for safety instead of just picking the shortest path. Give it a start and end address and it builds a live pedestrian graph from OpenStreetMap, weights every block using Toronto's crime and traffic data, and returns a route along with a 0-100 safety score and a short explanation of why it took that path.

## Structure

- `src/geocoding.py` - address search/autocomplete via Nominatim, bounded to Toronto
- `src/routing.py` - builds the walk graph and computes safety-weighted routes
- `src/scoring.py` - turns route penalties into a 0-100 score and explanation
- `src/app.py` - Streamlit UI
- `tests/` - unit tests
- `data/` - Toronto crime and traffic datasets
- `cache/` - local geocoding/graph cache (gitignored, rebuilds automatically)

## How the routing works

Each street segment gets a cost based on its length plus three penalties: crime risk, vehicle traffic risk, and (optionally) how well it's lit. Crime and traffic counts are binned geographically and ranked by percentile against the rest of the city rather than compared to a fixed threshold, so "high crime" means something consistent whether you're downtown or in a quiet residential pocket.

One thing worth calling out: vehicle traffic and foot/bike traffic are treated as opposites. Cars, trucks, and buses count against a route as a pedestrian hazard. Pedestrian and bike volume does the opposite - it discounts nearby crime risk, on the theory that busier sidewalks mean more people around to notice trouble. Earlier these were lumped into one "traffic" number, which meant a busy commercial street with lots of foot traffic got penalized the same as a busy arterial road. Splitting them by data column fixed that.

Once the graph is weighted, Dijkstra finds the lowest-cost path. That per-edge cost is unbounded so risk stays differentiated even on long routes, while the score shown to the user is a separate, bounded 0-100 formula - crime and traffic penalties are blended (55/45) rather than summed, since summing could blow past 100 even when neither factor was at its worst alone. The score is then rescaled onto a 15-100 range so nothing ever displays as a literal 0.

## Tech stack

OSMnx + NetworkX for routing, pandas/GeoPandas for the crime and traffic data, geopy (Nominatim) for geocoding, Streamlit + Folium for the UI.

## Getting started

```bash
pip install -r requirements.txt
streamlit run src/app.py
```

## Tests

```bash
python -m unittest discover -s tests -v
```

## What's not done yet

- No end-to-end test for `find_route` itself - only `attach_safety_weights` is tested directly, against a synthetic graph
- The score weights (like the 0.55/0.45 blend) are hand-picked, not calibrated against any real outcome data
- The OSM walk graph is rebuilt from scratch on every request - no persistent on-disk cache
- Only one route is shown; no way to compare safest vs. shortest side by side
- No CI running the tests on push

## MVP goals

- Enter a start and end address
- Generate a walking route
- Return a safety score
- Show a short explanation
- Support an optional dark-street avoidance toggle
