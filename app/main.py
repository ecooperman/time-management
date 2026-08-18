import subprocess
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import SHARED_ASSETS_BASE
from .database import SessionLocal
from .routers import categories, jobs, people, tasks
from .seed import seed_categories

# Schema is owned by Alembic migrations (see migrations/) - run
# `alembic upgrade head` before starting the app rather than relying on
# create_all, so schema changes never silently bypass migrations.

with SessionLocal() as db:
    seed_categories(db)


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

app = FastAPI(title="Time Management")
templates = Jinja2Templates(directory="templates")


@app.get("/api/version")
def get_version():
    return {"version": GIT_SHA}


# shared_assets_base baked in server-side (no client-side fetch, no flash
# of unstyled content) - see config.py's SHARED_ASSETS_BASE. Registered
# before the StaticFiles mount below so these take priority over it.
def _render(name: str):
    def handler(request: Request):
        return templates.TemplateResponse(name, {"request": request, "shared_assets_base": SHARED_ASSETS_BASE})

    return handler


app.get("/", response_class=HTMLResponse)(_render("index.html"))
app.get("/jobs.html", response_class=HTMLResponse)(_render("jobs.html"))
app.get("/admin.html", response_class=HTMLResponse)(_render("admin.html"))


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
app.include_router(jobs.router)
app.include_router(people.router)
app.include_router(tasks.router)

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    from .config import HOST, PORT

    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=True)
