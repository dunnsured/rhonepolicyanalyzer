# RhôneRisk Cyber Insurance Policy Analyzer
## Comprehensive Development Plan & Implementation Strategy

**Prepared by:** Manus AI  
**Date:** February 16, 2026  
**Version:** 1.0

---

## Executive Summary

This document presents a comprehensive development plan for the RhôneRisk Cyber Insurance Policy Analyzer, a platform designed to automate the evaluation of cyber insurance policies through AI-driven analysis. The system will extract data from complex PDF documents, assess coverage against industry-standard frameworks, identify critical gaps, and generate detailed reports with actionable recommendations. The development will proceed through three carefully structured phases over an estimated 11-17 days, transforming the existing prototype into an enterprise-ready platform capable of handling high-volume workloads with consistent accuracy and reliability.

The proposed architecture leverages cutting-edge technologies including Anthropic's Claude for natural language understanding, Unstructured.io for advanced document processing, and Supabase for real-time data management. By integrating industry-standard frameworks such as the NIST Cybersecurity Framework, CMMC, and CIS Controls, the analyzer will provide quantitative risk scores and peer benchmarking capabilities that enable organizations to make data-driven decisions about their cyber insurance coverage.

---

## 1. Project Overview & Objectives

### 1.1. Business Context

The cyber insurance market has experienced explosive growth, expanding from $3.15 billion in 2019 to a projected $20+ billion by 2025. As organizations face increasingly sophisticated cyber threats, the need for comprehensive policy evaluation has become critical. However, the complexity of insurance documents, combined with the technical nature of cybersecurity frameworks, creates significant challenges for manual analysis. The RhôneRisk Policy Analyzer addresses this gap by automating the evaluation process, ensuring consistent analysis quality while dramatically reducing the time required for policy review.

### 1.2. Strategic Objectives

The development plan is structured around five core objectives that align with both immediate operational needs and long-term strategic goals:

**Stabilize the Platform** by addressing seven critical gaps in the existing infrastructure, including unreliable analysis triggers, missing report delivery mechanisms, and inadequate security controls. This foundational work will create a reliable end-to-end pipeline capable of processing policies from upload through final report delivery.

**Enhance Data Quality** through the integration of advanced PDF extraction technologies. The current `pdfplumber` implementation struggles with scanned documents and complex layouts, leading to incomplete or inaccurate data extraction. By implementing Unstructured.io as the primary extraction engine with intelligent fallback mechanisms, the system will achieve significantly higher accuracy across diverse document types.

**Increase Analytical Depth** by implementing industry-standard evaluation frameworks and quantitative scoring methodologies. The analyzer will assess policies against the NIST Cybersecurity Framework, Cybersecurity Maturity Model Certification (CMMC), and CIS Controls, providing organizations with objective measurements of their coverage adequacy and specific recommendations for improvement.

**Improve User Experience** through real-time progress updates, intuitive report delivery mechanisms, and rich data visualizations. Users will receive immediate feedback during the analysis process and access professionally formatted reports that combine detailed textual analysis with visual representations of key metrics.

**Ensure Scalability & Security** by implementing enterprise-grade infrastructure components including persistent job queues, rate limiting, comprehensive audit logging, and robust monitoring systems. These capabilities will enable the platform to handle increased load while maintaining security and compliance requirements.

---

## 2. System Architecture

### 2.1. Architectural Overview

The proposed architecture implements an event-driven, microservices-based design that separates concerns while maintaining tight integration between components. The system consists of three primary layers: the presentation layer (Vercel CRM), the orchestration layer (Supabase), and the processing layer (Railway API). This separation enables independent scaling, simplified maintenance, and improved fault isolation.

The architecture follows a clear data flow pattern. When a user uploads a policy document through the CRM interface, the file is stored in Supabase Storage and a database record is created. A Supabase webhook immediately triggers a server-side function that initiates the analysis pipeline. This approach eliminates the reliability issues associated with client-side triggers and ensures that every uploaded policy is processed regardless of user navigation behavior.

### 2.2. Component Architecture

**Frontend Layer (Vercel CRM)** serves as the primary user interface, built with Next.js and TypeScript. This component handles policy uploads, displays real-time analysis progress through Supabase Realtime subscriptions, and provides secure report download functionality. The CRM integrates with Supabase for authentication, database operations, and file storage, while exposing API endpoints for webhook handling and job dispatch.

**Database & Storage Layer (Supabase)** provides comprehensive backend services including PostgreSQL database management, authentication, file storage, and real-time pub/sub capabilities. The database schema includes tables for policy metadata, structured data extraction results, analysis usage tracking, audit logs, and industry benchmarks. Supabase Storage hosts both uploaded policy documents and generated reports in separate buckets with appropriate security policies.

**Analysis Engine (Railway API)** implements the core processing logic using Python and FastAPI. This component orchestrates the entire analysis workflow, from PDF extraction through AI-powered evaluation to report generation. The engine integrates with multiple external services including Unstructured.io for document processing, Anthropic Claude for intelligent analysis, and Supabase for data persistence and status updates.

**Job Queue System (BullMQ + Redis)** provides persistent, reliable job management with automatic retry capabilities. This component will be introduced in Phase 3 to replace the current in-memory job tracking, ensuring that analysis jobs survive system restarts and can be retried in case of transient failures. The queue implements a dead-letter queue pattern for handling permanently failed jobs.

### 2.3. Data Flow Architecture

The complete analysis workflow proceeds through seven distinct stages, each with specific responsibilities and error handling mechanisms:

**Upload & Ingestion** begins when a user uploads a policy PDF through the CRM. The file is stored in Supabase Storage with a unique identifier, and a corresponding record is created in the `insurance_policies` table with status `pending`. A Supabase database trigger immediately fires, invoking a webhook to the Vercel API endpoint.

**Trigger & Dispatch** occurs when the Vercel webhook endpoint receives the notification, validates the request signature for security, and either dispatches the job directly to the Railway API (Phase 1-2) or enqueues it in BullMQ (Phase 3). The policy status is updated to `queued`.

**PDF Extraction** represents the first processing stage, where the Railway API retrieves the policy document from Supabase Storage and attempts extraction using Unstructured.io. If this fails or produces low-quality results, the system automatically falls back to `pdfplumber`. The extracted text and any identified structural elements (tables, headers) are stored temporarily. Status updates to `extracting_data`.

