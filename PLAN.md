# HSR Platform — Architecture and Delivery Plan

Status: Phase 0 complete; Phase 1 (React platform) is next.
Last updated: 2026-11-11.

This file is the durable context for chat/model handoffs. Refine it as decisions
change; do not replace history with assumptions.

---

## 1. Product direction

The current Telegram bot and static Mini App become one HSR user platform:

- A React-based user web app with a motion/animation library for polished,
  game-like transitions and feedback.
- A user-specific home page showing the signed-in Trailblazer's identity,
  linked game accounts, settings, recent activity, and shortcuts.
- Web-only game experiences: Wish Simulator, PvE, PvP, and arcade mini-games.
  These need the full browser viewport and cannot be delivered well inside a
  normal Telegram Mini App card.
- Entry from Telegram commands/deep links and from the public website.
- Cookie-based web sessions established through a one-time bot deep link,
  plus verified Telegram Mini App `initData` when launched inside Telegram.
- The bot remains the backend authority for Telegram identity, game-account
  bindings, authority, reports, panel access, and data ownership.

The existing `hsr_bot_webapp/webapp` static Mini App must remain working until
its React replacement is cut over. Do not edit that repo as part of Phase 0.

---

## 2. Repository architecture

Target source layout inside `hsr_bot/`:

```text
bot/        Telegram-only handlers, middleware, keyboards, bot services
server/     FastAPI app, routes, admin panel, polling/webhook runtime, startup
DB/         SQLAlchemy models, repositories, engine/session, Alembic bootstrap
shared/     Config, Redis, auth, runtime state, scheduler, cross-surface logic
alembic/    Migration history; schema changes are Alembic-only
tests/      Unit/regression tests
main.py     Thin entrypoint -> server.runtime.start
```

Allowed dependency direction:

```text
bot      -> shared, DB
server   -> bot, shared, DB
shared   -> DB
DB       -> (no bot/server imports)
```

`bot/` and `shared/` must not import `server.*`. Shared services that need the
running Telegram bot use `shared.runtime.bot_runtime`, bound once by
`server.runtime`.

---

## 3. Runtime modes and environment

| Variable | Values | Purpose |
|---|---|---|
| `ENV` | `local`, `prod` | Environment behavior; `dev`/`development` normalize to `local`. |
| `MODE` | `polling`, `webhook` | Telegram update transport. |
| `BACKEND_URL` | HTTPS origin | Public API origin used in links and by clients. |
| `BACKEND_TYPE` | `local`, `prod` | Backend selected by browser/Mini App clients. |
| `AUTO_MIGRATE` | `true`, `false` | Application-owned schema adoption at startup. |
| `WEBHOOK_URL` | HTTPS origin | Optional override; falls back to `BACKEND_URL`. |
| `PANEL_URL` | HTTPS origin | Optional override; falls back to `BACKEND_URL`. |

Local development uses ngrok for `BACKEND_URL`; production uses the deployed
Visihost origin. The future React client reads `GET /api/config` to pick the
correct backend for its build/run mode. Secrets never appear in that response.

---

## 4. Database and migrations

PostgreSQL is the source of truth; Redis is ephemeral coordination/cache.

- Alembic owns all schema changes. Application startup does not call
  `metadata.create_all`.
- Fresh databases run the baseline and upgrades to head.
- Pre-Alembic/partial production databases are detected when
  `alembic_version` is absent. The idempotent baseline/report revisions fill
  only missing tables/indexes, preserve existing rows, stamp the baseline, and
  then upgrade to head.
- An application advisory lock serializes concurrent starts.
- Startup fails closed if required tables/columns are still missing; it must
  not serve requests against a stale schema.
- `AUTO_MIGRATE=false` is for deployments that run migrations in a separate
  job.

Production incident context (2026-11-11): the deployed database lacked
`lore_settings.spoiler_default` and `web_sessions`, and report notification
failed because user-controlled text was interpolated into HTML without
escaping (for example `<message>`). The schema reconciliation and HTML escaping
fixes are in place. Old Fernet decryption failures are known legacy-key data
and are intentionally not repaired here.

Report flow requirement: when a user presses Report, persist reporter identity,
report type, UID, origin chat/message, lifecycle events, and admin replies.
Admins can reply from the group/DM where the report originated or from the web
panel; the sender is tagged by Telegram ID and the response is delivered to the
user. The panel exposes reports, users, and owner-only authority management
according to the caller's authority.

---

## 5. Authority and authentication

Authority levels: `basic < moderator < admin < owner`.

- `OWNER_TELE_ID` is the emergency owner override; owner rows are protected.
- Bot commands and panel APIs check authority server-side on every request.
- Admin panel: bot-issued one-time login token in Redis -> HttpOnly,
  SameSite=Lax session cookie -> SHA-256 token hash in `web_sessions` -> 8-hour
  TTL and revocation support.
- Mini App: verify Telegram `initData` HMAC with the bot token, check
  `auth_date` freshness, and reject tampered/stale payloads.
- Browser outside Telegram: one-time handoff links with short TTL, bound to the
  issuing Telegram user and destination message; no client-supplied identity
  is trusted.
- Future React platform: prefer HttpOnly cookies for browser sessions; keep
  tokens out of localStorage; issue state-changing requests with CSRF
  protection; scope cookies by path/domain; rotate/revoke on logout.

---

## 6. Admin panel

FastAPI serves the panel and its static files under `/admin/`. Static files
are allowlisted, protected by the same session/authority checks, and served
with `no-store`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and a
restrictive CSP.

Pages/capabilities:

- Moderator: reports queue, report detail/timeline, reply, resolve.
- Admin: user list/search and moderation in addition to reports.
- Owner: admin/authority management, protected against owner escalation.

