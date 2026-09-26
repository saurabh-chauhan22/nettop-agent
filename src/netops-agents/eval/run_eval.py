"""Supervised evaluation: detection against the planted incidents, then root cause and action per incident.
LangSmith traces every graph run when LANGSMITH_TRACING=true.
ponytail: plain loop; move to langsmith evaluate() for experiment comparison in the LangSmith UI."""
import json

from agents.investigation import graph
from agents.tools import lake, rows
from base import GOLD_FILE
from detect.anomaly_detector import detect
from eval.scorers import accuracy_by_slice, detection_scores


def main():
    gold = [json.loads(line) for line in GOLD_FILE.read_text().splitlines()]
    conn = lake()
    modems = {r["device_id"] for r in rows(conn, "SELECT device_id FROM topology WHERE parent_id IS NOT NULL")}
    events = {e["device_id"]: e for e in detect(conn)}

    print("Detection per modem:", detection_scores(set(events), {g["device_id"] for g in gold}, modems))

    results = []
    for g in gold:
        pred = {}  # a missed detection scores as a wrong diagnosis
        if g["device_id"] in events:
            # The graph pauses before any remediation runs, so evaluation never acts on a device.
            config = {"configurable": {"thread_id": f"eval-{g['device_id']}"}}
            pred = graph.invoke({"anomaly_event": events[g["device_id"]]}, config)["diagnosis"]
        results.append({"gold": g, "pred": pred})
        print(f"{g['device_id']}: gold {g['root_cause']}/{g['action']}, predicted {pred.get('root_cause')}/{pred.get('action')}")

    print("Root cause accuracy:", accuracy_by_slice(results, "root_cause"))
    print("Action accuracy:", accuracy_by_slice(results, "action"))


if __name__ == "__main__":
    main()