**Structured Data Parsing** applies regex-based extraction patterns to identify and extract key policy attributes including coverage limits, effective dates, deductibles, policy numbers, and covered events. This structured data is stored in the `policy_structured_data` table and will be used to enrich the AI analysis prompts. Status updates to `parsing_data`.

**AI-Powered Analysis** leverages Anthropic's Claude API to perform deep semantic analysis of the policy document. The analysis evaluates coverage against NIST CSF, CMMC, and CIS Controls frameworks, assigns maturity scores across multiple domains, identifies specific gaps and vulnerabilities, and generates actionable recommendations. The structured data extracted in the previous stage is injected into the prompt to provide context. Status updates to `analyzing_policy`.

**Report Generation** uses `reportlab` to create a comprehensive PDF report that includes an executive summary, detailed coverage analysis, maturity scoring across framework domains, gap analysis with prioritized recommendations, and data visualizations including radar charts and peer comparison graphs. The generated report is uploaded to the Supabase Storage `reports` bucket. Status updates to `generating_report`.

**Delivery & Notification** completes the workflow by updating the policy record with the report storage path and final status `completed`. The CRM interface, which has been subscribing to real-time updates via Supabase Realtime, immediately displays the download button. Users can generate a signed URL and download the report securely.

### 2.4. Security Architecture

Security is implemented through multiple layers of defense. All webhook communications are protected with HMAC-SHA256 signature verification, preventing unauthorized access to internal APIs. Supabase Storage buckets use row-level security policies to ensure users can only access their own organization's documents and reports. API keys and secrets are stored in environment variables and never hardcoded. All external API communications use HTTPS, and sensitive data is encrypted at rest in the database.

---

## 3. Technology Stack & Rationale

### 3.1. Core Technologies

The technology stack has been carefully selected to balance performance, reliability, developer productivity, and cost-effectiveness. Each component addresses specific technical requirements while maintaining compatibility with the overall architecture.

**Anthropic Claude API** serves as the primary AI analysis engine. Claude was selected over alternatives due to its exceptional performance on long-context document analysis, nuanced understanding of technical and legal language, and reliable structured output generation. The API provides token-level usage tracking, enabling precise cost monitoring and allocation. Claude's ability to process documents up to 200,000 tokens allows for comprehensive analysis of even lengthy policy documents without chunking.

**Unstructured.io API** provides state-of-the-art PDF extraction capabilities that significantly outperform traditional OCR solutions. The service uses a combination of computer vision, machine learning, and natural language processing to accurately extract text from complex layouts including multi-column documents, nested tables, and scanned images. Unstructured.io preserves document structure, identifies semantic elements (headers, footers, captions), and handles multilingual content. This capability is critical for insurance documents, which frequently contain complex tabular data and may include scanned signatures or amendments.

**Supabase** offers a comprehensive backend-as-a-service platform that accelerates development while providing enterprise-grade capabilities. The platform combines PostgreSQL database management, authentication, file storage, and real-time pub/sub functionality in a unified API. Supabase's real-time capabilities enable live progress updates without complex WebSocket infrastructure. The platform's row-level security policies provide fine-grained access control, and its automatic API generation reduces boilerplate code. Supabase also offers built-in database webhooks, eliminating the need for separate event processing infrastructure.

**Railway** provides a flexible deployment platform for the Python-based analysis engine. Railway offers automatic scaling, built-in monitoring, simple environment variable management, and seamless integration with GitHub for continuous deployment. The platform's pay-per-use pricing model aligns costs with actual usage, making it cost-effective for variable workloads.

**BullMQ & Upstash Redis** implement a robust, persistent job queue system. BullMQ provides advanced features including job prioritization, delayed jobs, automatic retries with exponential backoff, job progress tracking, and dead-letter queue handling. Upstash Redis offers a serverless Redis implementation with automatic scaling and per-request pricing, eliminating the operational overhead of managing Redis infrastructure.

**Sentry** delivers comprehensive error tracking and performance monitoring. The platform provides real-time error notifications, detailed stack traces with source code context, performance profiling, and user impact analysis. Sentry's integrations with both TypeScript and Python enable consistent monitoring across the entire stack.

### 3.2. Supporting Technologies

**ReportLab** generates professional PDF reports with precise layout control. The library supports advanced features including custom fonts, vector graphics, charts, and tables. ReportLab's drawing API enables the creation of custom visualizations such as radar charts and bar graphs directly within the PDF generation process.

**Supabase JavaScript Client** provides type-safe database access, authentication, storage operations, and real-time subscriptions in the Next.js frontend. The client automatically handles connection management, authentication token refresh, and error handling.

**FastAPI** implements the Python backend API with automatic OpenAPI documentation, request validation using Pydantic models, and high performance through async/await support. FastAPI's dependency injection system simplifies the implementation of authentication, logging, and error handling middleware.

**Structlog** provides structured logging capabilities in Python, enabling consistent, machine-parsable log output. Structured logs include contextual information such as policy IDs, tenant IDs, and processing stages, facilitating debugging and operational monitoring.

---

## 4. Phased Implementation Plan

### 4.1. Phase 1: Critical Fixes & Foundation (3-5 days)

Phase 1 focuses exclusively on resolving the seven critical gaps that prevent the current system from functioning reliably. This phase establishes a stable foundation for subsequent enhancements.

#### Task 1.1: Implement Server-Side Analysis Trigger

**Problem**: The current client-side trigger is unreliable and fails silently if the user navigates away from the page before the analysis completes.

**Solution**: Implement a Supabase database trigger that automatically invokes a webhook when a new policy is inserted.

**Implementation Steps**:

Create a new API endpoint at `src/app/api/policies/auto-analyze/route.ts` in the Vercel CRM. This endpoint will receive webhook notifications from Supabase, validate the request signature, extract the policy ID from the payload, and dispatch the analysis job to the Railway API using the same logic as the existing manual trigger endpoint.

Develop a PostgreSQL function using PL/pgSQL that performs an HTTP POST request to the Vercel webhook endpoint. The function will be triggered automatically after each insert to the `insurance_policies` table. The function will include the webhook secret in the request headers for signature verification.

