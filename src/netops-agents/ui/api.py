"""Web API for the AgentNet console. Wraps the supervisor graph and serves the built Svelte app from ui/web/dist.
Run: python ui/api.py, then open http://127.0.0.1:8000"""
import sys
from pathlib import Path

# Allow running this file directly: put the package root (src/netops-agents) on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
from langchain_core.messages import AIMessage, HumanMessage
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from agents.memory import long_term
from agents.supervisor import graph
from agents.tools import lake, rows
from base import AUDIT_LOG
from detect.anomaly_detector import detect

WEB_DIST = Path(__file__).parent / "web" / "dist"
MAX_MESSAGE = 2000
MAX_THREAD_ID = 100
HISTORY = ("conversations",)  # long-term store namespace: one item per conversation

store = long_term()


def to_ui(message):
    if message.type == "human":
        return {"role": "you", "text": message.content}
    return {"role": "agent", "text": message.content, "card": message.additional_kwargs.get("card", {"kind": "text"})}


def from_ui(entry):
    if entry["role"] == "you":
        return HumanMessage(entry["text"])
    return AIMessage(entry["text"], additional_kwargs={"card": entry["card"]})


def run_chat(thread_id, message):
    config = {"configurable": {"thread_id": thread_id}}
    saved = store.get(HISTORY, thread_id)
    restored = []
    # Short-term state expired but long-term history exists: reload the transcript so follow-ups keep context
    if saved and not graph.get_state(config).values.get("messages"):
        restored = [from_ui(m) for m in saved.value["messages"]]
    out = graph.invoke({"messages": [*restored, HumanMessage(message)]}, config)
    transcript = [to_ui(m) for m in out["messages"]]
    title = saved.value["title"] if saved else message[:80]
    store.put(HISTORY, thread_id, {"title": title, "messages": transcript})
    return {**transcript[-1], "pending": public_pending(out.get("pending"))}


def public_pending(pending):
    return {"action": pending["action"], "device_id": pending["device_id"]} if pending else None


def load_anomalies():
    """Detector events plus each flagged modem's 24-hour SNR trace for the sparkline."""
    conn = lake()
    events = detect(conn)
    if not events:
        return []
    traces = {r["device_id"]: r for r in rows(conn, """
        SELECT device_id, list(snr_db ORDER BY ts) AS snr, list(ts ORDER BY ts) AS ts
        FROM device_telemetry WHERE list_contains($ids, device_id) GROUP BY device_id""",
        {"ids": [e["device_id"] for e in events]})}
    return [{
        "device_id": e["device_id"],
        "signals": e["signals"],
        "start": e["start_ts"].isoformat(),
        "end": e["end_ts"].isoformat(),
        "snr": traces[e["device_id"]]["snr"],
        "ts": [t.isoformat() for t in traces[e["device_id"]]["ts"]],
    } for e in events]


async def anomalies(request):
    return JSONResponse(await run_in_threadpool(load_anomalies))


async def chat(request):
    body = await request.json()
    message, thread_id = body.get("message"), body.get("thread_id")
    # Trust boundary: the browser is untrusted input
    if not (isinstance(message, str) and message.strip() and len(message) <= MAX_MESSAGE
            and isinstance(thread_id, str) and 0 < len(thread_id) <= MAX_THREAD_ID):
        return JSONResponse({"error": f"Send a message of 1 to {MAX_MESSAGE} characters and a thread_id."}, status_code=400)
    return JSONResponse(await run_in_threadpool(run_chat, thread_id, message.strip()))


def list_conversations():
    # ponytail: newest 100 by the store's own ordering; page through search() if history grows past that
    items = store.search(HISTORY, limit=100)
    items.sort(key=lambda item: item.updated_at, reverse=True)
    return [{"id": i.key, "title": i.value["title"], "updated_at": i.updated_at.isoformat()} for i in items]


def load_conversation(thread_id):
    saved = store.get(HISTORY, thread_id)
    if not saved:
        return None
    # The transcript comes from long-term memory; a pending approval only exists while short-term state is alive
    live = graph.get_state({"configurable": {"thread_id": thread_id}}).values
    return {"messages": saved.value["messages"], "pending": public_pending(live.get("pending"))}


async def conversations(request):
    return JSONResponse(await run_in_threadpool(list_conversations))


async def conversation(request):
    found = await run_in_threadpool(load_conversation, request.path_params["thread_id"])
    if not found:
        return JSONResponse({"error": "No conversation with that id."}, status_code=404)
    return JSONResponse(found)


async def audit(request):
    lines = AUDIT_LOG.read_text().splitlines()[-8:] if AUDIT_LOG.exists() else []
    return JSONResponse(lines[::-1])


routes = [
    Route("/api/anomalies", anomalies),
    Route("/api/chat", chat, methods=["POST"]),
    Route("/api/conversations", conversations),
    Route("/api/conversations/{thread_id}", conversation),
    Route("/api/audit", audit),
]
if WEB_DIST.exists():  # built app; during development, Vite serves the UI and proxies /api here
    routes.append(Mount("/", StaticFiles(directory=WEB_DIST, html=True)))
app = Starlette(routes=routes)


if __name__ == "__main__":
    # ponytail: no auth, so it binds to localhost only; add auth before exposing it beyond this machine
    uvicorn.run(app, host="127.0.0.1", port=8000)
