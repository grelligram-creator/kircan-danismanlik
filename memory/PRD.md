# Valura AI — Gayrimenkul Değerleme AI Chat

## Original Problem Statement
Turkish real estate valuation AI chat: users choose report templates, AI collects required info sequentially, parses uploaded PDF/DOCX/XLSX documents into the template, provides live preview, credit-based usage with low-balance upsell, and delivers reports (PDF+DOCX + email).

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
- Page `<title>` updated to "KırCan AI · Değerleme Asistanı".

## Prioritized Backlog
### P0 (blocking full production)
- Real Stripe/Iyzico payment integration for credit packages (currently MOCK)
- Real Resend/SendGrid email dispatch (currently MOCK)
- Streaming LLM responses (SSE) for real-time typing effect (currently uses send_message)

### P1
- Editable fields inside the preview panel (manual overrides)
- Company/user report branding (logo upload) on generated PDFs
- Report version history + PDF signing
- Support for additional templates (tarım arazisi, deniz kenarı, otel/turistik)

### P2
- Team workspaces + role-based sharing
- Cost comparison across models (Sonnet vs Haiku for cheaper FAQ)
- Analytics dashboard (raporlar/ay, kredi kullanımı)
- Vector-based knowledge base expansion beyond FAQ

## Notes
- MOCKED integrations: email dispatch, credit purchase.
- LLM model: `claude-sonnet-5` via Emergent Universal Key (EMERGENT_LLM_KEY).
- Test user seeded: `test.valuer@example.com`, session_token=`test_session_seed_001`.