Create a database migration file at `supabase/migrations/YYYYMMDDHHMMSS_add_auto_analyze_trigger.sql` that defines both the trigger function and the trigger itself. The trigger will fire `AFTER INSERT` for each row, ensuring that every new policy automatically enters the analysis pipeline.

Remove the client-side automatic trigger from `insurance-policies-section.tsx` to prevent duplicate analysis requests. Retain the manual "Analyze" button for re-analysis scenarios.

**Expected Outcome**: Every uploaded policy will automatically enter the analysis pipeline without user intervention, and the process will continue even if the user closes their browser.

#### Task 1.2: Fix Report Delivery & Storage

**Problem**: Reports are generated by the Railway API but are not saved to persistent storage or made available to users.

**Solution**: Configure the Railway API to upload generated reports to Supabase Storage and update the CRM to provide download functionality.

**Implementation Steps**:

Create a new private storage bucket named `reports` in the Supabase dashboard. Configure row-level security policies to ensure users can only access reports belonging to their organization.

Add a new column `report_storage_path` to the `insurance_policies` table using a migration file. This column will store the path to the generated report in Supabase Storage.

Install the `supabase-py` library in the Railway API and configure the Supabase client using environment variables `SUPABASE_URL` and `SUPABASE_KEY` (service role key). After report generation in `orchestrator.py`, upload the PDF file to the `reports` bucket using a path format like `{tenant_id}/{policy_id}/report.pdf`.

Modify the callback payload sent from the Railway API to include the `report_storage_path`. Update the Vercel webhook handler at `/api/webhook/analysis-complete/route.ts` to save this path to the database.

Add a download button to the policy list in `insurance-policies-section.tsx`. When clicked, the button will generate a signed URL for the report using the Supabase client and open it in a new tab. The signed URL will be valid for a limited time (e.g., 1 hour) for security.

**Expected Outcome**: Users will be able to download completed analysis reports directly from the CRM interface, and reports will be securely stored with proper access controls.

#### Task 1.3: Enforce Webhook Signature Verification

**Problem**: Webhook endpoints do not verify request signatures, creating a security vulnerability that could allow unauthorized parties to trigger analyses or inject false completion notifications.

**Solution**: Implement HMAC-SHA256 signature verification on all webhook endpoints.

**Implementation Steps**:

In the Railway API's `webhook.py`, implement a signature verification function that computes the HMAC-SHA256 hash of the request body using the shared secret and compares it to the signature provided in the request headers. Apply this verification as a FastAPI dependency to the `/webhook/policy-uploaded` endpoint.

In the Vercel CRM's `/api/webhook/analysis-complete/route.ts`, implement equivalent signature verification using Node.js's built-in `crypto` module. Reject requests with invalid or missing signatures with a 401 Unauthorized response.

Ensure the shared webhook secret is stored in environment variables (`WEBHOOK_SECRET`) in both Railway and Vercel, and is sufficiently long and random (minimum 32 bytes). Document the secret management process for future team members.

**Expected Outcome**: All webhook communications will be cryptographically authenticated, preventing unauthorized access to internal APIs.

#### Task 1.4: Set Up Basic Monitoring and Logging

**Problem**: The current system provides no visibility into errors, performance issues, or operational metrics, making debugging and maintenance extremely difficult.

**Solution**: Integrate Sentry for error tracking and implement structured logging throughout the application.

**Implementation Steps**:

Create Sentry projects for both the Vercel CRM (TypeScript) and Railway API (Python). Install the respective Sentry SDKs and initialize them with the appropriate DSN values stored in environment variables.

Configure Sentry to capture unhandled exceptions, API errors, and performance data. Set up error grouping rules and notification channels (e.g., Slack, email) for critical errors.

Implement structured logging in the Railway API using `structlog`. Configure log output to include contextual information such as `policy_id`, `tenant_id`, `analysis_stage`, and `timestamp`. Log key events including analysis start, extraction completion, AI analysis completion, report generation, and errors.

In the Vercel CRM, implement similar structured logging for API endpoints, capturing request IDs, user IDs, and operation types.

**Expected Outcome**: The development team will have real-time visibility into system errors and performance issues, enabling rapid diagnosis and resolution of problems.

### 4.2. Phase 2: Quality & Feature Enhancement (5-7 days)

Phase 2 focuses on dramatically improving the quality of data extraction and the depth of analytical insights, while also enhancing the user experience through real-time feedback and richer report visualizations.

#### Task 2.1: Integrate Advanced PDF Extraction

**Problem**: The current `pdfplumber` implementation fails on scanned documents and struggles with complex layouts, leading to incomplete or inaccurate data extraction.

**Solution**: Integrate Unstructured.io API as the primary extraction strategy with fallback to `pdfplumber`.

**Implementation Steps**:

Create a new class `EnhancedPDFExtractor` in the Railway API that implements a multi-strategy extraction approach. The class will first attempt extraction using the Unstructured.io API, which provides superior OCR and layout analysis capabilities.

Implement the `extract_from_url` method that downloads the PDF from Supabase Storage, sends it to Unstructured.io with appropriate parameters (including element detection for tables and headers), and processes the returned structured data.

If Unstructured.io fails (due to API errors, timeouts, or quality issues), automatically fall back to the existing `pdfplumber` implementation. Log the fallback event for monitoring purposes.

Adapt downstream code to handle the richer output format from Unstructured.io, particularly for tables and document structure. Preserve this structural information for use in the AI analysis phase.

Store the Unstructured.io API key securely in Railway environment variables and implement usage tracking to monitor costs.

**Expected Outcome**: The system will successfully extract text from scanned documents and complex layouts with significantly higher accuracy, reducing analysis errors caused by poor data quality.

#### Task 2.2: Implement Structured Data Extraction

**Problem**: Critical policy information such as coverage limits, effective dates, and deductibles is buried in unstructured text and not explicitly used in the analysis, reducing analytical accuracy.

**Solution**: Create a regex-based pre-AI extraction layer that identifies and extracts key policy attributes.

**Implementation Steps**:

Create a new database table `policy_structured_data` with columns for common policy fields including `coverage_limit`, `deductible`, `effective_date`, `expiration_date`, `policy_number`, `covered_events`, and `exclusions`. Include a JSON column for additional extracted fields.

