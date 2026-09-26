"""Synthesize DOCSIS data (telemetry, syslogs, snmp_traps, dhcp_events, device_config, topology) with planted incidents. Writes parquet to data/ and the planted labels to eval/gold_dataset.jsonl."""
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Allow running this file directly: put the package root (src/netops-agents) on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from base import DATA_DIR, GOLD_FILE

# Planted incidents: (modem number, fault type, hours after the timeline starts).
INCIDENTS = [
    (6, 'rf_impairment', 12),
    (12, 'rf_impairment', 4),
    (3, 'dhcp_storm', 8),
    (16, 'dhcp_storm', 18),
    (9, 'interface_flap', 6),
    (18, 'interface_flap', 15),
]
INCIDENT_HOURS = 2

# The correct action per fault. Set by the author here; in production a network SME sets it.
EXPECTED_ACTION = {
    'rf_impairment': 'escalate_field_tech',  # plant noise: no remote command fixes it
    'dhcp_storm': 'dhcp_discard_clear',
    'interface_flap': 'interface_reset',
}


class DataGenerator:
    '''
    Generate synthetic DOCSIS data with planted incidents
    and write to parquet files
    '''

    def generate_relational_network_data(self, hours:int=24, interval_mins:int=15, num_modems:int=20,
                                         seed:int=42, end_time:datetime=datetime(2026, 9, 25)):
        # Fixed seed and end time: the same call always produces the same data and labels
        random.seed(seed)
        np.random.seed(seed)
        start_time = end_time - timedelta(hours=hours)
        timestamps = pd.date_range(start=start_time, end=end_time, freq=f'{interval_mins}min')

        # 1. Topology & 2. Device Config (Dimension Tables)
        cmts_nodes = ['CMTS-WEST-01', 'CMTS-WEST-02']
        topology_records = []
        config_records = []

        # Generate CMTS parents
        for cmts in cmts_nodes:
            topology_records.append({'device_id': cmts, 'parent_id': None, 'region': 'West', 'market': 'Denver'})
            config_records.append({'device_id': cmts, 'vendor': 'Cisco', 'model': 'cBR-8', 'interfaces': '100G', 'sw_version': 'IOS-XE 16.12'})

        # Generate Modem children
        modem_ids = [f"MODEM-{str(i).zfill(3)}" for i in range(1, num_modems + 1)]
        modem_macs = {}

        for modem in modem_ids:
            parent = random.choice(cmts_nodes)
            mac = f"00:1A:2B:3C:{np.random.randint(0, 255):02X}:{np.random.randint(0, 255):02X}"
            modem_macs[modem] = mac

            topology_records.append({'device_id': modem, 'parent_id': parent, 'region': 'West', 'market': 'Denver'})
            config_records.append({'device_id': modem, 'vendor': 'Arris', 'model': 'SB8200', 'interfaces': 'RF,Eth', 'sw_version': 'v9.1.103'})

        # Map every (modem, interval) inside an incident window to its fault type
        fault_at = {}
        gold = []
        for num, fault, hour in INCIDENTS:
            modem = f"MODEM-{num:03d}"
            start = start_time + timedelta(hours=hour)
            end = start + timedelta(hours=INCIDENT_HOURS)
            gold.append({'device_id': modem, 'start': str(start), 'end': str(end),
                         'root_cause': fault, 'action': EXPECTED_ACTION[fault]})
            for ts in timestamps[(timestamps >= start) & (timestamps <= end)]:
                fault_at[(modem, ts)] = fault

        # 3. Telemetry, 4. Syslogs, 5. SNMP Traps, 6. DHCP Events (Fact Tables)
        telemetry, syslogs, traps, dhcp = [], [], [], []

        for ts in timestamps:
            for modem in modem_ids:
                # Base healthy metrics
                snr = np.random.normal(38.0, 1.5)
                tx = np.random.normal(42.0, 1.0)
                rx = np.random.normal(0.0, 2.0)
                util = max(0.1, min(99.9, np.random.normal(15.0, 10.0)))
                errors = 0

                fault = fault_at.get((modem, ts))
                if fault == 'rf_impairment':
                    snr -= np.random.uniform(10, 15)  # Drop SNR below 30
                    tx += np.random.uniform(8, 12)    # Modem pushes transmit power to compensate
                    errors = int(np.random.exponential(50))
                    if random.random() > 0.5:
                        syslogs.append({'ts': ts, 'device_id': modem, 'severity': 'CRITICAL', 'facility': 'DOCSIS', 'message': f'T3 Timeout on interface RF0. SNR dropped to {snr:.1f}'})
                        traps.append({'ts': ts, 'device_id': modem, 'trap_name': 'linkDown', 'oid': '1.3.6.1.2.1.2.2.1.8', 'value': 'down(2)'})
                    # Re-registering modem spams DHCP DISCOVER (a deliberate look-alike of dhcp_storm)
                    dhcp.append({'ts': ts, 'device_id': modem, 'event_type': 'DISCOVER', 'mac': modem_macs[modem], 'count': np.random.randint(20, 100)})
                elif fault == 'dhcp_storm':
                    # RF stays healthy; a misbehaving device floods DHCP DISCOVER
                    dhcp.append({'ts': ts, 'device_id': modem, 'event_type': 'DISCOVER', 'mac': modem_macs[modem], 'count': np.random.randint(100, 300)})
                elif fault == 'interface_flap':
                    # RF stays healthy; the interface alternates down and up every interval
                    errors = int(np.random.exponential(10))
                    state = 'down' if (ts.hour * 60 + ts.minute) // interval_mins % 2 == 0 else 'up'
                    syslogs.append({'ts': ts, 'device_id': modem, 'severity': 'ERROR', 'facility': 'LINK', 'message': f'Interface RF0 changed state to {state}'})
                    traps.append({'ts': ts, 'device_id': modem, 'trap_name': f'link{state.capitalize()}', 'oid': '1.3.6.1.2.1.2.2.1.8', 'value': 'down(2)' if state == 'down' else 'up(1)'})
                elif random.random() < 0.02:
                    # Normal background noise for healthy modems
                    dhcp.append({'ts': ts, 'device_id': modem, 'event_type': 'REQUEST', 'mac': modem_macs[modem], 'count': 1})
                    dhcp.append({'ts': ts, 'device_id': modem, 'event_type': 'ACK', 'mac': modem_macs[modem], 'count': 1})

                telemetry.append({
                    'ts': ts,
                    'device_id': modem,
                    'interface': 'RF0',
                    'snr_db': round(snr, 2),
                    'tx_power_dbmv': round(tx, 2),
                    'rx_power_dbmv': round(rx, 2),
                    'util_pct': round(util, 2),
                    'error_count': errors
                })

        tables = {
            'topology': pd.DataFrame(topology_records),
            'device_config': pd.DataFrame(config_records),
            'device_telemetry': pd.DataFrame(telemetry),
            'syslogs': pd.DataFrame(syslogs),
            'snmp_traps': pd.DataFrame(traps),
            'dhcp_events': pd.DataFrame(dhcp)
        }
        return tables, gold

    def generate(self):
        '''
        Generate synthetic DOCSIS data and write to parquet files
        '''
        tables, gold = self.generate_relational_network_data()
        for table_name, df in tables.items():
            df.to_parquet(DATA_DIR / f"{table_name}.parquet", index=False)
            print(f"Exported {table_name} with {len(df)} records to data/{table_name}.parquet")
        # Labels go to eval/, never into the lake: the agent must not be able to query its own answer key
        GOLD_FILE.write_text("".join(json.dumps(g) + "\n" for g in gold))
        print(f"Wrote {len(gold)} planted incidents to eval/{GOLD_FILE.name}")


if __name__ == '__main__':
    generator = DataGenerator()
    generator.generate()
