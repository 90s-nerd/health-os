import csv
import io
import logging
import shutil
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import models, schemas
from .auth import (
    active_pin_hash,
    auth_mode,
    check_rate_limit,
    csrf_token,
    ensure_pin_identity,
    hash_pin,
    pin_is_available,
    profile_for_home_assistant,
    profile_for_pin,
    record_failure,
    require_session,
    serializer,
    verify_pin,
)
from .config import get_config
from .database import Base, db_session, engine
from .notifications import (
    HomeAssistantNotificationSender,
    process_due_reminders,
    recalculate_user_reminders,
)
from .services import (
    app_timezone,
    audit,
    completion_score,
    current_profile,
    ensure_tasks,
    generated_callouts,
    local_today,
    mode_for,
    next_action,
    seed,
    seed_profile,
    task_dict,
    user_setting,
    weight_series,
)
from .time_service import UserClock, utc_now

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","message":"%(message)s"}',
)
log = logging.getLogger("health-os")
cfg = get_config()


def create_backup() -> Path | None:
    if not cfg.database_url.startswith("sqlite") or ":///" not in cfg.database_url:
        return None
    source = Path(cfg.database_url.split(":///", 1)[1])
    if not source.exists():
        return None
    target_dir = Path(cfg.backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"health-os-{datetime.now():%Y%m%d-%H%M%S}.db"
    shutil.copy2(source, target)
    cutoff = datetime.now() - timedelta(days=cfg.backup_retention_days)
    for old in target_dir.glob("health-os-*.db"):
        if datetime.fromtimestamp(old.stat().st_mtime) < cutoff:
            old.unlink()
    return target


def process_notifications() -> None:
    with Session(engine) as db:
        process_due_reminders(db, HomeAssistantNotificationSender())


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed(db)
    Path(cfg.backup_dir).mkdir(parents=True, exist_ok=True)
    scheduler = BackgroundScheduler(timezone=cfg.timezone)
    scheduler.add_job(
        create_backup, "cron", hour=3, minute=15, id="daily-backup", replace_existing=True
    )
    scheduler.add_job(
        process_notifications,
        "interval",
        minutes=1,
        id="notification-worker",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Health OS API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)


@app.middleware("http")
async def security(request: Request, call_next):
    public_paths = (
        "/api/health",
        "/api/auth/status",
        "/api/auth/login",
        "/api/onboarding",
        "/api/onboarding/home-assistant",
        "/api/accounts",
    )
    ha_profile = None
    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        with Session(engine) as db:
            try:
                ha_profile = profile_for_home_assistant(request, db)
            except HTTPException as exc:
                return JSONResponse(
                    {"error": {"code": exc.status_code, "message": exc.detail}},
                    status_code=exc.status_code,
                )
            if ha_profile:
                request.state.profile_id = ha_profile.id
                request.state.auth_provider = "home_assistant"
            elif request.url.path not in public_paths:
                try:
                    payload = require_session(request, True)
                except HTTPException as exc:
                    return JSONResponse(
                        {"error": {"code": exc.status_code, "message": exc.detail}},
                        status_code=exc.status_code,
                    )
                profile = db.get(models.Profile, payload.get("profile_id")) if payload else None
                if not profile or not profile.onboarding_completed:
                    return JSONResponse(
                        {"error": {"code": 401, "message": "Sign in to continue"}},
                        status_code=401,
                    )
                request.state.profile_id = profile.id
                request.state.auth_provider = "pin"
    response = await call_next(request)
    if ha_profile:
        set_session_cookies(response, ha_profile)
    with Session(engine) as db:
        allow_embedding = db.get(models.Setting, "allow_embedding")
        origins = db.get(models.Setting, "embedding_origins")
        frame_ancestors = "'self'"
        if allow_embedding and allow_embedding.value.lower() == "true" and origins:
            frame_ancestors += " " + origins.value
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors {frame_ancestors}"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.exception_handler(HTTPException)
async def http_error(_request: Request, exc: HTTPException):
    return JSONResponse(
        {"error": {"code": exc.status_code, "message": exc.detail}}, status_code=exc.status_code
    )


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    message = "; ".join(error["msg"] for error in exc.errors())
    return JSONResponse(
        {"error": {"code": 422, "message": message}},
        status_code=422,
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/auth/status")
def auth_status(request: Request, db: Session = Depends(db_session)):
    configured_profiles = list(
        db.scalars(select(models.Profile).where(models.Profile.onboarding_completed.is_(True)))
    )
    state_profile_id = getattr(request.state, "profile_id", None)
    profile = db.get(models.Profile, state_profile_id) if state_profile_id else None
    provider = getattr(request.state, "auth_provider", None)
    if not profile and request.cookies.get("health_session"):
        try:
            payload = serializer().loads(
                request.cookies["health_session"], max_age=cfg.keep_signed_in_days * 86400
            )
            profile = db.get(models.Profile, payload.get("profile_id"))
            provider = "pin"
        except Exception:
            pass
    authenticated = bool(profile)
    mode = auth_mode()
    return {
        "onboarding_required": bool(
            profile and not profile.onboarding_completed
            or not profile and not configured_profiles and mode != "home_assistant"
        ),
        "pin_required": mode in {"pin", "auto"} and bool(configured_profiles),
        "registration_available": mode in {"pin", "auto"},
        "auth_mode": mode,
        "auth_provider": provider,
        "authenticated": authenticated,
        "csrf_token": request.cookies.get("health_csrf"),
        "profile": (
            {
                "id": profile.id,
                "display_name": profile.display_name,
                "setup_required": not profile.onboarding_completed,
            }
            if authenticated and profile
            else None
        ),
    }


def set_session_cookies(response: Response, profile: models.Profile, keep_signed_in: bool = False):
    max_age = (
        cfg.keep_signed_in_days * 86400
        if keep_signed_in
        else cfg.session_timeout_minutes * 60
    )
    response.set_cookie(
        "health_session",
        serializer().dumps({"profile_id": profile.id}),
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=cfg.session_secure,
    )
    csrf = csrf_token()
    response.set_cookie(
        "health_csrf",
        csrf,
        max_age=max_age,
        httponly=False,
        samesite="lax",
        secure=cfg.session_secure,
    )
    return csrf


@app.post("/api/onboarding", status_code=201)
def onboarding(
    body: schemas.OnboardingIn,
    response: Response,
    db: Session = Depends(db_session),
):
    if auth_mode() == "home_assistant":
        raise HTTPException(404, "PIN account creation is unavailable in this deployment")
    if not pin_is_available(db, body.pin):
        raise HTTPException(409, "Choose a different PIN")
    profile = models.Profile(
        display_name=body.display_name.strip(),
        pin_hash=hash_pin(body.pin),
        timezone=body.timezone,
        timezone_source="browser_detected",
        timezone_confirmed_at=utc_now(),
        starting_weight_kg=body.starting_weight_kg,
        is_admin=False,
        onboarding_completed=True,
        must_change_pin=False,
    )
    db.add(profile)
    db.flush()
    if body.height_cm is not None:
        profile.height_cm = body.height_cm
    ensure_pin_identity(db, profile)
    seed_profile(db, profile)
    water = db.get(models.UserSetting, (profile.id, "water_target_ml"))
    water.value = str(body.water_target_ml)
    db.commit()
    return {
        "authenticated": True,
        "csrf_token": set_session_cookies(response, profile),
        "profile": {"display_name": profile.display_name},
    }


@app.post("/api/accounts", status_code=201)
def create_account(
    body: schemas.OnboardingIn,
    response: Response,
    db: Session = Depends(db_session),
):
    return onboarding(body, response, db)


@app.post("/api/onboarding/home-assistant")
def home_assistant_onboarding(
    body: schemas.HomeAssistantOnboardingIn,
    request: Request,
    db: Session = Depends(db_session),
):
    if getattr(request.state, "auth_provider", None) != "home_assistant":
        raise HTTPException(403, "Home Assistant authentication is required")
    profile = db.get(models.Profile, db.info.get("profile_id"))
    if not profile:
        raise HTTPException(401, "Sign in to continue")
    profile.display_name = body.display_name.strip()
    profile.timezone = body.timezone
    profile.timezone_source = "browser_detected"
    profile.timezone_confirmed_at = utc_now()
    profile.starting_weight_kg = body.starting_weight_kg
    if body.height_cm is not None:
        profile.height_cm = body.height_cm
    profile.onboarding_completed = True
    seed_profile(db, profile)
    water = db.get(models.UserSetting, (profile.id, "water_target_ml"))
    water.value = str(body.water_target_ml)
    db.commit()
    return {"ok": True, "message": "Your private Health OS space is ready"}


@app.post("/api/auth/login")
def login(
    body: schemas.LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(db_session),
):
    ip = request.client.host if request.client else "unknown"
    check_rate_limit(ip)
    profile = profile_for_pin(db, body.pin)
    if not profile:
        record_failure(ip)
        raise HTTPException(401, "Incorrect PIN")
    csrf = set_session_cookies(response, profile, body.keep_signed_in)
    identity = ensure_pin_identity(db, profile)
    identity.last_login_at = utc_now()
    db.commit()
    return {
        "authenticated": True,
        "csrf_token": csrf,
        "profile": {
            "id": profile.id,
            "display_name": profile.display_name,
            "setup_required": not profile.onboarding_completed,
        },
    }


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie("health_session")
    response.delete_cookie("health_csrf")
    return {"ok": True}


@app.put("/api/auth/pin")
def change_pin(
    body: schemas.PinChangeIn,
    response: Response,
    db: Session = Depends(db_session),
):
    profile = db.get(models.Profile, db.info.get("profile_id"))
    current_hash = active_pin_hash(db)
    if (
        current_hash
        and (not body.current_pin or not verify_pin(body.current_pin, current_hash))
    ):
        raise HTTPException(400, "Current PIN is incorrect")
    if not pin_is_available(db, body.new_pin, profile.id):
        raise HTTPException(409, "We couldn't save that PIN. Try a different one")
    profile.pin_hash = hash_pin(body.new_pin)
    profile.must_change_pin = False
    ensure_pin_identity(db, profile)
    audit(db, "update", "app_profile", profile.id, {"field": "pin_hash"})
    db.commit()
    csrf = set_session_cookies(response, profile)
    return {"ok": True, "message": "PIN updated", "csrf_token": csrf}


def dashboard_for(db: Session, day: date):
    profile = current_profile(db)
    clock = UserClock(profile)
    now_local = clock.now()
    tasks = [task_dict(db, x, now_local) for x in ensure_tasks(db, day)]
    latest_weight = db.scalar(
        select(models.WeightEntry)
        .where(models.WeightEntry.profile_id == profile.id)
        .order_by(models.WeightEntry.entry_date.desc())
    )
    milestones_value = user_setting(db, "weight_milestones", "94,90,88,85")
    milestones = [
        float(value)
        for value in milestones_value.split(",")
        if value.strip()
    ]
    recent_sleep = db.scalar(
        select(models.SleepEntry)
        .where(models.SleepEntry.profile_id == profile.id)
        .order_by(models.SleepEntry.sleep_date.desc())
    )
    week_start = day - timedelta(days=day.weekday())
    week_tasks = list(
        db.scalars(
            select(models.DailyTask).where(
                models.DailyTask.task_date >= week_start,
                models.DailyTask.task_date <= day,
                models.DailyTask.habit_id.in_(
                    select(models.Habit.id).where(models.Habit.profile_id == profile.id)
                ),
            )
        )
    )
    week_required = [x for x in week_tasks if x.required]
    completed_ids = set(
        db.scalars(
            select(models.TaskCompletion.daily_task_id).where(
                models.TaskCompletion.daily_task_id.in_([x.id for x in week_required] or [-1]),
                models.TaskCompletion.state == "completed",
            )
        )
    )
    weekly = (
        round(100 * len(completed_ids) / len(week_required))
        if week_required
        else completion_score(tasks)
    )
    start_of_day = clock.start_of_day_utc(day)
    end_of_day = clock.end_of_day_utc(day)
    water_total = db.scalar(
        select(func.coalesce(func.sum(models.HydrationEntry.amount_ml), 0)).where(
            models.HydrationEntry.profile_id == profile.id,
            models.HydrationEntry.occurred_at >= start_of_day,
            models.HydrationEntry.occurred_at < end_of_day,
        )
    )
    latest_water = db.scalar(
        select(models.HydrationEntry)
        .where(
            models.HydrationEntry.profile_id == profile.id,
            models.HydrationEntry.occurred_at >= start_of_day,
            models.HydrationEntry.occurred_at < end_of_day,
        )
        .order_by(models.HydrationEntry.occurred_at.desc())
    )
    water_target = int(user_setting(db, "water_target_ml", "2000"))
    return {
        "date": day.isoformat(),
        "display_name": profile.display_name,
        "greeting": "Good morning"
        if now_local.hour < 12
        else "Good afternoon"
        if now_local.hour < 18
        else "Good evening",
        "mode": mode_for(day),
        "completion": completion_score(tasks),
        "weekly_consistency": weekly,
        "weight": {
            "current": latest_weight.weight_kg if latest_weight else profile.starting_weight_kg,
            "start": profile.starting_weight_kg,
            "next_milestone": next(
                (
                    value
                    for value in milestones
                    if value
                    < (latest_weight.weight_kg if latest_weight else profile.starting_weight_kg)
                ),
                milestones[-1],
            ),
        },
        "water": {
            "current_ml": water_total,
            "target_ml": water_target,
            "progress": min(100, round(water_total / water_target * 100)),
            "latest_entry_id": latest_water.id if latest_water else None,
            "latest_amount_ml": latest_water.amount_ml if latest_water else None,
        },
        "next_action": next_action(
            tasks,
            day,
            bool(recent_sleep and recent_sleep.minutes_asleep < 360),
            now_local,
        ),
        "tasks": tasks,
        "callouts": generated_callouts(db, day),
        "embedded_default": cfg.embedded_mode,
    }


@app.get("/api/today")
def today(day: date | None = None, db: Session = Depends(db_session)):
    return dashboard_for(db, day or local_today(db))


@app.get("/api/week")
def week(anchor: date | None = None, db: Session = Depends(db_session)):
    anchor = anchor or local_today(db)
    start = anchor - timedelta(days=anchor.weekday())
    days = []
    now_local = UserClock(current_profile(db)).now()
    for offset in range(7):
        current = start + timedelta(days=offset)
        tasks = [
            task_dict(db, x, now_local)
            for x in ensure_tasks(db, current)
        ]
        cats = {
            cat: any(x["category"] == cat and x["state"] == "completed" for x in tasks)
            for cat in ("movement", "hydration", "nutrition", "sleep", "weight")
        }
        days.append(
            {
                "date": current.isoformat(),
                "label": current.strftime("%a"),
                "day": current.day,
                "mode": mode_for(current),
                "completion": completion_score(tasks),
                **cats,
            }
        )
    return {
        "start": start.isoformat(),
        "days": days,
        "summary": "Every completed core habit is evidence that the routine is becoming easier.",
        "suggestion": "Choose one minimum version before the week begins.",
    }


@app.get("/api/progress")
def progress(
    range: str = Query("30", pattern="^(7|30|90|all)$"), db: Session = Depends(db_session)
):
    profile = current_profile(db)
    days = None if range == "all" else int(range)
    cutoff = date.min if days is None else local_today(db) - timedelta(days=days)
    sleeps = list(
        db.scalars(
            select(models.SleepEntry)
            .where(
                models.SleepEntry.profile_id == profile.id,
                models.SleepEntry.sleep_date >= cutoff,
            )
            .order_by(models.SleepEntry.sleep_date)
        )
    )
    exercises = list(
        db.scalars(
            select(models.ExerciseSession)
            .where(
                models.ExerciseSession.profile_id == profile.id,
                models.ExerciseSession.session_date >= cutoff,
            )
            .order_by(models.ExerciseSession.session_date)
        )
    )
    latest_weight = db.scalar(
        select(models.WeightEntry)
        .where(models.WeightEntry.profile_id == profile.id)
        .order_by(models.WeightEntry.entry_date.desc())
    )
    milestones_value = user_setting(db, "weight_milestones", "94,90,88,85")
    milestones = [
        float(value)
        for value in milestones_value.split(",")
        if value.strip()
    ]
    start_weight = profile.starting_weight_kg
    current_weight = latest_weight.weight_kg if latest_weight else start_weight
    goal_weight = min(milestones)
    goal_distance = start_weight - goal_weight
    goal_progress = (
        round(max(0, min(100, (start_weight - current_weight) / goal_distance * 100)))
        if goal_distance > 0
        else 100
    )
    return {
        "weight": weight_series(db, days),
        "weight_goal": {
            "start": start_weight,
            "current": current_weight,
            "goal": goal_weight,
            "change": round(start_weight - current_weight, 1),
            "remaining": round(max(0, current_weight - goal_weight), 1),
            "progress": goal_progress,
            "last_recorded": latest_weight.entry_date.isoformat() if latest_weight else None,
            "milestones": sorted(milestones, reverse=True),
        },
        "sleep": [
            {
                "date": x.sleep_date.isoformat(),
                "hours": round(x.minutes_asleep / 60, 1),
                "quality": x.quality,
            }
            for x in sleeps
        ],
        "exercise": [
            {
                "date": x.session_date.isoformat(),
                "minutes": x.actual_minutes,
                "activity": x.activity,
            }
            for x in exercises
        ],
        "summary": {
            "exercise_minutes": sum(x.actual_minutes for x in exercises),
            "average_sleep": round(sum(x.minutes_asleep for x in sleeps) / 60 / len(sleeps), 1)
            if sleeps
            else 0,
        },
    }


@app.get("/api/plan")
def plan(db: Session = Depends(db_session)):
    profile = current_profile(db)
    habits = list(
        db.scalars(
            select(models.Habit)
            .where(
                models.Habit.profile_id == profile.id,
                models.Habit.archived_at.is_(None),
            )
            .order_by(
                models.Habit.suggested_time.is_(None),
                models.Habit.suggested_time,
                models.Habit.sort_order,
            )
        )
    )
    return [
        {
            "id": x.id,
            "key": x.key,
            "name": x.name,
            "description": x.description,
            "category": x.category,
            "suggested_time": x.suggested_time.strftime("%H:%M") if x.suggested_time else None,
            "required": x.required,
            "minimum_label": x.minimum_label,
            "paused": x.paused,
            "days": [s.weekday for s in x.schedules],
        }
        for x in habits
    ]


@app.put("/api/plan/{habit_id}")
def update_habit(habit_id: int, payload: schemas.HabitUpdateIn, db: Session = Depends(db_session)):
    profile = current_profile(db)
    habit = db.get(models.Habit, habit_id)
    if not habit or habit.profile_id != profile.id or habit.archived_at:
        raise HTTPException(404, "Habit not found")
    changes = payload.model_dump(exclude_unset=True)
    days = changes.pop("days", None)
    for key, value in changes.items():
        setattr(habit, key, value or None if key == "minimum_label" else value)
    if days is not None:
        db.execute(delete(models.HabitSchedule).where(models.HabitSchedule.habit_id == habit_id))
        for weekday in days:
            db.add(models.HabitSchedule(habit_id=habit_id, weekday=weekday))
    audit(db, "update", "habit", habit_id, payload.model_dump(mode="json", exclude_unset=True))
    db.commit()
    return {"ok": True}


@app.post("/api/plan", status_code=201)
def create_habit(payload: schemas.HabitCreateIn, db: Session = Depends(db_session)):
    profile = current_profile(db)
    highest_order = max(
        db.scalars(
            select(models.Habit.sort_order).where(models.Habit.profile_id == profile.id)
        ).all(),
        default=0,
    )
    habit = models.Habit(
        profile_id=profile.id,
        key=f"custom-{uuid4().hex}",
        name=payload.name,
        description=payload.description,
        category=payload.category,
        icon="circle",
        suggested_time=payload.suggested_time,
        required=payload.required,
        minimum_label=payload.minimum_label or None,
        sort_order=highest_order + 10,
        paused=payload.paused,
    )
    db.add(habit)
    db.flush()
    for weekday in payload.days:
        db.add(models.HabitSchedule(habit_id=habit.id, weekday=weekday))
    audit(db, "create", "habit", habit.id, payload.model_dump(mode="json"))
    db.commit()
    return {"ok": True, "id": habit.id}


@app.delete("/api/plan/{habit_id}")
def archive_habit(habit_id: int, db: Session = Depends(db_session)):
    profile = current_profile(db)
    habit = db.get(models.Habit, habit_id)
    if not habit or habit.profile_id != profile.id or habit.archived_at:
        raise HTTPException(404, "Habit not found")
    habit.archived_at = utc_now()
    audit(db, "archive", "habit", habit_id)
    db.commit()
    return {"ok": True}


@app.post("/api/plan/reset")
def reset_plan(db: Session = Depends(db_session)):
    profile = current_profile(db)
    habit_ids = select(models.Habit.id).where(models.Habit.profile_id == profile.id)
    task_ids = select(models.DailyTask.id).where(models.DailyTask.habit_id.in_(habit_ids))
    db.execute(delete(models.TaskCompletion).where(models.TaskCompletion.daily_task_id.in_(task_ids)))
    db.execute(delete(models.DailyTask).where(models.DailyTask.habit_id.in_(habit_ids)))
    db.execute(delete(models.HabitSchedule).where(models.HabitSchedule.habit_id.in_(habit_ids)))
    db.execute(delete(models.Habit).where(models.Habit.profile_id == profile.id))
    db.commit()
    seed_profile(db, profile)
    db.commit()
    return {"ok": True}


@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: int, body: schemas.TaskAction, db: Session = Depends(db_session)):
    profile = current_profile(db)
    task = db.scalar(
        select(models.DailyTask)
        .join(models.Habit)
        .where(models.DailyTask.id == task_id, models.Habit.profile_id == profile.id)
    )
    if not task:
        raise HTTPException(404, "Task not found")
    entry = db.scalar(
        select(models.TaskCompletion).where(models.TaskCompletion.daily_task_id == task_id)
    )
    if not entry:
        entry = models.TaskCompletion(daily_task_id=task_id)
        db.add(entry)
    entry.state = "completed"
    entry.minimum_version = body.minimum_version
    entry.numeric_value = body.numeric_value
    entry.notes = body.notes
    entry.completed_at = utc_now()
    entry.user_local_date = task.task_date
    entry.timezone_at_completion = UserClock(profile).timezone_name
    audit(db, "complete", "task", task_id, body.model_dump())
    db.commit()
    return {"ok": True, "state": "completed", "minimum_version": entry.minimum_version}


@app.post("/api/tasks/{task_id}/skip")
def skip_task(task_id: int, db: Session = Depends(db_session)):
    profile = current_profile(db)
    task = db.scalar(
        select(models.DailyTask)
        .join(models.Habit)
        .where(models.DailyTask.id == task_id, models.Habit.profile_id == profile.id)
    )
    if not task:
        raise HTTPException(404, "Task not found")
    entry = db.scalar(
        select(models.TaskCompletion).where(models.TaskCompletion.daily_task_id == task_id)
    ) or models.TaskCompletion(daily_task_id=task_id)
    entry.state = "skipped"
    entry.user_local_date = task.task_date
    entry.timezone_at_completion = UserClock(profile).timezone_name
    db.add(entry)
    audit(db, "skip", "task", task_id)
    db.commit()
    return {"ok": True}


@app.delete("/api/tasks/{task_id}/completion")
def undo_task(task_id: int, db: Session = Depends(db_session)):
    profile = current_profile(db)
    task = db.scalar(
        select(models.DailyTask)
        .join(models.Habit)
        .where(models.DailyTask.id == task_id, models.Habit.profile_id == profile.id)
    )
    if not task:
        raise HTTPException(404, "Task not found")
    db.execute(delete(models.TaskCompletion).where(models.TaskCompletion.daily_task_id == task_id))
    audit(db, "undo", "task", task_id)
    db.commit()
    return {"ok": True}


def upsert_unique(db, model, key, value, body):
    profile = current_profile(db)
    entry = db.scalar(
        select(model).where(
            model.profile_id == profile.id,
            getattr(model, key) == value,
        )
    )
    if entry:
        for k, v in body.model_dump().items():
            setattr(entry, k, v)
    else:
        entry = model(profile_id=profile.id, **body.model_dump())
        db.add(entry)
    db.commit()
    db.refresh(entry)
    return {"id": entry.id, "ok": True}


@app.post("/api/exercise")
def exercise(body: schemas.ExerciseIn, db: Session = Depends(db_session)):
    profile = current_profile(db)
    entry = models.ExerciseSession(
        profile_id=profile.id,
        **body.model_dump(),
        started_at=utc_now(),
        completed_at=utc_now() if body.status == "completed" else None,
    )
    db.add(entry)
    db.commit()
    return {"id": entry.id, "ok": True}


@app.post("/api/sleep")
def sleep(body: schemas.SleepIn, db: Session = Depends(db_session)):
    return upsert_unique(db, models.SleepEntry, "sleep_date", body.sleep_date, body)


@app.post("/api/weight")
def weight(body: schemas.WeightIn, db: Session = Depends(db_session)):
    return upsert_unique(db, models.WeightEntry, "entry_date", body.entry_date, body)


@app.put("/api/weight/{entry_id}")
def update_weight(entry_id: int, body: schemas.WeightIn, db: Session = Depends(db_session)):
    profile = current_profile(db)
    entry = db.get(models.WeightEntry, entry_id)
    if not entry or entry.profile_id != profile.id:
        raise HTTPException(404, "Weight entry not found")
    duplicate = db.scalar(
        select(models.WeightEntry).where(
            models.WeightEntry.entry_date == body.entry_date,
            models.WeightEntry.profile_id == profile.id,
            models.WeightEntry.id != entry_id,
        )
    )
    if duplicate:
        raise HTTPException(409, "A weight entry already exists for that date")
    for key, value in body.model_dump().items():
        setattr(entry, key, value)
    audit(db, "update", "weight", entry_id, body.model_dump(mode="json"))
    db.commit()
    return {"id": entry.id, "ok": True}


@app.delete("/api/weight/{entry_id}")
def delete_weight(entry_id: int, db: Session = Depends(db_session)):
    profile = current_profile(db)
    entry = db.get(models.WeightEntry, entry_id)
    if not entry or entry.profile_id != profile.id:
        raise HTTPException(404, "Weight entry not found")
    db.delete(entry)
    audit(db, "delete", "weight", entry_id)
    db.commit()
    return {"ok": True}


@app.post("/api/hydration")
def hydration(body: schemas.HydrationIn, db: Session = Depends(db_session)):
    profile = current_profile(db)
    entry = models.HydrationEntry(profile_id=profile.id, amount_ml=body.amount_ml)
    db.add(entry)
    db.commit()
    return {"id": entry.id, "ok": True}


@app.delete("/api/hydration/{entry_id}")
def delete_hydration(entry_id: int, db: Session = Depends(db_session)):
    profile = current_profile(db)
    entry = db.get(models.HydrationEntry, entry_id)
    if not entry or entry.profile_id != profile.id:
        raise HTTPException(404, "Water entry not found")
    db.delete(entry)
    db.commit()
    return {"ok": True}


@app.post("/api/caffeine")
def caffeine(body: schemas.CaffeineIn, db: Session = Depends(db_session)):
    profile = current_profile(db)
    entry = models.CaffeineEntry(profile_id=profile.id, **body.model_dump())
    db.add(entry)
    db.commit()
    cutoff = user_setting(db, "caffeine_cutoff", "14:00")
    return {
        "id": entry.id,
        "ok": True,
        "after_cutoff": entry.occurred_at.astimezone(ZoneInfo(app_timezone(db))).strftime("%H:%M")
        > cutoff,
        "message": "Late caffeine may make sleep harder, but it does not undo your day.",
    }


@app.post("/api/alcohol")
def alcohol(body: schemas.AlcoholIn, db: Session = Depends(db_session)):
    profile = current_profile(db)
    entry = models.AlcoholEntry(profile_id=profile.id, **body.model_dump())
    db.add(entry)
    db.commit()
    return {
        "id": entry.id,
        "ok": True,
        "safety": "Choose a sober ride, designated driver, or stay in place."
        if body.plans_to_drive
        else None,
    }


@app.post("/api/meals/check-in")
def meal(body: schemas.MealIn, db: Session = Depends(db_session)):
    profile = current_profile(db)
    entry = models.MealCheckin(profile_id=profile.id, **body.model_dump())
    db.add(entry)
    db.commit()
    return {"id": entry.id, "ok": True}


@app.get("/api/meals/suggestion")
def meal_suggestion(meal: str | None = None, db: Session = Depends(db_session)):
    hour = UserClock(current_profile(db)).now().hour
    meal = meal or ("breakfast" if hour < 11 else "lunch" if hour < 16 else "dinner")
    options = {
        "breakfast": ["Greek yogurt, berries, and nuts", "Protein shake and banana"],
        "lunch": ["Mediterranean chicken bowl", "Burrito bowl with extra vegetables"],
        "dinner": [
            "Rotisserie chicken and salad",
            "Chicken with microwave rice and frozen vegetables",
        ],
        "snack": ["Fruit and Greek yogurt", "A small handful of nuts"],
    }
    return {
        "meal": meal,
        "suggestion": options.get(meal, options["dinner"])[local_today(db).day % 2],
    }


@app.get("/api/callouts")
def callouts(db: Session = Depends(db_session)):
    return generated_callouts(db, local_today(db))


@app.post("/api/callouts/{callout_id}/dismiss")
def dismiss(callout_id: str, db: Session = Depends(db_session)):
    profile = current_profile(db)
    stored = db.scalar(select(models.Callout).where(models.Callout.key == callout_id))
    if stored:
        db.add(models.CalloutDismissal(profile_id=profile.id, callout_id=stored.id))
        db.commit()
    return {"ok": True}


@app.get("/api/settings")
def settings(db: Session = Depends(db_session)):
    profile = current_profile(db)
    values = {
        x.key: x.value
        for x in db.scalars(
            select(models.UserSetting).where(models.UserSetting.profile_id == profile.id)
        )
    }
    milestones = [
        float(value)
        for value in values.get("weight_milestones", "94,90,88,85").split(",")
        if value.strip()
    ]
    identities = list(
        db.scalars(
            select(models.UserIdentity).where(models.UserIdentity.user_id == profile.id)
        )
    )
    ha_identity = next(
        (identity for identity in identities if identity.provider == "home_assistant"), None
    )
    clock = UserClock(profile)
    travel_active = clock.timezone_name != profile.timezone
    return {
        "display_name": profile.display_name,
        "starting_weight_kg": profile.starting_weight_kg,
        "timezone": profile.timezone,
        "caffeine_cutoff": values.get("caffeine_cutoff", "14:00"),
        "water_target_ml": int(values.get("water_target_ml", "2000")),
        "weight_milestones": milestones,
        "notification_target": values.get("notification_target", ""),
        "quiet_hours_start": values.get("quiet_hours_start", "22:30"),
        "quiet_hours_end": values.get("quiet_hours_end", "07:00"),
        "timezone_mismatch_alerts": values.get("timezone_mismatch_alerts", "true")
        == "true",
        "friday_reminders": values.get("friday_reminders", "gentle"),
        "saturday_reminders": values.get("saturday_reminders", "gentle"),
        "reminders_paused": values.get("reminders_paused", "false") == "true",
        "urgent_bypasses_quiet_hours": values.get(
            "urgent_bypasses_quiet_hours", "false"
        )
        == "true",
        "active_timezone": clock.timezone_name,
        "temporary_timezone": profile.temporary_timezone if travel_active else None,
        "temporary_timezone_expires_at": (
            profile.temporary_timezone_expires_at.isoformat()
            if travel_active and profile.temporary_timezone_expires_at
            else None
        ),
        "timezone_source": profile.timezone_source,
        "timezone_confirmed": bool(profile.timezone_confirmed_at),
        "pin_configured": bool(profile.pin_hash),
        "sign_in_methods": [identity.provider for identity in identities],
        "home_assistant_display_name": (
            ha_identity.provider_display_name if ha_identity else None
        ),
        "photo_uploads_enabled": cfg.photo_uploads_enabled,
    }


@app.put("/api/settings")
def save_settings(body: schemas.AppSettingsIn, db: Session = Depends(db_session)):
    profile = current_profile(db)
    profile.display_name = body.display_name.strip()
    if body.starting_weight_kg is not None:
        profile.starting_weight_kg = body.starting_weight_kg
    if profile.timezone != body.timezone or not profile.timezone_confirmed_at:
        profile.timezone = body.timezone
        profile.timezone_source = "user_selected"
        profile.timezone_confirmed_at = utc_now()
        profile.temporary_timezone = None
        profile.temporary_timezone_expires_at = None
        recalculate_user_reminders(db, profile)
    values = {
        "caffeine_cutoff": body.caffeine_cutoff.strftime("%H:%M"),
        "water_target_ml": str(body.water_target_ml),
        "weight_milestones": ",".join(f"{value:g}" for value in body.weight_milestones),
        "notification_target": body.notification_target.strip(),
        "quiet_hours_start": (
            body.quiet_hours_start.strftime("%H:%M") if body.quiet_hours_start else ""
        ),
        "quiet_hours_end": (
            body.quiet_hours_end.strftime("%H:%M") if body.quiet_hours_end else ""
        ),
        "timezone_mismatch_alerts": str(body.timezone_mismatch_alerts).lower(),
        "friday_reminders": body.friday_reminders,
        "saturday_reminders": body.saturday_reminders,
        "reminders_paused": str(body.reminders_paused).lower(),
        "urgent_bypasses_quiet_hours": str(
            body.urgent_bypasses_quiet_hours
        ).lower(),
    }
    for key, value in values.items():
        item = db.get(models.UserSetting, (profile.id, key)) or models.UserSetting(
            profile_id=profile.id, key=key, value=""
        )
        item.value = value
        db.add(item)
    recalculate_user_reminders(db, profile)
    audit(db, "update", "settings", None, {"keys": list(values)})
    db.commit()
    return {"ok": True, "message": "Settings saved"}


@app.put("/api/timezone/travel")
def enable_travel_timezone(
    body: schemas.TravelTimezoneIn, db: Session = Depends(db_session)
):
    profile = current_profile(db)
    expires = body.expires_at
    if expires.tzinfo is None:
        raise HTTPException(422, "Travel timezone expiration must include an offset")
    if expires <= utc_now() or expires > utc_now() + timedelta(days=90):
        raise HTTPException(422, "Travel timezone must expire within 90 days")
    profile.temporary_timezone = body.timezone
    profile.temporary_timezone_expires_at = expires
    recalculate_user_reminders(db, profile)
    db.commit()
    return {"ok": True, "message": "Travel timezone enabled"}


@app.delete("/api/timezone/travel")
def disable_travel_timezone(db: Session = Depends(db_session)):
    profile = current_profile(db)
    profile.temporary_timezone = None
    profile.temporary_timezone_expires_at = None
    recalculate_user_reminders(db, profile)
    db.commit()
    return {"ok": True, "message": "Returned to your home timezone"}


@app.delete("/api/auth/pin")
def disable_pin(db: Session = Depends(db_session)):
    profile = current_profile(db)
    ha_identity = db.scalar(
        select(models.UserIdentity).where(
            models.UserIdentity.user_id == profile.id,
            models.UserIdentity.provider == "home_assistant",
        )
    )
    if not ha_identity:
        raise HTTPException(400, "PIN access cannot be disabled without another sign-in method")
    profile.pin_hash = None
    db.execute(
        delete(models.UserIdentity).where(
            models.UserIdentity.user_id == profile.id,
            models.UserIdentity.provider == "pin",
        )
    )
    db.commit()
    return {"ok": True, "message": "Standalone PIN disabled"}


def delete_user_data(db: Session, profile: models.Profile) -> None:
    habit_ids = select(models.Habit.id).where(models.Habit.profile_id == profile.id)
    task_ids = select(models.DailyTask.id).where(models.DailyTask.habit_id.in_(habit_ids))
    rule_ids = select(models.ReminderRule.id).where(models.ReminderRule.profile_id == profile.id)
    db.execute(delete(models.NotificationDelivery).where(models.NotificationDelivery.rule_id.in_(rule_ids)))
    db.execute(delete(models.TaskCompletion).where(models.TaskCompletion.daily_task_id.in_(task_ids)))
    db.execute(delete(models.DailyTask).where(models.DailyTask.habit_id.in_(habit_ids)))
    db.execute(delete(models.HabitSchedule).where(models.HabitSchedule.habit_id.in_(habit_ids)))
    db.execute(delete(models.Habit).where(models.Habit.profile_id == profile.id))
    for model in (
        models.ExerciseSession,
        models.MealCheckin,
        models.HydrationEntry,
        models.CaffeineEntry,
        models.AlcoholEntry,
        models.SleepEntry,
        models.WeightEntry,
        models.CalloutDismissal,
        models.UserSetting,
        models.ReminderRule,
        models.ExternalEntityMapping,
        models.AuditEvent,
        models.UserIdentity,
    ):
        column = model.user_id if model is models.UserIdentity else model.profile_id
        db.execute(delete(model).where(column == profile.id))
    db.delete(profile)


@app.delete("/api/account")
def delete_account(response: Response, db: Session = Depends(db_session)):
    profile = current_profile(db)
    delete_user_data(db, profile)
    db.commit()
    response.delete_cookie("health_session")
    response.delete_cookie("health_csrf")
    return {"ok": True}


@app.post("/api/integration/test")
async def integration_test():
    if not cfg.integration_enabled or not cfg.integration_token:
        raise HTTPException(503, "External sensor integration is not configured")
    async with httpx.AsyncClient(verify=cfg.integration_verify_ssl, timeout=8) as client:
        response = await client.get(
            f"{cfg.integration_base_url.rstrip('/')}/api/",
            headers={"Authorization": f"Bearer {cfg.integration_token}"},
        )
    if response.status_code != 200:
        raise HTTPException(502, "External sensor connection failed")
    return {"ok": True, "message": "Connected to external sensor service"}


@app.get("/api/integration/entities")
async def integration_entities():
    if not cfg.integration_enabled or not cfg.integration_token:
        return []
    async with httpx.AsyncClient(verify=cfg.integration_verify_ssl, timeout=8) as client:
        response = await client.get(
            f"{cfg.integration_base_url.rstrip('/')}/api/states",
            headers={"Authorization": f"Bearer {cfg.integration_token}"},
        )
    if response.status_code != 200:
        raise HTTPException(502, "Could not retrieve external sensor entities")
    return [
        {
            "entity_id": x.get("entity_id"),
            "state": x.get("state"),
            "name": x.get("attributes", {}).get("friendly_name"),
        }
        for x in response.json()
        if x.get("entity_id", "").startswith("sensor.")
    ]


@app.get("/api/export/json")
def export_json(db: Session = Depends(db_session)):
    profile = current_profile(db)
    tables = [
        models.ExerciseSession,
        models.SleepEntry,
        models.WeightEntry,
        models.HydrationEntry,
        models.TaskCompletion,
    ]
    data = {
        model.__tablename__: [
            {
                c.name: (v.isoformat() if hasattr(v, "isoformat") else v)
                for c in model.__table__.columns
                if (v := getattr(row, c.name)) is not None
            }
            for row in db.scalars(
                select(model).where(model.profile_id == profile.id)
                if hasattr(model, "profile_id")
                else select(model)
                .join(models.DailyTask)
                .join(models.Habit)
                .where(models.Habit.profile_id == profile.id)
            )
        ]
        for model in tables
    }
    return JSONResponse(
        content=data,
        headers={
            "Content-Disposition": 'attachment; filename="health-os-data.json"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/export/{kind}.csv")
def export_csv(kind: str, db: Session = Depends(db_session)):
    profile = current_profile(db)
    choices = {
        "weight": models.WeightEntry,
        "sleep": models.SleepEntry,
        "exercise": models.ExerciseSession,
        "habits": models.TaskCompletion,
    }
    model = choices.get(kind)
    if not model:
        raise HTTPException(404, "Unknown export")
    out = io.StringIO()
    columns = [x.name for x in model.__table__.columns]
    writer = csv.writer(out)
    writer.writerow(columns)
    query = (
        select(model).where(model.profile_id == profile.id)
        if hasattr(model, "profile_id")
        else select(model)
        .join(models.DailyTask)
        .join(models.Habit)
        .where(models.Habit.profile_id == profile.id)
    )
    for row in db.scalars(query):
        writer.writerow([getattr(row, x) for x in columns])
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="health-os-{kind}.csv"'},
    )


@app.post("/api/backup")
def backup():
    target = create_backup()
    if not target:
        raise HTTPException(
            400, "Automatic file backup is available for an existing SQLite database"
        )
    return {"ok": True, "filename": target.name}


frontend_root = Path(__file__).parent.parent / "frontend"
frontend = frontend_root / "dist"
docs_assets = frontend / "docs-assets"
if not docs_assets.exists():
    docs_assets = frontend_root / "public" / "docs-assets"

if docs_assets.exists():
    app.mount("/docs-assets", StaticFiles(directory=docs_assets), name="docs-assets")


@app.get("/docs", include_in_schema=False)
def openapi_docs():
    return HTMLResponse(
        """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Health OS API · API documentation</title>
    <link rel="icon" href="./docs-assets/favicon-32x32.png">
    <link rel="stylesheet" href="./docs-assets/swagger-ui.css">
  </head>
  <body>
    <div id="swagger-ui"></div>
    <script src="./docs-assets/swagger-ui-bundle.js"></script>
    <script src="./docs-assets/swagger-init.js"></script>
  </body>
</html>"""
    )


@app.api_route(
    "/api/{unknown_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
def unknown_api_route(unknown_path: str):
    raise HTTPException(404, "API route not found")


if frontend.exists():
    app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        return FileResponse(frontend / "index.html")