Develop a `StructuredDataExtractor` class in the Railway API that implements regex patterns for each field type. The patterns will be designed to handle common formatting variations (e.g., different date formats, currency representations).

Integrate the extractor into `orchestrator.py` immediately after text extraction. The extractor will process the raw text, identify matching patterns, and save the results to the `policy_structured_data` table.

Modify the Claude analysis prompts in `claude_analyzer.py` to fetch the structured data and inject it into the prompt as a structured context section. This will provide the AI with explicit access to key policy attributes, improving analysis accuracy.

Implement validation logic to flag extracted values that seem anomalous (e.g., coverage limits that are unusually high or low) for manual review.

**Expected Outcome**: The AI analysis will have explicit access to key policy attributes, enabling more accurate and detailed evaluation of coverage adequacy.

#### Task 2.3: Implement Real-Time Progress Updates

**Problem**: The UI provides no feedback during the 1-3 minute analysis process, creating a poor user experience and leading users to believe the system has failed.

**Solution**: Use Supabase Realtime to push status updates from the backend to the frontend.

**Implementation Steps**:

Enable Realtime replication for the `insurance_policies` table in the Supabase dashboard. Configure replication to include the `analysis_status` and `analysis_progress` columns.

Modify `orchestrator.py` in the Railway API to update the policy's `analysis_status` field at each major processing stage: `extracting_data`, `parsing_data`, `analyzing_policy`, `generating_report`. Also update an `analysis_progress` field with a percentage value (0-100).

In the CRM's `insurance-policies-section.tsx`, implement a Supabase Realtime subscription that listens for `UPDATE` events on the policy record. When status or progress changes are received, update the UI to display the current stage and a progress bar.

Implement a timeout mechanism that alerts the user if the analysis takes longer than expected (e.g., 5 minutes), suggesting they check back later or contact support.

**Expected Outcome**: Users will receive real-time feedback during the analysis process, improving perceived performance and reducing support inquiries about "stuck" analyses.

#### Task 2.4: Enhance Report with Visualizations

**Problem**: The current text-heavy reports lack visual impact and make it difficult for users to quickly grasp key insights.

**Solution**: Add charts and graphs to the PDF reports using `reportlab`.

**Implementation Steps**:

Create charting functions in `report_generator.py` that generate `reportlab` Drawing objects for two primary visualizations: a maturity radar chart showing scores across NIST CSF, CMMC, and CIS Controls domains, and a coverage comparison bar chart showing the policy's scores against industry benchmarks.

Integrate these chart objects into the `SimpleDocTemplate` flow, positioning the radar chart in the executive summary section and the comparison chart in the coverage analysis section.

Design the charts with professional styling including the RhôneRisk brand colors (navy and cyan), clear axis labels, and legends. Ensure the charts are readable when printed in grayscale.

For the comparison chart, implement the initial version of the benchmarking database (a simplified version of Task 3.4) with representative industry data. This data will be refined in Phase 3.

Test the report generation with various policy types to ensure charts render correctly and provide meaningful insights.

**Expected Outcome**: Reports will include professional data visualizations that enable users to quickly understand their policy's strengths and weaknesses relative to industry standards.

### 4.3. Phase 3: Production Hardening & Scale (3-5 days)

Phase 3 focuses on making the platform resilient, scalable, and observable, ensuring it can handle enterprise-level workloads and meet stringent security and compliance requirements.

#### Task 3.1: Implement a Persistent Job Queue

**Problem**: The current in-memory job tracking in Railway is lost on restart, and there is no automatic retry logic for failed analyses.

**Solution**: Implement a Redis-backed job queue using BullMQ.

**Implementation Steps**:

Create a new Upstash Redis database and obtain the connection URL and credentials.

Create a new Node.js service (either standalone on Railway or integrated into the Vercel Next.js app) that implements a BullMQ worker. This worker will listen for analysis jobs and dispatch them to the Railway API.

Refactor the Vercel `auto-analyze` endpoint to add jobs to the BullMQ queue instead of directly calling the Railway API. Include all necessary job data (policy ID, tenant ID, callback URL) in the job payload.

Configure BullMQ with a retry policy (3 attempts with exponential backoff) and a dead-letter queue for jobs that fail permanently. Implement monitoring for the dead-letter queue to alert the team of persistent failures.

Update the Railway API to report job progress back to BullMQ, enabling the queue to track job status and provide visibility into processing times.

**Expected Outcome**: Analysis jobs will survive system restarts, failed jobs will be automatically retried, and the team will have visibility into job queue metrics and failures.

#### Task 3.2: Implement Rate Limiting and Cost Controls

**Problem**: There are no controls on API usage, potentially leading to abuse and unexpectedly high costs from AI API usage.

**Solution**: Implement tenant-based rate limiting and usage tracking.

**Implementation Steps**:

Create a new database table `analysis_usage` with columns for tracking token consumption, API costs, and analysis counts per tenant and time period.

Modify `claude_analyzer.py` to capture token usage data from the Anthropic API response and save it to the `analysis_usage` table after each analysis.

Implement rate limiting in the Vercel API layer using `@upstash/ratelimit`. Configure a sliding window rate limit (e.g., 100 analyses per tenant per day) that prevents excessive usage.

Create an admin dashboard view that displays usage statistics per tenant, enabling the business team to monitor costs and identify potential abuse.

Implement soft and hard limits: soft limits trigger email notifications to the tenant, while hard limits temporarily block new analyses until the next time window.

**Expected Outcome**: The platform will have controls to prevent cost overruns and abuse, while providing visibility into usage patterns for business planning.

#### Task 3.3: Implement Comprehensive Audit Logging

**Problem**: There is no audit trail for user and system actions, making it difficult to investigate issues or meet compliance requirements.

**Solution**: Create an audit logging system that captures all critical events.

**Implementation Steps**:

Create a new database table `audit_logs` with columns for timestamp, user ID, tenant ID, action type, resource ID, and metadata (JSON).

Create a helper function `log_audit_event` in the Vercel API that inserts records into the audit logs table. Design the function to be non-blocking (fire-and-forget) to avoid impacting API performance.

Integrate audit logging into key API endpoints including policy upload, analysis trigger, report download, user login/logout, and administrative actions.

