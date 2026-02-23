"""
test_llm_speed.py  —  AeroGuard LLM Speed Tester
==================================================
Sends random sensor readings to /api/telemetry forever (Ctrl+C to stop).
After each POST it polls /api/status until the ml_explanation changes and
prints the elapsed time + a preview of the new explanation.

Run:
    python test_llm_speed.py               # default: send every 1 s
    python test_llm_speed.py --interval 2  # send every 2 s

SAFE TO DELETE — nothing in the application imports this file.
"""

import argparse
import random
import time
import math

try:
    import requests
except ImportError:
    print("Install requests first:  pip install requests")
    raise

BASE_URL = "http://localhost:5000/api"

# ── Helpers ────────────────────────────────────────────────────────────────────
def rand(lo, hi, dec=2):
    return round(random.uniform(lo, hi), dec)

def randi(lo, hi):
    return random.randint(lo, hi)


def random_payload(t: int) -> dict:
    phase = math.sin(t * 0.8)          # -1 … +1 oscillator

    temperature = round(37.5 + phase * 17.5, 1)   # 20–55 °C
    humidity    = round(69.0 + phase * 29.0, 1)   # 40–98 %
    satellites  = randi(0, 12)
    hdop        = rand(0.8, 9.0)
    vib_scale   = max(0.0, phase)
    acc_x       = rand(-0.1, 0.1) + vib_scale * rand(2.0, 5.0)
    acc_y       = rand(-0.1, 0.1) + vib_scale * rand(1.5, 4.0)
    acc_z       = round(9.81 - vib_scale * rand(5.0, 8.0), 3)
    water       = randi(0, 1023) if phase > 0.5 else randi(0, 60)
    current     = rand(0.5, 9.0)
    battery     = rand(5.0, 95.0)

    lat, lon, zone_label = random.choice([
        (13.15, 77.48, "GREEN"),
        (10.85, 76.27, "YELLOW"),
        (12.95, 77.62, "RED"),
    ])

    return zone_label, {
        "temperature":    temperature,
        "humidity":       humidity,
        "pressure":       rand(1005.0, 1025.0),
        "latitude":       round(lat + rand(-0.001, 0.001), 5),
        "longitude":      round(lon + rand(-0.001, 0.001), 5),
        "altitude":       rand(0.0, 50.0),
        "satellites":     satellites,
        "hdop":           hdop,
        "accX":           round(acc_x, 3),
        "accY":           round(acc_y, 3),
        "accZ":           round(acc_z, 3),
        "gyroX":          rand(-180.0, 180.0) if phase > 0.6 else rand(-2.0, 2.0),
        "gyroY":          rand(-150.0, 150.0) if phase > 0.6 else rand(-2.0, 2.0),
        "gyroZ":          rand(-100.0, 100.0) if phase > 0.6 else rand(-1.0, 1.0),
        "distance":       rand(2.0, 300.0),
        "ldr":            randi(0, 1023),
        "water":          water,
        "ir":             randi(0, 1),
        "pir":            1 if phase > 0.7 else 0,
        "current":        current,
        "battery_pct":    battery,
        "voltage":        rand(10.0, 13.0),
        "signal_strength":randi(5, 100),
        "sensor_failure": phase > 0.85,
        "rain_detected":  water > 200,
    }


def poll_explanation(old_expl: str, timeout: float = 12.0, poll_every: float = 0.2):
    t0 = time.monotonic()
    while (time.monotonic() - t0) < timeout:
        try:
            r = requests.get(f"{BASE_URL}/status", timeout=5)
            data = r.json()
            new_expl = data.get("ml_explanation", "")
            if new_expl and new_expl != old_expl:
                return new_expl, time.monotonic() - t0
        except Exception as e:
            print(f"  [poll error] {e}")
        time.sleep(poll_every)
    return old_expl, timeout


# ── Main loop ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="AeroGuard LLM speed tester (runs forever)")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="Seconds between sends (default 1.0)")
    args = parser.parse_args()

    print("=" * 65)
    print("  AeroGuard LLM Speed Test  —  running forever, Ctrl+C to stop")
    print(f"  Interval: {args.interval}s between sends")
    print("=" * 65)

    # Grab current explanation as baseline
    try:
        current_expl = requests.get(f"{BASE_URL}/status", timeout=5).json().get("ml_explanation", "")
    except Exception:
        current_expl = ""

    t = 0
    update_times = []

    try:
        while True:
            zone_label, payload = random_payload(t)

            # ── Print what we're sending ───────────────────────────────────────
            sep = "─" * 65
            print(f"\n{sep}")
            print(f"  Round {t+1}   Zone: {zone_label}")
            print(f"  temp={payload['temperature']}°C  "
                  f"hum={payload['humidity']}%  "
                  f"sats={payload['satellites']}  "
                  f"hdop={payload['hdop']}  "
                  f"water={payload['water']}")
            print(f"  accX={payload['accX']}  accY={payload['accY']}  accZ={payload['accZ']}")
            print(f"  current={payload['current']}A  battery={payload['battery_pct']}%  "
                  f"ir={payload['ir']}  pir={payload['pir']}  "
                  f"rain={payload['rain_detected']}  fault={payload['sensor_failure']}")

            # ── POST ──────────────────────────────────────────────────────────
            t_send = time.monotonic()
            try:
                resp = requests.post(f"{BASE_URL}/telemetry", json=payload,
                                 headers={"X-Source": "test"}, timeout=5).json()
                post_ms = (time.monotonic() - t_send) * 1000
                print(f"  → POST {post_ms:.0f}ms  "
                      f"score={resp.get('safety_score','?')}  "
                      f"risk={resp.get('risk_level','?')}  "
                      f"zone={resp.get('zone_status','?')}")
            except Exception as e:
                print(f"  → POST failed: {e}")
                time.sleep(args.interval)
                t += 1
                continue

            # ── Poll for explanation update ───────────────────────────────────
            new_expl, elapsed = poll_explanation(current_expl)
            if new_expl != current_expl:
                update_times.append(elapsed)
                avg = sum(update_times) / len(update_times)
                preview_lines = new_expl.strip().split("\n")[:4]
                print(f"  ✓ Explanation updated in {elapsed:.2f}s  (avg {avg:.2f}s over {len(update_times)} updates)")
                for line in preview_lines:
                    print(f"    {line}")
                current_expl = new_expl
            else:
                print(f"  ✗ Explanation unchanged after {elapsed:.1f}s timeout")

            time.sleep(args.interval)
            t += 1

    except KeyboardInterrupt:
        print(f"\n\n{'='*65}")
        print(f"  Stopped after {t} rounds.")
        if update_times:
            print(f"  Explanation updated {len(update_times)}/{t} times")
            print(f"  Min: {min(update_times):.2f}s  "
                  f"Max: {max(update_times):.2f}s  "
                  f"Avg: {sum(update_times)/len(update_times):.2f}s")
        print("=" * 65)


if __name__ == "__main__":
    main()
