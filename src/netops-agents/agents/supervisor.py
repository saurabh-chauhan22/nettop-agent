"""Supervisor: a conversational router over the investigation agent and the Data Lake Exploration agent.
Remote actions are approved in the chat by an exact yes or no, never by the LLM's reading of the message."""
import uuid
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command
from pydantic import BaseModel, Field

from agents import dle, investigation
from agents.llm import claude
from agents.memory import short_term
from detect.anomaly_detector import TRIAGE_RULE, detect, rank

APPROVE, REJECT = {"yes", "y", "approve"}, {"no", "n", "reject"}
HISTORY = 10  # recent messages the router sees: enough for follow-ups, bounded for cost

ROUTER_PROMPT = """You are the front desk of a DOCSIS network operations assistant. Pick one route for the user's latest message:
- investigate: the user wants to know what is wrong with a specific device. Set device_id, for example MODEM-012.
- triage: the user asks which devices have problems, what needs attention or should be looked at first, or for an overview of current anomalies. No fields needed.
- data_lake: a factual question the network data can answer (counts, readings, logs, topology). Set question to a standalone version that carries any context from earlier turns. Questions about which devices need attention go to triage, not data_lake.
- respond: anything else, including greetings and topics outside network operations. Set reply to a short answer that says what you can help with.
Leave fields that do not apply as empty strings.{pending}"""

PENDING_NOTE = "\nA remote action is waiting for approval: {action} on {device_id}. If the user seems to be answering it, use respond and ask them to reply exactly yes or no."


class Route(BaseModel):
    route: Literal["investigate", "triage", "data_lake", "respond"]
    device_id: str = Field(description="Device to investigate, for example MODEM-012, or empty")
    question: str = Field(description="Standalone data question for the data lake, or empty")
    reply: str = Field(description="Direct reply for the respond route, or empty")


class ChatState(TypedDict, total=False):
    messages: Annotated[list, add_messages]  # conversation memory, persisted per thread by the checkpointer
    route: dict
    pending: dict  # a remote action waiting for the operator's yes or no


router_llm = claude().with_structured_output(Route, method="json_schema")


def reply(text, card):
    """An agent message carrying its structured card for the UI. langchain-anthropic ignores
    additional_kwargs, so cards are stored with the conversation but never sent to Claude."""
    return AIMessage(text, additional_kwargs={"card": card})


def router(state: ChatState) -> dict:
    text = state["messages"][-1].content.strip().lower()
    pending = state.get("pending")
    # Deterministic gate: approval is an exact word from the human, not an LLM interpretation
    if pending and text in APPROVE | REJECT:
        return {"route": {"route": "approve" if text in APPROVE else "reject"}}
    prompt = ROUTER_PROMPT.format(pending=PENDING_NOTE.format(**pending) if pending else "")
    history = state["messages"][-HISTORY:]
    history = history[next(i for i, m in enumerate(history) if m.type == "human"):]  # the window must open on a user turn
    decision = router_llm.invoke([("system", prompt), *history])
    return {"route": decision.model_dump()}


def investigate(state: ChatState) -> dict:
    device = state["route"]["device_id"].strip().upper()
    event = next((e for e in detect() if e["device_id"] == device), None)
    if not event:
        text = f"The detector found no anomaly on {device or 'that device'}, so there is nothing to investigate."
        return {"messages": [reply(text, {"kind": "text"})]}
    config = {"configurable": {"thread_id": f"chat-{device}-{uuid.uuid4().hex[:8]}"}}
    result = investigation.graph.invoke({"anomaly_event": event}, config)
    d = result["diagnosis"]
    text = f"{device}: {d['root_cause']}, recommended action {d['action']}.\n" + "\n".join(f"- {f}" for f in d["evidence"])
    card = {"kind": "diagnosis", "device_id": device, **d}
    if "__interrupt__" not in result:
        return {"messages": [reply(text, card)]}
    # The investigation graph is paused at its approval gate; keep its thread so a yes or no can resume it
    text += f"\n\n{d['action']} on {device} is a remote action. Reply yes to run it or no to skip it."
    return {"messages": [reply(text, card)],
            "pending": {"config": config, "action": d["action"], "device_id": device}}


def triage(state: ChatState) -> dict:
    # Deterministic on purpose: an LLM writing its own "priority score" SQL invented criteria and missed faults
    ranked = rank(detect())
    if not ranked:
        return {"messages": [reply("The detector found no anomalies in the last 24 hours.", {"kind": "text"})]}
    items = [{"device_id": e["device_id"], "severity": e["severity"], "signals": e["signals"],
              "start": e["start_ts"].isoformat(), "end": e["end_ts"].isoformat()} for e in ranked]
    lines = [f"{i}. {e['device_id']}: {e['severity']} ({', '.join(e['signals'])})" for i, e in enumerate(items, 1)]
    text = f"{len(items)} modems are flagged, most urgent first.\n" + "\n".join(lines) + f"\n\n{TRIAGE_RULE}"
    return {"messages": [reply(text, {"kind": "triage", "items": items, "rule": TRIAGE_RULE})]}


def data_lake(state: ChatState) -> dict:
    out = dle.graph.invoke({"question": state["route"]["question"]})
    card = {"kind": "sql", "answer": out["answer"], "sql": out["sql"]}
    return {"messages": [reply(f"{out['answer']}\n\nSQL: {out['sql']}", card)]}


def resolve(state: ChatState) -> dict:
    pending, approved = state["pending"], state["route"]["route"] == "approve"
    # The paused investigation lives in process memory; after a server restart it is gone, so never guess
    if not investigation.graph.get_state(pending["config"]).next:
        text = (f"That approval expired when the server restarted, so nothing was run. "
                f"Investigate {pending['device_id']} again to get a fresh recommendation.")
        return {"messages": [reply(text, {"kind": "text"})], "pending": {}}
    result = investigation.graph.invoke(Command(resume=approved), pending["config"])
    card = {"kind": "action", "approved": approved, "action": pending["action"], "device_id": pending["device_id"]}
    return {"messages": [reply(result["action_result"], card)], "pending": {}}


def respond(state: ChatState) -> dict:
    return {"messages": [reply(state["route"]["reply"], {"kind": "text"})]}


builder = StateGraph(ChatState)
for node in (router, investigate, triage, data_lake, resolve, respond):
    builder.add_node(node)
builder.add_edge(START, "router")
builder.add_conditional_edges("router", lambda s: s["route"]["route"], {
    "investigate": "investigate", "triage": "triage", "data_lake": "data_lake",
    "approve": "resolve", "reject": "resolve", "respond": "respond",
})
for node in ("investigate", "triage", "data_lake", "resolve", "respond"):
    builder.add_edge(node, END)
# Short-term memory in Redis: each conversation's live state, restored on every turn by thread id
graph = builder.compile(checkpointer=short_term())


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "cli"}}
    print("Ask about the network. Try: what's wrong with MODEM-009? or: how many modems are on CMTS-WEST-01?")
    while True:
        try:
            text = input("\nyou> ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if text:
            print(f"agent> {graph.invoke({'messages': [HumanMessage(text)]}, config)['messages'][-1].content}")
