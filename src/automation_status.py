#!/usr/bin/env python3
"""Kleiner gemeinsamer Status-Writer fuer die Cloud-Automation."""

import json
import os
from datetime import datetime, timezone


HERE = os.path.dirname(__file__)
OUT = os.path.join(HERE, "..", "output")
STATUS_PATH = os.path.join(OUT, "automation_status.json")


def load():
    if os.path.exists(STATUS_PATH):
        with open(STATUS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"updated_at": None, "steps": {}}


def write_step(name, ok, message, extra=None):
    os.makedirs(OUT, exist_ok=True)
    data = load()
    data["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    step = {
        "ok": bool(ok),
        "message": message,
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if extra:
        step.update(extra)
    data.setdefault("steps", {})[name] = step
    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

