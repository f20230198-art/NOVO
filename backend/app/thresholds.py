import json
from pathlib import Path

THRESHOLDS_PATH = Path(__file__).parent / "thresholds.json"
THRESHOLDS: dict = json.loads(THRESHOLDS_PATH.read_text(encoding="utf-8"))
BOAT_TYPES = ("non_motorised", "motorised", "mechanised")
