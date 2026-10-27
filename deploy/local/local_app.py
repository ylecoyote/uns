"""Serve UNS and its compiled console with an explicit local-recording banner."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import Depends
from recording_runtime import make_runtime
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles

from agsignal.api.auth import require_write_principal
from agsignal.app import create_app

app = create_app(runtime=make_runtime())
release = json.loads(Path("/release.json").read_text())
index = (
    Path("/console/index.html")
    .read_text()
    .replace('<link rel="icon" type="image/svg+xml" href="/vite.svg" />', "")
)
index = index.replace(
    "<body>",
    '<body><aside style="display:flex;align-items:center;justify-content:space-between;gap:16px;padding:8px 24px;background:#eae9e9;color:#201e1d;border-bottom:1px solid rgba(32,30,29,0.4);font:12px Archivo,system-ui,sans-serif" role="note"><span style="display:inline-flex;align-items:center;gap:10px"><span style="width:10px;height:10px;background:#ec3013;display:inline-block;flex:none" aria-hidden="true"></span><span><strong style="font-weight:800;letter-spacing:0.04em;text-transform:uppercase">Local recording mode.</strong> Notifications are saved on this Mac. No Slack, email or PagerDuty messages are sent.</span></span><span style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px">PROFILE: LOCAL-RECORDING</span></aside>',
)


@app.get("/local-status", dependencies=[Depends(require_write_principal)])
def local_status() -> dict[str, Any]:
    return {"profile": "local-recording", "external_delivery": False, **release}


@app.get("/", response_class=HTMLResponse)
@app.get("/deliveries", response_class=HTMLResponse)
@app.get("/deliveries/{identifier}", response_class=HTMLResponse)
@app.get("/policy", response_class=HTMLResponse)
@app.get("/operations", response_class=HTMLResponse)
@app.get("/invariants", response_class=HTMLResponse)
@app.get("/audit", response_class=HTMLResponse)
@app.get("/docs", response_class=HTMLResponse)
def console(identifier: str | None = None) -> str:
    return index


app.mount("/assets", StaticFiles(directory="/console/assets"), name="console-assets")
