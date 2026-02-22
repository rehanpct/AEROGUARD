🚀 AeroGuard

AI-Enabled UAV Ground Station & Smart Docking Safety System

AeroGuard is an intelligent UAV ground-station platform designed to prevent unsafe or unauthorized drone operations through environmental monitoring, GPS-based zone validation, and machine learning-driven risk analysis. The system functions as a virtual safety officer and physically enforces decisions using a relay-controlled smart docking and charging mechanism.

🧠 Key Features

🌍 GPS-based Green / Yellow / Red zone classification

📡 HDOP & satellite quality validation

🌦 Environmental sensing (temperature, humidity, pressure, light, rain)

⚙ Vibration monitoring using MPU6050

🔋 Charging current & dock power monitoring

📊 Dynamic UAV Risk Index (0–100)

🤖 Hybrid Rule-Based + ML Risk Engine

🗺 Interactive dashboard with map visualization

📈 Risk analytics & flight logs

🔒 Hardware enforcement via 5V relay

🏗 System Architecture

ESP32 (Edge Layer)

Sensor data acquisition

Dock control & relay enforcement

Telemetry transmission

Backend (Flask / FastAPI)

Risk engine

Zone logic

ML inference

Data logging

Frontend Dashboard

Live monitoring panel

Risk visualization

Map interface

Analytics & logs

🔬 AI Integration

AeroGuard uses a hybrid safety model:

Deterministic rule-based override system

Machine learning risk prediction model

The system outputs:

Risk probability

Safety classification (Safe / Caution / Unsafe)

Explainable safety recommendations

⚡ Docking & Charging System

The ground station also acts as a charging dock that:

Monitors charging current stability

Blocks launch in unsafe conditions

Controls dock power via relay

Triggers fail-safe during zone violations or severe risk

🛠 Hardware Components

ESP32

GPS Module

Temperature & Humidity Sensor

Pressure Sensor

MPU6050

LDR Module

Water/Rain Sensor

Current Sensor

5V Relay Module

Buzzer

3 Status LEDs

Buck Converter

🎯 Purpose

AeroGuard enhances UAV safety, regulatory compliance, and operational reliability by combining intelligent decision-support, predictive analytics, and hardware-level enforcement into a scalable ground-station architecture.
