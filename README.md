<div align="center">

<img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI"/>
<img src="https://img.shields.io/badge/Next.js_15-000000?style=for-the-badge&logo=next.js&logoColor=white" alt="Next.js 15"/>
<img src="https://img.shields.io/badge/React_19-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React 19"/>
<img src="https://img.shields.io/badge/Tailwind_CSS_4-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white" alt="Tailwind 4"/>
<img src="https://img.shields.io/badge/PostgreSQL-316192?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL"/>
<img src="https://img.shields.io/badge/SQLAlchemy_2-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white" alt="SQLAlchemy 2"/>
<img src="https://img.shields.io/badge/Pydantic_v2-E92063?style=for-the-badge&logo=pydantic&logoColor=white" alt="Pydantic v2"/>
<img src="https://img.shields.io/badge/TypeScript_5-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript 5"/>
<img src="https://img.shields.io/badge/Alembic-2E2E2E?style=for-the-badge&logo=alembic&logoColor=white" alt="Alembic"/>
<img src="https://img.shields.io/badge/HMAC--SHA256-4053D6?style=for-the-badge&logo=datadog&logoColor=white" alt="HMAC-SHA256"/>
<img src="https://img.shields.io/badge/Token_Bucket-FF6F00?style=for-the-badge&logo=cloudflare&logoColor=white" alt="Token Bucket"/>

<br/><br/>

# 💸 TrustLedger

### *Transaction Truth — A Provably Honest Money-Movement Platform*

**A double-entry ledger for peer-to-peer transfers, hardened with HMAC-signed requests and a live token-bucket rate limiter. Built end-to-end in 48 hours.**

