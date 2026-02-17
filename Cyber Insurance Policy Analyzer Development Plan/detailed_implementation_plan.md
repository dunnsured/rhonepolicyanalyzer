# Step-by-Step Implementation Plan: RhôneRisk Policy Analyzer

**Version:** 1.0  
**Author:** Manus AI  
**Date:** February 16, 2026

## 0. Introduction & Prerequisites

This document provides an exhaustive, step-by-step guide for a developer to build the RhôneRisk Cyber Insurance Policy Analyzer from the ground up. It assumes the developer has access to and proficiency with the following:

- **GitHub Repository**: Access to the existing codebase.
- **Supabase**: Admin access to the Supabase project.
- **Vercel**: Access to the Vercel project for the CRM/frontend.
- **Railway**: Access to the Railway project for the Python/FastAPI analysis engine.
- **API Keys**: Secure access to API keys for Anthropic Claude, Unstructured.io, and Sentry.

### Project Structure Overview

- **`rhonerisk-crm`**: The Next.js/TypeScript frontend application deployed on Vercel.
- **`rhonerisk-api`**: The Python/FastAPI analysis engine deployed on Railway.

### Initial Setup

1.  **Clone Repositories**: Clone both the `rhonerisk-crm` and `rhonerisk-api` repositories.
2.  **Install Dependencies**:
    ```bash
    # In rhonerisk-crm directory
    pnpm install

    # In rhonerisk-api directory
    pip install -r requirements.txt
    ```
