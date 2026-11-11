from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from shared.auth.panel_sessions import (
    PANEL_COOKIE,
    SESSION_TTL_SECONDS,
    consume_login_token,
    create_session,
    get_panel_user,
    require_panel_user,
    revoke_session,
)
from shared.auth.authority import get_authority, has_authority
from shared.config.settings import ENV
from DB.asyncsessions import session_factory
from DB.models.reports import Report
from DB.repo.admin_repo import AdminRepo
from DB.repo.report_repo import ReportRepo
from DB.repo.user_repo import UserRepo
from bot.services.reports.workflow import deliver_reply

router = APIRouter(tags=["admin-panel"])


def _safe_next(value: str | None) -> str:
    if not value or not value.startswith("/admin/") or value.startswith("//"):
        return "/admin/"
    return value


def _user_payload(user) -> dict:
    return {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "display_name": user.display_name,
        "banned": user.banned,
    }


def _report_payload(row: Report) -> dict:
    return {
        "id": row.id,
        "reporter_id": row.reporter_id,
        "report_type": row.report_type,
        "uid": row.uid,
        "status": row.status,
        "origin_chat_id": row.origin_chat_id,
        "origin_message_id": row.origin_message_id,
        "assigned_to": row.assigned_to,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
    }


@router.get("/admin/login")
async def admin_login(token: str, next: str | None = None):
    telegram_id = await consume_login_token(token)
    target = _safe_next(next)
    if not telegram_id:
        return RedirectResponse(f"/admin/login-required?error=login_expired&next={target}", status_code=303)

    async with session_factory() as session:
        user = await UserRepo(session).get_by_tele_id(telegram_id)
        authority = await get_authority(session, telegram_id)
    if not user or not authority:
        return RedirectResponse("/admin/login-required?error=forbidden", status_code=303)

    cookie_value = await create_session(telegram_id)
    response = RedirectResponse(target, status_code=303)
    response.set_cookie(
        PANEL_COOKIE,
        cookie_value,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=ENV == "prod",
        samesite="lax",
        path="/admin",
    )
    return response


@router.post("/admin/api/logout")
async def admin_logout(request: Request):
    token = request.cookies.get(PANEL_COOKIE) or ""
    await revoke_session(token)
    response = RedirectResponse("/admin/login-required?error=signed_out", status_code=303)
    response.delete_cookie(PANEL_COOKIE, path="/admin")
    return response


@router.get("/admin/api/me")
async def admin_me(request: Request):
    user = await get_panel_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    return {"user": user}


@router.get("/admin/api/summary")
async def admin_summary(request: Request):
    user = await require_panel_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")

    async with session_factory() as session:
        open_count = await session.scalar(
            select(func.count()).select_from(Report).where(Report.status.in_(["open", "claimed"]))
        )
        report_count = await session.scalar(select(func.count()).select_from(Report))
        users = await UserRepo(session).count_users()
        admins = await AdminRepo(session).get_all_admins()

    return {
        "user": user,
        "reports": {"open": int(open_count or 0), "total": int(report_count or 0)},
        "users": users,
        "admins": len(admins) if has_authority(user["authority"], "admin") else None,
        "capabilities": {
            "reports": True,
            "users": has_authority(user["authority"], "admin"),
            "admins": has_authority(user["authority"], "owner"),
        },
    }


@router.get("/admin/api/reports")
async def admin_reports(request: Request, status: str = "open", limit: int = 50):
    user = await require_panel_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    limit = max(1, min(limit, 200))

    async with session_factory() as session:
        repo = ReportRepo(session)
        if status in {"open", "claimed"}:
            rows = await repo.list_open(limit)
        else:
            query = select(Report).order_by(Report.created_at.desc()).limit(limit)
            if status and status != "all":
                query = query.where(Report.status == status)
            rows = (await session.execute(query)).scalars().all()

    return {"reports": [_report_payload(row) for row in rows]}


