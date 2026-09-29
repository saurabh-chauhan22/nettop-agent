"""Agent memory. Start both services with: docker compose up -d
- Short-term (Redis): the LangGraph checkpointer, holding each conversation's live state. It expires when idle.
- Long-term (Postgres): the LangGraph store, holding conversation history for good."""
import os

from langgraph.checkpoint.redis import RedisSaver
from langgraph.store.postgres import PostgresStore
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from utils.config import load_env

load_env()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
POSTGRES_URI = os.getenv("POSTGRES_URI", "postgresql://agentnet:agentnet@localhost:5432/agentnet")
SHORT_TERM_MINUTES = 24 * 60  # an idle conversation's working state expires after a day; any access resets the clock


def short_term() -> RedisSaver:
    try:
        saver = RedisSaver(redis_url=REDIS_URL, ttl={"default_ttl": SHORT_TERM_MINUTES, "refresh_on_read": True})
        saver.setup()
    except Exception as e:  # fail loud with the fix, not a bare connection error
        raise RuntimeError(f"Redis is not reachable at {REDIS_URL}. Start it with: docker compose up -d") from e
    return saver


def long_term() -> PostgresStore:
    try:
        pool = ConnectionPool(POSTGRES_URI, open=True, timeout=5,
                              kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})
        store = PostgresStore(pool)
        store.setup()
    except Exception as e:
        raise RuntimeError(f"Postgres is not reachable at {POSTGRES_URI}. Start it with: docker compose up -d") from e
    return store
