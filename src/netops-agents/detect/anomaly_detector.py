"""Robust z-score and rule-based anomaly detection over the lake. Emits one anomaly_event per device; each event triggers an investigation."""
from agents.tools import lake, rows

# Each device is scored against its own median and MAD (robust to the incident itself skewing the baseline).
# ponytail: one event per device; split events on time gaps if a device can have two incidents in range.
DETECT_SQL = """
WITH t AS (
    SELECT device_id, ts, error_count,
           (snr_db - median(snr_db) OVER w) / (1.4826 * mad(snr_db) OVER w) AS snr_z,
           (tx_power_dbmv - median(tx_power_dbmv) OVER w) / (1.4826 * mad(tx_power_dbmv) OVER w) AS tx_z
    FROM device_telemetry
    WINDOW w AS (PARTITION BY device_id)
),
flags AS (
    SELECT device_id, ts, 'snr_drop' AS signal FROM t WHERE snr_z < -4
    UNION ALL SELECT device_id, ts, 'tx_power_spike' FROM t WHERE tx_z > 4
    UNION ALL SELECT device_id, ts, 'errors' FROM t WHERE error_count > 0
    UNION ALL SELECT device_id, ts, 'dhcp_discover_burst' FROM dhcp_events WHERE event_type = 'DISCOVER' AND "count" >= 10
    UNION ALL SELECT device_id, ts, 'link_down' FROM snmp_traps WHERE trap_name = 'linkDown'
)
SELECT device_id, min(ts) AS start_ts, max(ts) AS end_ts, list(DISTINCT signal ORDER BY signal) AS signals
FROM flags
GROUP BY device_id
-- Persistence rule: one anomalous 15-minute sample is noise (seed 42 has a healthy modem at tx z = 4.07)
HAVING count(DISTINCT ts) >= 2
ORDER BY device_id
"""


def detect(conn=None) -> list[dict]:
    return rows(conn or lake(), DETECT_SQL)


# Triage order, most urgent first. A fixed rule, reviewable in code; in production NSOC SMEs would set it.
SEVERITY = [
    ("snr_drop", "RF signal loss"),  # needs a field tech, which has the longest lead time
    ("link_down", "Link loss"),
    ("errors", "Errors"),
    ("dhcp_discover_burst", "DHCP storm"),
]
TRIAGE_RULE = ("Ranked by a fixed severity rule: RF signal loss first (it needs a field tech, the longest lead time), "
               "then link loss, then errors, then DHCP storms. Ties go to the longer anomaly.")


def rank(events: list[dict]) -> list[dict]:
    """Detector events, most urgent first, each labeled with its severity tier."""
    def tier(e):
        return next((i for i, (signal, _) in enumerate(SEVERITY) if signal in e["signals"]), len(SEVERITY))
    ranked = sorted(events, key=lambda e: (tier(e), -(e["end_ts"] - e["start_ts"]).total_seconds(), e["device_id"]))
    return [{**e, "severity": SEVERITY[tier(e)][1] if tier(e) < len(SEVERITY) else "Other"} for e in ranked]