[🚀 Live Demo](#) · [📖 API Docs](#-api-surface) · [🏗️ Architecture](#-architecture) · [⚡ Quickstart](#-quickstart) · [🏆 Why It Wins](#-why-this-wins-the-hackathon)

---

</div>

## 🎯 The Problem

Most fintech demos treat money like a spreadsheet cell — `balance = balance - amount`. That's how you ship a bug that lets someone pay twice, or two people deadlock each other mid-transfer, or an attacker replay a forged request.

**TrustLedger** refuses that shortcut. Every taka is a credit on one side and a debit on the other. Every write is signed. Every client is rate-limited. Every number you see on the dashboard is *recomputed from the ledger*, never stored.

---

## ✨ What It Does

| Feature | What You See | What's Really Happening |
|---|---|---|
| 🧾 **Double-entry ledger** | "৳ 1,200 — Available balance" | Balance is `Σ credits − Σ debits` over the entire journal. No `balance` column exists. |
| 🔁 **Peer transfers** | 3-step send flow with atomic confirmation | `SELECT … FOR UPDATE` on both users in *ascending UUID order*, single transaction, 2 ledger rows. |
| 🛡️ **HMAC-SHA256 request signing** | Every API call carries `X-Signature` + `X-Timestamp` | Server rejects unsigned/expired/stale requests beyond ±300s clock skew. Replay-resistant. |
| ⏱️ **Live token-bucket rate limit** | A real-time dashboard of remaining tokens per client | 60-burst / 1-RPS bucket; visualized live with 3-second polling and a stress-test playground. |
| 🏦 **System treasury** | New user signs up → instantly funded with ৳ 100,000 | A fixed-UUID system account is the *only* source of new money; can go negative, everything else cannot. |
| � **Money requests** | "Approve" / "Decline" buttons to settle a pending ask | Two-phase commit: request → atomic transfer on approval. |
| 📊 **System health check** | "Consistent · No duplicates · Concurrency-safe" | Three live invariants that prove the ledger hasn't drifted. |

---

## 🏆 Why This Wins the Hackathon

1. **It's actually correct.** Most demos skip the ledger. We built one — with locking, ordering, and a treasury pattern that mirrors real banking systems.
2. **It's secure by default, not as an afterthought.** HMAC signing and rate limiting are first-class dependencies on every write route, not bolted on.
3. **It's demoable.** The x402 admin panel turns invisible infra (rate limit buckets, request signatures) into a *live, observable* dashboard — judges see it working in real time.
4. **It ships the UI/UX bar.** Material 3 design tokens, three-step send flow, gradient avatars, atomic-transaction trust banner. No `lorem ipsum`.
5. **It has a stress test.** `tests/test_concurrent_transfers.py` proves the deadlock-ordering works under load.

> **Tagline judges remember:** *"No balance column exists — only journal entries. The truth is in the math."*

---

## 🖼️ Screenshots

<div align="center">

| Dashboard | 3-Step Send Flow | x402 Live Dashboard |
|:-:|:-:|:-:|
| Balance card · recent activity · ledger health | Recipient → Amount → Review → Confirmed | Live token-bucket bars · sign-this-payload playground |

</div>

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                   Next.js 15 (App Router)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌────────────�  │
│  │ Overview │  │  /send   │  │ /transactions│  │ /admin/x402│  │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘  └─────┬──────┘  │
│       └──────────────┴──────────────┴─────────────────┘         │
│                              │                                  │
│                    lib/api.ts  (typed fetch wrappers)           │
│                              │  /api/* rewrite → :8000          │
└──────────────────────────────┼──────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                            │
│  �────────────┐  ┌────────────┐  ┌─────────────┐  ┌──────────┐  │
│  │ /transfers │  │  /requests │  │   /users    │  │  /x402   │  │
│  └─────�──────┘  └─────┬──────┘  └──────┬──────┘  └────┬─────┘  │
│        │               │                │              │        │
│        └───────────────┴────────────────┴──────────────┘        │
│                              │                                  │
│              ┌───────────────┴───────────────┐                  │
│              ▼                               ▼                  │
│   ┌─────────────────────┐         ┌─────────────────────────┐   │
│   │   x402_signing      │         │   x402_rate_limit       │   │
│   │   HMAC-SHA256       │         │   TokenBucket (60/1s)   │   │
│   │   ±300s clock skew  │         │   per client key        │   │
│   └─────────────────────┘         └─────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│              ┌───────────────────────────────┐                  │
│              │  app/services.py              │                  │
│              │  • execute_transfer           │                  │
│              │  • register_user              │                  │
│              │  • seed_treasury              │                  │
│              │  • system_ledger_health       │                  │
│              └───────────────┬───────────────┘                  │
│                              ▼                                  │
│              ┌───────────────────────────────┐                  │
│              │  PostgreSQL + SQLAlchemy 2    │                  │
│              │  • users                      │                  │
│              │  • transfers (idempotent)     │                  │
│              │  • ledger_entries (2 per xfer)│                  │
│              │  • money_requests             │                  │
│              └───────────────────────────────┘                  │
└────────────────────────────────────────────────────────────────┘
```

### The Five Invariants We Prove

1. **No negative non-treasury balances.** Every transfer is atomic; sender cannot overdraft.
2. **Every transfer writes exactly 2 ledger entries.** No missing debits, no missing credits.
3. **No replay.** `idempotency_key` is unique on the `transfers` table.
4. **No deadlock.** Rows are always locked in ascending UUID order — no AB/BA cycles.
5. **No drift.** `system_ledger_health` reconciles `SUM(credits) == SUM(debits)` across the whole journal.

---

## ⚡ Quickstart

### Prerequisites

- **Python 3.11+**
- **Node.js 20+** and **npm**
- **PostgreSQL 14+** (or Docker — see below)

### 1. Clone & install

```bash
git clone https://github.com/Andrew-Velox/pstu-final-onsite.git
cd pstu-final-onsite

# Backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -r requirements.txt

# Frontend
cd frontend
npm install
cd ..
```

### 2. Database

**Option A — Docker (fastest):**
```bash
docker run -d --name trustledger-db \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=trustledger -p 5432:5432 postgres:16
```

**Option B — local Postgres:** create a database called `trustledger`.

Copy `.env.example` to `.env` and set `DATABASE_URL`:
```env
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/trustledger
```

### 3. Migrate & seed

```bash
alembic upgrade head
```
The lifespan hook in `main.py` seeds the system treasury on startup — no manual step needed.

### 4. Run

**Two terminals:**

```bash
# Terminal 1 — backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev
```

Open **http://localhost:3000**.

### 5. Verify

```bash
# Backend health
curl http://localhost:8000/health
# → {"status":"ok"}

# Live ledger invariants
curl http://localhost:8000/system/health-check
# → {"consistent": true, "duplicates": false, "concurrency_safe": true}

# Open Swagger UI
open http://localhost:8000/docs
```

---

## 📖 API Surface

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/health` | Liveness ping |
| `POST` | `/users` | Register a new user (auto-funded � 100,000) |
| `GET`  | `/users` | List all users |
| `GET`  | `/users/{id}/balance` | Recomputed balance from the ledger |
| `GET`  | `/users/{id}/transactions` | Paginated transaction history |
| `POST` | `/transfers` | Atomic peer transfer (idempotent) |
| `POST` | `/requests` | Create a money request |
| `GET`  | `/requests` | List incoming + outgoing requests |
| `POST` | `/requests/{id}/approve` | Approve & settle as a transfer |
| `POST` | `/requests/{id}/decline` | Decline a pending request |
| `GET`  | `/system/health-check` | Ledger invariant report |
| `GET`  | `/x402/info` | x402 capabilities (signing + rate limit config) |
| `POST` | `/x402/sign` | Mint an HMAC-SHA256 signature for a payload |
| `GET`  | `/x402/usage` | Current token-bucket state for all clients |

Full schema available at **`/docs`** (Swagger UI) once the backend is running.

---

## 🔐 Security in Depth

| Layer | Mechanism | Where |
|---|---|---|
| **Transport** | CORS allow-list (`localhost:3000`) | `main.py` |
| **Authentication** | HMAC-SHA256 signed requests, ±300s skew window | `app/x402_signing.py` |
| **Rate limiting** | Token-bucket, 60 burst / 1 RPS per client | `app/x402_rate_limit.py` |
| **Idempotency** | Unique `idempotency_key` on `transfers` | `app/routers/transfers.py` |
| **Concurrency** | `SELECT … FOR UPDATE` in UUID order | `app/services.py` |
| **Treasury** | Fixed-UUID system account, may go negative | `app/services.py:42` |
| **Replay window** | Timestamped, server-validated | `app/x402_signing.py:37` |

### Generate a signed request

```bash
TS=$(date +%s)
BODY='{"sender_id":"...","receiver_id":"...","amount":500}'
SIG=$(python -c "import hmac,hashlib,sys; print(hmac.new(b'dev-only-secret-rotate-me-in-production', f'$TS.$BODY'.encode(), hashlib.sha256).hexdigest())")

curl -X POST http://localhost:8000/transfers \
  -H "X-Timestamp: $TS" \
  -H "X-Signature: $SIG" \
  -H "Content-Type: application/json" \
  -d "$BODY"
```

---

## 🧪 Tests

```bash
# Backend — concurrent-transfer stress test
pytest tests/test_concurrent_transfers.py -v
```

This test launches N parallel transfers from the same sender to the same receiver and asserts:

- No deadlocks (no AB/BA cycles).
- Final balance reconciles with the journal.
- No duplicate `idempotency_key` rows.

---

## � Tech Stack

**Backend**
- [FastAPI](https://fastapi.tiangolo.com/) 0.141+ — async Python web framework
- [SQLAlchemy](https://www.sqlalchemy.org/) 2.0 — ORM with `FOR UPDATE` semantics
- [Alembic](https://alembic.sqlalchemy.org/) — schema migrations
- [PostgreSQL](https://www.postgresql.org/) 14+ — relational store
- [Pydantic](https://docs.pydantic.io/) v2 — request/response validation
- [psycopg2-binary](https://www.psycopg.org/) — Postgres driver

**Frontend**
- [Next.js](https://nextjs.org/) 15 (App Router) — React framework
- [React](https://react.dev/) 19 — UI runtime
- [TypeScript](https://www.typescriptlang.org/) 5 — type safety
- [Tailwind CSS](https://tailwindcss.com/) 4 — utility-first styling, Material 3 tokens via `@theme`
- Material Symbols Outlined · Geist · Inter · JetBrains Mono

---

## 📁 Project Layout

```
pstu-final-onsite/
├── alembic/                       # DB migrations
│   ├── env.py
│   └── versions/
│       └── 0001_initial_schema.py
├── app/                           # FastAPI app package
│   ├── __init__.py
│   ├── database.py                # SQLAlchemy session factory
│   ├── models.py                  # User, Transfer, LedgerEntry, MoneyRequest
│   ├── schemas.py                 # Pydantic v2 schemas
│   ├── services.py                # Core double-entry logic + treasury
│   ├── x402_signing.py            # HMAC-SHA256 request signing
│   ├── x402_rate_limit.py         # Token-bucket rate limiter
│   └── routers/
│       ├── transfers.py           # POST /transfers (atomic)
│       ├── requests.py            # /requests (create/approve/decline)
│       ├── users.py               # /users (register, balance, history)
│       ├── system.py              # /system/health-check
│       └── x402.py                # /x402/sign | /info | /usage
├── frontend/                      # Next.js 15 app
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx           # Dashboard
│   │   │   ├── send/              # 3-step send money flow
│   │   │   ├── request/           # Money request flow
│   │   │   ├── transactions/      # History + filters + pagination
│   │   │   └── admin/x402/        # Live token-bucket dashboard
│   │   ├── components/            # TopNav, SideNav
│   │   └── lib/                   # api.ts, UserContext.tsx
│   ├── package.json
│   ├── next.config.ts             # /api/* → :8000 rewrite
│   └── tsconfig.json
├── tests/
│   ├── conftest.py
│   └── test_concurrent_transfers.py
├── main.py                        # FastAPI entry, lifespan seeds treasury
├── alembic.ini
├── requirements.txt
└── README.md                      # you are here
```

---

## 🌟 Roadmap (post-hackathon)

- [ ] JWT/OAuth in addition to HMAC for user-scoped auth
- [ ] WebSocket push for the dashboard instead of polling
- [ ] Multi-currency support (the ledger model already supports it — one `currency` column)
- [ ] Redis-backed rate limiter for multi-instance deploys
- [ ] Append-only cryptographic audit log (Merkle root per block)
- [ ] Mobile client (React Native, reuse the typed API layer)

---

## 👥 Team & Acknowledgments

Built with 🧡 for **PSTU Hackathon Final Round**.

Special thanks to the open-source community — FastAPI, SQLAlchemy, Next.js, and Tailwind made this 48-hour build possible.

---

<div align="center">

### *“If the math doesn't reconcile, the truth isn't there.”*

⭐ **Star this repo if you'd back a fintech that shows its work.** ⭐

</div>
