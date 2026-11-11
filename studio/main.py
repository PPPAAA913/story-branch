import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .workspace import WorkspaceStore, ModelGateway, make_router
from .auth import AuthStore, COOKIE

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
app = FastAPI(title="Short Drama Studio", version="0.3.0")
allowed_hosts = [h.strip() for h in os.getenv("STUDIO_ALLOWED_HOSTS", "127.0.0.1,localhost,[::1],testserver").split(",") if h.strip()]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
app.mount("/static", StaticFiles(directory=ROOT / "studio" / "static"), name="static")
workspace_store = WorkspaceStore(DATA_PATH)
workspace_gateway = ModelGateway()
auth = AuthStore(DATA_PATH)
app.include_router(make_router(workspace_store, workspace_gateway))


@app.middleware("http")
async def local_writes(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
        if origin and origin != expected:
            return JSONResponse({"detail": "不允许跨站修改工作台。"}, status_code=403)
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            return JSONResponse({"detail": "请使用 JSON 请求。"}, status_code=415)
    path = request.url.path
    request.state.user = auth.user(request.cookies.get(COOKIE))
    if path.startswith("/api/") and path not in {"/api/health", "/api/auth/login"}:
        if not request.state.user:
            return JSONResponse({"detail": "请先登录。"}, status_code=401, headers={"Cache-Control": "no-store"})
        if path == "/api/workspace/settings" and request.method == "POST" and request.state.user["role"] != "admin":
            return JSONResponse({"detail": "只有管理员可以配置模型。"}, status_code=403)
        prefix = "/api/workspace/projects/"
        if path.startswith(prefix):
            pid = path[len(prefix):].split("/")[0]
            if not auth.member(pid, request.state.user["id"]):
                return JSONResponse({"detail": "项目不存在或没有访问权限。"}, status_code=404)
        # Legacy endpoints have no membership model; keep them offline in team mode.
        if path.startswith("/api/projects/") or path == "/api/action":
            return JSONResponse({"detail": "旧流程已停用，请使用新版工作台。"}, status_code=410)
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.post("/api/auth/login")
def login(data: dict, request: Request):
    username, password = data.get("username"), data.get("password")
    if not isinstance(username, str) or not 1 <= len(username) <= 80 or not isinstance(password, str) or not 1 <= len(password) <= 128:
        raise HTTPException(400, "请输入正确的账号和密码。")
    token, error = auth.login(username.strip().lower(), password, request.client.host if request.client else "unknown")
    if error:
        raise HTTPException(429 if error == "limited" else 401, "登录尝试过多，请 15 分钟后再试。" if error == "limited" else "账号或密码错误。")
    response = JSONResponse({"user": auth.user(token)})
    response.set_cookie(COOKIE, token, httponly=True, secure=os.getenv("STUDIO_COOKIE_SECURE", "0") == "1", samesite="strict", max_age=43200)
    return response


@app.get("/api/auth/me")
def me(request: Request):
    return request.state.user


@app.post("/api/auth/logout")
def logout(request: Request):
    auth.logout(request.cookies.get(COOKIE, ""))
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE)
    return response


@app.get("/login")
def login_page():
    return FileResponse(ROOT / "studio" / "static" / "login.html")


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
