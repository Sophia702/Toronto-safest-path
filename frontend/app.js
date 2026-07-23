const API_BASE = "/api";
const WALK_SPEED_KMH = 5.0;
const DEBOUNCE_MS = 400;
const MIN_QUERY_LENGTH = 3;
const ACCENT = "#2a78d6";

// Same fixed status palette as the rest of the app's design system:
// (threshold, label, fill, track tint, ink)
const SEVERITY_BANDS = [
    [75, "Good", "#0ca30c", "rgba(12, 163, 12, 0.14)", "#ffffff"],
    [55, "Moderate", "#fab219", "rgba(250, 178, 25, 0.18)", "#0b0b0b"],
    [35, "Elevated risk", "#ec835a", "rgba(236, 131, 90, 0.18)", "#0b0b0b"],
    [0, "High risk", "#d03b3b", "rgba(208, 59, 59, 0.14)", "#ffffff"],
];

function severity(score) {
    for (const band of SEVERITY_BANDS) {
        if (score >= band[0]) return { label: band[1], fill: band[2], track: band[3], ink: band[4] };
    }
    return { label: SEVERITY_BANDS[3][1], fill: SEVERITY_BANDS[3][2], track: SEVERITY_BANDS[3][3], ink: SEVERITY_BANDS[3][4] };
}

function debounce(fn, ms) {
    let timer = null;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), ms);
    };
}

class AddressAutocomplete {
    constructor(inputEl, listEl) {
        this.inputEl = inputEl;
        this.listEl = listEl;
        this.selected = null;

        const debouncedSearch = debounce((query) => this._search(query), DEBOUNCE_MS);
        this.inputEl.addEventListener("input", () => {
            this.selected = null;
            const query = this.inputEl.value.trim();
            if (query.length < MIN_QUERY_LENGTH) {
                this.listEl.innerHTML = "";
                return;
            }
            debouncedSearch(query);
        });

        document.addEventListener("click", (event) => {
            if (!this.listEl.contains(event.target) && event.target !== this.inputEl) {
                this.listEl.innerHTML = "";
            }
        });
    }

    async _search(query) {
        let data;
        try {
            const resp = await fetch(`${API_BASE}/addresses?q=${encodeURIComponent(query)}&limit=5`);
            if (resp.status === 503) {
                this._renderMessage("Address lookup is temporarily unavailable. Please try again in a moment.");
                return;
            }
            if (!resp.ok) {
                this._renderMessage("Address lookup failed. Please try again.");
                return;
            }
            data = await resp.json();
        } catch (err) {
            this._renderMessage("Address lookup failed. Please try again.");
            return;
        }
        this._renderResults(data.results);
    }

    _renderMessage(text) {
        this.listEl.innerHTML = "";
        const item = document.createElement("div");
        item.className = "suggestion-item";
        item.textContent = text;
        this.listEl.appendChild(item);
    }

    _renderResults(results) {
        this.listEl.innerHTML = "";
        for (const result of results) {
            const item = document.createElement("div");
            item.className = "suggestion-item";
            item.textContent = result.label;
            item.addEventListener("click", () => {
                this.selected = { lat: result.lat, lon: result.lon };
                this.inputEl.value = result.label;
                this.listEl.innerHTML = "";
            });
            this.listEl.appendChild(item);
        }
    }

    getCoords() {
        return this.selected;
    }
}

function statTileHtml(label, value, sub) {
    const subHtml = sub ? `<div class="stat-tile-sub">${sub}</div>` : "";
    return `
        <div class="stat-tile-label">${label}</div>
        <div class="stat-tile-value">${value}</div>
        ${subHtml}
    `;
}

function scoreTileHtml(score) {
    const s = severity(score);
    const pct = Math.max(0, Math.min(100, score));
    return `
        <div class="stat-tile-label">Safety score</div>
        <div class="stat-tile-value">${score.toFixed(0)}<span class="unit">/100</span></div>
        <span class="badge" style="background:${s.fill};color:${s.ink};">${s.label}</span>
        <div class="meter-track" style="background:${s.track};">
            <div class="meter-fill" style="width:${pct}%; background:${s.fill};"></div>
        </div>
    `;
}

