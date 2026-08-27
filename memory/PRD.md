# KırCan Report AI — Gayrimenkul Değerleme AI Chat

## Original Problem Statement
Turkish real estate valuation AI chat: users choose report templates, AI collects required info sequentially, parses uploaded PDF/DOCX/XLSX documents into the template, provides live preview, credit-based usage with low-balance upsell, and delivers reports (PDF+DOCX + email). Product must be branded as "KırCan Report AI" (no Emergent references) with role-based multi-tenancy (super_admin / admin / user), company-scoped budgets, invite links, and an admin-managed knowledge base whose contents feed into every AI reply.

## Architecture
- **Backend**: FastAPI + MongoDB (motor). Emergentintegrations LlmChat with Claude Sonnet 5 (`claude-sonnet-5`). Emergent Google Auth. Report generators via reportlab (PDF) and python-docx (DOCX). File parsing via pypdf, python-docx, openpyxl.
- **Frontend**: React 19 + React Router 7 + Tailwind + Shadcn UI. Resizable panels for split view. Sonner for toasts. Manrope/IBM Plex Sans/JetBrains Mono/Instrument Serif typography.

## User Personas
- SPK-licensed real estate appraisers preparing residential, commercial, land, and industrial valuation reports.
- Junior appraisers who need FAQ-style technical guidance on cap rates, imar, amortization, SPK standards.

## Core Requirements (Static)
- Google login (Emergent OAuth)
- 4 report templates: Konut, Ticari, Arsa, Endüstriyel
- AI-driven sequential field collection
- File uploads (PDF/DOCX/XLSX) parsed and used as context
- Live document preview updating during chat
- Credits per message (10 report / 5 FAQ), auto-deduction, low-balance upsell
- Download PDF + DOCX; email delivery (MOCK)

## Implemented (v1 — Feb 2026)
- Emergent Google Auth end-to-end with session cookie + Bearer fallback (2026-02-19)
- 4 seeded report templates + FAQ knowledge base (2026-02-19)
- Chat sessions with persistent messages, chat history sidebar, delete (2026-02-19)
- Claude Sonnet 5 integration with system prompt that emits `<!--UPDATE {...}-->` markers → auto-populates `chat.fields` and `chat.sections` (2026-02-19)
- File upload endpoint parsing PDF/DOCX/XLSX text into LLM context (2026-02-19)
- Live report preview panel with A4-styled paper, sections + field table (2026-02-19)
- PDF + DOCX report generators with brand styling (2026-02-19)
- Mock email dispatch + email log (2026-02-19)

## Implemented (v2 — Feb 2026)
- **SSE Streaming** for chat: `stream_message` API + fetch reader in ChatPanel; typewriter effect + live preview updates (2026-02-19)
- **Wallet in TRY**: migrated `credits` (int) → `wallet_balance` (float TL); per-template cost model (konut 4 / ticari 6 / arsa 3 / endüstriyel 8 / FAQ 2 TL per message)
- **Stripe Checkout wallet top-up** via emergentintegrations Flow B (`sk_test_emergent`, TRY currency): 5 packages (100/250/500/1000/2500 TL) with bonus tiers, redirect to Stripe, webhook + polling status verification, atomic `$inc` credit
- **Payment success/cancel pages** with 404 fast-fail
- **Atomic wallet deduction** with `find_one_and_update` prevents concurrency races & revenue leak on client disconnect
- Testing agent iteration_2: 11/11 backend pytest + full UI verified

## Implemented (v3 — Feb 2026)
- **Usage Analytics dashboard** (`/analytics`): 4 KPI cards (30d harcama, tamamlanan raporlar, AI mesajları, rapor başı ort.), 30-day area chart of daily TL spending, preferred-template highlight card, template breakdown table (messages/reports/spent per template)
- New `usage_events` ledger persists every charged message for accurate analytics
- Backend endpoint `GET /api/analytics/summary` with totals, KPIs, preferred_template, template_breakdown, daily_spend
- Sidebar link "Kullanım Analitiği" for quick navigation
- Testing agent iteration_3: 10/10 backend + full UI verified

