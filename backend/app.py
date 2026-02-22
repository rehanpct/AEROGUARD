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
    app.run(debug=True, host="0.0.0.0", port=5000)
