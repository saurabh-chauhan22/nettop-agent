"""Pytest smoke tests. None of these call the LLM."""
import duckdb
import pytest

from agents.tools import check_select
from detect.anomaly_detector import detect, rank
from eval.scorers import detection_scores
from ingest.generate_data import DataGenerator
from utils.config import ConfigIniReader


def seeded_lake():
    """The seed-42 data as an in-memory lake, so tests never touch data/ or S3."""
    tables, gold = DataGenerator().generate_relational_network_data()
    conn = duckdb.connect()
    for name, df in tables.items():
        conn.register(name, df)
    return conn, tables, gold


def test_config_reader_reads_env_style_settings():
    reader = ConfigIniReader()
    reader.read()

    assert reader.get("DEFAULT", "LANGSMITH_TRACING") == "true"
    assert reader.get("DEFAULT", "ANTHROPIC_API_KEY")


def test_detector_flags_every_planted_incident_and_no_clean_modem():
    conn, tables, gold = seeded_lake()

    flagged = {e["device_id"] for e in detect(conn)}
    planted = {g["device_id"] for g in gold}

    assert flagged == planted
    assert detection_scores(flagged, planted, set(tables["topology"]["device_id"]))["false_alarm_rate"] == 0.0


def test_triage_puts_rf_faults_first_and_dhcp_storms_last():
    conn, _, _ = seeded_lake()
    ranked = rank(detect(conn))

    assert [e["device_id"] for e in ranked] == [
        "MODEM-006", "MODEM-012",  # RF signal loss
        "MODEM-009", "MODEM-018",  # link loss (flapping)
        "MODEM-003", "MODEM-016",  # DHCP storm
    ]
    assert [e["severity"] for e in ranked][::2] == ["RF signal loss", "Link loss", "DHCP storm"]


def test_sql_guard_allows_one_select_and_blocks_everything_else():
    check_select("SELECT count(*) FROM topology")
    check_select("WITH t AS (SELECT 1 AS x) SELECT x FROM t")
    for bad in [
        "DROP TABLE topology",
        "SELECT 1; DROP TABLE topology",
        "COPY topology TO 'out.csv'",
        "SELECT * FROM read_csv('secrets.csv')",
        "ATTACH 'other.db'",
        "SELECT * FROM 's3://some-bucket/x.parquet'",
    ]:
        with pytest.raises(ValueError):
            check_select(bad)
