"""Read the DuckDB lake file directly from S3 (read-only) and list its tables.

Connection logic lives in agents.tools.lake(). Set S3_LAKE_BUCKET (and AWS_REGION) in settings.ini
or the environment. S3_LAKE_KEY overrides the object key, which defaults to the local lake filename.
"""
import os
import sys
from pathlib import Path

# Allow running this file directly: put the package root (src/netops-agents) on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.tools import lake, rows

if not os.getenv("S3_LAKE_BUCKET"):
    sys.exit("S3_LAKE_BUCKET is not set")  # fail loud, not silently local

print("Tables in S3 lake:", [r["name"] for r in rows(lake(), "SHOW TABLES")])
