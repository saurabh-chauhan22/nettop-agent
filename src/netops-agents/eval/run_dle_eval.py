"""Execution-based evaluation of the Data Lake Exploration agent: run a reference query and the agent's
own query on the same lake, and check the agent's result contains the reference answer."""
import json

from agents import dle
from agents.tools import lake, rows
from base import DLE_GOLD_FILE
from eval.scorers import answer_match


def main():
    conn = lake()
    cases = [json.loads(line) for line in DLE_GOLD_FILE.read_text().splitlines()]
    correct = 0
    for case in cases:
        # Reference answers are computed from the lake at eval time, so they stay right if the data is regenerated
        reference = rows(conn, case["reference_sql"])
        out = dle.graph.invoke({"question": case["question"]})
        ok = not out.get("error") and answer_match(reference, out.get("rows", []))
        correct += ok
        expected = next(iter(reference[0].values())) if reference else None
        print(f"{'PASS' if ok else 'FAIL'} {case['question']}\n  expected {expected}, attempts {out['attempts']}, SQL: {out['sql']}")
    print(f"Execution accuracy: {correct} of {len(cases)}")


if __name__ == "__main__":
    main()
