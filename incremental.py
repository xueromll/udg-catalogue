import json
import os
from datetime import datetime

META_FILE = "pipeline_meta.json"

def load_pipeline_metadata() -> dict:
    if os.path.exists(META_FILE):
        try:
            with open(META_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_run_date": None, "last_start_index": 0}

def save_pipeline_metadata(start_index: int) -> None:
    meta = {
        "last_run_date": datetime.now().isoformat(),
        "last_start_index": start_index
    }
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=4)