function breakdownBarsHtml(breakdown, avoidDark) {
    const rows = [
        ["Crime exposure", breakdown.crime],
        ["Vehicle traffic exposure", breakdown.traffic],
    ];
    if (avoidDark) {
        rows.push(["Lighting penalty", breakdown.lighting]);
    }
    return rows
        .map(([label, { value, cap }]) => {
            const pct = cap ? Math.max(0, Math.min(100, (value / cap) * 100)) : 0;
            return `
                <div class="bar-row">
                    <div class="bar-label">${label}</div>
                    <div class="bar-track"><div class="bar-fill" style="width:${pct}%;"></div></div>
                    <div class="bar-value">${value.toFixed(1)} / ${cap.toFixed(0)}</div>
                </div>
            `;
        })
        .join("");
}

let map = null;
let routeLayer = null;

function initMap() {
    map = L.map("map").setView([43.6532, -79.3832], 12);
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        maxZoom: 19,
    }).addTo(map);
}

function renderRouteOnMap(routeCoords, startCoords, endCoords) {
    if (routeLayer) {
        map.removeLayer(routeLayer);
    }
    const startIcon = L.divIcon({ className: "", html: '<div style="width:14px;height:14px;border-radius:50%;background:#0ca30c;border:2px solid white;"></div>' });
    const endIcon = L.divIcon({ className: "", html: '<div style="width:14px;height:14px;border-radius:50%;background:#d03b3b;border:2px solid white;"></div>' });

    const polyline = L.polyline(routeCoords, { color: ACCENT, weight: 5, opacity: 0.9 });
    const startMarker = L.marker([startCoords.lat, startCoords.lon], { icon: startIcon, title: "Start" });
    const endMarker = L.marker([endCoords.lat, endCoords.lon], { icon: endIcon, title: "End" });

    routeLayer = L.layerGroup([polyline, startMarker, endMarker]).addTo(map);
    map.fitBounds(polyline.getBounds(), { padding: [24, 24] });
}

function renderResults(data, avoidDark) {
    document.getElementById("score-tile").innerHTML = scoreTileHtml(data.safety_score);

    const distanceKm = data.distance_m / 1000;
    document.getElementById("distance-tile").innerHTML = statTileHtml("Distance", `${distanceKm.toFixed(1)} km`);

    const walkMinutes = (distanceKm / WALK_SPEED_KMH) * 60;
    document.getElementById("walktime-tile").innerHTML = statTileHtml(
        "Estimated walk time",
        `${walkMinutes.toFixed(0)} min`,
        `at ${WALK_SPEED_KMH.toFixed(0)} km/h`
    );

    document.getElementById("explanation-text").textContent = data.explanation;
    document.getElementById("breakdown-bars").innerHTML = breakdownBarsHtml(data.breakdown, avoidDark);

    document.getElementById("results").classList.remove("hidden");
}

function setStatus(message, kind) {
    const banner = document.getElementById("status-banner");
    banner.textContent = message || "";
    banner.className = "status-banner" + (message ? ` ${kind}` : "");
}

function setFormError(message) {
    document.getElementById("form-error").textContent = message || "";
}

document.addEventListener("DOMContentLoaded", () => {
    initMap();

    const startAutocomplete = new AddressAutocomplete(
        document.getElementById("start-input"),
        document.getElementById("start-suggestions")
    );
    const endAutocomplete = new AddressAutocomplete(
        document.getElementById("end-input"),
        document.getElementById("end-suggestions")
    );

    const form = document.getElementById("route-form");
    const submitBtn = document.getElementById("submit-btn");

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        setFormError("");
        setStatus("", "info");

        const start = startAutocomplete.getCoords();
        const end = endAutocomplete.getCoords();
        if (!start || !end) {
            setFormError("Please select both addresses from the suggestions.");
            return;
        }

        const avoidDark = document.getElementById("avoid-dark").checked;

        submitBtn.disabled = true;
        submitBtn.textContent = "Finding route...";
        setStatus("Loading the Toronto walking network and scoring nearby streets. This can take a while on a cold start.", "info");

        try {
            const resp = await fetch(`${API_BASE}/route`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    start_lat: start.lat,
                    start_lon: start.lon,
                    end_lat: end.lat,
                    end_lon: end.lon,
                    avoid_dark: avoidDark,
                }),
            });

            if (!resp.ok) {
                const body = await resp.json().catch(() => ({}));
                setStatus(body.detail || "Could not compute a route. Please try again.", "error");
                return;
            }

            const data = await resp.json();
            setStatus("Route found", "info");
            renderResults(data, avoidDark);
            renderRouteOnMap(data.route, start, end);
        } catch (err) {
            setStatus("Could not reach the server. Please try again.", "error");
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = "Find route";
        }
    });
});
