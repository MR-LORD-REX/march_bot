from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
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
from shared.config.settings import ADMIN_GC_ID, ENV, OWNER_TELE_ID
from shared.i18n import available_languages
from server.admin.panel.broadcast import AUDIENCES, enqueue, validate_html
from server.admin.panel.commands import (
    ADMIN_COMMANDS,
    DEFAULT_SCOPES,
    PUBLIC_COMMANDS,
    current_state,
    set_command_state,
    sync_all_menus,
)
from DB.asyncsessions import session_factory
from DB.models.broadcast import Broadcast
from DB.models.reports import Report
from DB.models.tele_group import TeleGroup
from DB.repo.admin_repo import AdminRepo
from DB.repo.broadcast_repo import BroadcastRepo
from DB.repo.cmd_meta_repo import CommandMetaRepo
from DB.repo.game_ids_repo import GameIDs_repo
from DB.repo.report_repo import ReportRepo
from DB.repo.user_repo import UserRepo
from DB.repo.user_setting_repo import UserSettingsRepo
from bot.services.reports.workflow import deliver_reply

router = APIRouter(tags=["admin-panel"])

_ASSET_ROOT = Path(__file__).resolve().parents[3] / "bot" / "assets"
_ASSET_RE = re.compile(r"^[a-z0-9][a-z0-9_./-]*$", re.IGNORECASE)
_ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm"}
_ASSET_MAX_BYTES = 12 * 1024 * 1024


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
        "warns": getattr(user, "warns", 0),
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


