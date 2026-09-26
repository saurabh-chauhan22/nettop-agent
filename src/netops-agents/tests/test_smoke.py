"""Pytest smoke tests. None of these call the LLM."""
import duckdb

from detect.anomaly_detector import detect
from eval.scorers import detection_scores
from ingest.generate_data import DataGenerator
from utils.config import ConfigIniReader


def test_config_reader_reads_env_style_settings():
    reader = ConfigIniReader()
    reader.read()

    assert reader.get("DEFAULT", "LANGSMITH_TRACING") == "true"
    assert reader.get("DEFAULT", "ANTHROPIC_API_KEY")


def test_detector_flags_every_planted_incident_and_no_clean_modem():
    tables, gold = DataGenerator().generate_relational_network_data()
    conn = duckdb.connect()  # in-memory lake: the test never touches data/
    for name, df in tables.items():
        conn.register(name, df)

    flagged = {e["device_id"] for e in detect(conn)}
    planted = {g["device_id"] for g in gold}

    assert flagged == planted
    assert detection_scores(flagged, planted, set(tables["topology"]["device_id"]))["false_alarm_rate"] == 0.0