## Implemented (v4 — Feb 2026)
- **Range selector** (7 / 30 / 90 Gün + Özel): analytics endpoint now accepts `days` OR `date_from`+`date_to`; window returned in response, chart & KPIs auto-adjust
- **Custom date range** via Shadcn Calendar (range mode, 2-month popover) in Analytics UI
- **CSV export** (`GET /api/analytics/export.csv?days=|date_from=&date_to=`) with UTF-8 BOM for Excel — includes summary, template breakdown, daily spend, per-message ledger, and top-up history in Turkish
- Frontend one-click download preserving current filter

## Implemented (v5 — Feb 2026)
- **Trend comparison**: analytics response now includes `trends` block computing % delta of each KPI vs the previous same-length window (7d compared to prior 7d, custom compared to prior custom, etc.). Also returns `prev_date_from` / `prev_date_to`.
- **Semantic KPI badges**: `▲ %87,5` (red for cost increase / green for activity increase), `▼` inverse, `— yeni` when no baseline. Tooltip reveals previous-period raw value.

## Implemented (v6 — Feb 2026)
- **Custom Word template management**: user uploads a `.docx`, Claude Sonnet 5 auto-detects fillable placeholders (`____`, `[YAZINIZ]`, image slots, table cells) with types (text/number/date/textarea/image). Backend injects `{{ key }}` Jinja tokens into a prepared copy while preserving all original Word formatting (fonts, headings, tables). Templates library page (`/templates`) supports upload + field editor + delete.
- **User templates in chat**: New Chat picker shows a "Word Kütüphaneniz" section alongside built-in templates. Chat greeting adapts to the custom template.
- **Live in-app preview**: `ReportPreviewPanel` renders mammoth-converted HTML with amber `.ph-empty` chips for unfilled placeholders and green `.ph-filled` chips for filled values, updating as fields come in. Preview reflects the exact Word structure.
- **Image slots**: `image` type fields render as an "Image Slot Bar" with per-slot upload buttons; uploaded images embed inline in preview HTML and in the final docxtpl-rendered .docx (via `InlineImage`).
- **Final download**: DOCX rendered via `docxtpl` preserves original Word styles, headings, tables, images.
- **Security**: user_templates queries scoped to owner; `/api/uploads/file/{id}` requires auth + ownership.
- Testing agent iteration_4: **10/10 backend + full UI verified**. Security scoping gaps fixed post-report.

## Implemented (v7 — Feb 2026)
- **Dynamic table rows**: `type: table` fields detected by AI (columns list). Backend injects docxtpl `{%tr for r in items %}` marker rows around the template row, so `docxtpl` renders one output row per user-supplied dict. Preview HTML expands the triple-row marker/template/endfor pattern into N filled `<tr>` elements.
- **Chat-side table editor**: `PATCH /api/chats/{id}/table/{key}` accepts `{rows:[{col:val,...}]}` — the preview panel shows a "Tablolar" chip that opens an inline editor for adding/removing/editing rows.
- **Image resizing**: `PATCH /api/chats/{id}/image/{key}` with `{width_mm}` (20-170mm clamp). Preview `<img>` sizes accordingly; final docxtpl `InlineImage(width=Mm(x))` matches.
- **Template sharing**: `POST /api/user_templates/{id}/share {add:[emails], remove:[emails]}` — owner-only. Recipients (matching by email, case-insensitive) see the template in `/templates`, `/api/user_templates`, can preview + create chats + download; cannot PATCH/DELETE/re-share.
- **Security hardening**: `create_chat` rejects unresolved `user_template_id` with 404; `download_report` re-checks visibility; image uploads validate bytes via PIL (rejects corrupt files at ingest instead of failing at render).
- Testing agent iteration_5: 26/29 backend passed; the 2 HIGH bugs (ACL bypass + preview regex) and image validation gap have all been fixed and re-verified via curl.

