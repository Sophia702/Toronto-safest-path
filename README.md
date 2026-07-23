# Toronto Safest Path

A walking-directions app for Toronto that scores routes for safety instead of just picking the shortest path. Give it a start and end address and it builds a live pedestrian graph from OpenStreetMap, weights every block using Toronto's crime and traffic data, and returns a route along with a 0-100 safety score and a short explanation of why it took that path.

## Structure

- `src/geocoding.py` - address search/autocomplete via Nominatim, bounded to Toronto
- `src/routing.py` - builds the walk graph and computes safety-weighted routes
- `src/scoring.py` - turns route penalties into a 0-100 score and explanation
- `src/api.py` - FastAPI backend: the `/api/addresses` and `/api/route` endpoints, plus a lazy, thread-safe cache for the (expensive to build) safety-weighted graph
- `frontend/` - static HTML/CSS/vanilla JS UI, served by the API, with a Leaflet map
- `tests/` - unit tests
- `data/` - Toronto crime and traffic datasets
- `cache/` - local geocoding/graph cache (gitignored, rebuilds automatically)

## How the routing works

Each street segment gets a cost based on its length plus three penalties: crime risk, vehicle traffic risk, and (optionally) how well it's lit. Crime and traffic counts are binned geographically and ranked by percentile against the rest of the city rather than compared to a fixed threshold, so "high crime" means something consistent whether you're downtown or in a quiet residential pocket.

One thing worth calling out: vehicle traffic and foot/bike traffic are treated as opposites. Cars, trucks, and buses count against a route as a pedestrian hazard. Pedestrian and bike volume does the opposite - it discounts nearby crime risk, on the theory that busier sidewalks mean more people around to notice trouble. Earlier these were lumped into one "traffic" number, which meant a busy commercial street with lots of foot traffic got penalized the same as a busy arterial road. Splitting them by data column fixed that.

Once the graph is weighted, Dijkstra finds the lowest-cost path. That per-edge cost is unbounded so risk stays differentiated even on long routes, while the score shown to the user is a separate, bounded 0-100 formula - crime and traffic penalties are blended (55/45) rather than summed, since summing could blow past 100 even when neither factor was at its worst alone. The score is then rescaled onto a 15-100 range so nothing ever displays as a literal 0.

## The API

Two endpoints, both consumed by the frontend but usable on their own (interactive docs at `/docs` once the server's running):

- `GET /api/addresses?q=&limit=` - Toronto-bounded address autocomplete. Returns `{"results": [{"label", "lat", "lon"}, ...]}`. A `GeocodingServiceError` from the upstream geocoder maps to a 503 rather than a 500, since it's an upstream outage, not a bug.
- `POST /api/route` - body is `{start_lat, start_lon, end_lat, end_lon, avoid_dark}` (coordinates, not addresses - geocoding already happened client-side). Returns distance, safety score, explanation, and a crime/traffic/lighting breakdown (each with its point value and cap, so the client doesn't need to hardcode caps twice). A same-point request maps to 400; no walkable path between the two points maps to 404.

Route computation needs a safety-weighted graph, and building one is expensive (crime/traffic data has to be geographically binned and percentile-ranked across the whole city). Since `avoid_dark` is the only thing that changes between requests, the API caches the raw OSM graph once and the two weighted variants (`avoid_dark` true/false) separately, built lazily on first use and guarded by a lock so concurrent cold-start requests don't duplicate the work.

## Tech stack

OSMnx + NetworkX for routing, pandas/GeoPandas for the crime and traffic data, geopy (Nominatim) for geocoding, FastAPI for the API, vanilla JS + Leaflet for the frontend.

## Getting started

```bash
pip install -r requirements.txt
uvicorn src.api:app --reload
```

Then open `http://localhost:8000`.

## Tests

```bash
python -m unittest discover -s tests -v
```

## What's not done yet

- No end-to-end test for `find_route` itself - only `attach_safety_weights` is tested directly, against a synthetic graph
- The score weights (like the 0.55/0.45 blend) are hand-picked, not calibrated against any real outcome data
- The graph cache lives in process memory only - a server restart pays the full OSM download + crime/traffic binning cost again, there's no persistent on-disk cache
- Only one route is shown; no way to compare safest vs. shortest side by side
- No CI running the tests on push
- No auth, rate limiting, or CORS handling - built for local/single-user demo use, not multi-tenant deployment
- No frontend build step or bundler - the JS is a single unbundled file, fine at this size but wouldn't scale to a bigger UI

## MVP goals

The original v1 scope, still the core of the app - everything since (the FastAPI/Leaflet rewrite, the vehicle/foot traffic split, the graph cache) has built on top of this, not replaced it:

- Enter a start and end address
- Generate a walking route
- Return a safety score
- Show a short explanation
- Support an optional dark-street avoidance toggle
