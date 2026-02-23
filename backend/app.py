"""
AeroGuard - UAV Ground Station Safety Backend
Flask REST API
"""

from flask import Flask
from routes.telemetry import telemetry_bp
from routes.status import status_bp
from routes.logs import logs_bp
from routes.ai_prediction import ai_bp
from routes.zone import zone_bp
from database import init_db

app = Flask(__name__)

# Allow CORS manually (no dependency needed)
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PATCH,DELETE,OPTIONS"
    return response

# Register Blueprints
app.register_blueprint(telemetry_bp, url_prefix="/api")
app.register_blueprint(status_bp,    url_prefix="/api")
app.register_blueprint(logs_bp,      url_prefix="/api")
app.register_blueprint(ai_bp,        url_prefix="/api")
app.register_blueprint(zone_bp,      url_prefix="/api")

@app.route("/")
def index():
    return {"message": "AeroGuard Backend Running", "version": "1.0.0"}, 200

if __name__ == "__main__":
    init_db()

    # ── Optional dev sensor simulator ─────────────────────────────────────────
    # If dev_sensor_sim.py exists on disk it is imported and started as a
    # background thread.  If the file is absent (production / hardware mode)
    # this block is silently skipped — no change in behaviour whatsoever.
    try:
        import dev_sensor_sim as _sim
        _sim.maybe_start(mode="rotate")
        print("[AeroGuard] Dev simulator loaded — will auto-start if no hardware detected.")
    except ImportError:
        pass  # dev_sensor_sim.py not present — hardware-only mode, carry on
    # ──────────────────────────────────────────────────────────────────────────

    # debug=False + use_reloader=False: eliminates the Werkzeug double-process
    # overhead that runs a second Python interpreter for file watching.
    # threaded=True: allows concurrent handling of multiple frontend requests.
    app.run(debug=False, use_reloader=False, threaded=True, host="0.0.0.0", port=5000)
