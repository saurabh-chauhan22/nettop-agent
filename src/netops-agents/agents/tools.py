"""Agent tools: read-only queries over the DuckDB lake, plus simulated remediation actions with an audit log."""
import os
from datetime import datetime

import duckdb

from base import AUDIT_LOG, DUCKDB_FILE
from utils.config import load_env

load_env()


def lake():
    """Read-only connection, so no investigation step can modify the lake. Uses the S3 copy when
    S3_LAKE_BUCKET is set, else the local file. AWS credentials come from the standard chain
    (env vars, ~/.aws/credentials, or an IAM role); nothing is hardcoded."""
    bucket = os.getenv("S3_LAKE_BUCKET")
    if not bucket:
        return duckdb.connect(str(DUCKDB_FILE), read_only=True)
    conn = duckdb.connect()
    conn.execute("INSTALL httpfs; LOAD httpfs; INSTALL aws; LOAD aws;")
    region = os.getenv("AWS_REGION")
    conn.execute("CREATE SECRET (TYPE s3, PROVIDER credential_chain" + (f", REGION '{region}'" if region else "") + ")")
    # ponytail: re-attaches on every call; cache one connection if S3 latency starts to matter
    conn.execute(f"ATTACH 's3://{bucket}/{os.getenv('S3_LAKE_KEY', DUCKDB_FILE.name)}' AS lake (READ_ONLY)")
    conn.execute("USE lake")
    return conn


def rows(conn, sql, params=None):
    cur = conn.execute(sql, params) if params else conn.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def gather_evidence(device_id, start, end, conn=None):
    """Everything the diagnosis sees: device context, telemetry in the window vs the device's own baseline,
    and syslog, SNMP trap, and DHCP activity inside the window."""
    conn = conn or lake()
    window = {"device": device_id, "start": start, "end": end}
    return {
        "device": rows(conn, """
            SELECT t.device_id, t.parent_id AS cmts, c.vendor, c.model, c.sw_version
            FROM topology t JOIN device_config c USING (device_id)
            WHERE device_id = $device""", {"device": device_id}),
        "telemetry": rows(conn, """
            SELECT CASE WHEN ts BETWEEN $start AND $end THEN 'anomaly_window' ELSE 'baseline' END AS period,
                   count(*) AS samples,
                   round(avg(snr_db), 1) AS avg_snr_db, round(min(snr_db), 1) AS min_snr_db,
                   round(avg(tx_power_dbmv), 1) AS avg_tx_power_dbmv, round(max(tx_power_dbmv), 1) AS max_tx_power_dbmv,
                   sum(error_count) AS total_errors
            FROM device_telemetry WHERE device_id = $device
            GROUP BY period ORDER BY period""", window),
        "syslogs": rows(conn, r"""
            SELECT severity, regexp_replace(message, '[0-9]+\.[0-9]+', 'N', 'g') AS pattern, count(*) AS n
            FROM syslogs WHERE device_id = $device AND ts BETWEEN $start AND $end
            GROUP BY ALL ORDER BY n DESC""", window),
        "snmp_traps": rows(conn, """
            SELECT trap_name, count(*) AS n
            FROM snmp_traps WHERE device_id = $device AND ts BETWEEN $start AND $end
            GROUP BY ALL ORDER BY n DESC""", window),
        "dhcp": rows(conn, """
            SELECT event_type, sum(count) AS total
            FROM dhcp_events WHERE device_id = $device AND ts BETWEEN $start AND $end
            GROUP BY ALL ORDER BY total DESC""", window),
    }


def _audit(action, device_id):
    line = f"{datetime.now().isoformat(timespec='seconds')} {action} {device_id} (simulated)"
    with open(AUDIT_LOG, "a") as f:
        f.write(line + "\n")
    return line


def interface_reset(device_id):
    return _audit("interface_reset", device_id)


def dhcp_discard_clear(device_id):
    return _audit("dhcp_discard_clear", device_id)