3.  **Environment Variables**: Ensure all required environment variables (e.g., `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `ANTHROPIC_API_KEY`, etc.) are set up in your local `.env` files and in the Vercel/Railway project settings.

---

## Phase 1: Critical Fixes & Foundational Stability (3-5 Days)

**Goal**: To create a stable, reliable, and secure end-to-end pipeline that correctly processes a policy from upload to report delivery.

### Task 1.1: Implement Server-Side Analysis Trigger

**Objective**: Replace the unreliable client-side trigger with a robust Supabase Database Webhook.

**Step 1: Create a New API Endpoint in the Vercel CRM**

This endpoint will receive the webhook from Supabase and dispatch the job to the Railway API.

-   **File**: `rhonerisk-crm/src/app/api/policies/start-analysis/route.ts`
-   **Action**: Create the file and add the following code.

```typescript
// rhonerisk-crm/src/app/api/policies/start-analysis/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

export async function POST(req: NextRequest) {
  const WEBHOOK_SECRET = process.env.SUPABASE_WEBHOOK_SECRET;
  const RAILWAY_API_URL = process.env.RAILWAY_API_URL;
  const RAILWAY_API_KEY = process.env.RAILWAY_API_KEY;

  // 1. Verify the webhook secret
  const secret = req.headers.get('x-webhook-secret');
  if (secret !== WEBHOOK_SECRET) {
    console.error('Invalid webhook secret');
    return new NextResponse('Unauthorized', { status: 401 });
  }

  // 2. Parse the payload
  const payload = await req.json();
  const policyId = payload.record.id;

  if (!policyId) {
    return new NextResponse('Missing policy ID', { status: 400 });
  }

  // 3. Update policy status to 'queued'
  const supabase = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!);
  await supabase.from('insurance_policies').update({ status: 'queued' }).eq('id', policyId);

  // 4. Dispatch the job to the Railway API
  try {
    const response = await fetch(`${RAILWAY_API_URL}/analyze/${policyId}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': RAILWAY_API_KEY!,
      },
      body: JSON.stringify({ policy_id: policyId }),
    });

    if (!response.ok) {
      throw new Error(`Failed to dispatch analysis job: ${await response.text()}`);
    }

    return NextResponse.json({ message: 'Analysis job dispatched successfully' });

  } catch (error) {
    console.error('Error dispatching analysis job:', error);
    // Update status to 'failed'
    await supabase.from('insurance_policies').update({ status: 'failed', analysis_notes: 'Failed to dispatch job to API.' }).eq('id', policyId);
    return new NextResponse('Internal Server Error', { status: 500 });
  }
}
```

**Step 2: Create the Supabase Database Trigger**

This SQL script creates a function and a trigger that fires after a new policy is inserted.

-   **Action**: In the Supabase dashboard, go to `Database` > `Migrations` and create a new migration.
-   **File**: `supabase/migrations/<timestamp>_add_auto_analyze_trigger.sql`
-   **Content**:

```sql
-- supabase/migrations/<timestamp>_add_auto_analyze_trigger.sql

-- 1. Create the function to be called by the trigger
create or replace function trigger_policy_analysis() 
returns trigger as $$
declare
  webhook_url text := 'https://<your-vercel-project-url>/api/policies/start-analysis';
  webhook_secret text;
begin
  -- Get the secret from Supabase secrets
  select decrypted_secret into webhook_secret from vault.decrypted_secrets where name = 'webhook_secret';

  -- Perform the HTTP POST request to our Vercel endpoint
  perform http_post(
    webhook_url,
    json_build_object('type', 'INSERT', 'table', 'insurance_policies', 'record', new)::jsonb,
    'application/json',
    json_build_object('x-webhook-secret', webhook_secret)::jsonb
  );
  return new;
end;
$$ language plpgsql;

-- 2. Create the trigger to fire AFTER INSERT on the insurance_policies table
create trigger on_new_policy_insert
after insert on insurance_policies
for each row execute procedure trigger_policy_analysis();
```

-   **Action**: Add your `SUPABASE_WEBHOOK_SECRET` to the Supabase secrets manager under the name `webhook_secret`.

**Step 3: Deprecate the Client-Side Trigger**

-   **File**: `rhonerisk-crm/src/components/insurance-policies-section.tsx`
-   **Action**: Find and remove the `fetch` call that POSTs to `/api/policies/[id]/analyze` within the file upload or policy creation logic. The backend now handles this automatically.


---

### Task 1.2: Fix Report Delivery & Storage

**Objective**: Securely store the generated PDF report and make it accessible to the user for download.

**Step 1: Create Supabase Storage Bucket**

-   **Action**: In the Supabase dashboard, navigate to `Storage`.
-   Click `New bucket`.
-   **Bucket name**: `reports`
-   **Public bucket**: Uncheck this box. This bucket must be private.
-   **Action**: Set up Row Level Security (RLS) policies to ensure users can only access reports associated with their organization.

    ```sql
    -- Policy: Allow users to view reports belonging to their organization
    CREATE POLICY "Allow org members to view reports" ON storage.objects
    FOR SELECT USING (
      bucket_id = 'reports' AND
      auth.uid() IN (
        SELECT user_id FROM organization_users WHERE organization_id = (storage.foldername(name))[1]::uuid
      )
    );

    -- Policy: Allow service role to upload reports
    CREATE POLICY "Allow service role to upload reports" ON storage.objects
    FOR INSERT WITH CHECK (bucket_id = 'reports' AND auth.role() = 'service_role');
    ```

**Step 2: Add `report_storage_path` Column to Database**

-   **Action**: Create a new migration in Supabase.
-   **File**: `supabase/migrations/<timestamp>_add_report_storage_path.sql`
-   **Content**:

    ```sql
    -- supabase/migrations/<timestamp>_add_report_storage_path.sql
    ALTER TABLE insurance_policies
    ADD COLUMN report_storage_path TEXT,
    ADD COLUMN analysis_notes TEXT; -- Also add a field for error messages or notes
    ```

**Step 3: Configure Supabase Client in Railway API**

-   **Action**: Add `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` to your Railway project's environment variables.
-   **Action**: Add `supabase-py` to your `requirements.txt` file.
    ```
    supabase
    ```
-   **Action**: In the `rhonerisk-api` project, modify the analysis orchestrator to upload the generated report.

    ```python
    # rhonerisk-api/src/analysis_engine.py
    import os
    from supabase import create_client, Client

    def upload_report_and_update_status(policy_id: str, report_path: str, status: str, notes: str = None):
        supabase_url = os.environ.get("SUPABASE_URL")
        supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        supabase: Client = create_client(supabase_url, supabase_key)

        storage_path = f"{policy_id}/RhoneRisk_Analysis_Report.pdf"

        try:
            # 1. Upload the file
            with open(report_path, 'rb') as f:
                supabase.storage.from_("reports").upload(storage_path, f)

            # 2. Update the database record
            update_data = {
                "status": status,
                "report_storage_path": storage_path,
                "analysis_notes": notes
            }
            supabase.from_("insurance_policies").update(update_data).eq("id", policy_id).execute()

        except Exception as e:
            print(f"Error uploading report or updating status: {e}")
            # Handle error, maybe update status to 'failed'
            supabase.from_("insurance_policies").update({"status": "failed", "analysis_notes": f"Report upload failed: {e}"}).eq("id", policy_id).execute()

    # In your main analysis function, after the report is generated:
    # ... report_file_path = generate_report(...)
    # upload_report_and_update_status(policy_id, report_file_path, "completed", "Analysis successful.")
    ```

**Step 4: Add Download Functionality to CRM UI**

-   **Action**: Modify the frontend component to display a download button when a report is available.
-   **File**: `rhonerisk-crm/src/components/insurance-policies-section.tsx`

    ```tsx
    // rhonerisk-crm/src/components/insurance-policies-section.tsx

    // ... inside your component

    const handleDownload = async (filePath: string) => {
      const supabase = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!);
      const { data, error } = await supabase.storage.from('reports').createSignedUrl(filePath, 3600); // URL valid for 1 hour

      if (error) {
        console.error('Error creating signed URL:', error);
        // Handle error (e.g., show a toast notification)
        return;
      }

      window.open(data.signedUrl, '_blank');
    };

    // ... in your table rendering logic
    {
      policy.status === 'completed' && policy.report_storage_path && (
        <button onClick={() => handleDownload(policy.report_storage_path)}>
          Download Report
        </button>
      )
    }
    ```

---

### Task 1.3: Secure Inter-Service Communication

**Objective**: Ensure all communication between services is authenticated and secure, preventing unauthorized access.

**Step 1: Secure the Supabase -> Vercel Webhook**

-   **Action**: This was implemented in Task 1.1, Step 1. The `start-analysis/route.ts` endpoint validates a shared secret (`x-webhook-secret`) on every request. 
-   **Security Best Practice**: Ensure the `SUPABASE_WEBHOOK_SECRET` is a long, randomly generated string and is stored securely in both Supabase Vault and Vercel Environment Variables. Do not commit it to code.

**Step 2: Secure the Vercel -> Railway API Call**

-   **Objective**: The Vercel API calls the Railway API to start the analysis. This must be secured.
-   **Action**: In the Railway API (`rhonerisk-api`), create a dependency to verify a static API key.

    ```python
    # rhonerisk-api/src/security.py
    import os
    from fastapi import Security, HTTPException, status
    from fastapi.security import APIKeyHeader

    API_KEY = os.environ.get("RAILWAY_API_KEY")
    api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)

    async def get_api_key(
        api_key_header: str = Security(api_key_header),
    ):
        if api_key_header == API_KEY:
            return api_key_header
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Could not validate credentials",
            )
    ```

-   **Action**: Protect the analysis endpoint in the Railway API.

    ```python
    # rhonerisk-api/src/main.py
    from fastapi import FastAPI, Depends
    from .security import get_api_key

    app = FastAPI()

    @app.post("/analyze/{policy_id}")
    async def analyze_policy(policy_id: str, api_key: str = Depends(get_api_key)):
        # The get_api_key dependency will handle authentication
        # ... start your analysis logic here
        return {"message": "Analysis started"}
    ```

-   **Action**: Ensure the `RAILWAY_API_KEY` is set in both Vercel and Railway environment variables. The Vercel `start-analysis` endpoint (Task 1.1) already sends this key in the `x-api-key` header.

---

### Task 1.4: Set Up Basic Monitoring and Logging

**Objective**: Gain visibility into application errors and performance for debugging and maintenance.

**Step 1: Integrate Sentry for Error Tracking**

-   **For Vercel (Next.js):**
    1.  In the `rhonerisk-crm` directory, run the Sentry wizard:
        ```bash
        pnpm sentry-wizard -i nextjs
        ```
    2.  Follow the prompts. This will automatically create/update necessary files (`sentry.client.config.ts`, `sentry.server.config.ts`, etc.) and add the `@sentry/nextjs` package.
    3.  Add your Sentry DSN to Vercel environment variables as `SENTRY_DSN`.

-   **For Railway (Python/FastAPI):**
    1.  Add `sentry-sdk[fastapi]` to your `requirements.txt` file.
    2.  Initialize Sentry in your main application file.

        ```python
        # rhonerisk-api/src/main.py
        import sentry_sdk
        import os

        SENTRY_DSN = os.environ.get("SENTRY_DSN")

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            # Set traces_sample_rate to 1.0 to capture 100%
            # of transactions for performance monitoring.
            traces_sample_rate=1.0,
        )

        app = FastAPI()
        # ... rest of your app
        ```
    3.  Add your Sentry DSN to Railway environment variables as `SENTRY_DSN`.

**Step 2: Implement Structured Logging in Python API**

-   **Objective**: Configure the Python logger to output JSON for easier parsing by log management systems.
-   **Action**: Add `python-json-logger` to `requirements.txt`.
-   **Action**: Create a logging configuration utility.

    ```python
    # rhonerisk-api/src/logging_config.py
    import logging
    from python_json_logger import jsonlogger

    def setup_logging():
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        logHandler = logging.StreamHandler()
        formatter = jsonlogger.JsonFormatter(
            fmt=\"%(asctime)s %(name)s %(levelname)s %(message)s\"
        )
        logHandler.setFormatter(formatter)
        # Avoid adding duplicate handlers
        if not logger.handlers:
            logger.addHandler(logHandler)

    # Call this function once at startup
    # setup_logging()
    ```

-   **Action**: Initialize logging at application startup.

    ```python
    # rhonerisk-api/src/main.py
    from .logging_config import setup_logging

    # ... Sentry init

    setup_logging()
    app = FastAPI()
    ```

-   **Action**: Use the logger throughout the application.

    ```python
    # rhonerisk-api/src/analysis_engine.py
    import logging

    logger = logging.getLogger(__name__)

    def some_function():
        logger.info("Starting analysis for policy.", extra={\"policy_id\": \"123\"})
        try:
            # ...
        except Exception as e:
            logger.error("Analysis failed.", exc_info=True, extra={\"policy_id\": \"123\"})
    ```

This completes Phase 1. The system should now be stable and reliable, forming a solid foundation for the advanced features in Phase 2.


---

## Phase 2: Advanced Analysis & Feature Enhancement (5-7 Days)

**Goal**: To implement the core analytical engine, replacing placeholder logic with high-quality data extraction and the proprietary RhôneRisk scoring methodology.

### Task 2.1: Integrate Advanced PDF Extraction (Unstructured.io)

**Objective**: Improve the accuracy of text extraction from complex or scanned PDFs by using a specialized service, with a fallback to the existing method.

**Step 1: Environment and Library Setup**

-   **Action**: Add `UNSTRUCTURED_API_KEY` to the Railway project's environment variables.
-   **Action**: Add `unstructured-client` to the `rhonerisk-api/requirements.txt` file.

**Step 2: Create a Dedicated PDF Extraction Module**

-   **Action**: Create a new file for handling different extraction strategies.
-   **File**: `rhonerisk-api/src/pdf_extractor.py`
-   **Content**:

    ```python
    # rhonerisk-api/src/pdf_extractor.py
    import os
    import logging
    from unstructured_client import UnstructuredClient
    from unstructured_client.models import shared
    from unstructured_client.models.errors import SDKError
    # Assume you have a pdfplumber extractor in another file, e.g., legacy_extractor.py
    # from .legacy_extractor import extract_with_pdfplumber 

    logger = logging.getLogger(__name__)

    def extract_text_from_pdf(file_path: str) -> str:
        """Orchestrates PDF extraction, trying Unstructured.io first and falling back to pdfplumber."""
        try:
            logger.info("Attempting PDF extraction with Unstructured.io.")
            client = UnstructuredClient(api_key_auth=os.environ.get("UNSTRUCTURED_API_KEY"))
            with open(file_path, "rb") as f:
                files = shared.Files(content=f.read(), file_name=os.path.basename(file_path))
            
            req = shared.PartitionParameters(files=files, strategy="hi_res")
            res = client.general.partition(req)
            
            extracted_elements = [str(el.text) for el in res.elements]
            full_text = "\n\n".join(extracted_elements)

            if len(full_text) < 500: # Threshold to detect a failed/poor extraction
                raise ValueError("Unstructured.io extraction resulted in very low text output.")

            logger.info("Successfully extracted text with Unstructured.io.")
            return full_text

        except (SDKError, ValueError, Exception) as e:
            logger.warning(f"Unstructured.io extraction failed: {e}. Falling back to pdfplumber.")
            # return extract_with_pdfplumber(file_path) # Fallback to your old method
            # For now, we'll just return a placeholder for the fallback
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                 return f.read() # Placeholder for pdfplumber logic
    ```

**Step 3: Integrate into Analysis Engine**

-   **Action**: In the main analysis orchestrator, replace the direct call to `pdfplumber` with a call to the new `extract_text_from_pdf` function.

### Task 2.2: Implement Structured Data Extraction

**Objective**: Use regular expressions to parse key data points from the raw text before AI analysis to improve accuracy and provide structured context.

**Step 1: Create a Structured Data Parser Module**

-   **Action**: Create a new file to house the regex logic.
-   **File**: `rhonerisk-api/src/structured_data_parser.py`
-   **Content**:

    ```python
    # rhonerisk-api/src/structured_data_parser.py
    import re
    import json

    # Define regex patterns for key data points
    PATTERNS = {
        "policy_number": r"Policy\sNumber[:\s]+([A-Z0-9-]+)",
        "aggregate_limit": r"Aggregate\sLimit[:\s]+\$([\d,]+)",
        "effective_date": r"Effective\sDate[:\s]+(\d{2}/\d{2}/\d{4})",
        "bi_waiting_period": r"Business\sInterruption\sWaiting\sPeriod[:\s]+(\d+)\sHours",
        # Add more patterns for deductibles, sublimits, etc.
    }

    def parse_structured_data(text: str) -> dict:
        """Extracts key-value pairs from policy text using regex."""
        results = {}
        for key, pattern in PATTERNS.items():
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                results[key] = match.group(1).strip()
        return results
    ```

**Step 2: Add Database Column and Integrate**

-   **Action**: Create a new Supabase migration to add a column for the structured data.
-   **File**: `supabase/migrations/<timestamp>_add_structured_data_column.sql`
-   **Content**:
    ```sql
    ALTER TABLE insurance_policies ADD COLUMN structured_data JSONB;
    ```
-   **Action**: In the analysis engine, call the parser and store its output.

    ```python
    # rhonerisk-api/src/analysis_engine.py
    # ... after text extraction
    # extracted_text = extract_text_from_pdf(...)
    # structured_data = parse_structured_data(extracted_text)
    # supabase.from_("insurance_policies").update({"structured_data": structured_data}).eq("id", policy_id).execute()
    ```

### Task 2.3: Develop the RhôneRisk Scoring Engine

**Objective**: Implement the core AI logic to score each coverage part according to the proprietary 4-tier maturity model.

**Step 1: Create Pydantic Models for Structured Output**

-   **Action**: Define the exact JSON structure you want the AI to return.
-   **File**: `rhonerisk-api/src/models.py`
-   **Content**:
    ```python
    # rhonerisk-api/src/models.py
    from pydantic import BaseModel, Field
    from typing import List

    class CoverageScore(BaseModel):
        coverage_name: str = Field(description="The name of the insurance coverage part being scored.")
        score: int = Field(description="The maturity score from 0 to 10.")
        rating: str = Field(description="The rating based on the score (Superior, Average, Basic, No Coverage).")
        justification: str = Field(description="A detailed explanation for the assigned score and rating.")
        red_flags: List[str] = Field(description="A list of any critical issues or red flags found.")
    ```

**Step 2: Create Prompt Template**

-   **Action**: Create a file to hold the prompt template.
-   **File**: `rhonerisk-api/src/prompts/coverage_scoring_prompt.jinja2`
-   **Content**:
    ```jinja2
    You are an expert cyber insurance analyst for RhôneRisk Advisory. Your task is to analyze a specific coverage part of a client's policy and score it using the proprietary RhôneRisk 4-Tier Maturity Scoring System.

    **Policy Text:**
    ```
    {{ policy_text }}
    ```

    **Structured Data Highlights:**
    ```json
    {{ structured_data | tojson }}
    ```

    **Scoring Guide:**
    - 9-10 (Superior): Best-in-class, exceeds industry standards.
    - 5-8 (Average): Standard market terms, baseline protection.
    - 2-4 (Basic): Significant limitations or gaps.
    - 0-1 (No Coverage): Excluded or not mentioned.

    **Analysis Task:**
    Analyze the "**{{ coverage_to_analyze }}**" coverage ONLY. Provide a score from 0-10, the corresponding rating, and a detailed justification. Identify any red flags.
    ```

**Step 3: Implement the AI Analysis Loop**

-   **Action**: Create the main loop that calls the AI for each coverage part.
-   **File**: `rhonerisk-api/src/analysis_engine.py`
-   **Content**:
    ```python
    # rhonerisk-api/src/analysis_engine.py
    import anthropic
    from .models import CoverageScore
    # ... other imports

    COVERAGE_PARTS_TO_ANALYZE = [
        "Network Security Liability",
        "Privacy Liability",
        "Business Interruption",
        "Cyber Extortion",
        "Social Engineering Fraud",
        # ... add all 20+ coverage parts
    ]

    def run_full_analysis(policy_id: str, policy_text: str, structured_data: dict):
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        all_scores = []

        for coverage_part in COVERAGE_PARTS_TO_ANALYZE:
            # 1. Render the Jinja2 prompt
            prompt = render_jinja_template(
                "prompts/coverage_scoring_prompt.jinja2",
                policy_text=policy_text,
                structured_data=structured_data,
                coverage_to_analyze=coverage_part
            )

            # 2. Call Claude with the Pydantic model for structured output
            response = client.beta.tools.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
                tools=[CoverageScore.model_json_schema()]
            )

            # 3. Parse and store the result
            # ... logic to extract the tool_use block, parse JSON, and validate with Pydantic
            # score_object = CoverageScore(**parsed_json)
            # all_scores.append(score_object)
            # save_score_to_db(policy_id, score_object)
        
        return all_scores
    ```

### Task 2.4: Generate the Final Report

-   **Objective**: Use the collected scores and justifications to generate the full, 21-section narrative report.
-   **Action**: Create a final prompt template and a function to generate the report.
-   **File**: `rhonerisk-api/src/prompts/final_report_prompt.jinja2`
-   **Content**: A large prompt that instructs the AI to write the Executive Summary, Gap Analysis, etc., based on the structured scores provided.
-   **Action**: In `analysis_engine.py`, after the loop in Task 2.3 is complete, call the AI one last time with this final prompt to generate the full report text. Then, use a library like `weasyprint` to convert the generated Markdown/HTML into a branded PDF.

This completes the core of Phase 2. The system can now perform a sophisticated, multi-step analysis based on the proprietary methodology.


---

## Phase 3: Production Hardening & Scale (3-5 Days)

**Goal**: To transform the functional application into a resilient, scalable, and observable platform ready for enterprise-level load.

### Task 3.1: Implement a Persistent Job Queue

**Objective**: Replace the direct HTTP dispatch with a robust job queue to ensure reliability, retries, and scalability. We will use **Celery with Redis** as it is the industry standard for Python.

**Step 1: Set Up Redis**

-   **Action**: On Railway, add a Redis service to your project. Railway will automatically provide the `REDIS_URL` environment variable.

**Step 2: Install and Configure Celery**

-   **Action**: Add `celery` and `redis` to the `rhonerisk-api/requirements.txt` file.
    ```
    celery[redis]
    ```
-   **Action**: Create a Celery configuration file in the API project.
-   **File**: `rhonerisk-api/src/celery_app.py`
-   **Content**:
    ```python
    # rhonerisk-api/src/celery_app.py
    import os
    from celery import Celery

    # The broker URL is read from the environment variable provided by Railway
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    celery_app = Celery(
        "rhonerisk_tasks",
        broker=redis_url,
        backend=redis_url,
        include=["rhonerisk-api.src.tasks"]
    )

    celery_app.conf.update(
        task_track_started=True,
        result_expires=3600, # Keep results for 1 hour
    )
    ```

**Step 3: Create a Celery Task**

-   **Objective**: Move the analysis logic into a background task.
-   **Action**: Create a new file for Celery tasks.
-   **File**: `rhonerisk-api/src/tasks.py`
-   **Content**:
    ```python
    # rhonerisk-api/src/tasks.py
    from .celery_app import celery_app
    from .analysis_engine import run_full_analysis # Assume this function contains the main logic
    import logging

    logger = logging.getLogger(__name__)

    @celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={
        'max_retries': 3
    })
    def process_policy_analysis(self, policy_id: str):
        """Celery task to perform the full policy analysis."""
        logger.info(f"Starting analysis for policy_id: {policy_id}")
        try:
            # This function will now contain the full orchestration:
            # 1. Fetch policy data from Supabase
            # 2. Download PDF from Storage
            # 3. Extract text (Unstructured.io)
            # 4. Parse structured data
            # 5. Run AI analysis loop
            # 6. Generate final report
            # 7. Upload report to Storage and update status
            run_full_analysis(policy_id)
            logger.info(f"Successfully completed analysis for policy_id: {policy_id}")
            return {"status": "Completed", "policy_id": policy_id}
        except Exception as e:
            logger.error(f"Analysis failed for policy_id: {policy_id}", exc_info=True)
            # Update status to failed in Supabase here
            raise e
    ```

**Step 4: Modify Vercel Endpoint to Enqueue Jobs**

-   **Objective**: Instead of calling the Railway API via HTTP, the Vercel endpoint will now add a task to the Celery queue.
-   **Action**: This requires a way for the Node.js backend to talk to Celery. The simplest way is to create a small endpoint on the Railway API whose only job is to enqueue the task.
-   **Action**: Create a new endpoint in the Railway API.
-   **File**: `rhonerisk-api/src/main.py`
    ```python
    # rhonerisk-api/src/main.py
    from .tasks import process_policy_analysis

    @app.post("/enqueue-analysis/{policy_id}")
    async def enqueue_analysis(policy_id: str, api_key: str = Depends(get_api_key)):
        process_policy_analysis.delay(policy_id)
        return {"message": "Analysis task enqueued"}
    ```
-   **Action**: Update the Vercel `start-analysis` endpoint to call this new enqueueing endpoint instead of the old `/analyze/{policy_id}` one.

**Step 5: Run the Celery Worker**

-   **Action**: Modify the `Procfile` or startup command on Railway to run the Celery worker process alongside the FastAPI web server.
-   **Command**: `celery -A rhonerisk-api.src.celery_app worker --loglevel=info`

### Task 3.2: Implement Rate Limiting and Cost Control

**Objective**: Prevent abuse and track API costs.

**Step 1: Database Schema**

-   **Action**: Create a migration for a `usage_logs` table.
-   **File**: `supabase/migrations/<timestamp>_add_usage_logs.sql`
-   **Content**:
    ```sql
    CREATE TABLE usage_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        policy_id UUID REFERENCES insurance_policies(id),
        organization_id UUID REFERENCES organizations(id),
        created_at TIMESTAMPTZ DEFAULT now(),
        input_tokens INT,
        output_tokens INT,
        cost_usd NUMERIC(10, 6)
    );
    ```

**Step 2: Track Costs in Celery Task**

-   **Action**: Modify the Celery task to record usage after each AI call.
-   **File**: `rhonerisk-api/src/tasks.py`
    ```python
    # In process_policy_analysis task
    # After getting a response from Anthropic API
    # usage = response.usage
    # cost = calculate_cost(usage.input_tokens, usage.output_tokens)
    # supabase.from_("usage_logs").insert({
    #     "policy_id": policy_id,
    #     "organization_id": org_id, # You'll need to fetch this
    #     "input_tokens": usage.input_tokens,
    #     "output_tokens": usage.output_tokens,
    #     "cost_usd": cost
    # }).execute()
    ```

### Task 3.3: Implement Audit Logging

**Objective**: Record critical actions for security and compliance.

**Step 1: Database Schema**

-   **Action**: Create a migration for an `audit_logs` table.
-   **File**: `supabase/migrations/<timestamp>_add_audit_logs.sql`
-   **Content**:
    ```sql
    CREATE TABLE audit_logs (
        id BIGSERIAL PRIMARY KEY,
        timestamp TIMESTAMPTZ DEFAULT now(),
        user_id UUID REFERENCES auth.users(id),
        organization_id UUID REFERENCES organizations(id),
        action TEXT NOT NULL,
        details JSONB
    );
    ```

**Step 2: Create a Logging Service in Vercel**

-   **Action**: Create a server-side helper function to log events.
-   **File**: `rhonerisk-crm/src/lib/audit.ts`
-   **Content**:
    ```typescript
    import { createClient } from '@supabase/supabase-js';

    export async function logAuditEvent(userId: string, orgId: string, action: string, details: object) {
      const supabase = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!);
      await supabase.from('audit_logs').insert({
        user_id: userId,
        organization_id: orgId,
        action: action,
        details: details
      });
    }
    ```

**Step 3: Integrate Logging**

-   **Action**: Call `logAuditEvent` in various API routes and server actions for events like `USER_LOGIN`, `POLICY_UPLOADED`, `REPORT_DOWNLOADED`.

### Task 3.4: Implement the Maturity Benchmarking Engine

**Objective**: Provide users with context by comparing their policy scores against anonymized industry data.

**Step 1: Database Schema**

-   **Action**: Create a table to store aggregated, anonymized scores.
-   **File**: `supabase/migrations/<timestamp>_add_benchmarks.sql`
-   **Content**:
    ```sql
    CREATE TABLE industry_benchmarks (
        id BIGSERIAL PRIMARY KEY,
        industry_code TEXT, -- e.g., NAICS code
        coverage_name TEXT,
        average_score NUMERIC(4, 2),
        percentile_25 NUMERIC(4, 2),
        percentile_50 NUMERIC(4, 2),
        percentile_75 NUMERIC(4, 2),
        last_updated TIMESTAMPTZ DEFAULT now(),
        UNIQUE(industry_code, coverage_name)
    );
    ```

**Step 2: Create a Batch Job to Calculate Benchmarks**

-   **Action**: Create a scheduled Supabase Edge Function or a separate script that runs periodically (e.g., weekly).
-   **Logic**: This script will query all completed analyses, group them by industry and coverage type, calculate the average and percentile scores, and `UPSERT` the results into the `industry_benchmarks` table.

**Step 3: Display Benchmarks in the Report**

-   **Action**: In the final report generation prompt (Task 2.4), fetch the relevant benchmark data for the client's industry and include it in the context. Instruct the AI to generate a 
comparison table or chart in the final report.

---

## 4. Conclusion

This step-by-step plan provides a complete roadmap for building the RhôneRisk Policy Analyzer. By following these phases and tasks sequentially, a developer can construct the entire system, from foundational infrastructure to advanced, AI-driven analysis and enterprise-grade features.

-   **Phase 1** establishes a stable, secure, and reliable application backbone.
-   **Phase 2** builds the core value proposition, codifying the proprietary RhôneRisk methodology into the AI engine.
-   **Phase 3** ensures the platform is robust, scalable, and ready for production use.

Executing this plan will result in a powerful, strategic asset for RhôneRisk, enabling the firm to scale its unique expertise and deliver consistent, high-quality analysis to its clients.
