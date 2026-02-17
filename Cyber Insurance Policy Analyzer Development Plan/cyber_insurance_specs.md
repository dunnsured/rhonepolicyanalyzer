# RhôneRisk Cyber Insurance Policy Analyzer - Key Specifications

## Project Overview
A cyber insurance policy analysis platform that processes PDF policies, extracts data, performs AI-driven analysis, and generates comprehensive reports.

## Current Architecture
- **Frontend/CRM**: Vercel (Next.js + TypeScript)
- **Backend/Analysis**: Railway (Python + FastAPI)
- **Database**: Supabase (PostgreSQL)
- **AI**: Anthropic Claude API
- **Storage**: Supabase Storage

## Critical Gaps Identified (7 Total)
1. **No server-side analysis trigger** - relies on unreliable client-side trigger
2. **Reports not saved** - generated but not stored in Supabase Storage
3. **No webhook signature verification** - security vulnerability
4. **No report delivery mechanism** - users can't download reports
5. **No real-time progress updates** - poor UX during 1-3 min analysis
6. **Inadequate PDF extraction** - pdfplumber fails on scanned/complex docs
7. **No structured data extraction** - key policy data not parsed

## Three-Phase Implementation Plan

### Phase 1: Critical Fixes & Foundation (3-5 days) - IMMEDIATE
**Goal**: Stabilize pipeline for reliable end-to-end processing

**Tasks**:
1. **Server-side analysis trigger** - Supabase webhook → Vercel API → Railway
2. **Report delivery & storage** - Upload to Supabase Storage, add download UI
3. **Webhook signature verification** - HMAC-SHA256 on all webhooks
4. **Basic monitoring** - Sentry integration + structured logging

### Phase 2: Quality & Feature Enhancement (5-7 days) - HIGH
**Goal**: Improve data quality and analytical depth

**Tasks**:
1. **Advanced PDF extraction** - Integrate Unstructured.io API
2. **Structured data extraction** - Regex-based pre-AI extraction layer
3. **Real-time progress updates** - Supabase Realtime subscriptions
4. **Report visualizations** - Add charts (radar, bar charts) to PDFs

### Phase 3: Production Hardening & Scale (3-5 days) - MEDIUM
**Goal**: Enterprise-ready scalability and resilience

**Tasks**:
1. **Persistent job queue** - Redis + BullMQ with retry logic
2. **Rate limiting** - Tenant-based limits + usage tracking
3. **Audit logging** - Comprehensive event tracking
4. **Benchmarking** - Industry comparison database + peer analysis

## Key Technologies to Integrate
- **Unstructured.io API** - Advanced PDF/OCR extraction
- **Supabase Realtime** - WebSocket-based progress updates
- **BullMQ + Redis** - Job queue management
- **Sentry** - Error tracking and monitoring
- **ReportLab** - PDF generation with charts
- **Anthropic Claude** - AI analysis engine

## Database Schema Additions Needed
- `report_storage_path` column in `insurance_policies`
- `policy_structured_data` table (limits, dates, coverage details)
- `analysis_usage` table (token tracking, costs)
- `audit_logs` table (user/system actions)
- `industry_benchmarks` table (peer comparison data)
- `policy_peer_comparisons` table (analysis results vs benchmarks)

## Security Requirements
- HMAC-SHA256 webhook verification
- Secure secret management (env vars, not hardcoded)
- Private Supabase Storage bucket with signed URLs
- Service role key for backend operations

## User Experience Goals
- Real-time progress feedback during analysis
- One-click report download
- Visual charts in reports (radar, bar charts)
- Peer comparison insights
- Multi-format report export capability

## Scalability Requirements
- Persistent job queue (survives restarts)
- Retry logic (3 attempts + dead letter queue)
- Rate limiting (100 analyses/tenant/day)
- Cost controls and usage tracking
- Comprehensive monitoring and logging