Implement a searchable audit log viewer in the admin interface that allows filtering by user, tenant, action type, and date range.

Configure automatic retention policies to archive old audit logs after a specified period (e.g., 1 year) while maintaining compliance with data retention requirements.

**Expected Outcome**: The platform will maintain a comprehensive audit trail of all user and system actions, supporting compliance requirements and incident investigation.

#### Task 3.4: Introduce Benchmarking and Peer Comparison

**Problem**: Analysis lacks context; scores are not compared against industry baselines, making it difficult for users to understand whether their coverage is adequate.

**Solution**: Create a benchmarking database and add peer comparison features to the analysis.

**Implementation Steps**:

Create database tables `industry_benchmarks` (storing aggregate statistics by industry and company size) and `policy_peer_comparisons` (storing individual policy comparisons).

Develop a `generate_peer_comparison` function in the Railway API that retrieves relevant benchmark data based on the policy's industry and organization size, compares the policy's scores against these benchmarks, and identifies areas where the policy significantly underperforms or overperforms.

Integrate the peer comparison function into `orchestrator.py` to run automatically after the main analysis completes. Store the comparison results in the database.

Add a new "Peer Comparison" section to the PDF report that presents the comparison data using the bar chart visualization developed in Phase 2. Include narrative explanations of significant differences.

Implement a data collection mechanism that anonymizes and aggregates analysis results to continuously improve the benchmark database over time (with appropriate user consent and privacy protections).

**Expected Outcome**: Users will be able to understand their policy's adequacy relative to industry peers, enabling more informed decision-making about coverage improvements.

---

## 5. Policy Analysis Framework

### 5.1. Evaluation Frameworks

The analyzer will implement a comprehensive evaluation methodology based on three industry-standard frameworks that collectively provide a holistic assessment of cyber insurance policy adequacy.

**NIST Cybersecurity Framework (CSF)** provides the foundational structure for risk management evaluation. The framework's five core functions—Identify, Protect, Detect, Respond, and Recover—map directly to essential insurance coverage areas. The analyzer will assess whether the policy provides adequate coverage for each function, using the NIST CSF's four implementation tiers (Partial, Risk Informed, Repeatable, Adaptive) as a maturity scale. For example, a policy that covers incident response but only for specific types of incidents would be rated as "Risk Informed," while comprehensive coverage with proactive risk management would achieve "Adaptive" status.

**Cybersecurity Maturity Model Certification (CMMC)** provides a structured approach to evaluating the maturity of cybersecurity practices covered by the policy. CMMC's three levels—Basic Cyber Hygiene (Level 1), Intermediate Cyber Hygiene (Level 2), and Good Cyber Hygiene (Level 3)—enable granular assessment of control implementation. The analyzer will map policy coverage to CMMC practices and determine the highest level of maturity supported by the policy terms. This assessment is particularly valuable for organizations in regulated industries or those working with government contracts.

**CIS Controls** offer a prioritized set of 20 critical security controls that represent the most effective defenses against common cyber attacks. The analyzer will evaluate whether the policy provides coverage for incidents resulting from failures in each control area. For example, the policy will be assessed on whether it covers losses from inadequate access control (CIS Control 6), data recovery issues (CIS Control 11), or security awareness failures (CIS Control 14). The CIS Controls assessment provides actionable insights into specific security gaps that may not be adequately covered by the current policy.

### 5.2. Scoring Methodology

The analyzer implements a standardized 1-5 maturity scale that provides consistent, objective measurements across all evaluation dimensions. This scale enables quantitative comparison and trend analysis over time.

**Level 1 (Initial)** represents ad-hoc or chaotic coverage where policies provide minimal protection with significant exclusions and limitations. Coverage may be reactive rather than proactive, and terms may be vague or inconsistent. Organizations at this level face substantial uninsured risk.

**Level 2 (Repeatable)** indicates that basic coverage exists and is documented, but implementation is inconsistent. Policies at this level may cover major incidents but lack provisions for emerging threats or have significant gaps in coverage areas. There may be limited coordination between different coverage components.

**Level 3 (Defined)** represents standardized coverage that is well-documented and consistently applied. Policies at this level provide comprehensive coverage for known risks, with clear terms and reasonable limits. Coverage aligns with industry standards and addresses most common cyber incidents.

**Level 4 (Managed)** indicates that coverage is not only comprehensive but also measured and controlled. Policies at this level include provisions for risk assessment, proactive risk management, and continuous monitoring. Coverage limits are based on quantitative risk analysis, and policies include mechanisms for adapting to changing threat landscapes.

**Level 5 (Optimized)** represents the highest level of maturity, where coverage is continuously improved based on lessons learned and emerging threats. Policies at this level include innovative coverage options, incentives for security improvements, and integration with broader risk management strategies. Organizations at this level have achieved alignment between insurance coverage and overall cybersecurity posture.

### 5.3. Gap Analysis Methodology

The gap analysis component identifies specific deficiencies in policy coverage that expose organizations to uninsured risk. Based on research into common policy gaps and regulatory frameworks, the analyzer will systematically check for seven critical gap categories.

**Untested Controls** represent a significant source of hidden risk. Many policies include coverage for incident response or business continuity, but if these capabilities have never been tested, they may fail when needed. The analyzer will flag policies that lack provisions for regular testing or validation of covered controls.

**Incomplete Assessments** occur when policies are based on outdated or partial risk assessments. The analyzer will identify cases where coverage does not align with the organization's current technology environment, business model, or threat landscape.

**Low Maturity Levels** indicate that the policy fails to meet minimum industry standards for coverage adequacy. Based on research indicating that Level 2 (Risk Score 3.0) represents the minimum acceptable standard, the analyzer will flag policies that fall below this threshold and recommend specific improvements.

**IAM Vulnerabilities** represent a critical gap area, as identity and access management failures are a leading cause of cyber incidents. The analyzer will assess whether the policy provides adequate coverage for identity theft, credential compromise, privilege escalation, and insider threats.

**Risk Outside Appetite** occurs when the policy's coverage limits or exclusions expose the organization to risks that exceed its stated risk tolerance. The analyzer will compare coverage limits to potential loss scenarios and flag cases where the gap is significant.

**Control Insufficiencies** identify specific security controls that are inadequately addressed by the policy. This includes gaps in coverage for monitoring and detection, insufficient response capabilities, or lack of coverage for supply chain risks.

