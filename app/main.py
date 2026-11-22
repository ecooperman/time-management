import asyncio
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from shared_python import accounts_gate, feedback_relay, oidc_login, owned

from . import access, config, crud, schemas
from .config import SHARED_ASSETS_BASE
from .reminders import run_reminder_loop
from .routers import categories, push, stats, tasks, users

# Schema is owned by Alembic migrations (see migrations/) - run
# `alembic upgrade head` before starting the app rather than relying on
# create_all, so schema changes never silently bypass migrations. (A new
# account's default categories are made when the account is, see crud.py.)


def _get_git_sha() -> str:
    """Short commit hash the running app was deployed from, read straight
    from the repo on disk (the deploy pulls a real git checkout) - no CI
    wiring needed, and it can never drift from what's actually running.
    """
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


GIT_SHA = _get_git_sha()


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(run_reminder_loop())
    yield


app = FastAPI(title="Time Management", lifespan=lifespan)
access.install(app)  # only people with an account get in, each inside their own private data (app/access.py)
templates = Jinja2Templates(directory="templates")


@app.get("/api/version")
def get_version():
    return {"version": GIT_SHA}


@app.exception_handler(crud.BadReference)
def _bad_reference(request: Request, exc: crud.BadReference):
    return JSONResponse({"detail": str(exc)}, status_code=400, headers={"Cache-Control": "no-store"})


@app.exception_handler(crud.DeviceInUse)
def _device_in_use(request: Request, exc: crud.DeviceInUse):
    return JSONResponse({"detail": str(exc)}, status_code=409, headers={"Cache-Control": "no-store"})


@app.exception_handler(owned.WrongOwner)
def _wrong_owner(request: Request, exc: owned.WrongOwner):
    """The data layer's last line of defence refused a write that touched someone else's data."""
    return JSONResponse({"detail": "That isn't yours to change"}, status_code=403, headers={"Cache-Control": "no-store"})


@app.get("/api/me", response_model=schemas.Me)
def get_me(request: Request, account=Depends(accounts_gate.current_account)):
    """Who is signed in, for the menu's Log out entry and for hiding what only an administrator may use (the shared
    Global.currentUser reads this)."""
    return schemas.Me(
        id=account.id,
        email=account.email,
        is_admin=account.is_admin,
        logout_url=oidc_login.logout_url(request),
    )


# shared_assets_base baked in server-side (no client-side fetch, no flash
# of unstyled content) - see config.py's SHARED_ASSETS_BASE. Registered
# before the StaticFiles mount below so these take priority over it.
def _render(name: str):
    def handler(request: Request):
        return templates.TemplateResponse(request, name, {"shared_assets_base": SHARED_ASSETS_BASE})

    return handler


app.get("/", response_class=HTMLResponse)(_render("index.html"))
app.get("/admin.html", response_class=HTMLResponse)(_render("admin.html"))
app.get("/users.html", response_class=HTMLResponse)(_render("users.html"))


@app.middleware("http")
async def no_cache(request: Request, call_next):
    """Never let the browser (or iOS's aggressive standalone-PWA cache) serve
    a stale copy of the app - this is a single-user local tool, not a public
    site, so there's no real cost to always fetching fresh.
    """
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(categories.router)
app.include_router(push.router)
app.include_router(stats.router)
feedback_relay.install(app, "time")  # Send feedback in the menu, passed on to the dashboard's inbox (behind the accounts gate)
app.include_router(tasks.router)
app.include_router(users.router)


app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    from .config import HOST, PORT

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
