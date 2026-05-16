#!/usr/bin/env python3
"""
Quick launcher for the Price Bot dashboard.
Run from the project root:  python dashboard/run.py
"""
import sys
from pathlib import Path

# Make sure price-bot root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app

if __name__ == "__main__":
    print("\n  Price Bot Dashboard")
    print("  ──────────────────────────────")
    print("  http://localhost:5000\n")
    app.run(debug=True, port=5000)