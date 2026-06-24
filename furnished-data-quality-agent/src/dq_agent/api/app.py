"""Service API.

Endpoints:
  GET  /health                      - liveness (real)
  POST /batches/{batch_id}/validate - run the deterministic engine, return anomalies (real)
  POST /batches/{batch_id}/pipeline - run the full agent pipeline (stub -> 501)
  GET  /reviews                     - the HITL review queue (stub -> 501)
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from dq_agent.rules.engine import run_batch, summarize

app = FastAPI(title="Furnished Data Quality Agent", version="0.0.1")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/batches/{batch_id}/validate")
def validate(batch_id: str) -> dict:
    """Run the deterministic rule engine over a batch and return its anomalies."""
    from dq_agent.data.load import load_batch

    try:
        batch, records, labels = load_batch(batch_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    anomalies = run_batch(records, labels=labels)
    return {
        "batch_id": batch.batch_id,
        "furnisher_id": batch.furnisher_id,
        "summary": summarize(anomalies),
        "anomalies": [a.model_dump(mode="json") for a in anomalies],
    }


@app.post("/batches/{batch_id}/pipeline")
def pipeline(batch_id: str) -> dict:
    raise HTTPException(status_code=501, detail="Agent pipeline not implemented yet.")


@app.get("/reviews")
def reviews() -> dict:
    raise HTTPException(status_code=501, detail="HITL review queue not implemented yet.")


def main() -> None:
    import uvicorn

    from dq_agent.config import get_settings

    s = get_settings()
    uvicorn.run("dq_agent.api.app:app", host=s.api_host, port=s.api_port, reload=True)


if __name__ == "__main__":
    main()
