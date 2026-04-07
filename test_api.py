#!/usr/bin/env python3
"""
Test script per WallClock — replica le stesse chiamate del firmware ESP32

Uso:
    python test_api.py [SERVER_URL]
    
Default: http://localhost:8000
"""

import sys
import requests
import json
from datetime import datetime

# Configurazione
SERVER = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.1.185:8077"
TIMEOUT = 5

# Mapping dei segmenti 7-segmenti
SEGMENT_NAMES = ["a(top)", "b(top-right)", "c(bot-right)", "d(bottom)", "e(bot-left)", "f(top-left)", "g(middle)"]
DIGITS_7SEG = [
    {0, 1, 2, 3, 4, 5},      # 0
    {1, 2},                   # 1
    {0, 1, 3, 4, 6},         # 2
    {0, 1, 2, 3, 6},         # 3
    {1, 2, 5, 6},            # 4
    {0, 2, 3, 5, 6},         # 5
    {0, 2, 3, 4, 5, 6},      # 6
    {0, 1, 2},               # 7
    {0, 1, 2, 3, 4, 5, 6},   # 8
    {0, 1, 2, 3, 5, 6},      # 9
]


def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print('='*60)


def print_ok(text):
    print(f"  ✓ {text}")


def print_error(text):
    print(f"  ✗ {text}")


def print_info(text):
    print(f"  • {text}")


def fetch_clock():
    """Fetch /api/clock — le stesse dati che l'ESP32 legge ogni 30s"""
    print_header("GET /api/clock")
    
    try:
        resp = requests.get(f"{SERVER}/api/clock", timeout=TIMEOUT)
        print_info(f"HTTP {resp.status_code}")
        
        if resp.status_code != 200:
            print_error(f"Unexpected status code: {resp.status_code}")
            return None
        
        data = resp.json()
        print_ok("JSON parsed successfully")
        
        # Mostra i dati
        active = data.get("active")
        hour = data.get("hour")
        minute = data.get("minute")
        mode = data.get("mode")
        config_version = data.get("config_version")
        
        print_info(f"active: {active}")
        print_info(f"hour: {hour}")
        print_info(f"minute: {minute}")
        print_info(f"mode: {mode}")
        print_info(f"config_version: {config_version}")
        
        # Caso speciale: alarm_ringing
        if mode == "alarm_ringing":
            print_info("🔔 ALARM RINGING! Display dovrebbe fare: 88:88 ↔ 00:00")
        elif mode == "timer":
            print_info("⏱️  TIMER MODE: hour/minute are countdown remaining")
        elif mode == "clock":
            print_info("🕐 CLOCK MODE: normal time display")
        
        # Analizza i segmenti che dovrebbero accendersi
        if hour != 88 and minute != 88:
            hour_tens = hour // 10
            hour_units = hour % 10
            minute_tens = minute // 10
            minute_units = minute % 10
            
            print_info(f"\nSegment display:")
            print_info(f"  {hour_tens}  {hour_units} : {minute_tens}  {minute_units}")
            
            for pos, digit in [("H tens", hour_tens), ("H units", hour_units), 
                               ("M tens", minute_tens), ("M units", minute_units)]:
                on_segments = DIGITS_7SEG[digit]
                seg_str = " ".join([SEGMENT_NAMES[i] for i in on_segments])
                print_info(f"  {pos} ({digit}): {seg_str}")
        
        return data
        
    except requests.exceptions.ConnectionError:
        print_error(f"Connection refused: {SERVER}")
        return None
    except requests.exceptions.Timeout:
        print_error(f"Timeout after {TIMEOUT}s")
        return None
    except Exception as e:
        print_error(f"Exception: {e}")
        return None


def fetch_servo_config():
    """Fetch /api/servo-config — i parametri calibrazione servo"""
    print_header("GET /api/servo-config")
    
    try:
        resp = requests.get(f"{SERVER}/api/servo-config", timeout=TIMEOUT)
        print_info(f"HTTP {resp.status_code}")
        
        if resp.status_code != 200:
            print_error(f"Unexpected status code: {resp.status_code}")
            return None
        
        data = resp.json()
        print_ok("JSON parsed successfully")
        
        # Mostra configurazione servo
        h_on = data.get("h_on", [])
        h_off = data.get("h_off", [])
        m_on = data.get("m_on", [])
        m_off = data.get("m_off", [])
        mid_offset = data.get("mid_offset")
        time_delay = data.get("time_delay")
        time_delay2 = data.get("time_delay2")
        
        print_info(f"mid_offset: {mid_offset} (collisione segmento centrale)")
        print_info(f"time_delay: {time_delay} ms")
        print_info(f"time_delay2: {time_delay2} ms")
        
        print_info("\nOre (H) - board address 0x40:")
        for i in range(14):
            if i == 7:
                print_info("  ─── Ore Decine (ch 7-13) ───")
            pos_type = "≡ Hz Unità" if i < 7 else "≡ Hz Decine"
            print_info(f"  ch {i:2d} {pos_type}: ON={h_on[i]:3d} OFF={h_off[i]:3d}")
        
        print_info("\nMinuti (M) - board address 0x41:")
        for i in range(14):
            if i == 7:
                print_info("  ─── Min Decine (ch 7-13) ───")
            pos_type = "≡ Min Unità" if i < 7 else "≡ Min Decine"
            print_info(f"  ch {i:2d} {pos_type}: ON={m_on[i]:3d} OFF={m_off[i]:3d}")
        
        return data
        
    except requests.exceptions.ConnectionError:
        print_error(f"Connection refused: {SERVER}")
        return None
    except requests.exceptions.Timeout:
        print_error(f"Timeout after {TIMEOUT}s")
        return None
    except Exception as e:
        print_error(f"Exception: {e}")
        return None


def main():
    print("\n" + "="*60)
    print("  WallClock API Test — Replica delle chiamate ESP32")
    print("="*60)
    print(f"Server: {SERVER}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    
    # Simula il ciclo di boot dell'ESP32:
    # 1. fetchServoConfig()
    # 2. fetchClockData()
    
    servo_config = fetch_servo_config()
    clock_data = fetch_clock()
    
    # Summary
    print_header("Summary")
    if servo_config and clock_data:
        print_ok("All requests succeeded ✓")
        active = clock_data.get("active")
        if not active:
            print_info("⚠️  Clock is INACTIVE — ESP32 won't update display")
        else:
            print_ok("Clock is ACTIVE — ESP32 will update display")
    else:
        print_error("Some requests failed — check server connectivity")
    
    print()


if __name__ == "__main__":
    main()
