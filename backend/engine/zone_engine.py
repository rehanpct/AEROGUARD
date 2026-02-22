"""
AeroGuard - Zone Engine
Classifies a GPS coordinate as GREEN / YELLOW / RED based on defined airspace zones.

Supports:
  - Polygon-based geofences (point-in-polygon via ray casting)
  - Simulated bounding-box zones as fallback / example data

Priority: RED > YELLOW > GREEN
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple, Optional


# ── Data Structures ───────────────────────────────────────────────────────────

@dataclass
class AirspaceZone:
    """Represents a single airspace zone."""
    name:     str
    color:    str                           # 'GREEN' | 'YELLOW' | 'RED'
    polygon:  List[Tuple[float, float]]     # list of (lat, lon) vertices
    reason:   str = ""                      # e.g. "Airport restricted area"

    def contains(self, lat: float, lon: float) -> bool:
        """
        Ray-casting algorithm to test if (lat, lon) lies inside the polygon.
        Works well for small geographic areas.
        """
        vertices = self.polygon
        n = len(vertices)
        inside = False
        x, y = lat, lon
        j = n - 1
        for i in range(n):
            xi, yi = vertices[i]
            xj, yj = vertices[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside


def _bbox_to_polygon(lat_min, lon_min, lat_max, lon_max) -> List[Tuple[float, float]]:
    """Helper: convert a bounding-box to a 4-vertex polygon."""
    return [
        (lat_min, lon_min),
        (lat_min, lon_max),
        (lat_max, lon_max),
        (lat_max, lon_min),
    ]


# ── Simulated Zone Registry ───────────────────────────────────────────────────
# In production these would be loaded from a DB or regulatory API (e.g. OpenSky).
# Zones are checked highest-priority first (RED → YELLOW → GREEN).

_ZONE_REGISTRY: List[AirspaceZone] = [

    # ── RED Zones ─────────────────────────────────────────────────────────────
    AirspaceZone(
        name    = "Airport Exclusion Zone",
        color   = "RED",
        polygon = _bbox_to_polygon(12.9400, 77.6000, 12.9700, 77.6400),
        reason  = "Active airport – flight strictly prohibited",
    ),
    AirspaceZone(
        name    = "Government Restricted Airspace",
        color   = "RED",
        polygon = _bbox_to_polygon(28.6100, 77.2000, 28.6300, 77.2300),
        reason  = "Restricted government zone",
    ),
    AirspaceZone(
        name    = "Nuclear Facility Buffer",
        color   = "RED",
        polygon = _bbox_to_polygon(21.7050, 70.1500, 21.7250, 70.1800),
        reason  = "Nuclear installation – no-fly zone",
    ),

    # ── YELLOW Zones ──────────────────────────────────────────────────────────
    AirspaceZone(
        name    = "Urban Caution Zone A",
        color   = "YELLOW",
        polygon = _bbox_to_polygon(12.9500, 77.5800, 12.9750, 77.6200),
        reason  = "Dense urban area – authorisation required",
    ),
    AirspaceZone(
        name    = "Hospital Vicinity",
        color   = "YELLOW",
        polygon = _bbox_to_polygon(13.0100, 77.5700, 13.0250, 77.5900),
        reason  = "Hospital airspace – exercise caution",
    ),
    AirspaceZone(
        name    = "Stadium Event Zone",
        color   = "YELLOW",
        polygon = _bbox_to_polygon(28.6300, 77.2100, 28.6500, 77.2350),
        reason  = "Public event – temporary restriction",
    ),

    # ── GREEN Zones ───────────────────────────────────────────────────────────
    AirspaceZone(
        name    = "Rural Open Area",
        color   = "GREEN",
        polygon = _bbox_to_polygon(13.1000, 77.4500, 13.2000, 77.5500),
        reason  = "Open rural area – flight permitted",
    ),
    AirspaceZone(
        name    = "Approved Testing Ground",
        color   = "GREEN",
        polygon = _bbox_to_polygon(12.8000, 77.4000, 12.8500, 77.4600),
        reason  = "Certified UAV testing area",
    ),
]


# ── Public API ────────────────────────────────────────────────────────────────

def classify_zone(lat: float, lon: float) -> dict:
    """
    Classify the given coordinates against all registered zones.

    Returns a dict with:
        zone        : 'GREEN' | 'YELLOW' | 'RED'
        zone_name   : name of the matched zone (or 'Unclassified')
        reason      : human-readable explanation
        hard_lock   : True when zone is RED (engine must block launch)
    """
    matched_red    = None
    matched_yellow = None
    matched_green  = None

    for zone in _ZONE_REGISTRY:
        if zone.contains(lat, lon):
            if zone.color == "RED"    and matched_red    is None:
                matched_red    = zone
            elif zone.color == "YELLOW" and matched_yellow is None:
                matched_yellow = zone
            elif zone.color == "GREEN"  and matched_green  is None:
                matched_green  = zone

    # Priority: RED > YELLOW > GREEN > default YELLOW (unclassified = caution)
    if matched_red:
        zone = matched_red
    elif matched_yellow:
        zone = matched_yellow
    elif matched_green:
        zone = matched_green
    else:
        # Unclassified coordinates → treat as YELLOW (caution, unknown space)
        return {
            "zone":      "YELLOW",
            "zone_name": "Unclassified Airspace",
            "reason":    "Coordinates not in any registered zone – proceed with caution",
            "hard_lock": False,
        }

    return {
        "zone":      zone.color,
        "zone_name": zone.name,
        "reason":    zone.reason,
        "hard_lock": zone.color == "RED",
    }


def get_all_zones() -> list:
    """Return metadata for all registered zones (for map display)."""
    result = []
    for z in _ZONE_REGISTRY:
        result.append({
            "name":    z.name,
            "color":   z.color,
            "polygon": [{"lat": lat, "lon": lon} for lat, lon in z.polygon],
            "reason":  z.reason,
        })
    return result


def add_zone(name: str, color: str, polygon: List[Tuple[float, float]], reason: str = "") -> dict:
    """
    Dynamically register a new zone at runtime (in-memory only).
    For persistence, connect this to the database layer.
    """
    if color not in ("GREEN", "YELLOW", "RED"):
        raise ValueError(f"Invalid zone color: {color}")
    new_zone = AirspaceZone(name=name, color=color, polygon=polygon, reason=reason)
    _ZONE_REGISTRY.append(new_zone)
    return {"added": True, "zone": name, "color": color}