**Emerging Threat Gaps** highlight areas where the policy has not been updated to address new attack vectors or threat scenarios. This includes coverage for ransomware, supply chain attacks, cloud security incidents, and AI-related risks.

### 5.4. Benchmarking Methodology

The benchmarking component provides critical context by comparing the analyzed policy against industry standards and peer organizations. This comparison enables organizations to understand whether their coverage is adequate relative to similar organizations facing similar risks.

Benchmarks will be segmented by industry sector, organization size, geographic region, and risk profile. For example, a healthcare organization with 500 employees will be compared against other mid-sized healthcare organizations rather than against the entire market. This segmentation ensures that comparisons are meaningful and actionable.

The benchmarking database will initially be populated with representative data derived from industry research and publicly available information. As the platform processes more policies, the database will be continuously enriched with anonymized, aggregated data from actual analyses (with appropriate user consent). This approach ensures that benchmarks remain current and reflect real-world coverage patterns.

Benchmark comparisons will highlight both strengths and weaknesses. If a policy significantly exceeds industry standards in certain areas, this will be noted as a potential opportunity to reduce costs without sacrificing protection. Conversely, areas where the policy falls significantly below peer standards will be flagged as high-priority gaps requiring attention.

---

## 6. Database Schema Design

### 6.1. Core Tables

The database schema extends the existing `insurance_policies` table and introduces several new tables to support enhanced functionality.

**insurance_policies** (modified) retains all existing columns and adds `report_storage_path` (TEXT) to store the Supabase Storage path to the generated report, `analysis_progress` (INTEGER) to track completion percentage for real-time updates, and `structured_data_extracted` (BOOLEAN) to indicate whether structured data extraction has been completed.

**policy_structured_data** (new) stores extracted key-value pairs from policy documents. Columns include `id` (UUID, primary key), `policy_id` (UUID, foreign key to insurance_policies), `coverage_limit` (NUMERIC), `deductible` (NUMERIC), `effective_date` (DATE), `expiration_date` (DATE), `policy_number` (TEXT), `covered_events` (TEXT[]), `exclusions` (TEXT[]), `additional_data` (JSONB for flexible storage of other extracted fields), and `extraction_confidence` (NUMERIC, 0-1 scale indicating confidence in extracted values).

**analysis_usage** (new) tracks API usage and costs for monitoring and billing purposes. Columns include `id` (UUID, primary key), `policy_id` (UUID, foreign key), `tenant_id` (UUID), `analysis_timestamp` (TIMESTAMP), `tokens_input` (INTEGER), `tokens_output` (INTEGER), `tokens_total` (INTEGER), `estimated_cost` (NUMERIC), `model_used` (TEXT), and `processing_time_seconds` (INTEGER).

**audit_logs** (new) maintains a comprehensive audit trail. Columns include `id` (UUID, primary key), `timestamp` (TIMESTAMP), `user_id` (UUID), `tenant_id` (UUID), `action_type` (TEXT, e.g., 'policy_upload', 'analysis_trigger', 'report_download'), `resource_id` (UUID), `resource_type` (TEXT), `metadata` (JSONB for additional context), and `ip_address` (INET).

**industry_benchmarks** (new) stores aggregate statistics for peer comparison. Columns include `id` (UUID, primary key), `industry_sector` (TEXT), `organization_size` (TEXT, e.g., 'small', 'medium', 'large'), `geographic_region` (TEXT), `framework` (TEXT, e.g., 'NIST_CSF', 'CMMC', 'CIS'), `domain` (TEXT, specific framework domain), `average_score` (NUMERIC), `percentile_25` (NUMERIC), `percentile_50` (NUMERIC), `percentile_75` (NUMERIC), `sample_size` (INTEGER), and `last_updated` (TIMESTAMP).

**policy_peer_comparisons** (new) stores individual policy comparison results. Columns include `id` (UUID, primary key), `policy_id` (UUID, foreign key), `framework` (TEXT), `domain` (TEXT), `policy_score` (NUMERIC), `benchmark_average` (NUMERIC), `percentile_rank` (NUMERIC), `comparison_category` (TEXT, e.g., 'above_average', 'below_average', 'significantly_below'), and `generated_at` (TIMESTAMP).

### 6.2. Indexes and Performance Optimization

To ensure optimal query performance, the following indexes will be created:

- `idx_policies_tenant_status` on `insurance_policies(tenant_id, analysis_status)` for efficient filtering of policies by organization and status.
- `idx_structured_data_policy` on `policy_structured_data(policy_id)` for fast retrieval of extracted data.
- `idx_usage_tenant_date` on `analysis_usage(tenant_id, analysis_timestamp)` for usage reporting queries.
- `idx_audit_tenant_action_date` on `audit_logs(tenant_id, action_type, timestamp)` for audit log searches.
- `idx_benchmarks_lookup` on `industry_benchmarks(industry_sector, organization_size, framework, domain)` for fast benchmark retrieval.

### 6.3. Row-Level Security Policies

Supabase row-level security (RLS) policies will enforce data isolation between tenants:

- Users can only read/write policies belonging to their own `tenant_id`.
- Structured data, usage records, and peer comparisons inherit the same tenant isolation through their foreign key relationships.
- Audit logs are read-only for regular users and only accessible to administrators.
- Industry benchmarks are read-only for all users, as they contain aggregate data without tenant-specific information.

---

## 7. AI Prompt Engineering Strategy

### 7.1. Prompt Structure

The effectiveness of the AI analysis depends critically on well-structured prompts that provide clear instructions, relevant context, and specific output requirements. The prompt architecture follows a four-part structure: system context, document context, analysis instructions, and output format specification.

**System Context** establishes the AI's role and expertise. The prompt will position Claude as an expert cyber insurance analyst with deep knowledge of industry frameworks, regulatory requirements, and common policy gaps. This framing encourages the AI to apply appropriate domain knowledge and professional judgment.

**Document Context** provides the AI with all relevant information about the policy being analyzed. This includes the full extracted text, structured data extracted by the regex layer (coverage limits, dates, etc.), organization metadata (industry, size, risk profile), and any previous analysis results if this is a re-analysis.

