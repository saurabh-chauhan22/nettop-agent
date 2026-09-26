import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

SETTINGS_INIT = BASE_DIR / "settings.ini"

DATA_DIR = BASE_DIR / "data"

DUCKDB_FILE = BASE_DIR / "data_lake.duckdb"

GOLD_FILE = BASE_DIR / "eval" / "gold_dataset.jsonl"

AUDIT_LOG = BASE_DIR / "audit.log"