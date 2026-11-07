import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .workspace import WorkspaceStore, ModelGateway, make_router

from .generation import DemoGenerator, GenerationError, OpenRouterGenerator
from .service import InputError, NotFoundError, StudioService, UnsupportedActionError
from .storage import Database


ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = Path(os.getenv("STUDIO_DB_PATH", str(ROOT / "data" / "projects.db")))
MODE = os.getenv("STUDIO_MODEL_MODE", "demo").strip().lower()
if MODE not in {"demo", "openrouter"}:
    raise RuntimeError("STUDIO_MODEL_MODE must be 'demo' or 'openrouter'.")

database = Database(DATA_PATH)
generator = DemoGenerator() if MODE == "demo" else OpenRouterGenerator()
service = StudioService(database, generator)
app = FastAPI(title="Short Drama Studio", version="0.2.0")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])
app.mount("/static", StaticFiles(directory=ROOT / "studio" / "static"), name="static")
workspace_store = WorkspaceStore(DATA_PATH)
workspace_gateway = ModelGateway()
app.include_router(make_router(workspace_store, workspace_gateway))


@app.middleware("http")
async def local_writes(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
        if origin and origin != expected:
            return JSONResponse({"detail": "不允许跨站修改本地工作台。"}, status_code=403)
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            return JSONResponse({"detail": "请使用 JSON 请求。"}, status_code=415)
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def home():
    return FileResponse(ROOT / "studio" / "static" / "workspace.html")


@app.get("/classic")
def classic():
    return FileResponse(ROOT / "studio" / "static" / "index.html")


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "model_mode": MODE,
        "model_configured": MODE == "demo" or bool(os.getenv("OPENROUTER_API_KEY") and os.getenv("OPENROUTER_MODEL")),
        "implemented_workflows": ["concept", "outline"],
    }


@app.post("/api/action")
def action(payload: dict):
    try:
        return service.dispatch(payload)
    except UnsupportedActionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    try:
        return service.get_project(project_id)
    except (NotFoundError, InputError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
