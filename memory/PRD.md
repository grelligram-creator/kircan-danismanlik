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
- Mock credit purchase (starter/pro/enterprise) with upsell dialog + low-credit warning (2026-02-19)
- Data-testids on all interactive elements; 100% test pass on iteration_1

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