**Analysis Instructions** specify the exact tasks the AI should perform. These instructions are broken down into discrete steps: evaluate coverage against NIST CSF, CMMC, and CIS Controls; assign maturity scores (1-5) for each framework domain with justification; identify specific gaps and vulnerabilities; assess coverage adequacy relative to industry standards; and generate prioritized recommendations for improvement.

**Output Format Specification** defines the structure of the AI's response using JSON schema. This ensures consistent, parseable output that can be reliably processed by downstream code. The schema includes fields for scores, gap descriptions, recommendations, confidence levels, and supporting evidence.

### 7.2. Few-Shot Examples

To improve consistency and accuracy, the prompts will include few-shot examples demonstrating the desired analysis style and output format. These examples will cover diverse scenarios including strong policies with comprehensive coverage, weak policies with significant gaps, and edge cases such as policies with unusual exclusions or non-standard terms.

### 7.3. Iterative Refinement

The prompt engineering process will be iterative, with continuous refinement based on actual analysis results. A feedback mechanism will be implemented to capture cases where the AI's analysis is inaccurate or incomplete, enabling systematic prompt improvements. The development team will maintain a prompt version history and conduct A/B testing of prompt variations to optimize for accuracy, consistency, and insight quality.

---

## 8. Testing & Quality Assurance Strategy

### 8.1. Test Corpus Development

A comprehensive test corpus will be developed to validate the system's accuracy across diverse policy types and document formats. The corpus will include:

- **Standard Policies**: Well-formatted, text-based PDFs from major insurers representing typical coverage scenarios.
- **Scanned Documents**: Image-based PDFs requiring OCR, including policies with varying scan quality.
- **Complex Layouts**: Multi-column documents, policies with extensive tables, and documents with mixed formatting.
- **Edge Cases**: Policies with unusual exclusions, non-standard terms, or incomplete information.
- **Multilingual Policies**: Documents in languages other than English to test internationalization capabilities.

Each test document will be manually analyzed by domain experts to create ground truth labels for coverage scores, identified gaps, and recommendations. These labels will serve as the benchmark for automated testing.

### 8.2. Testing Levels

**Unit Tests** will validate individual components in isolation. This includes tests for PDF extraction functions (ensuring text is correctly extracted from various formats), structured data extraction (verifying regex patterns correctly identify policy attributes), scoring functions (confirming maturity scores are calculated correctly), and report generation (ensuring PDFs are properly formatted).

**Integration Tests** will validate the interaction between components. These tests will verify that the complete pipeline functions correctly, from policy upload through report delivery. Integration tests will use the test corpus to ensure consistent results across the entire workflow.

**End-to-End Tests** will simulate complete user workflows, including uploading policies through the CRM interface, monitoring real-time progress updates, downloading generated reports, and verifying report content. These tests will run against a staging environment that mirrors production configuration.

**Performance Tests** will validate that the system meets performance requirements under load. Tests will measure processing time for policies of various sizes, concurrent analysis capacity, API response times, and database query performance. Load testing will simulate multiple concurrent users to identify bottlenecks.

### 8.3. Accuracy Validation

Accuracy validation will compare automated analysis results against expert-generated ground truth labels. Key metrics include:

- **Coverage Score Accuracy**: Mean absolute error between automated and expert scores across all framework domains.
- **Gap Detection Recall**: Percentage of expert-identified gaps that are also identified by the automated system.
- **Gap Detection Precision**: Percentage of system-identified gaps that are confirmed as valid by experts.
- **Recommendation Relevance**: Expert rating of recommendation quality and actionability.

The system will be considered production-ready when it achieves minimum thresholds: coverage score MAE < 0.5 (on 1-5 scale), gap detection recall > 85%, gap detection precision > 80%, and recommendation relevance rating > 4.0/5.0.

### 8.4. Continuous Quality Monitoring

Post-deployment, the system will implement continuous quality monitoring through user feedback mechanisms. Users will be able to rate the accuracy and usefulness of analyses, and these ratings will be tracked over time. Significant drops in quality metrics will trigger alerts for investigation. A sample of analyses will be randomly selected for expert review on an ongoing basis to detect any degradation in accuracy.

---

## 9. Deployment & Operations

### 9.1. Deployment Architecture

The application will be deployed across multiple platforms to leverage each platform's strengths. The Vercel CRM will be deployed on Vercel's global edge network, providing low-latency access for users worldwide. The Railway Analysis Engine will be deployed on Railway with automatic scaling configured based on CPU and memory utilization. Supabase will be used in its hosted configuration, eliminating the need for database administration. Upstash Redis will provide serverless Redis for the job queue.

### 9.2. Environment Configuration

Three environments will be maintained: development (for active feature development), staging (for pre-production testing), and production (for live user traffic). Each environment will have separate instances of all services with appropriate configuration. Secrets and API keys will be managed through each platform's environment variable system, never committed to version control.

### 9.3. Continuous Integration & Deployment

A CI/CD pipeline will be implemented using GitHub Actions. On every push to the main branch, the pipeline will run all unit and integration tests, perform code quality checks using linters and formatters, build Docker images for the Railway API, and automatically deploy to the staging environment. Production deployments will require manual approval after successful staging validation.

### 9.4. Monitoring & Alerting

Comprehensive monitoring will be implemented across all system components. Sentry will track application errors, performance issues, and user impact. Custom dashboards will display key operational metrics including analysis throughput (policies processed per hour), processing time distribution (p50, p95, p99), error rates by type, API usage and costs, queue depth and processing lag, and user engagement metrics.

Alerts will be configured for critical conditions including error rate exceeding 5%, p95 processing time exceeding 5 minutes, queue depth exceeding 100 jobs, API cost rate exceeding budget thresholds, and any security-related events (failed authentication attempts, invalid webhook signatures).

### 9.5. Backup & Disaster Recovery

Database backups will be performed automatically by Supabase with point-in-time recovery capability. Supabase Storage will maintain versioned backups of all uploaded policies and generated reports. In the event of a catastrophic failure, the system can be restored from backups with a maximum data loss of 1 hour (RPO) and a recovery time of 4 hours (RTO).

---

## 10. Cost Estimation & Resource Planning

### 10.1. Infrastructure Costs

Monthly infrastructure costs are estimated as follows based on moderate usage (1,000 analyses per month):

