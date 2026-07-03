def compute_safety_score(route_length: float, crime_penalty: float, traffic_penalty: float, lighting_penalty: float = 0.0) -> float:
    """Return a simple safety score for the route."""
    raw_score = 100.0 - (route_length * 0.002) - crime_penalty - traffic_penalty - lighting_penalty
    return max(0.0, min(100.0, raw_score))


def build_explanation(crime_penalty: float, traffic_penalty: float, avoid_dark: bool) -> str:
    """Create a short explanation string for the route."""
    if avoid_dark:
        return "This route favors lower-risk streets and slightly prefers better-lit roads."
    if crime_penalty > traffic_penalty:
        return "This route avoids higher-crime areas and favors less exposed streets."
    return "This route uses a balance of distance, crime exposure, and traffic activity."
