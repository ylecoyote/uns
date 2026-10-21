"""Recording-only local smoke app serving the unchanged production SPA assets."""
import os
from fastapi import Depends
from starlette.staticfiles import StaticFiles
from starlette.responses import FileResponse
from agsignal.app import create_app
from agsignal.api.auth import require_write_principal
from runtime_profile import make_runtime
app=create_app(runtime=make_runtime())
@app.get('/__smoke__/identity',dependencies=[Depends(require_write_principal)])
def identity():
    return {'profile':'recording-only-local-smoke','revision':os.environ['SMOKE_REVISION']}
@app.get('/')
@app.get('/deliveries')
@app.get('/deliveries/{identifier}')
@app.get('/policy')
@app.get('/invariants')
@app.get('/audit')
def spa(identifier: str | None=None):
    return FileResponse('/console/index.html')
app.mount('/assets',StaticFiles(directory='/console/assets'),name='console-assets')