- **Vercel**: $20/month (Pro plan for CRM hosting)
- **Railway**: $50/month (Analysis Engine with automatic scaling)
- **Supabase**: $25/month (Pro plan for database, storage, and realtime)
- **Upstash Redis**: $10/month (serverless Redis for job queue)
- **Anthropic Claude API**: $300/month (estimated at $0.30 per analysis for Claude Sonnet)
- **Unstructured.io API**: $200/month (estimated at $0.20 per document)
- **Sentry**: $26/month (Team plan for error monitoring)

**Total Estimated Monthly Cost**: $631 for 1,000 analyses, or approximately $0.63 per analysis.

### 10.2. Development Resources

The project requires the following development resources:

- **Backend Developer**: 11-17 days for Python API development, database schema design, and integration work.
- **Frontend Developer**: 5-7 days for CRM enhancements, real-time updates, and UI improvements.
- **AI/ML Engineer**: 3-5 days for prompt engineering, accuracy validation, and model optimization.
- **DevOps Engineer**: 2-3 days for deployment automation, monitoring setup, and security configuration.

### 10.3. Ongoing Maintenance

Post-launch, the system will require ongoing maintenance including monitoring and incident response (estimated 5 hours/week), prompt refinement and accuracy improvements (estimated 3 hours/week), and feature enhancements based on user feedback (estimated 8 hours/week).

---

## 11. Risk Assessment & Mitigation

### 11.1. Technical Risks

**PDF Extraction Accuracy Risk**: Even with Unstructured.io, some documents may be difficult to extract accurately. **Mitigation**: Implement quality scoring for extracted text, flag low-quality extractions for manual review, and continuously expand the test corpus to identify problematic document types.

**AI Analysis Consistency Risk**: LLM outputs may vary between runs, potentially producing inconsistent results. **Mitigation**: Use low temperature settings for more deterministic outputs, implement output validation to catch anomalous results, and maintain a feedback loop for continuous prompt refinement.

**API Dependency Risk**: The system depends on external APIs (Anthropic, Unstructured.io) that may experience outages or rate limiting. **Mitigation**: Implement graceful degradation (fallback to pdfplumber for extraction), use job queue with automatic retries, and maintain buffer capacity in API rate limits.

### 11.2. Operational Risks

**Cost Overrun Risk**: Unexpected usage spikes could lead to high API costs. **Mitigation**: Implement rate limiting per tenant, set up cost monitoring and alerts, and establish hard caps on daily API spending.

**Data Security Risk**: Policy documents contain sensitive information that must be protected. **Mitigation**: Implement encryption at rest and in transit, enforce row-level security policies, conduct regular security audits, and maintain compliance with data protection regulations.

### 11.3. Business Risks

**Accuracy Expectations Risk**: Users may expect perfect accuracy, which is unrealistic for AI systems. **Mitigation**: Clearly communicate that the system provides decision support rather than definitive judgments, include confidence scores with all outputs, and recommend expert review for high-stakes decisions.

**Regulatory Risk**: Insurance analysis may be subject to regulatory requirements. **Mitigation**: Consult with legal experts on compliance requirements, maintain comprehensive audit logs, and implement disclaimers about the advisory nature of the analysis.

---

## 12. Success Metrics & KPIs

### 12.1. Technical Performance Metrics

- **Analysis Completion Rate**: Target 95% of analyses complete successfully without manual intervention.
- **Processing Time**: Target p95 processing time < 3 minutes for standard policies.
- **Extraction Accuracy**: Target > 90% accuracy on structured data extraction validated against manual review.
- **System Uptime**: Target 99.5% uptime for the complete pipeline.

### 12.2. Business Metrics

- **User Adoption**: Track number of policies analyzed per month and growth rate.
- **User Satisfaction**: Collect and track user ratings of analysis quality and usefulness.
- **Cost Efficiency**: Monitor cost per analysis and optimize to maintain target margins.
- **Feature Utilization**: Track usage of key features (real-time updates, report downloads, benchmarking).

### 12.3. Quality Metrics

- **Analysis Accuracy**: Maintain > 85% agreement with expert reviews on coverage scores.
- **Gap Detection Effectiveness**: Track percentage of identified gaps that users act upon.
- **Recommendation Actionability**: Measure percentage of recommendations that users implement.

---

## 13. Future Enhancements

Beyond the initial three-phase implementation, several enhancements could further increase the platform's value:

**Advanced Risk Quantification** could integrate with cyber risk quantification (CRQ) models to provide financial impact estimates for identified gaps. This would enable organizations to prioritize improvements based on potential loss reduction.

**Historical Trend Analysis** could track policy changes over time, showing how an organization's coverage has evolved and whether gaps are being addressed. This would provide valuable insights for risk management teams.

**Integration with Security Tools** could connect the analyzer with security information and event management (SIEM) systems, vulnerability scanners, and other security tools to provide real-time risk assessment based on actual security posture rather than just policy documents.

**Multi-Policy Comparison** could enable organizations to compare multiple policy options side-by-side, facilitating more informed purchasing decisions.

**Automated Renewal Recommendations** could analyze policy renewal options and recommend optimal coverage adjustments based on changes in the organization's risk profile.

---

## 14. Conclusion

This comprehensive development plan provides a clear roadmap for transforming the RhôneRisk Cyber Insurance Policy Analyzer from a promising prototype into a production-ready platform. By executing the three phases systematically—first stabilizing the foundation, then enhancing quality and features, and finally hardening for enterprise scale—the project will deliver a robust, accurate, and user-friendly solution that addresses a critical need in the rapidly growing cyber insurance market.

The proposed architecture leverages modern technologies and industry best practices to ensure scalability, security, and maintainability. The integration of established frameworks (NIST CSF, CMMC, CIS Controls) provides credibility and ensures that analyses are grounded in recognized standards. The phased approach allows for iterative refinement and validation, reducing risk while maintaining development momentum.

With careful execution of this plan, the RhôneRisk Policy Analyzer will provide organizations with the insights they need to make informed decisions about their cyber insurance coverage, ultimately helping them better protect against the financial impacts of cyber incidents.

---

**Document Version**: 1.0  
**Last Updated**: February 16, 2026  
**Next Review**: Upon completion of Phase 1
