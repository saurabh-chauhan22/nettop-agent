"""Supervised scorers: every score compares a prediction against planted ground truth, which an LLM judge cannot know."""


def detection_scores(flagged: set, planted: set, devices: set) -> dict:
    tp, fp, fn = len(flagged & planted), len(flagged - planted), len(planted - flagged)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    clean = devices - planted
    return {
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "false_alarm_rate": fp / len(clean) if clean else 0.0,
    }


def answer_match(reference: list[dict], predicted: list[dict]) -> bool:
    """Execution-based check for the data lake agent: the reference query's answer (first value of its
    first row) must appear somewhere in the agent's result. Lenient on shape, strict on the value."""
    if not reference:
        return not predicted
    norm = lambda v: round(float(v), 1) if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)
    target = norm(next(iter(reference[0].values())))
    return any(norm(v) == target for row in predicted for v in row.values())


def accuracy_by_slice(results: list[dict], field: str) -> dict:
    """Share of incidents where the prediction matches gold on `field`, overall and per fault type."""
    slices = {}
    for r in results:
        for key in ("all", r["gold"]["root_cause"]):
            slices.setdefault(key, []).append(r["pred"].get(field) == r["gold"][field])
    return {k: sum(v) / len(v) for k, v in slices.items()}
