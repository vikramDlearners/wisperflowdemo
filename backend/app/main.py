"""FastAPI application: registers the API routers and maps domain errors to HTTP status codes."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    activity,
    appointments,
    auth,
    care_profiles,
    conversation_summaries,
    families,
    insurance,
    medicines,
    notifications,
    parent,
    prescription_scans,
    roles,
    settings,
    task_links,
    tasks,
)
from app.core.config import settings as app_settings
from app.services import scheduler
from app.services.errors import AuthError, LinkGone, NotFound
from app.services.parent_context import ParentNotLinked
from app.services.permissions import NotAMember, PermissionDenied


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Background jobs (missed-dose alerts, daily summaries); tests set SCHEDULER_ENABLED=false.
    if app_settings.scheduler_enabled:
        scheduler.start_scheduler()
    try:
        yield
    finally:
        scheduler.stop_scheduler()


app = FastAPI(title="CareCircle API", lifespan=lifespan)

# Local development frontend (Vite dev server).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(NotFound)
def _not_found(_: Request, exc: NotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc) or "Not found"})


@app.exception_handler(LinkGone)
def _link_gone(_: Request, exc: LinkGone) -> JSONResponse:
    return JSONResponse(status_code=410, content={"detail": str(exc) or "This link no longer works"})


@app.exception_handler(PermissionDenied)
def _permission_denied(_: Request, exc: PermissionDenied) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": str(exc) or "Permission denied"})


@app.exception_handler(NotAMember)
def _not_a_member(_: Request, exc: NotAMember) -> JSONResponse:
    # Non-members get 403 rather than 404 so family IDs cannot be probed.
    return JSONResponse(status_code=403, content={"detail": "You are not a member of this family"})


@app.exception_handler(ParentNotLinked)
def _parent_not_linked(_: Request, exc: ParentNotLinked) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": "Ask your family to link your profile"})


@app.exception_handler(AuthError)
def _auth_error(_: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse(status_code=401, content={"detail": str(exc) or "Sign in required"})


@app.exception_handler(ValueError)
def _value_error(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.get("/api/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


for _router in (
    auth.router,
    families.router,
    roles.router,
    care_profiles.router,
    medicines.router,
    insurance.router,
    prescription_scans.router,
    tasks.router,
    task_links.family_router,
    task_links.public_router,
    appointments.router,
    notifications.router,
    activity.router,
    conversation_summaries.router,
    settings.router,
    parent.router,
):
    app.include_router(_router)
