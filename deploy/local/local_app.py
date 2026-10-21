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
    '<body><aside style="padding:10px 24px;background:#fff4ce;color:#513c00;font:14px system-ui" role="note"><strong>Local recording mode.</strong> Notifications are saved on this Mac. No Slack, email or PagerDuty messages are sent.</aside>',
)


@app.get("/local-status", dependencies=[Depends(require_write_principal)])
def local_status() -> dict[str, Any]:
    return {"profile": "local-recording", "external_delivery": False, **release}


@app.get("/", response_class=HTMLResponse)
@app.get("/deliveries", response_class=HTMLResponse)
@app.get("/deliveries/{identifier}", response_class=HTMLResponse)
@app.get("/policy", response_class=HTMLResponse)
@app.get("/invariants", response_class=HTMLResponse)
@app.get("/audit", response_class=HTMLResponse)
def console(identifier: str | None = None) -> str:
    return index


app.mount("/assets", StaticFiles(directory="/console/assets"), name="console-assets")
