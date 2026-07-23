# Toronto Safest Path MVP

A simple walking-focused prototype for finding a safer route in Toronto from one address to another.

## Structure

- `data/` contains the Toronto crime and traffic datasets
- `src/geocoding.py` geocodes addresses via Nominatim, with Toronto-bounded search and address autocomplete
- `src/routing.py` builds the walking graph and computes safety-weighted routes
- `src/scoring.py` computes the 0-100 safety score and a short explanation
- `src/app.py` provides a Streamlit UI (address autocomplete, avoid-dark toggle, route map)
- `tests/` unit tests for geocoding, routing, and scoring
- `cache/` local geocoding/graph cache (gitignored, rebuilds automatically)

## Run locally

```bash
pip install -r requirements.txt
streamlit run src/app.py
```

## Current state

- Address input uses live autocomplete (`search_addresses`) against Nominatim, bounded to a Toronto
  viewbox, with a `GeocodingServiceError` surfaced in the UI if the service is unreachable.
- Routing weights each street edge by crime risk, vehicle-traffic risk, and (optionally) lighting,
  then runs Dijkstra over that combined cost to pick a route:
  - Crime risk is a percentile-ranked count of nearby assault/robbery incidents (2020+), discounted
    in areas with heavy foot/bike traffic (more people around = more "eyes on the street").
  - Traffic risk is now vehicle-only (cars, trucks, buses) — pedestrian and bike volume no longer
    counts against a route, since it isn't a pedestrian hazard the way vehicle traffic is.
  - Lighting penalty only applies when "Avoid dark streets" is checked.
- The route's average penalties are blended into a single 0-100 safety score for display, rescaled
  onto a `[15, 100]` floor so nothing reads as a literal 0.
- Unit tests cover the scoring formula, the routing cost formula, and geocoding edge cases (empty
  input, service failures).

## Known gaps / next steps

- No integration test exercises `find_route` end-to-end against real (or fixture) crime/traffic data
  — only `attach_safety_weights` is tested directly with a synthetic 2-node graph.
- The safety score and routing cost formulas are heuristic and untuned against any ground truth
  (e.g. real pedestrian incident data); weights like the 0.55/0.45 crime/traffic blend are guesses,
  not calibrated.
- `build_walk_graph` downloads the full Toronto walk network from OSM on every request with no
  persistent on-disk graph cache, which makes first-route latency high; only geocoding results are
  cached in-process.
- No route alternatives are offered — the UI shows a single shortest-safety-cost path with no way to
  compare it against the plain-shortest-distance route.
- No automated CI (lint/test) is configured yet; tests are run manually via `python -m unittest`.

## MVP goals

- Enter a start and end address
- Generate a walking route
- Return a safety score
- Show a short explanation
- Support an optional dark-street avoidance toggle

## Tests

```bash
python -m unittest discover -s tests -v
```
