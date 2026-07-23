CRIME_PENALTY_MAX = 80.0
TRAFFIC_PENALTY_MAX = 80.0
LIGHTING_PENALTY_MAX = 25.0
SOFT_FLOOR = 15.0


def compute_safety_score(route_length: float, crime_penalty: float, traffic_penalty: float, lighting_penalty: float = 0.0) -> float:
    """Return a realistic safety score for the route."""
    # crime_penalty and traffic_penalty are each independently bounded at ~80
    # (see attach_safety_weights), so simply adding them could already exceed
    # the 100-point budget whenever both were just moderately elevated - not
    # only when both were at their worst. Blending them as a weighted average
    # (bounded 0-1) instead means the score only bottoms out when both are
    # genuinely near their individual maximums at once.
    crime_fraction = min(1.0, crime_penalty / CRIME_PENALTY_MAX)
    traffic_fraction = min(1.0, traffic_penalty / TRAFFIC_PENALTY_MAX)
    risk_blend = 0.55 * crime_fraction + 0.45 * traffic_fraction

    distance_penalty = route_length / 1000.0 * 0.65
    # Lighting is only ever nonzero when avoid_dark is on, so it's kept as a
    # small secondary deduction rather than part of the blend above - giving
    # it a fixed weight share there would cap how low the score could go
    # whenever lighting isn't being tracked (avoid_dark=False).
    lighting_penalty_weighted = min(LIGHTING_PENALTY_MAX, lighting_penalty)

    raw_score = 100.0 * (1.0 - risk_blend) - distance_penalty - lighting_penalty_weighted
    clamped = max(0.0, min(100.0, raw_score))

    # Rescale onto [SOFT_FLOOR, 100] so a route is never shown as a literal 0
    # (which reads as "impossible" rather than "worst measured in the city").
    # This is a linear rescale of the already-clamped value, so it preserves
    # relative differentiation between routes exactly - it only compresses the
    # visible range, it doesn't flatten anything the way a hard floor would.
    return SOFT_FLOOR + clamped * (100.0 - SOFT_FLOOR) / 100.0


def build_explanation(crime_penalty: float, traffic_penalty: float, avoid_dark: bool) -> str:
    """Create a short explanation string for the route."""
    if avoid_dark:
        if crime_penalty > traffic_penalty:
            return "This route avoids dark streets and reduces crime exposure where possible."
        return "This route avoids dark streets and balances crime and traffic exposure."
    if crime_penalty > traffic_penalty:
        return "This route avoids higher-crime areas and favors less exposed streets."
    return "This route uses a balance of distance, crime exposure, and traffic activity."
