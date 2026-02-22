"""
AeroGuard - /api/zones
Manage and query airspace zones.
"""

from flask import Blueprint, request, jsonify
from engine import classify_zone, get_all_zones, add_zone

zone_bp = Blueprint("zone", __name__)


@zone_bp.route("/zones", methods=["GET"])
def list_zones():
    """Return all registered airspace zones (for map rendering)."""
    return jsonify({"zones": get_all_zones()}), 200


@zone_bp.route("/zones/classify", methods=["GET"])
def classify():
    """
    Classify a coordinate pair.

    Query params:
        lat : float (required)
        lon : float (required)
    """
    try:
        lat = float(request.args["lat"])
        lon = float(request.args["lon"])
    except (KeyError, ValueError):
        return jsonify({"error": "lat and lon query params are required and must be floats"}), 400

    result = classify_zone(lat, lon)
    return jsonify(result), 200


@zone_bp.route("/zones", methods=["POST"])
def create_zone():
    """
    Dynamically add a new airspace zone.

    JSON body:
        name    : str   (required)
        color   : str   'GREEN' | 'YELLOW' | 'RED'  (required)
        polygon : list  of {lat, lon} objects  (required, min 3 points)
        reason  : str   (optional)
    """
    payload = request.get_json(force=True, silent=True)
    if not payload:
        return jsonify({"error": "Invalid or missing JSON body"}), 400

    name   = payload.get("name")
    color  = payload.get("color", "").upper()
    raw_poly = payload.get("polygon", [])
    reason = payload.get("reason", "")

    if not name or not color or len(raw_poly) < 3:
        return jsonify({"error": "name, color, and polygon (≥3 points) are required"}), 400

    try:
        polygon = [(float(p["lat"]), float(p["lon"])) for p in raw_poly]
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Each polygon point must have lat and lon as numbers"}), 400

    try:
        result = add_zone(name=name, color=color, polygon=polygon, reason=reason)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(result), 201