## Implemented (v8 — Feb 2026)
- **Template versioning**: every PATCH `/user_templates/{id}` snapshots current fields + name + description into `template_versions` collection (plus a copy of the prepared.docx binary). New endpoint `GET /user_templates/{id}/versions` lists them and `POST /user_templates/{id}/versions/{vid}/restore` re-applies that version (auto-snapshots the current state first, so restore itself is undoable).
- **Versions UI**: history icon on each template card opens the Sürüm Geçmişi dialog with per-version "Geri Yükle" buttons; auto-snapshots are visually marked "Otomatik".
- **Image auto-crop**: `PATCH /api/chats/{id}/image/{key}` extended to accept `aspect_ratio` (16:9 / 4:3 / 1:1 / 3:4 / original) — server crops via PIL center-crop; or explicit `crop {left,top,right,bottom}` pixel rect. Preview URL is cache-busted with a `?v=xxx` query param so the browser re-fetches.
- **Frontend crop UI**: image resize popup now has a "Otomatik Kırpma" row with 5 preset aspect ratio chips; each triggers server-side crop and refreshes preview + eventually the DOCX render.

## Implemented (v9 — Feb 2026)
- **KırCan brand rollout**: logo (`/kircan-logo.jpg`) placed in `public/`; navy `#0b2340` + gold `#c9a24a` palette exposed as CSS variables and applied across login hero, sidebar header, chat bubbles, template preview headings, PDF `reportlab` styles, and the AI's Bearer badge.
- **AI persona**: system prompt now opens with "Sen KırCan Danışmanlık, Eğitim ve Değerleme Ltd. Şti. bünyesinde çalışan bir yapay zeka asistanısın..." so identity/tone stays on-brand across FAQ, built-in templates, and custom Word templates.
- **PDF / DOCX headers**: generated reports now stamp "KırCan Danışmanlık, Eğitim ve Değerleme Ltd. Şti." with the brand palette on every downloaded document.
- **Developer credit**: "Powered by Algorisma" in gold at the bottom of the login page and inside the sidebar footer.
- Page `<title>` updated to "KırCan Report AI".

## Implemented (v4 — Feb 2026 · Rebrand + RBAC + Knowledge Base)
- **Full rebrand to "KırCan Report AI"** — HTML `<title>`, meta description, favicon, PWA colors updated. Emergent script tag & PostHog analytics removed from `index.html`. Login page copy: "Emergent Google Auth" → "Güvenli Google Girişi". Sidebar wordmark: "KırCan AI" → "KırCan Report AI".
- **Role-based access (super_admin / admin / user)** — `User` model extended with `role`, `company_id`, `blocked`. `SUPER_ADMIN_EMAILS = {"grelligram@gmail.com"}` whitelist in `backend/auth_deps.py` auto-promotes on login. `get_current_user` backfills legacy documents, refuses blocked users with 403, and invalidates their sessions on block.
- **Super Admin Panel `/admin/super`** — `SuperAdmin.jsx`: Users tab (list, wallet topup, role change with auto-company creation, block/unblock, delete, chat viewer), Companies tab (create + budget top-up), Invites tab (create link + email lock + revoke), Summary tab (aggregate metrics).
- **Admin Panel `/admin`** — `AdminPanel.jsx`: company-scoped user list, wallet transfer from company budget with balance guard, invite creation limited to `role: user` inside own company.
- **Invite flow `/join/:code`** — `JoinInvite.jsx`: public validation via `GET /api/invites/{code}`, invite code stashed in `sessionStorage` before Google redirect, `POST /api/auth/session/invite` finalizes signup and attaches `company_id` + role atomically.
- **Knowledge Base `/knowledge-base`** — `KnowledgeBase.jsx`: PDF/DOCX/TXT/XLSX/CSV upload with `scope=global|company`. `knowledge_base.get_kb_context()` injects up to ~25k chars of context per request into the Claude system prompt for both FAQ and report chats.
- **Profile `/profile`** — Users can update their own name. Email/picture/role are read-only (Google Auth managed).
- **Backend routers** — `admin_routes.py` (all `/api/admin/*`), `knowledge_base.py` (all `/api/kb/*`), registered via `register_admin_routes(db, get_current_user, User)` factories to keep server.py imports acyclic.
- **New Mongo collections** — `companies`, `company_invites`, `company_ledger`, `wallet_ledger`, `kb_docs`.

