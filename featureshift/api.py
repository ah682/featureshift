"""Loopback report API; all executable inputs come from the closed case registry."""

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from featureshift.artifacts import html_report, regression_test, write_artifacts
from featureshift.cases import load_cases, public_case
from featureshift.config import ROOT, STATE, upload_policy
from featureshift.engine import Engine, get_environments
from featureshift.evidence import corpus_status
from featureshift.models import AcceptRequest, RunRequest


def create_app(state: Path = STATE) -> FastAPI:
    engine = Engine(state)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="preflight")
    slots = threading.BoundedSemaphore(8)

    @asynccontextmanager
    async def lifespan(app):
        engine.store.recover_interrupted()
        yield
        executor.shutdown(wait=True, cancel_futures=False)

    app = FastAPI(title="FeatureShift", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method in ("POST", "PUT", "DELETE") and origin:
            if urlparse(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "Cross-origin changes are disabled for this local service."}, status_code=403)
        if request.method in ("POST", "PUT"):
            if len(await request.body()) > 16_384:
                return JSONResponse({"detail": "Request exceeds the local control payload limit."}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'"
        return response

    def get_report(run_id: str) -> dict:
        try:
            return engine.store.get(run_id)
        except KeyError:
            raise HTTPException(404, "Run not found") from None

    @app.get("/api/status")
    def status():
        return {**upload_policy(), "environments": get_environments(), "corpus": corpus_status()}

    @app.get("/api/cases")
    def cases():
        return [public_case(c) for c in load_cases()]

    @app.get("/api/runs")
    def runs():
        return engine.store.list()

    @app.post("/api/runs", status_code=202)
    def start_run(request: RunRequest):
        if not slots.acquire(blocking=False):
            raise HTTPException(429, "The local queue is full. Wait for a running preflight to finish.")
        try:
            report = engine.create(request)
        except KeyError:
            slots.release()
            raise HTTPException(404, "Unknown trusted example") from None
        except ValueError as exc:
            slots.release()
            raise HTTPException(422, str(exc)) from exc

        def execute():
            try:
                engine.execute(report["id"])
            finally:
                slots.release()

        executor.submit(execute)
        return {"id": report["id"], "status": report["status"]}

    @app.get("/api/runs/{run_id}")
    def run_details(run_id: str):
        return get_report(run_id)

    @app.post("/api/runs/{run_id}/accept")
    def accept(run_id: str, request: AcceptRequest):
        get_report(run_id)
        try:
            with engine.store.lock:
                report = engine.store.accept(run_id, request.finding_id, request.reason)
                write_artifacts(report, engine.store.state / "runs" / run_id)
            return report
        except KeyError:
            raise HTTPException(404, "Finding not found") from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/uploads")
    def uploads():
        raise HTTPException(403, upload_policy()["upload_reason"])

    @app.get("/api/runs/{run_id}/report.json")
    def json_download(run_id: str):
        return JSONResponse(get_report(run_id), headers={"Content-Disposition": f'attachment; filename="featureshift-{run_id}.json"'})

    @app.get("/api/runs/{run_id}/report.html")
    def html_download(run_id: str):
        return HTMLResponse(html_report(get_report(run_id)), headers={"Content-Disposition": f'attachment; filename="featureshift-{run_id}.html"'})

    @app.get("/api/runs/{run_id}/regression_test.py")
    def regression_download(run_id: str):
        return Response(regression_test(get_report(run_id)), media_type="text/x-python", headers={"Content-Disposition": f'attachment; filename="test_featureshift_{run_id}.py"'})

    @app.get("/")
    def index():
        return FileResponse(ROOT / "featureshift" / "static" / "index.html")

    app.mount("/static", StaticFiles(directory=ROOT / "featureshift" / "static"), name="static")
    return app