@router.get("/admin/api/reports/{report_id}")
async def admin_report_detail(report_id: int, request: Request):
    user = await require_panel_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")

    async with session_factory() as session:
        report = await ReportRepo(session).get_with_timeline(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="report not found")
        reporter = await UserRepo(session).get_by_tele_id(report.reporter_id)
        return {
            "report": _report_payload(report),
            "reporter": _user_payload(reporter) if reporter else None,
            "messages": [
                {
                    "id": item.id,
                    "author_id": item.author_id,
                    "direction": item.direction,
                    "body": item.body,
                    "delivered": item.delivered,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in report.messages
            ],
            "events": [
                {
                    "id": item.id,
                    "actor_id": item.actor_id,
                    "event": item.event,
                    "detail": item.detail,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in report.events
            ],
        }


class ReplyBody(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


@router.post("/admin/api/reports/{report_id}/reply")
async def admin_report_reply(report_id: int, body: ReplyBody, request: Request):
    user = await require_panel_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")

    async with session_factory() as session:
        repo = ReportRepo(session)
        report = await repo.get(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="report not found")
        if report.status in {"resolved", "closed"}:
            raise HTTPException(status_code=409, detail=f"report is already {report.status}")
        delivered = await deliver_reply(
            session,
            request.app.state.bot,
            report,
            user["telegram_id"],
            body.body,
        )
        await session.commit()

    return {"ok": True, "delivered": delivered}


@router.post("/admin/api/reports/{report_id}/resolve")
async def admin_report_resolve(report_id: int, request: Request):
    user = await require_panel_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")

    async with session_factory() as session:
        repo = ReportRepo(session)
        report = await repo.get(report_id)
        if not report:
            raise HTTPException(status_code=404, detail="report not found")
        await repo.resolve(report, user["telegram_id"])
        await session.commit()

    return {"ok": True}


@router.get("/admin/api/users")
async def admin_users(request: Request, page: int = 0, per_page: int = 25):
    user = await require_panel_user(request, "admin")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")

    per_page = max(1, min(per_page, 100))
    page = max(0, page)

    async with session_factory() as session:
        repo = UserRepo(session)
        page_users = await repo.get_page(page, per_page=per_page)
        total = await repo.count_users()
        return {
            "users": [_user_payload(row) for row in page_users],
            "page": page,
            "per_page": per_page,
            "total": total,
        }


@router.get("/admin/api/admins")
async def admin_admins(request: Request):
    user = await require_panel_user(request, "owner")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")

    async with session_factory() as session:
        admins = await AdminRepo(session).get_all_admins()
        return {
            "admins": [
                {
                    "telegram_id": row.telegram_id,
                    "username": row.username,
                    "display_name": row.display_name,
                    "authority": row.authority,
                }
                for row in admins
            ]
        }


class AuthorityBody(BaseModel):
    authority: str


@router.post("/admin/api/admins/{telegram_id}/authority")
async def admin_set_authority(telegram_id: int, body: AuthorityBody, request: Request):
    user = await require_panel_user(request, "owner")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    if body.authority not in {"basic", "moderator", "admin", "owner"}:
        raise HTTPException(status_code=422, detail="invalid authority")
    if body.authority == "owner":
        raise HTTPException(
            status_code=403,
            detail="owner authority is reserved for OWNER_TELE_ID",
        )

    async with session_factory() as session:
        repo = AdminRepo(session)
        existing = await repo.get_admin(telegram_id)
        if not existing:
            raise HTTPException(status_code=404, detail="admin not found")
        if existing.authority == "owner":
            raise HTTPException(
                status_code=403,
                detail="the owner row can only be changed by the owner bot command",
            )
        await repo.update_admin(telegram_id, body.authority)
        await session.commit()

    return {"ok": True}

# Static files are served only after the caller has a valid panel session,
# except for the login shell itself. The shell contains no data.
@router.get("/admin/")
@router.get("/admin")
async def admin_index(request: Request):
    if not await get_panel_user(request):
        return RedirectResponse("/admin/login-required", status_code=303)
    return FileResponse(_static_path("index.html"))


@router.get("/admin/login-required")
async def admin_login_required():
    return FileResponse(_static_path("login.html"))


@router.get("/admin/static/{filename}")
async def admin_static(filename: str):
    if filename not in {"panel.css", "panel.js", "login.js", "login.html"}:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(_static_path(filename))


def _static_path(filename: str):
    from pathlib import Path

    return Path(__file__).resolve().parent / "static" / filename