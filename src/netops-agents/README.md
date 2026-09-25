# NetOps IIA Agent Platform (mini)

Multi-agent LangGraph platform for DOCSIS/cable network operations:
anomaly trigger -> root-cause investigation -> cited recommendation ->
human-approved remediation, with NL data-lake access, MCP real-time tools,
gold-standard evaluation, tracing, tests, and CI/CD.

## Architecture
TODO: diagram (see blueprint).

## Components
- ingest/     data lake generation + load (DuckDB | S3/Athena)
- detect/     anomaly detector (investigation trigger)
- agents/     dle, investigation, recommendation, remediation, supervisor
- mcp_server/ real-time device/modem status
- eval/       gold dataset + supervised & LLM-judge scorers
- tests/      pytest

## Setup
TODO: venv, pip install -r requirements.txt, copy .env.example to .env.

## Run
TODO.

## Evaluation methodology
TODO: gold-standard (SME) ground truth vs LLM-as-judge; where they disagree.
