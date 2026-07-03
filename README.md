# Toronto Safest Path MVP

A simple walking-focused prototype for finding a safer route in Toronto from one address to another.

## Structure

- `data/` contains the Toronto crime and traffic datasets
- `src/geocoding.py` handles address geocoding
- `src/routing.py` builds the walking graph and finds routes
- `src/scoring.py` computes the safety score and explanation
- `src/app.py` provides a Streamlit UI

## Run locally

```bash
pip install -r requirements.txt
streamlit run src/app.py
```

## MVP goals

- Enter a start and end address
- Generate a walking route
- Return a safety score
- Show a short explanation
- Support an optional dark-street avoidance toggle