The panel is not a public static site: it is reachable only after a bot-issued
login link and only by staff.

---

## 7. Web platform phases

### Phase 0 — Stabilize the bot backend (complete)

- Restructure into `bot/`, `server/`, `DB/`, `shared/`.
- Alembic baseline + reconciliation + verified legacy adoption.
- Typed config (`ENV`, `MODE`, `BACKEND_URL`, `BACKEND_TYPE`, `AUTO_MIGRATE`).
- Admin panel report reply/resolve flow and authority enforcement.
- Report HTML escaping and regression coverage.
- aiogram 3.31 upgrade and compatibility pass.
- Document architecture, risks, and next phases in this file.

### Phase 1 — React foundation and identity

- Design the React information architecture and key screens in Figma before
  coding, using the Figma MCP workflow in `../FIGMA.md`.
- Create the React app in the webapp repo with routing, design tokens, motion
  primitives, accessibility, and an API client.
- Build `/api/me`, `/api/home`, session bootstrap, logout, and CSRF-protected
  mutations.
- Cookie + bot deep-link login for normal browsers; verified `initData` for
  Telegram Mini App launches.
- User home: profile, linked game accounts, preferences, reports/activity, game
  shortcuts, and a clear signed-in/signed-out state.
- Preserve the existing static Mini App until feature parity is proven.

### Phase 2 — Admin platform migration

- Move the admin panel to the React design system while keeping FastAPI as the
  API and static-file authority.
- Role-aware navigation and server-enforced capabilities.
- Report conversation UI with delivery status and audit timeline.

### Phase 3 — Wish Simulator

- Vendor every required asset locally; no runtime dependency on the reference
  site.
- Reproduce the HSR Warp Simulator UI, animation timing, banner logic,
  probabilities, pity, guarantees, and history using backend-owned state.
- Keep the reference implementation as a behavioral/UI reference only:
  `https://github.com/Mantan21/HSR-Warp-Simulator`.
- Store pulls/history in PostgreSQL; use Redis only for transient simulation
  state where appropriate.

### Phase 4 — PvE, PvP, and arcade games

- Define server-authoritative rules, matchmaking/rooms, anti-cheat boundaries,
  and replay/audit records.
- Telegram commands can deep-link into a game; public website entry uses the
  same authenticated session.
- Full-screen browser UI is the primary experience.

### Phase 5 — Hardening and operations

- Load/performance tests, rate limits, observability, error budgets, backups,
  restore drills, privacy/retention controls, and admin audit exports.
- Verify production migrations in a staging database before each deploy.

---

## 8. aiogram 3.31 / Telegram Bot API upgrade notes

Upgrade performed: `aiogram==3.31.0` (from 3.24.0). The existing test suite
passes; no handler API breakage was found in this codebase. The official docs
and Bot API reference were checked on 2026-11-11.

Relevant capabilities and product use:

- **Rich messages (Bot API 10.2–10.4):** structured blocks, tables, collages,
  expandable quotations, anchors, buttons, and media. Useful for polished lore,
  help, and report output, but the React web app remains the primary visual
  surface.
- **Ephemeral messages (10.3–10.4):** replies visible only to the requesting
  user in a group, including callback-query responses. Use for private
  status/errors and guided actions without group noise. They are presentation,
  not authentication.
- **Widgets (10.4):** HTML widgets with protected content and TON-wallet
  query flows, currently private-chat-only. Out of scope for Phase 0; do not
  adopt wallet/payment behavior without an explicit product and privacy review.
- **Disabled/force-reply keyboard buttons:** clearer unavailable actions and
  guided input flows.
- **Web App deep links (`startapp`), menu buttons, and `WebAppInfo`:** the
  primary bridge from a Telegram command into the full-screen React experience.
  Use a short-lived, audience-bound handoff token rather than putting identity
  in URL parameters.
- **`initData` validation:** HMAC-SHA-256 with the `WebAppData` key, sorted
  data-check-string, and `auth_date` freshness. The Ed25519 `signature` allows
  third-party verification without the bot token. Validate server-side on
  every launch and never trust `initDataUnsafe`.
- **Bot API 8.0 Mini App capabilities:** fullscreen, safe-area insets,
  orientation lock, home-screen shortcuts, secure storage, share/download,
  haptics, and device-performance checks. Use them for game presentation and
  UX, not as proof of identity.
- **Command scopes and localization:** per-chat/per-language command scopes
  keep normal-user menus clean and hide staff-only commands. Authority still
  has to be enforced by the backend; hiding UI is not authorization.
- **Privacy and retention:** collect the minimum Telegram fields, document
  retention, never log `initData` or session tokens, use one-time handoffs,
  expire/revoke sessions, and give users a clear logout/revoke path. Separate
  public profile data from private game-account bindings.
- **Rate limits and anti-abuse:** Telegram limits are not a substitute for
  server-side quotas. Keep Redis-backed rate limits for commands and API
  mutations, and use ephemeral replies for retry/cooldown feedback.

Upgrade strategy: keep aiogram pinned, run the full suite plus import/compile
checks, and test one polling and one webhook startup against a staging bot
before production rollout.

---

## 9. Immediate next actions

1. Run the production recovery rehearsal in `PHASE0.md` against a staging copy,
   then deploy and confirm the schema-ready log line.
2. Design the React information architecture and key screens in Figma before
   implementation; reuse the HSR visual language and verify accessibility.
3. Implement `/api/me`, session bootstrap, and the user home against the
   existing auth/handoff primitives.
4. Build the admin reports conversation UX on the existing panel APIs.
5. Add automated fresh/partial-legacy migration tests to CI.