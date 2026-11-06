"""Traffic generator and outage verification for Northwind Pay checkout-api."""

import json
import time
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8080"


def send_checkout():
    req = urllib.request.Request(
        f"{BASE_URL}/api/v1/checkout",
        data=b'{"amount": 49.99, "currency": "USD"}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def check_health():
    try:
        with urllib.request.urlopen(f"{BASE_URL}/health", timeout=3.0) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())


def trigger_chaos():
    req = urllib.request.Request(f"{BASE_URL}/chaos/break", method="POST")
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        return resp.status


def trigger_heal():
    req = urllib.request.Request(f"{BASE_URL}/chaos/heal", method="POST")
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        return resp.status


if __name__ == "__main__":
    print("1. Checking health...")
    status, body = check_health()
    print(f"   Status: {status} -> {body['status']}")

    print("2. Sending a checkout request...")
    status, body = send_checkout()
    print(f"   Status: {status} -> {body}")

    print("3. Triggering outage (Connection Pool Exhaustion)...")
    trigger_chaos()

    print("4. Checking health during outage...")
    status, body = check_health()
    print(f"   Status: {status} -> {body}")

    print("5. Healing service (Rollback to v3.4.0)...")
    trigger_heal()

    print("6. Checking health after healing...")
    status, body = check_health()
    print(f"   Status: {status} -> {body['status']}")