## Implemented (v7 — Feb 2026 · Phase 1a: Object Storage + Preview Speed)
- **Emergent Object Storage** — All uploads (`/api/uploads`, `/api/chats/{id}/image`, `/api/kb/upload`) now persist to Object Storage instead of pod-local disk. Legacy pod-local files still readable (graceful fallback). New helpers: `storage_utils.py`, `_resolve_image_paths`, `_ensure_local_template`. Startup event mints a shared `storage_key` once.
- **Template preview cache** — `GET /user_templates/{tid}/preview` now caches rendered HTML by hash(template + values + images + tables). Bounded LRU (200 entries). Repeated same-fields fetches return instantly, no mammoth reparse.
- **Preview reload polish** — Frontend debounces preview requests by 300ms and guards against stale race responses. "Şablon yükleniyor..." shows spinner + Turkish error message with a "Tekrar dene" button on failure.

## Implemented (v6 — Feb 2026 · Invite Link Base URL Fix)
- **Bug fix — "site cannot be reached" on shared invite links**: Root cause was invite URLs being built from `window.location.origin`, which in preview mode is the preview host that external invitees cannot access.
- **Solution**: New `APP_BASE_URL` env in `backend/.env` (set to `https://realestate-ai-flow.emergent.host`). Backend `create_invite` and `list_invites` now compute a canonical `join_url` using this env as highest priority (falls back to `origin_url` payload → Origin → Referer if unset).
- **API surface**: `POST /api/admin/invites` response now returns `join_url` field. `GET /api/admin/invites` returns `join_url_prefix`. Both point to production URL.
- **Frontend**: SuperAdmin & AdminPanel invite copy buttons now use backend-provided URLs; `window.location.origin` only as last-resort fallback.
- **Verification**: 74/74 backend tests pass (12 new invite-URL tests + 45 RBAC + 17 email regression). Real Resend email confirmed to render production URL. Production host reachable (200).

## Implemented (v5 — Feb 2026 · Real Email via Resend)
- **Resend integration** — `backend/email_utils.py`: async wrapper via `asyncio.to_thread`, branded HTML template (navy/gold, table layout, inline CSS), base64 attachment support.
- **Report email now real** — `/api/chats/{chat_id}/email` renders the DOCX (user template or built-in), attaches it, sends via Resend. `email_logs` records `provider='resend'`, `provider_message_id`, and `status` (sent | failed) with sanitized error string for failures.
- **Invite auto-email** — `POST /api/admin/invites` optionally emails the invite link when `email` is provided. Origin resolves in order: explicit `origin_url` → `Origin` header → `Referer` header. Sanitized error messages surface as `email_error` (validation / rate-limit / generic).
- **Environment** — Added `RESEND_API_KEY` and `SENDER_EMAIL=onboarding@resend.dev` to `/app/backend/.env`. `resend==2.37.0` in `requirements.txt`.
- **Note (test mode)**: Resend's default sender `onboarding@resend.dev` in test mode can only deliver to the account owner's verified email. For production, a custom domain must be verified in Resend Dashboard → Domains.

## Prioritized Backlog
### P0 (blocking full production)
- Verify a custom domain in Resend so emails can be sent to any recipient (currently only the owner's inbox works)

### P1
- Report cover page with KırCan logo on exported DOCX/PDF
- Excel/PDF data extraction to auto-suggest template field values
- Deployment (Publish button) — code is deploy-ready

### P2
- Editable fields inside the preview panel (manual overrides)
- Vector search over KB (currently full-text concatenation with a size cap)
- Cost comparison across models (Sonnet vs Haiku for cheaper FAQ)
- Refactor `server.py` (~1800 LoC) into modular routers; split `SuperAdmin.jsx` dialogs into separate files

## Notes
- MOCKED integrations: email dispatch.
- LLM model: `claude-sonnet-5` via Emergent Universal Key (EMERGENT_LLM_KEY).
- Seeded test users: see `/app/memory/test_credentials.md`.