def _broadcast_payload(row) -> dict:
    return {
        "id": row.id,
        "created_by": row.created_by,
        "audience": row.audience,
        "body": row.body,
        "parse_mode": row.parse_mode,
        "status": row.status,
        "total_targets": row.total_targets,
        "sent_count": row.sent_count,
        "failed_count": row.failed_count,
        "last_error": row.last_error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


def _settings_payload(settings) -> dict:
    if not settings:
        return {"lang": "en"}
    return {
        "profile_template": settings.profile_template,
        "character_template": settings.character_template,
        "lang": settings.lang or "en",
        "dalies_reminder": settings.dalies_reminder,
        "weekly_reminder": settings.weekly_reminder,
        "perform_daily": settings.perform_daily,
        "benchmark": settings.benchmark,
    }


def _asset_path(relative: str) -> Path:
    if not relative or not _ASSET_RE.fullmatch(relative) or ".." in Path(relative).parts:
        raise HTTPException(status_code=400, detail="invalid asset path")
    root = _ASSET_ROOT.resolve()
    candidate = (root / relative).resolve()
    if root != candidate and root not in candidate.parents:
        raise HTTPException(status_code=400, detail="invalid asset path")
    if candidate.suffix.lower() not in _ASSET_EXTENSIONS:
        raise HTTPException(status_code=415, detail="unsupported asset type")
    return candidate


def _public_capabilities(authority: str) -> dict:
    admin = has_authority(authority, "admin")
    owner = has_authority(authority, "owner")
    return {
        "reports": True,
        "users": admin,
        "admins": owner,
        "broadcast": admin,
        "commands": owner,
        "assets": owner,
        "languages": True,
    }


@router.get("/admin/login")
async def admin_login(token: str, next: str | None = None):
    telegram_id = await consume_login_token(token)
    target = _safe_next(next)
    if not telegram_id:
        return RedirectResponse(
            f"/admin/login-required?error=login_expired&next={target}",
            status_code=303,
        )

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
    return {"user": user, "capabilities": _public_capabilities(user["authority"])}


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
        groups = await session.scalar(select(func.count()).select_from(TeleGroup))
        broadcasts = await session.scalar(select(func.count()).select_from(Broadcast))

    return {
        "user": user,
        "reports": {"open": int(open_count or 0), "total": int(report_count or 0)},
        "users": users,
        "groups": int(groups or 0),
        "broadcasts": int(broadcasts or 0),
        "admins": len(admins) if has_authority(user["authority"], "admin") else None,
        "capabilities": _public_capabilities(user["authority"]),
        "languages": available_languages(),
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


class ModerationBody(BaseModel):
    reason: str = Field(default="", max_length=500)


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


@router.get("/admin/api/users/{telegram_id}")
async def admin_user_detail(telegram_id: int, request: Request):
    """Rich user view; sensitive game auth tokens are never returned."""
    user = await require_panel_user(request, "moderator")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")

    async with session_factory() as session:
        row = await UserRepo(session).get_by_tele_id(telegram_id)
        if not row:
            raise HTTPException(status_code=404, detail="user not found")
        settings = await UserSettingsRepo(session).get_user_settings(telegram_id)
        game_ids = await GameIDs_repo(session).get_UIDs(telegram_id)
        groups = await UserRepo(session).get_groups(telegram_id)
        reports = (
            await session.execute(
                select(Report)
                .where(Report.reporter_id == telegram_id)
                .order_by(Report.created_at.desc())
                .limit(10)
            )
        ).scalars().all()
        admin = await AdminRepo(session).get_admin(telegram_id)
        return {
            "user": _user_payload(row),
            "settings": _settings_payload(settings),
            "game_ids": [
                {
                    "game_id": item.game_id,
                    "active": item.active,
                    "has_token": bool(item.auth_token),
                }
                for item in game_ids
            ],
            "groups": [
                {
                    "group_id": item.group.group_id if item.group else item.group_id,
                    "group_name": item.group.group_name if item.group else None,
                }
                for item in groups
            ],
            "reports": [_report_payload(item) for item in reports],
            "staff": (
                {"authority": admin.authority, "is_owner_override": telegram_id == OWNER_TELE_ID}
                if admin or telegram_id == OWNER_TELE_ID
                else None
            ),
            "capabilities": {
                "ban": has_authority(user["authority"], "admin"),
                "warn": has_authority(user["authority"], "moderator"),
                "unwarn": has_authority(user["authority"], "moderator"),
                "reset_warns": has_authority(user["authority"], "admin"),
                "set_language": has_authority(user["authority"], "admin"),
                "authority": has_authority(user["authority"], "owner") and telegram_id != OWNER_TELE_ID,
            },
            "languages": available_languages(),
        }


class UserActionBody(BaseModel):
    action: str = Field(pattern="^(ban|unban|warn|unwarn|reset_warns|set_language)$")
    value: str | int | None = None


@router.post("/admin/api/users/{telegram_id}/action")
async def admin_user_action(telegram_id: int, body: UserActionBody, request: Request):
    user = await require_panel_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    if telegram_id == OWNER_TELE_ID and body.action in {"ban", "unban"}:
        raise HTTPException(status_code=403, detail="the owner account cannot be moderated here")

    if not has_authority(user["authority"], "admin"):
        raise HTTPException(status_code=403, detail="insufficient authority")

    async with session_factory() as session:
        repo = UserRepo(session)
        target = await repo.get_by_tele_id(telegram_id)
        if not target:
            raise HTTPException(status_code=404, detail="user not found")
        if body.action == "ban":
            target.banned = True
        elif body.action == "unban":
            target.banned = False
        elif body.action == "warn":
            target.warns = (target.warns or 0) + 1
        elif body.action == "unwarn":
            target.warns = max(0, (target.warns or 0) - 1)
        elif body.action == "reset_warns":
            target.warns = 0
        elif body.action == "set_language":
            language = str(body.value or "").lower()
            if language not in available_languages():
                raise HTTPException(status_code=422, detail="unsupported language")
            await UserSettingsRepo(session).change_user_settings(telegram_id, lang=language)
        await session.commit()

    return {"ok": True}


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


class BroadcastBody(BaseModel):
    audience: str = Field(pattern="^(groups|users|all)$")
    body: str = Field(min_length=1, max_length=4000)
    parse_mode: str | None = Field(default=None, pattern="^(HTML|Markdown|MarkdownV2)?$")


@router.get("/admin/api/broadcasts")
async def admin_broadcasts(request: Request, limit: int = 50):
    user = await require_panel_user(request, "admin")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    async with session_factory() as session:
        rows = await BroadcastRepo(session).list(limit)
        counts = {}
        counts["groups"] = int(
            await session.scalar(select(func.count()).select_from(TeleGroup)) or 0
        )
        counts["users"] = int(
            await session.scalar(select(func.count()).select_from(UserRepo(session).model)) or 0
        )
        counts["all"] = counts["groups"] + counts["users"]
    return {
        "broadcasts": [_broadcast_payload(row) for row in rows],
        "audiences": [
            {"value": "groups", "label": "All registered groups", "count": counts["groups"]},
            {"value": "users", "label": "All registered users", "count": counts["users"]},
            {"value": "all", "label": "Users and groups", "count": counts["all"]},
        ],
        "parse_modes": ["plain", "HTML"],
    }


@router.post("/admin/api/broadcasts")
async def admin_broadcast_create(body: BroadcastBody, request: Request):
    user = await require_panel_user(request, "admin")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    if body.audience not in AUDIENCES:
        raise HTTPException(status_code=422, detail="invalid audience")
    parse_mode = body.parse_mode if body.parse_mode in {"HTML", "Markdown", "MarkdownV2"} else None
    if parse_mode == "HTML":
        problem = validate_html(body.body)
        if problem:
            raise HTTPException(status_code=422, detail=f"invalid Telegram HTML: {problem}")
    async with session_factory() as session:
        row = await BroadcastRepo(session).create(
            user["telegram_id"], body.audience, body.body, parse_mode
        )
        await session.commit()
        broadcast_id = row.id
    await enqueue(broadcast_id, request.app.state.bot)
    return {"ok": True, "id": broadcast_id, "status": "queued"}


@router.get("/admin/api/broadcasts/{broadcast_id}")
async def admin_broadcast_detail(broadcast_id: int, request: Request):
    user = await require_panel_user(request, "admin")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    async with session_factory() as session:
        row = await BroadcastRepo(session).get(broadcast_id)
        if not row:
            raise HTTPException(status_code=404, detail="broadcast not found")
        return {"broadcast": _broadcast_payload(row)}


@router.post("/admin/api/broadcasts/{broadcast_id}/retry")
async def admin_broadcast_retry(broadcast_id: int, request: Request):
    user = await require_panel_user(request, "admin")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    async with session_factory() as session:
        row = await BroadcastRepo(session).get(broadcast_id)
        if not row:
            raise HTTPException(status_code=404, detail="broadcast not found")
        if row.status in {"queued", "running"}:
            raise HTTPException(status_code=409, detail="broadcast is already queued")
        row.status = "queued"
        await session.commit()
    await enqueue(broadcast_id, request.app.state.bot)
    return {"ok": True, "status": "queued"}


@router.get("/admin/api/commands")
async def admin_commands(request: Request):
    user = await require_panel_user(request, "owner")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    async with session_factory() as session:
        state = await current_state(CommandMetaRepo(session))
    labels = {**PUBLIC_COMMANDS, **ADMIN_COMMANDS}
    return {
        "commands": [
            {
                "command": command,
                "enabled": enabled,
                "label": labels.get(command, ""),
                "scope": "admin" if command in ADMIN_COMMANDS else "public",
            }
            for command, enabled in sorted(state.items())
        ],
        "scopes": sorted(DEFAULT_SCOPES),
        "admin_chat_id": int(ADMIN_GC_ID),
    }


class CommandBody(BaseModel):
    enabled: bool
    reason: str = Field(default="", max_length=500)


class SyncBody(BaseModel):
    scopes: list[str] = Field(default_factory=list)


@router.post("/admin/api/commands/sync")
async def admin_command_sync(body: SyncBody, request: Request):
    user = await require_panel_user(request, "owner")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    scopes = set(body.scopes or DEFAULT_SCOPES)
    if not scopes.issubset(DEFAULT_SCOPES):
        raise HTTPException(status_code=422, detail="invalid scope")
    async with session_factory() as session:
        state = await current_state(CommandMetaRepo(session))
    synced = await sync_all_menus(request.app.state.bot, state, scopes)
    return {"ok": True, "synced": synced, "skipped": sorted(scopes - set(synced))}


@router.post("/admin/api/commands/{command}")
async def admin_command_toggle(command: str, body: CommandBody, request: Request):
    user = await require_panel_user(request, "owner")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    if not re.fullmatch(r"[a-z0-9_]{1,64}", command):
        raise HTTPException(status_code=422, detail="invalid command")
    async with session_factory() as session:
        repo = CommandMetaRepo(session)
        try:
            await set_command_state(repo, command, body.enabled, body.reason)
        except KeyError:
            raise HTTPException(status_code=404, detail="command not found") from None
        state = await current_state(repo)
    return {"ok": True, "commands": state}


@router.get("/admin/api/assets")
async def admin_assets(request: Request):
    user = await require_panel_user(request, "owner")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    assets = []
    if _ASSET_ROOT.exists():
        for path in sorted(_ASSET_ROOT.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in _ASSET_EXTENSIONS:
                continue
            assets.append(
                {
                    "path": path.relative_to(_ASSET_ROOT).as_posix(),
                    "size": path.stat().st_size,
                    "modified": path.stat().st_mtime,
                }
            )
    return {"assets": assets}


@router.post("/admin/api/assets/{asset_path:path}")
async def admin_asset_upload(asset_path: str, request: Request, file: UploadFile = File(...)):
    user = await require_panel_user(request, "owner")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    target = _asset_path(asset_path)
    if target.exists():
        raise HTTPException(status_code=409, detail="asset already exists; delete it first")
    payload = await file.read(_ASSET_MAX_BYTES + 1)
    if len(payload) > _ASSET_MAX_BYTES:
        raise HTTPException(status_code=413, detail="asset exceeds 12 MB")
    if not payload:
        raise HTTPException(status_code=422, detail="empty asset")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".uploading")
    temporary.write_bytes(payload)
    temporary.replace(target)
    return {"ok": True, "path": target.relative_to(_ASSET_ROOT.resolve()).as_posix()}


@router.delete("/admin/api/assets/{asset_path:path}")
async def admin_asset_delete(asset_path: str, request: Request):
    user = await require_panel_user(request, "owner")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    target = _asset_path(asset_path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="asset not found")
    target.unlink()
    return {"ok": True}


class AssetRefreshBody(BaseModel):
    refresh_game_assets: bool = True


@router.post("/admin/api/assets/refresh")
async def admin_assets_refresh(body: AssetRefreshBody, request: Request):
    """Run Enka's asset refresh; this is the same action as /update_assets."""
    user = await require_panel_user(request, "owner")
    if not user:
        raise HTTPException(status_code=401, detail="not signed in")
    if not body.refresh_game_assets:
        return {"ok": True, "refreshed": False}
    try:
        import enka

        async with enka.HSRClient() as hsr:
            await hsr.update_assets()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"asset refresh failed: {exc}") from exc
    return {"ok": True, "refreshed": True}


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
    return Path(__file__).resolve().parent / "static" / filename