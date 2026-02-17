# RhoneRisk Cyber Insurance Policy Analyzer
## Micro Application Build Plan & Architecture Decision Record

**Prepared for:** RhoneRisk Advisory
**Date:** February 17, 2026
**Version:** 3.0 — Supersedes all prior Manus AI plans (v1.0, v2.0)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Analysis of Prior Plans](#2-analysis-of-prior-plans)
3. [Current Codebase Assessment](#3-current-codebase-assessment)
4. [Architecture Decision: ETL Runtime](#4-architecture-decision-etl-runtime)
5. [Architecture Decision: Knowledge Base & Context](#5-architecture-decision-knowledge-base--context)
6. [Architecture Decision: Document Storage](#6-architecture-decision-document-storage)
7. [Architecture Decision: Orchestration & Queuing](#7-architecture-decision-orchestration--queuing)
8. [Final Architecture](#8-final-architecture)
9. [Process Flow](#9-process-flow)
10. [Codebase Changes Required](#10-codebase-changes-required)
11. [Deployment Guide](#11-deployment-guide)
12. [Cost Analysis](#12-cost-analysis)
13. [Growth Path](#13-growth-path)
14. [Appendix A: Complete File Inventory](#appendix-a-complete-file-inventory)
15. [Appendix B: Existing Pipeline Technical Reference](#appendix-b-existing-pipeline-technical-reference)
16. [Appendix C: Platform Research Data](#appendix-c-platform-research-data)

---

## 1. Executive Summary

### The Problem

RhoneRisk needs a production-deployable micro application that runs its cyber insurance policy analysis pipeline: PDF ingestion, AI-powered coverage scoring, deterministic post-processing, and branded PDF report generation. The application must be efficient, consistent, and cost-effective at 100-1,000 analyses per month.

### What Already Exists

A fully functional analysis engine has been built and tested. The codebase contains:

- **6-stage analysis pipeline** (extract, parse, score, post-process, narrative, report)
- **2 Claude API calls** per analysis with Anthropic prompt caching (90% discount on call 2)
- **21 coverage types** scored across 10 factors each using a 4-tier maturity system
- **10 deterministic red flag rules** with automatic score caps
- **Weighted overall scoring** (Coverage 40%, Limits 25%, Exclusions 20%, Terms 15%)
- **4-tier binding recommendations** (Recommend Binding, Bind with Conditions, Require Major Modifications, Recommend Decline)
- **21-section branded PDF reports** via Jinja2 + WeasyPrint
- **31 passing tests** covering the engine, post-processing, ETL, and report generation

### The Decision

Deploy the existing codebase as-is to **Google Cloud Run** with minimal modifications (async endpoint, object storage, status polling). No new services, no new databases, no new queue infrastructure. The existing architecture is already optimized; what's needed is deployment, not re-architecture.

### Cost Comparison

| Component | Prior Plans (Manus AI) | This Plan |
|---|---|---|
| Runtime | Railway ($15/mo always-on) | Cloud Run ($0 — free tier) |
| Database | Supabase ($25/mo) | Not needed for v1 |
| Queue | Redis + BullMQ ($10/mo) | BackgroundTasks ($0) |
| PDF Extraction | Unstructured.io ($200/mo) | PyMuPDF4LLM ($0 — already working) |
| Monitoring | Sentry ($26/mo) | Cloud Run built-in ($0) |
| Frontend | Vercel ($20/mo) | API-only ($0 — add UI later) |
| Storage | Supabase Storage (included) | Cloudflare R2 ($0 — free tier) |
| Claude API | ~$300/mo (20+ calls/analysis) | ~$50-150/mo (2 calls + caching) |
| **Total (1,000 analyses/mo)** | **~$631/mo** | **~$50-152/mo** |

---

## 2. Analysis of Prior Plans

Ten development plan documents were evaluated. They fall into two versions:

### Plan V1: Compliance-Based Framework (RhoneRisk_Development_Plan.md)

- **Approach:** Score policies against NIST CSF, CMMC, and CIS Controls
- **Architecture:** Vercel CRM + Supabase + Railway + BullMQ/Redis + Unstructured.io
- **Analysis Method:** 20+ separate Claude API calls (one per coverage type)
- **Report Generation:** ReportLab with radar charts
- **Scoring:** Generic 1-5 compliance maturity scale

**Why this plan was rejected:**
1. It evaluates organizational cybersecurity compliance, not insurance policy coverage maturity. The system prompt in the current codebase explicitly states: *"You evaluate cyber insurance policy coverage maturity — the quality, breadth, and adequacy of the insurance policy itself. You do NOT evaluate organizational cybersecurity compliance."*
2. A 5-service distributed architecture is massively over-engineered for 100-1,000 analyses/month
3. 20+ Claude API calls per analysis is 10x more expensive and 10x slower than the 2-call approach already implemented
4. Unstructured.io adds $200/month for extraction that PyMuPDF4LLM already handles well

### Plan V2: Proprietary Scoring Framework (RhôneRisk Cyber Insurance Policy Analyzer.md)

- **Approach:** RhoneRisk's proprietary 4-tier maturity scoring (correct)
- **Architecture:** Same 5-service distributed architecture as V1
- **Analysis Method:** Still proposes per-coverage API calls
- **Scoring:** 0-10 scale with Superior/Average/Basic/No Coverage tiers (correct)

**Why this plan was partially adopted:**
1. The scoring methodology is correct and is already implemented in the codebase
2. The 21-section analysis framework is correct and is already implemented
3. Red flag detection with score caps is correct and is already implemented
4. The architecture and deployment recommendations remain over-engineered

### What Both Plans Miss

The existing codebase has already solved the hard problems that both plans treat as future work:

| Capability | Plans say "build this" | Codebase status |
|---|---|---|
| Coverage scoring engine | Phase 2 (5-7 days) | `app/analysis/client.py` — working |
| Red flag penalty system | Phase 2 (5-7 days) | `app/analysis/postprocess.py` — working |
| 21-section report generation | Phase 2 (5-7 days) | `templates/report.html.j2` — working |
| Structured data extraction | Phase 2 (5-7 days) | `app/etl/parser.py` — working |
| Prompt caching | Not mentioned | `app/analysis/client.py` — implemented |
| Extended thinking | Not mentioned | Enabled with 8,192 token budget |
| Forced tool-use outputs | Not mentioned | `tool_choice: {"type": "tool"}` enforced |
| Weighted overall scoring | Not mentioned | `app/analysis/postprocess.py` — working |
| Binding recommendation logic | Not mentioned | `app/analysis/postprocess.py` — working |

---

## 3. Current Codebase Assessment

### Directory Structure

```
rhonepolicyanalyzer/
├── app/
│   ├── __init__.py
│   ├── main.py                          # FastAPI routes (health, analyze, status, download)
│   ├── config.py                        # pydantic-settings configuration
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── engine.py                    # 6-stage pipeline orchestrator
│   │   ├── client.py                    # Claude API wrapper (caching, retries, tool-use)
│   │   ├── postprocess.py              # Red flag penalties, scoring, binding rec
│   │   └── prompts.py                  # Prompt building utilities
│   ├── etl/
│   │   ├── __init__.py
│   │   ├── extractor.py                # PyMuPDF4LLM markdown + pdfplumber tables
│   │   └── parser.py                   # Regex metadata extraction (11 fields)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── requests.py                 # ClientInfo model
│   │   ├── responses.py                # API response models
│   │   └── scoring.py                  # PolicyAnalysis, CoverageScore, ReportSections
│   ├── knowledge/
│   │   ├── __init__.py
│   │   ├── system_prompt.md            # Master AI prompt (110 lines, ~8K tokens)
│   │   ├── red_flags.yaml              # 10 red flag rules with score caps
│   │   ├── scoring_methodology.yaml    # Weights, tiers, binding thresholds
│   │   ├── coverage_definitions.yaml   # 21 coverage types with key factors
│   │   └── report_sections.yaml        # 21-section framework definition
│   └── report/
│       ├── __init__.py
│       └── generator.py                # Jinja2 HTML rendering + WeasyPrint PDF
├── templates/
│   └── report.html.j2                  # 390-line branded HTML report template
├── tests/
│   ├── __init__.py
│   ├── conftest.py                     # Fixtures: sample policy text, scores, analysis
│   ├── test_engine.py                  # Pipeline integration tests
│   ├── test_postprocess.py             # Scoring, penalties, binding recommendation tests
│   ├── test_report.py                  # HTML rendering and PDF generation tests
│   ├── test_parser.py                  # Metadata extraction tests
│   └── test_extractor.py              # PDF extraction tests
├── Dockerfile                          # python:3.12-slim + WeasyPrint system deps
├── pyproject.toml                      # hatchling build, all dependencies
├── .env.example                        # Environment variable template
└── .gitignore
```

### Pipeline Architecture (Already Implemented)

The analysis engine (`app/analysis/engine.py`) executes a 6-stage synchronous pipeline:

```
Stage 1: EXTRACT     PyMuPDF4LLM → markdown text    (5-15 seconds)
                     pdfplumber → structured tables   (2-5 seconds)

Stage 2: PARSE       Regex patterns → 11 metadata    (instant)
                     fields (policy #, carrier,
                     limits, dates, etc.)

Stage 3: SCORE       Claude API Call 1                (10-30 seconds)
                     System prompt CACHED (ephemeral)
                     Tool-use forced output
                     Extended thinking (8K budget)
                     → list[CoverageScore] for all
                       21 coverage types

Stage 4: POST-PROC   Red flag penalty application     (instant)
                     Score capping per YAML rules
                     Weighted overall score calc
                     Binding recommendation logic

Stage 5: NARRATIVE   Claude API Call 2                (10-30 seconds)
                     System prompt from CACHE (90%
                     discount on input tokens)
                     Tool-use forced output
                     → ReportSections (21 sections)

Stage 6: REPORT      Jinja2 HTML rendering            (1-2 seconds)
                     WeasyPrint PDF conversion         (3-5 seconds)
                     → Branded PDF report
```

**Total pipeline time:** 30 seconds to 3 minutes (dominated by Claude API response time)

### API Design (Already Implemented)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/v1/health` | GET | Health check, knowledge base validation |
| `/api/v1/analyze` | POST | Upload PDF + client info, run analysis |
| `/api/v1/analyze/{id}` | GET | Retrieve analysis results by ID |
| `/api/v1/analyze/{id}/report` | GET | Download generated PDF report |

### Test Coverage (31 Tests, All Passing)

| Test File | Tests | What's Covered |
|---|---|---|
| `test_engine.py` | 1 | Full pipeline integration with mocked Claude client |
| `test_postprocess.py` | 8 | Score-to-rating, red flag penalties, overall score, all 4 binding tiers |
| `test_report.py` | 5 | Score colors, rating badges, HTML rendering, all scores present, sections present |
| `test_parser.py` | 7+ | Metadata regex extraction for all 11 fields |
| `test_extractor.py` | 5+ | PDF-to-markdown, table extraction, formatting |

### AI Architecture Details

**System Prompt** (`app/knowledge/system_prompt.md`):
- 110 lines defining the RhoneRisk analyst persona
- Critical distinction: evaluates policy coverage maturity, NOT organizational compliance
- 4-tier scoring definitions with explicit boundaries
- 21 coverage types across 3 categories (third-party, first-party, cyber crime)
- 10 scoring factors per coverage type
- 10 red flag rules with score caps
- MSP-specific emphasis areas
- Weighted overall score formula
- Binding recommendation framework

**Prompt Caching Strategy**:
- Call 1: System prompt sent with `cache_control: {"type": "ephemeral"}`
- Call 2: Same system prompt, served from Anthropic's cache at 10% cost
- 5-minute cache TTL covers both calls within a single pipeline run

**Structured Output Enforcement**:
- Call 1 uses `COVERAGE_SCORES_TOOL` schema with `tool_choice: {"type": "tool", "name": "submit_coverage_scores"}`
- Call 2 uses `REPORT_NARRATIVE_TOOL` schema with `tool_choice: {"type": "tool", "name": "submit_report_narrative"}`
- This guarantees parseable JSON output every time (no prompt-based JSON parsing)

**Deterministic Post-Processing** (`app/analysis/postprocess.py`):
- Red flags detected by AI are cross-referenced against YAML rules
- Matching flags trigger automatic score caps on affected coverages
- Example: "War/Terrorism Exclusion Without Buyback" caps ALL coverage scores at 6
- Overall score computed via weighted formula, not by AI
- Binding recommendation is deterministic based on score thresholds + flag count

---

## 4. Architecture Decision: ETL Runtime

### Workload Profile

| Characteristic | Value |
|---|---|
| PDF extraction | CPU-intensive (PyMuPDF4LLM + pdfplumber) |
| Claude API calls | 2 per analysis, 10-30s each, I/O-bound |
| Report generation | CPU-intensive, requires libcairo2, libpango system libraries |
| Pipeline duration | 30 seconds to 3 minutes |
| Volume | 100-1,000 analyses/month (3-33/day) |
| Docker image | ~400-600MB (python:3.12-slim + system deps) |
| Concurrency | Low — typically 1-3 concurrent analyses |

### Platform Comparison

#### Google Cloud Run (SELECTED)

| Factor | Detail |
|---|---|
| **Timeout** | 60 minutes. Pipeline needs 3 minutes max. Massive headroom. |
| **Cold start** | 2-5 seconds. Eliminated with `min-instances=1` if needed. |
| **System deps** | Full Docker support. Existing Dockerfile works unmodified. |
| **Auto-scaling** | Scales to zero (pay nothing when idle), scales up to 1000 instances. |
| **Cost (100/mo)** | **$0.** Free tier: 180,000 vCPU-seconds/month. Usage: ~18,000 (100 x 180s x 1 vCPU) = 10% of free tier. |
| **Cost (1,000/mo)** | **$0-2.** ~180,000 vCPU-seconds = at free tier boundary. Overage: $0.0000240/vCPU-sec. |
| **Deploy command** | `gcloud run deploy rhone-analyzer --source . --region us-central1` |

#### Railway (Rejected)

| Factor | Detail |
|---|---|
| **Timeout** | **5 minutes hard limit.** Barely fits the pipeline — variance could cause failures. |
| **Cold start** | None (always-on). But you pay for idle time 24/7. |
| **Cost (100/mo)** | ~$12-15/month. Always-on 0.5 vCPU/1GB at $20/vCPU/month + $10/GB/month. |
| **Rejection reason** | 5-minute timeout too tight. Always-on pricing wasteful for bursty workload. |

#### AWS Lambda (Rejected)

| Factor | Detail |
|---|---|
| **Timeout** | 15 minutes. Sufficient. |
| **Cold start** | 2-9 seconds for Docker containers. |
| **Cost (100/mo)** | ~$0.50-1.00. Cheapest option at scale. |
| **Rejection reason** | WeasyPrint system dependencies (libcairo2, libpango) are extremely difficult to install in Lambda. Multiple GitHub issues document the pain. The engineering tax does not justify the marginal savings over Cloud Run's free tier. |

#### Fly.io (Strong Alternative)

| Factor | Detail |
|---|---|
| **Timeout** | Unlimited (app-controlled). |
| **Cold start** | 2-5 seconds with auto-stop/auto-start. |
| **Cost (100/mo)** | ~$3-5/month. Scale-to-zero available. |
| **Assessment** | Strong second choice. No timeout limits, Docker works natively. Slightly more complex deployment than Cloud Run. +$2/month for IPv4. |

#### Modal (Rejected for Now)

| Factor | Detail |
|---|---|
| **Timeout** | 24 hours. More than sufficient. |
| **Cold start** | 2-4 seconds. Among the fastest. |
| **Cost (100/mo)** | $0 ($30/month free credits). |
| **Rejection reason** | Requires rewriting Dockerfile into Modal's Python-native image builder DSL. Lock-in risk: Modal-specific code does not port to other platforms. Good for greenfield, not ideal when a working Docker setup exists. |

#### Render (Rejected)

| Factor | Detail |
|---|---|
| **Timeout** | 100 minutes. Very generous. |
| **Cold start** | 30-60 seconds on free tier. |
| **Cost (100/mo)** | ~$7-14/month. No scale-to-zero on paid plans. |
| **Rejection reason** | Starter plan (512MB) insufficient for PDF extraction + WeasyPrint. Always-on pricing. No advantage over Cloud Run. |

### Decision Summary

| Platform | Timeout | Cold Start | WeasyPrint | Cost (100/mo) | Cost (1K/mo) | Scale-to-Zero |
|---|---|---|---|---|---|---|
| **Cloud Run** | 60 min | 2-5s | Works | **$0** | **$0-2** | **Yes** |
| Railway | 5 min | None | Works | $12-15 | $12-15 | No |
| Lambda | 15 min | 2-9s | Painful | $0-1 | $3-5 | Yes |
| Fly.io | Unlimited | 2-5s | Works | $3-5 | $5-7 | Yes |
| Modal | 24 hr | 2-4s | Rewrite | $0 | $8-15 | Yes |
| Render | 100 min | 30-60s | Works | $7-14 | $7-14 | No |

**Winner: Google Cloud Run.** Zero cost at current volume, 60-minute timeout, Docker works unmodified, scale-to-zero.

---

## 5. Architecture Decision: Knowledge Base & Context

### Current Implementation (No Change Required)

The knowledge base is implemented as a set of files bundled with the application:

| File | Purpose | Size |
|---|---|---|
| `app/knowledge/system_prompt.md` | Master AI persona and instructions | ~8K tokens (110 lines) |
| `app/knowledge/red_flags.yaml` | 10 red flag rules with score caps | 128 lines |
| `app/knowledge/scoring_methodology.yaml` | Weights, tiers, binding thresholds | 84 lines |
| `app/knowledge/coverage_definitions.yaml` | 21 coverage types with key factors | 202 lines |
| `app/knowledge/report_sections.yaml` | 21-section framework definition | 130 lines |

### Why This Is Already Optimal

**Prompt Caching Economics:**

| API Call | System Prompt Cost | Savings |
|---|---|---|
| Call 1 (scoring) | 1.25x base input price (cache write) | — |
| Call 2 (narrative) | 0.10x base input price (cache read) | **90% discount** |

The 5-minute cache TTL covers both calls within a single 1-3 minute pipeline run. At 1,000 analyses/month, prompt caching saves approximately $15-30/month in API costs.

**Why alternatives were rejected:**

| Option | Assessment |
|---|---|
| Claude Projects | Web/consumer interface only. Not applicable for API usage. |
| External database (Supabase/PostgreSQL) | Knowledge base is static — changes with releases, not at runtime. A database adds latency, complexity, and a failure point for zero benefit. |
| S3-hosted knowledge files | Adds network latency to every analysis. Files are tiny (<50KB total). Ship them with the container. |

**When to reconsider:** If per-customer scoring rules or dynamic knowledge base updates become a requirement, then move rules to a database. Not needed now.

---

## 6. Architecture Decision: Document Storage

### Problem

The current application stores uploaded PDFs and generated reports in `/tmp/rhone-analyzer/`. This works for local development but fails in production:
- Cloud Run containers are ephemeral — `/tmp` is wiped between invocations
- No persistent access to generated reports after the request completes
- No way to re-download reports

### Decision: Cloudflare R2

| Factor | Detail |
|---|---|
| **API** | S3-compatible (use `boto3` with custom endpoint) |
| **Storage cost** | $0.015/GB/month (vs S3's $0.023/GB) |
| **Egress cost** | **$0** (vs S3's $0.09/GB) |
| **Free tier** | 10GB storage + 10M reads + 1M writes/month |
| **At your volume** | Effectively $0. 1,000 PDFs at ~5MB each = 5GB storage |

### Storage Layout

```
rhone-analyzer/
├── uploads/
│   └── {analysis_id}/
│       └── policy.pdf                    # Original uploaded PDF
└── reports/
    └── {analysis_id}/
        └── RhoneRisk_Analysis_{client}_{date}.pdf  # Generated report
```

### Why Not Supabase Storage?

Supabase Storage requires a Supabase project ($25/month Pro plan for production). R2 is free at this volume and doesn't couple storage to a specific backend-as-a-service vendor.

### Why Not AWS S3?

S3 charges $0.09/GB for egress. R2 charges $0. For report downloads, egress adds up. R2 is a drop-in replacement with the same API.

---

## 7. Architecture Decision: Orchestration & Queuing

### Pipeline Characteristics

| Characteristic | Implication |
|---|---|
| 1-3 minute total runtime | Too long for synchronous HTTP response |
| 3-33 jobs per day | Far too few to justify queue infrastructure |
| Single-process sufficient | No need for distributed workers |
| Bottleneck is I/O (Claude API) | Not CPU-bound, no need for worker pools |
| Users need the result (PDF) | Must support polling or webhook notification |

### Decision: FastAPI BackgroundTasks (Now)

The pattern:

```
POST /api/v1/analyze
  → Validates PDF, saves to R2
  → Creates job record in memory
  → Returns 202 Accepted + {analysis_id}
  → Kicks off BackgroundTask

BackgroundTask:
  → Runs full 6-stage pipeline
  → Uploads report PDF to R2
  → Updates job status to "completed"

GET /api/v1/analyze/{id}/status
  → Returns {status, progress, report_url}
```

**Pros:**
- Zero additional infrastructure
- Zero additional cost
- Trivially testable
- Works on any platform

**Cons:**
- Jobs lost on container crash/deploy (acceptable at 3-33 jobs/day — user can re-upload)
- Single-process only (sufficient for current volume)
- No automatic retry (easy to add in code)

### Why Not Celery + Redis?

| Celery + Redis | BackgroundTasks |
|---|---|
| $10-15/month for managed Redis | $0 |
| Separate Celery worker process (doubles compute) | Same process |
| Complex configuration, monitoring (Flower) | Zero configuration |
| Worth it at 10,000+ jobs/month | Sufficient at 3-33 jobs/day |

### Upgrade Path: Inngest

When guaranteed delivery, retries, or multi-step observability become requirements:

| Feature | Inngest |
|---|---|
| Free tier | 50,000 function runs/month (50x max volume) |
| Python SDK | Integrates directly with FastAPI |
| Retries | Built-in with configurable backoff |
| Observability | Dashboard showing pipeline step execution |
| Pro plan | $25/month if free tier exceeded |

Adopt Inngest when: (a) you need guaranteed delivery, (b) you have multiple workers, or (c) you want pipeline observability beyond logging.

---

## 8. Final Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    Google Cloud Run                               │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  FastAPI Application (app/main.py)                          │ │
│  │                                                              │ │
│  │  POST /api/v1/analyze          → 202 + {analysis_id}       │ │
│  │  GET  /api/v1/analyze/{id}/status → {status, progress}     │ │
│  │  GET  /api/v1/analyze/{id}/report → redirect to signed URL │ │
│  │  GET  /api/v1/health            → {status, version}        │ │
│  │                                                              │ │
│  │  ┌───────────────────────────────────────────────────────┐  │ │
│  │  │  BackgroundTask: AnalysisEngine.analyze_policy()      │  │ │
│  │  │                                                        │  │ │
│  │  │  1. EXTRACT   → PyMuPDF4LLM + pdfplumber             │  │ │
│  │  │  2. PARSE     → Regex metadata (11 fields)            │  │ │
│  │  │  3. SCORE     → Claude Call 1 (cached system prompt)  │  │ │
│  │  │  4. POST-PROC → Red flags, weighted score, binding    │  │ │
│  │  │  5. NARRATIVE → Claude Call 2 (cache hit, 90% off)    │  │ │
│  │  │  6. REPORT    → Jinja2 HTML → WeasyPrint PDF          │  │ │
│  │  │  7. STORE     → Upload report to R2                   │  │ │
│  │  └───────────────────────────────────────────────────────┘  │ │
│  │                                                              │ │
│  │  Knowledge Base (bundled):                                   │ │
│  │  ├── system_prompt.md (8K tokens, cached via Anthropic)     │ │
│  │  ├── red_flags.yaml (10 rules)                              │ │
│  │  ├── scoring_methodology.yaml (weights, thresholds)         │ │
│  │  ├── coverage_definitions.yaml (21 types)                   │ │
│  │  └── report_sections.yaml (21 sections)                     │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  Docker: python:3.12-slim + libcairo2 + libpango + fonts         │
│  Scaling: 0 to N instances, scale-to-zero when idle              │
│  Timeout: 60 minutes (pipeline needs ~3 min)                     │
└───────────────────┬──────────────────┬──────────────────────────┘
                    │                  │
                    ▼                  ▼
     ┌──────────────────────┐  ┌──────────────────────┐
     │   Cloudflare R2      │  │   Anthropic API      │
     │                      │  │                      │
     │   uploads/           │  │   Claude Sonnet 4.5  │
     │     {id}/policy.pdf  │  │   Prompt caching     │
     │   reports/           │  │   Extended thinking  │
     │     {id}/report.pdf  │  │   Tool-use outputs   │
     │                      │  │                      │
     │   Free tier:         │  │   ~$0.05-0.15 per    │
     │   10GB + 10M reads   │  │   analysis           │
     └──────────────────────┘  └──────────────────────┘
```

### What's NOT in this architecture (by design)

| Omitted | Reason |
|---|---|
| Frontend/CRM | API-first. Add a UI when needed. A simple form that POSTs to `/api/v1/analyze` is sufficient. |
| Database | Job state stored in-memory. At 3-33 jobs/day on a single container, this is acceptable. Add a database when you need multi-user accounts, persistent history, or audit logs. |
| Message queue | BackgroundTasks is sufficient. Add Inngest when you need guaranteed delivery. |
| Unstructured.io | PyMuPDF4LLM + pdfplumber already work. $200/month savings. |
| Redis | No caching layer needed. Each analysis is independent. |
| Sentry | Cloud Run provides built-in logging, error reporting, and request tracing via Cloud Logging and Cloud Trace. Add Sentry when you need alerting or deeper APM. |

---

## 9. Process Flow

### Happy Path: Complete Analysis

```
Client                          Cloud Run                     R2        Anthropic
  │                                │                          │            │
  │  POST /api/v1/analyze          │                          │            │
  │  {PDF + client_name + ...}     │                          │            │
  │──────────────────────────────>│                          │            │
  │                                │                          │            │
  │                                │  Validate PDF type/size  │            │
  │                                │  Generate analysis_id    │            │
  │                                │                          │            │
  │                                │  PUT uploads/{id}/       │            │
  │                                │──────────────────────────>│            │
  │                                │           OK             │            │
  │                                │<──────────────────────────│            │
  │                                │                          │            │
  │  202 Accepted                  │                          │            │
  │  {analysis_id, status:pending} │                          │            │
  │<──────────────────────────────│                          │            │
  │                                │                          │            │
  │                                │── BackgroundTask ──────────────────────
  │                                │  1. Extract PDF → markdown + tables   │
  │                                │  2. Parse metadata (regex)            │
  │                                │                          │            │
  │                                │  3. Score coverages      │            │
  │                                │  (system prompt + policy text)         │
  │                                │───────────────────────────────────────>│
  │                                │        {21 CoverageScores}            │
  │                                │<───────────────────────────────────────│
  │                                │                          │            │
  │                                │  4. Post-process scores  │            │
  │                                │  (red flags, weights, binding)        │
  │                                │                          │            │
  │                                │  5. Generate narrative   │            │
  │                                │  (system prompt from CACHE)           │
  │                                │───────────────────────────────────────>│
  │                                │        {21 ReportSections}            │
  │                                │<───────────────────────────────────────│
  │                                │                          │            │
  │                                │  6. Render HTML + PDF    │            │
  │                                │                          │            │
  │                                │  PUT reports/{id}/       │            │
  │                                │──────────────────────────>│            │
  │                                │           OK             │            │
  │                                │<──────────────────────────│            │
  │                                │                          │            │
  │                                │  Update status:completed │            │
  │                                │── End BackgroundTask ─────────────────
  │                                │                          │            │
  │  GET /status/{id}              │                          │            │
  │──────────────────────────────>│                          │            │
  │  {status:completed,            │                          │            │
  │   overall_score: 6.8,          │                          │            │
  │   binding_rec: "Bind with      │                          │            │
  │     Conditions",               │                          │            │
  │   report_url: "/report"}       │                          │            │
  │<──────────────────────────────│                          │            │
  │                                │                          │            │
  │  GET /report/{id}              │                          │            │
  │──────────────────────────────>│                          │            │
  │                                │  GET signed URL          │            │
  │                                │──────────────────────────>│            │
  │                                │  Pre-signed URL (1hr)    │            │
  │                                │<──────────────────────────│            │
  │  302 → R2 signed URL           │                          │            │
  │<──────────────────────────────│                          │            │
  │                                │                          │            │
  │  Download PDF                  │                          │            │
  │<─────────────────────────────────────────────────────────│            │
```

### Error Path: Analysis Failure

```
Client                          Cloud Run
  │                                │
  │  POST /api/v1/analyze          │
  │──────────────────────────────>│
  │  202 Accepted {id}             │
  │<──────────────────────────────│
  │                                │
  │                                │── BackgroundTask ──
  │                                │  ... Claude API error ...
  │                                │  Log error
  │                                │  Update status: "failed"
  │                                │  Store error message
  │                                │── End ──
  │                                │
  │  GET /status/{id}              │
  │──────────────────────────────>│
  │  {status: "failed",            │
  │   error: "Claude API rate      │
  │     limited after 3 retries"}  │
  │<──────────────────────────────│
```

### Polling Strategy (Client-Side)

```
Poll interval: 3 seconds for first 30 seconds, then 5 seconds
Max poll time: 5 minutes (then show "taking longer than expected" message)

Typical timeline:
  t=0s    POST /analyze → 202
  t=3s    GET /status → {status: "extracting", progress: 15}
  t=6s    GET /status → {status: "scoring", progress: 35}
  t=15s   GET /status → {status: "scoring", progress: 50}
  t=30s   GET /status → {status: "generating_narrative", progress: 70}
  t=60s   GET /status → {status: "generating_report", progress: 90}
  t=65s   GET /status → {status: "completed", progress: 100, report_url: "..."}
```

---

## 10. Codebase Changes Required

### Change 1: Make `/api/v1/analyze` Asynchronous

**Current:** Synchronous — blocks for 1-3 minutes, returns full analysis.
**Target:** Returns 202 immediately, runs pipeline in background.

**File:** `app/main.py`

**What changes:**
- `POST /api/v1/analyze` saves PDF to R2, returns `{analysis_id, status: "pending"}` with HTTP 202
- Background task runs `AnalysisEngine.analyze_policy()`
- Background task updates in-memory status dict at each pipeline stage
- Background task uploads report PDF to R2 on completion

**New endpoint:** `GET /api/v1/analyze/{id}/status` — returns current status and progress percentage

**Modified endpoint:** `GET /api/v1/analyze/{id}/report` — returns pre-signed R2 URL redirect instead of `FileResponse`

### Change 2: Add R2 Storage Client

**New file:** `app/storage/r2.py`

**What it does:**
- Wraps `boto3` S3 client configured for R2 endpoint
- `upload_file(bucket_path, file_bytes)` — upload PDF to R2
- `get_signed_url(bucket_path, expires_in=3600)` — generate pre-signed download URL
- `download_file(bucket_path)` — retrieve file bytes

**New environment variables:**
```
R2_ACCOUNT_ID=<cloudflare-account-id>
R2_ACCESS_KEY_ID=<r2-access-key>
R2_SECRET_ACCESS_KEY=<r2-secret-key>
R2_BUCKET_NAME=rhone-analyzer
```

### Change 3: Add Progress Tracking

**File:** `app/analysis/engine.py`

**What changes:**
- Accept an optional `progress_callback` parameter
- Call it at each pipeline stage with status string and progress percentage
- Status values: `extracting` (15%), `parsing` (25%), `scoring` (50%), `post_processing` (60%), `generating_narrative` (80%), `generating_report` (90%), `completed` (100%)

### Change 4: Cloud Run Configuration

**New file:** `cloudbuild.yaml` or use `gcloud run deploy --source .`

**Configuration:**
```yaml
# Cloud Run service settings
service: rhone-analyzer
region: us-central1
platform: managed
memory: 2Gi          # WeasyPrint + PDF extraction need ~1.5GB
cpu: 2               # Parallel extraction + API calls
timeout: 300s        # 5 minutes (pipeline needs ~3 min)
max-instances: 10    # Cap scaling
min-instances: 0     # Scale to zero
concurrency: 4       # Max concurrent requests per instance
```

### Change 5: Update .env.example

**Add:**
```
# Cloudflare R2
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=rhone-analyzer

# Cloud Run (set automatically)
PORT=8000
```

### Summary of Changes

| Change | Files Modified | Files Created | Effort |
|---|---|---|---|
| Async endpoint | `app/main.py` | — | ~2 hours |
| R2 storage | `app/config.py` | `app/storage/r2.py` | ~2 hours |
| Progress tracking | `app/analysis/engine.py` | — | ~1 hour |
| Cloud Run config | `Dockerfile` (minor) | — | ~1 hour |
| .env update | `.env.example` | — | ~15 min |
| Tests | `tests/test_main.py` | `tests/test_storage.py` | ~2 hours |
| **Total** | **4 files** | **2 files** | **~8 hours** |

**What doesn't change:** The entire analysis engine, ETL pipeline, Claude client, knowledge base, post-processing, scoring models, and report generator remain untouched.

---

## 11. Deployment Guide

### Prerequisites

1. Google Cloud account with billing enabled
2. Cloudflare account with R2 enabled
3. Anthropic API key

### Step 1: Create R2 Bucket

```bash
# Via Cloudflare dashboard or Wrangler CLI
# Create bucket: rhone-analyzer
# Create R2 API token with read/write access
# Note: Account ID, Access Key ID, Secret Access Key
```

### Step 2: Deploy to Cloud Run

```bash
# Authenticate
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Deploy from source (builds Docker image automatically)
gcloud run deploy rhone-analyzer \
  --source . \
  --region us-central1 \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --max-instances 10 \
  --min-instances 0 \
  --concurrency 4 \
  --set-env-vars "ANTHROPIC_API_KEY=sk-ant-xxx" \
  --set-env-vars "R2_ACCOUNT_ID=xxx" \
  --set-env-vars "R2_ACCESS_KEY_ID=xxx" \
  --set-env-vars "R2_SECRET_ACCESS_KEY=xxx" \
  --set-env-vars "R2_BUCKET_NAME=rhone-analyzer" \
  --allow-unauthenticated
```

### Step 3: Verify Deployment

```bash
# Health check
curl https://rhone-analyzer-HASH-uc.a.run.app/api/v1/health

# Expected response:
# {"status":"ok","version":"0.1.0","knowledge_base_loaded":true}
```

### Step 4: Run an Analysis

```bash
# Upload a policy PDF
curl -X POST https://rhone-analyzer-HASH-uc.a.run.app/api/v1/analyze \
  -F "file=@policy.pdf" \
  -F "client_name=Acme Corp" \
  -F "industry=Technology" \
  -F "is_msp=true"

# Response: {"analysis_id":"abc123def456","status":"pending"}

# Poll for status
curl https://rhone-analyzer-HASH-uc.a.run.app/api/v1/analyze/abc123def456/status

# Download report when completed
curl -L https://rhone-analyzer-HASH-uc.a.run.app/api/v1/analyze/abc123def456/report -o report.pdf
```

---

## 12. Cost Analysis

### Per-Analysis Cost Breakdown

| Component | Cost per Analysis | Calculation |
|---|---|---|
| Claude API (Call 1 — scoring) | ~$0.04-0.08 | ~8K input tokens (system prompt, cached write) + 50K policy text + ~4K output |
| Claude API (Call 2 — narrative) | ~$0.02-0.06 | ~8K input tokens (cache read, 90% off) + 50K policy text + ~8K output |
| Cloud Run compute | ~$0.004 | 180s x 2 vCPU x $0.0000240/vCPU-sec (if past free tier) |
| R2 storage | ~$0.0001 | 10MB stored x $0.015/GB |
| R2 operations | ~$0.000009 | 3 operations (upload PDF, upload report, download report) |
| **Total per analysis** | **~$0.06-0.14** | |

### Monthly Cost at Different Volumes

| Volume | Claude API | Cloud Run | R2 | Total |
|---|---|---|---|---|
| 100/month | $6-14 | $0 (free tier) | $0 (free tier) | **$6-14** |
| 500/month | $30-70 | $0 (free tier) | $0 (free tier) | **$30-70** |
| 1,000/month | $60-140 | $0-2 | $0 | **$60-142** |
| 5,000/month | $300-700 | $10-20 | $1 | **$311-721** |

### vs. Prior Plans at 1,000 Analyses/Month

| Line Item | Manus AI Plans | This Plan | Savings |
|---|---|---|---|
| Compute (Railway) | $15 | $0 | $15 |
| Database (Supabase) | $25 | $0 | $25 |
| Queue (Redis) | $10 | $0 | $10 |
| PDF extraction (Unstructured.io) | $200 | $0 | $200 |
| Monitoring (Sentry) | $26 | $0 | $26 |
| Frontend (Vercel) | $20 | $0 | $20 |
| Claude API | $300 | $60-140 | $160-240 |
| **Total** | **$631** | **$60-142** | **$489-571** |
| **Savings** | — | — | **78-90%** |

The savings come from two sources: (1) using free tiers instead of always-on paid services, and (2) making 2 Claude API calls instead of 20+ per analysis.

---

## 13. Growth Path

### Phase 1: Current (0-1,000 analyses/month)

```
Cloud Run + BackgroundTasks + R2 + Prompt Caching
Total cost: $6-142/month
```

- Single Cloud Run service, scale-to-zero
- In-memory job tracking
- R2 for PDF/report storage
- No database, no queue, no frontend

### Phase 2: Growth (1,000-5,000 analyses/month)

```
Add: Inngest for orchestration
Add: Cloud Run min-instances=1 (eliminate cold starts)
Add: Cloud SQL (PostgreSQL) for analysis history and audit logs
Total cost: $100-750/month
```

- Inngest provides guaranteed delivery, retries, step-level observability
- PostgreSQL stores analysis results for historical access and search
- `min-instances=1` ensures consistent response time (~$15/month)
- Consider adding a simple web UI (Next.js on Vercel, $0-20/month)

### Phase 3: Scale (5,000+ analyses/month)

```
Add: Redis for extracted text caching (avoid re-extraction)
Add: Cloud Run Jobs for batch processing
Add: Multi-region deployment
Add: Supabase or Auth0 for multi-tenant authentication
Total cost: $500-2,000/month
```

- Redis caches extracted policy text for re-analysis scenarios
- Cloud Run Jobs handle batch uploads (e.g., "analyze these 50 policies")
- Multi-region deployment reduces latency for global users
- Multi-tenant auth enables per-organization access control

### Phase 4: Enterprise (10,000+ analyses/month)

```
Add: Celery + Redis for distributed workers
Add: Benchmarking database (aggregated anonymized scores)
Add: Custom LLM fine-tuning for domain-specific accuracy
Add: SOC 2 compliance infrastructure
```

---

## Appendix A: Complete File Inventory

### Application Code

| File | Lines | Purpose |
|---|---|---|
| `app/__init__.py` | 0 | Package marker |
| `app/main.py` | 205 | FastAPI routes: health, analyze, status, download |
| `app/config.py` | 34 | pydantic-settings: API key, model, limits, paths |
| `app/analysis/__init__.py` | 0 | Package marker |
| `app/analysis/engine.py` | 144 | 6-stage pipeline orchestrator |
| `app/analysis/client.py` | 326 | Claude API: caching, retries, tool schemas, scoring, narrative |
| `app/analysis/postprocess.py` | 217 | Red flags, overall score, binding recommendation |
| `app/analysis/prompts.py` | 71 | Prompt building: metadata, scores, client context |
| `app/etl/__init__.py` | 0 | Package marker |
| `app/etl/extractor.py` | 98 | PyMuPDF4LLM markdown + pdfplumber tables |
| `app/etl/parser.py` | 77 | Regex metadata extraction (11 fields, 25 patterns) |
| `app/models/__init__.py` | 0 | Package marker |
| `app/models/requests.py` | 10 | ClientInfo Pydantic model |
| `app/models/responses.py` | 31 | API response models (status, summary, health) |
| `app/models/scoring.py` | 76 | PolicyAnalysis, CoverageScore, ScoringFactors, ReportSections, PolicyMetadata |
| `app/knowledge/__init__.py` | 0 | Package marker |
| `app/knowledge/system_prompt.md` | 110 | Master AI persona and instructions (~8K tokens) |
| `app/knowledge/red_flags.yaml` | 128 | 10 red flag rules with detection keywords and score caps |
| `app/knowledge/scoring_methodology.yaml` | 84 | Weights, tiers, binding thresholds, scoring factors |
| `app/knowledge/coverage_definitions.yaml` | 202 | 21 coverage types across 3 categories with key factors |
| `app/knowledge/report_sections.yaml` | 130 | 21-section framework definition |
| `app/report/__init__.py` | 0 | Package marker |
| `app/report/generator.py` | 110 | Jinja2 HTML rendering + WeasyPrint PDF conversion |
| `templates/report.html.j2` | 390 | Branded HTML report template (21 sections) |

### Test Code

| File | Tests | Purpose |
|---|---|---|
| `tests/__init__.py` | — | Package marker |
| `tests/conftest.py` | — | Fixtures: settings, sample policy text (91 lines), sample scores, sample analysis |
| `tests/test_engine.py` | 1 | Full pipeline integration test with mocked Claude |
| `tests/test_postprocess.py` | 8 | Score tiers, red flag caps, overall score, 4 binding recs |
| `tests/test_report.py` | 5 | Score colors, badges, HTML rendering, completeness |
| `tests/test_parser.py` | 7+ | Metadata regex extraction |
| `tests/test_extractor.py` | 5+ | PDF extraction and table formatting |

### Configuration

| File | Purpose |
|---|---|
| `Dockerfile` | python:3.12-slim + WeasyPrint deps + non-root user |
| `pyproject.toml` | hatchling build, 12 runtime deps, 5 dev deps |
| `.env.example` | Environment variable template |
| `.gitignore` | Standard Python + IDE + env ignores |

---

## Appendix B: Existing Pipeline Technical Reference

### Coverage Scoring Tool Schema (Call 1)

The Claude API is forced to return structured output matching this schema via `tool_choice`:

```json
{
  "name": "submit_coverage_scores",
  "input_schema": {
    "type": "object",
    "properties": {
      "coverage_scores": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "coverage_name": {"type": "string"},
            "coverage_category": {"type": "string", "enum": ["third_party", "first_party", "cyber_crime"]},
            "score": {"type": "integer", "minimum": 0, "maximum": 10},
            "rating": {"type": "string", "enum": ["Superior", "Average", "Basic", "No Coverage"]},
            "justification": {"type": "string"},
            "red_flags": {"type": "array", "items": {"type": "string"}},
            "scoring_factors": {
              "type": "object",
              "properties": {
                "limit_adequacy": {"type": "integer", "minimum": 0, "maximum": 10},
                "trigger_mechanism": {"type": "integer", "minimum": 0, "maximum": 10},
                "exclusion_scope": {"type": "integer", "minimum": 0, "maximum": 10},
                "sublimit_analysis": {"type": "integer", "minimum": 0, "maximum": 10},
                "waiting_period": {"type": "integer", "minimum": 0, "maximum": 10},
                "coinsurance": {"type": "integer", "minimum": 0, "maximum": 10},
                "coverage_extensions": {"type": "integer", "minimum": 0, "maximum": 10}
              }
            },
            "key_provisions": {"type": "array", "items": {"type": "string"}},
            "recommendations": {"type": "array", "items": {"type": "string"}}
          },
          "required": ["coverage_name", "coverage_category", "score", "rating", "justification", "red_flags"]
        }
      }
    },
    "required": ["coverage_scores"]
  }
}
```

### Report Narrative Tool Schema (Call 2)

```json
{
  "name": "submit_report_narrative",
  "input_schema": {
    "type": "object",
    "properties": {
      "executive_summary": {"type": "string"},
      "policy_overview": {"type": "string"},
      "coverage_scoring_matrix": {"type": "string"},
      "third_party_analysis": {"type": "string"},
      "first_party_analysis": {"type": "string"},
      "cyber_crime_analysis": {"type": "string"},
      "policy_terms_analysis": {"type": "string"},
      "exclusion_analysis": {"type": "string"},
      "sublimit_analysis": {"type": "string"},
      "gap_analysis": {"type": "string"},
      "red_flag_summary": {"type": "string"},
      "msp_specific_analysis": {"type": "string"},
      "regulatory_compliance": {"type": "string"},
      "incident_response_evaluation": {"type": "string"},
      "business_interruption_analysis": {"type": "string"},
      "social_engineering_analysis": {"type": "string"},
      "vendor_dependency_analysis": {"type": "string"},
      "benchmarking_analysis": {"type": "string"},
      "scenario_analysis": {"type": "string"},
      "recommendations": {"type": "string"},
      "binding_recommendation": {"type": "string"}
    },
    "required": [
      "executive_summary", "policy_overview", "coverage_scoring_matrix",
      "third_party_analysis", "first_party_analysis", "cyber_crime_analysis",
      "policy_terms_analysis", "exclusion_analysis", "gap_analysis",
      "red_flag_summary", "recommendations", "binding_recommendation"
    ]
  }
}
```

### Red Flag Rules Reference

| # | Red Flag | Severity | Score Cap | Affected Coverages |
|---|---|---|---|---|
| 1 | War/Terrorism Exclusion Without Buyback | Critical | 6 | All |
| 2 | Nation-State Attack Exclusion | Critical | 5 | All |
| 3 | Absolute Unencrypted Data Exclusion | Critical | 6 | Privacy, Incident Response, Regulatory |
| 4 | Ransomware Carve-Out | Critical | 5 | Extortion, BI Cyber, Data Recovery |
| 5 | BI Waiting Period >24 Hours | Major | 6 | BI Cyber, BI System Failure, Dependent BI |
| 6 | Social Engineering Sublimit <20% of Aggregate | Major | 6 | Social Engineering, Funds Transfer |
| 7 | Missing Prior Acts Coverage | Major | 6 | All |
| 8 | BIPA Exclusion | Major | 7 | Privacy, Regulatory |
| 9 | Widespread/Systemic Event Exclusion | Critical | 5 | All |
| 10 | Professional Services Exclusion (MSP) | Critical | 4 | Technology E&O, Network Security |

### Scoring Weights

| Dimension | Weight | Derived From |
|---|---|---|
| Coverage Adequacy | 40% | Average of all coverage scores |
| Limit Sufficiency | 25% | `scoring_factors.limit_adequacy` (or coverage score if absent) |
| Exclusion Analysis | 20% | `scoring_factors.exclusion_scope` (or coverage score if absent) |
| Policy Terms | 15% | Average of `trigger_mechanism`, `waiting_period`, `coinsurance` factors |

### Binding Recommendation Thresholds

| Recommendation | Overall Score | Red Flag Max | Description |
|---|---|---|---|
| Recommend Binding | >= 7.0 | 0 | Meets or exceeds standards |
| Bind with Conditions | >= 5.0 | 3 | Adequate but needs negotiation |
| Require Major Modifications | >= 3.0 | 6 | Significant gaps |
| Recommend Decline | < 3.0 | — | Fundamentally inadequate |

---

## Appendix C: Platform Research Data

### Cloud Run Free Tier (as of February 2026)

| Resource | Monthly Free Allocation | Your Usage (1,000 analyses) |
|---|---|---|
| vCPU-seconds | 180,000 | ~180,000 (100%) |
| GiB-seconds | 360,000 | ~360,000 (100%) |
| Requests | 2,000,000 | ~5,000 (0.25%) |

Overage pricing:
- vCPU: $0.00002400/vCPU-second
- Memory: $0.00000250/GiB-second
- Requests: $0.40/million

### Anthropic Claude Sonnet 4.5 Pricing (as of February 2026)

| Component | Price |
|---|---|
| Input tokens | $3.00/million |
| Output tokens | $15.00/million |
| Prompt cache write | $3.75/million (1.25x input) |
| Prompt cache read | $0.30/million (0.10x input) |

### Cloudflare R2 Free Tier

| Resource | Monthly Free Allocation |
|---|---|
| Storage | 10 GB |
| Class A operations (write) | 1,000,000 |
| Class B operations (read) | 10,000,000 |
| Egress | Unlimited (always free) |

---

*Document version 3.0. This plan supersedes all prior Manus AI development plans (v1.0 compliance-based, v2.0 proprietary scoring). The existing codebase implements the analysis engine, ETL pipeline, scoring system, and report generator. What remains is deployment and minor API modifications.*
