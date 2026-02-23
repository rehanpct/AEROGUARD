# 🚁 AEROGUARD

### AI-Powered Autonomous Drone Docking & Monitoring System

AEROGUARD is an intelligent drone docking and environmental monitoring system designed for real-time surveillance, automated landing, and sensor-based anomaly detection.

The system integrates **ESP32 firmware, a Flask backend, machine learning modules, and a live frontend dashboard** to provide seamless monitoring and decision-making.

---

## 📌 Project Overview

AEROGUARD acts as:

* 🛰 Autonomous drone docking controller
* 🌡 Environmental monitoring station
* 📡 Real-time telemetry system
* 🤖 AI-powered anomaly detection platform

The system collects sensor data from hardware, sends it to a backend server, stores it in a database, and displays it on a live frontend dashboard.

---

## 🏗 System Architecture

```
Sensors → ESP32 → Flask Backend → Database → Frontend Dashboard → ML Models
```

### Components:

* **Hardware Layer** – ESP32 + Sensors
* **Communication Layer** – WiFi + HTTP POST
* **Backend Layer** – Flask API
* **Database Layer** – SQLite
* **Frontend Layer** – Live dashboard UI
* **ML Layer** – Anomaly detection & classification

---

## 🔌 Hardware Components

* ESP32
* BME280 (Temperature, Humidity, Pressure)
* MPU6050 (Accelerometer + Gyroscope)
* GPS Module (TinyGPS++)
* IR Sensor (Dock/Object detection)
* LDR Sensor (Light detection)
* Buzzer
* Status LEDs
* Relay module (optional docking control)

---

## 📡 Sensor Data Collected

| Sensor  | Data                                    |
| ------- | --------------------------------------- |
| BME280  | Temperature, Humidity, Pressure         |
| MPU6050 | Acceleration (X,Y,Z), Gyroscope (X,Y,Z) |
| GPS     | Latitude, Longitude                     |
| IR      | Object detection (Dock presence)        |
| LDR     | Ambient light level                     |
| System  | Timestamp                               |

---

## 🖥 Backend (Flask)

Handles:

* Receiving ESP32 JSON POST data
* Storing telemetry in SQLite database
* Serving API endpoints for frontend
* Handling ML inference (if enabled)

### Main Endpoint

```
POST /sensor-data
GET  /latest
GET  /history
```

---

## 📊 Frontend Dashboard

Features:

* Live sensor updates
* Real-time environmental metrics
* Dock detection status
* GPS location display
* Sensor health monitoring
* ML alert indicators

If GPS is unavailable → system uses fixed fallback coordinates.

---

## 🤖 Machine Learning Integration

Optional ML module supports:

* Environmental anomaly detection
* Abnormal vibration detection (MPU6050)
* Docking failure detection
* Predictive alert system

Models can be integrated using:

* TensorFlow
* Scikit-learn
* PyTorch

---

## 🚀 Installation & Setup

### 1️⃣ Clone Repository

```bash
git clone https://github.com/yourusername/AEROGUARD.git
cd AEROGUARD
```

---

### 2️⃣ Backend Setup

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Server runs on:

```
http://localhost:5000
```

---

### 3️⃣ ESP32 Setup

* Open firmware in Arduino IDE
* Install required libraries:

  * Adafruit BME280
  * MPU6050
  * TinyGPS++
  * ArduinoJson
* Set WiFi credentials
* Upload to ESP32

---

### 4️⃣ Frontend

If using static frontend:

Open `index.html`

If using Node:

```bash
npm install
node server.js
```

---

## 🔄 Data Flow Example

ESP32 sends:

```json
{
  "temperature": 29.5,
  "humidity": 78,
  "pressure": 1008,
  "ax": 0.01,
  "ay": -0.02,
  "az": 9.81,
  "latitude": 9.674,
  "longitude": 76.340,
  "ir_status": 1,
  "ldr_value": 3120
}
```

---

## 🛡 Key Features

* Real-time telemetry
* Autonomous docking detection
* Sensor-based environmental monitoring
* AI anomaly detection
* Modular architecture
* Scalable backend
* Low-latency communication

---

## 🎯 Use Cases

* Smart drone docking stations
* Wildlife monitoring systems
* Remote surveillance
* Environmental monitoring hubs
* Smart aviation infrastructure

---

## 📁 Project Structure

```
AEROGUARD/
│
├── backend/
│   ├── app.py
│   ├── database.js / db.py
│   └── trustchain.db
│
├── frontend/
│   ├── index.html
│   ├── scripts.js
│
├── AeroGuard_ESP32/
│   └── firmware.ino
│
└── README.md
```

---

## 🔐 Security Notes

* Ensure backend runs in secure environment
* Use HTTPS in production
* Add authentication for production deployment
* Protect WiFi credentials

---

🚀 Future Architecture – Autonomous Drone Brain & Cloud Dock System
🧠 AEROGUARD as the Drone’s Brain

In future versions, AEROGUARD will evolve from a monitoring dock into a full autonomous decision-making brain for drone operations.

The dock will:

Analyze landing safety in real time

Validate docking alignment

Monitor environmental conditions before landing

Confirm stable touchdown using motion sensors

Reject unsafe docking attempts automatically

This shifts intelligence from the drone alone to the infrastructure itself.

🛬 Intelligent Autonomous Dock System

Planned docking upgrades include:

IR-based precision alignment

Vision-assisted landing verification

LiDAR-based distance validation

Auto-lock mechanical docking system

Smart battery charging integration

Weather-aware docking logic

Dock will operate in three modes:

Standby Mode – Monitors environment continuously

Landing Mode – Validates approach & confirms alignment

Post-Dock Mode – Verifies stability & initiates charging

⚡ Real-Time Processing Architecture

Future real-time flow:

Drone → Dock Edge Processor → Local AI Validation → Cloud Sync → Dashboard

Edge processing ensures:

Sub-second response time

Immediate safety decision

Low-latency anomaly detection

Independent operation even without cloud

Cloud is used for:

Long-term storage

Deep AI analytics

Fleet-wide monitoring

Predictive maintenance

🌩 Cloud-Connected Smart Infrastructure

AEROGUARD will function as a cloud node in a distributed drone ecosystem.

Capabilities:

Multi-dock cloud synchronization

Fleet monitoring dashboard

Remote firmware updates

Encrypted telemetry transmission

Global deployment scalability

Even if internet fails:

Dock operates locally

Data buffers safely

Syncs automatically once reconnected

🤖 Advanced AI Integration (Planned)

Vibration anomaly detection

Environmental risk prediction

Docking failure classification

Battery health analytics

Sensor drift detection

Self-learning safety thresholds

Edge AI (Jetson-ready) + Cloud AI hybrid architecture.

🔋 Full Infrastructure Vision

Long-term goal:

AEROGUARD becomes a self-managed drone station capable of:

Autonomous landing

Smart locking

Automated charging

Environmental intelligence

Cloud reporting

Zero human intervention
