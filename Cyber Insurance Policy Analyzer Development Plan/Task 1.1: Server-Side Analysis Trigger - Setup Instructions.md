# Task 1.1: Server-Side Analysis Trigger - Setup Instructions

## Overview
This task replaces the unreliable client-side trigger with a robust Supabase Database Webhook that automatically starts policy analysis when a new policy is uploaded.

## Files Included

1. **`start-analysis-route.ts`** - Vercel webhook endpoint
2. **`supabase_trigger_migration.sql`** - Database trigger and function
3. **`env-template.txt`** - Environment variables template

---

## Step-by-Step Setup

### Step 1: Generate Webhook Secret

Generate a secure random secret for webhook authentication:

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

Copy the output - you'll need it in the next steps.

### Step 2: Configure Supabase Vault

1. Go to your Supabase Dashboard
2. Navigate to **Project Settings** > **Vault**
3. Click **New Secret**
4. Enter:
   - **Name**: `webhook_secret`
   - **Secret**: Paste the secret you generated in Step 1
5. Click **Save**

### Step 3: Configure Vercel Environment Variables

1. Go to your Vercel project dashboard
2. Navigate to **Settings** > **Environment Variables**
3. Add the following variables:

```
SUPABASE_WEBHOOK_SECRET=<paste-the-secret-from-step-1>
RAILWAY_API_URL=https://your-railway-app.railway.app
RAILWAY_API_KEY=<your-railway-api-key>
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>
```

4. Make sure to set them for **Production**, **Preview**, and **Development** environments

### Step 4: Deploy the Webhook Endpoint

1. Copy `start-analysis-route.ts` to your project:
   ```bash
   cp start-analysis-route.ts rhonerisk-crm/src/app/api/policies/start-analysis/route.ts
   ```

2. Commit and push to trigger Vercel deployment:
   ```bash
   git add .
   git commit -m "Add server-side analysis trigger webhook"
   git push
   ```

3. Wait for Vercel to deploy

4. Test the endpoint:
   ```bash
   curl https://your-vercel-project.vercel.app/api/policies/start-analysis
   ```
   
   You should see:
   ```json
   {
     "endpoint": "start-analysis",
     "description": "Webhook endpoint for Supabase policy insertion triggers",
     "method": "POST",
     "authentication": "x-webhook-secret header required",
     "status": "operational"
   }
   ```

### Step 5: Update the SQL Migration

1. Open `supabase_trigger_migration.sql`
2. Replace `https://your-vercel-project.vercel.app` with your actual Vercel deployment URL
3. The line should look like:
   ```sql
   webhook_url TEXT := 'https://rhonerisk-crm.vercel.app/api/policies/start-analysis';
   ```

### Step 6: Run the Database Migration

**Option A: Using Supabase CLI (Recommended)**

```bash
# Make sure you're in your project directory
cd rhonerisk-crm

# Run the migration
supabase db push

# Or if you want to apply a specific migration file:
supabase db execute -f supabase_trigger_migration.sql
```

**Option B: Using Supabase Dashboard**

1. Go to your Supabase Dashboard
2. Navigate to **Database** > **SQL Editor**
3. Click **New Query**
4. Copy and paste the entire contents of `supabase_trigger_migration.sql`
5. Click **Run**

### Step 7: Verify the Trigger

Check that the trigger was created successfully:

```sql
-- Run this query in Supabase SQL Editor
SELECT 
  trigger_name, 
  event_manipulation, 
  event_object_table, 
  action_statement
FROM information_schema.triggers
WHERE trigger_name = 'on_new_policy_insert';
```

You should see one row with the trigger details.

### Step 8: Test End-to-End

1. Go to your CRM application
2. Upload a new policy document
3. Check the Supabase logs:
   - Go to **Database** > **Logs**
   - Look for log entries about the webhook call
4. Check the policy status in the database:
   ```sql
   SELECT id, policy_name, status, analysis_notes, created_at
   FROM insurance_policies
   ORDER BY created_at DESC
   LIMIT 5;
   ```
5. The status should change from `pending` → `queued` → `analyzing` → `completed`

### Step 9: Remove Client-Side Trigger (Cleanup)

Now that the server-side trigger is working, remove the old client-side trigger:

1. Open `rhonerisk-crm/src/components/insurance-policies-section.tsx`
2. Find and remove any code that looks like this:
   ```typescript
   // OLD CODE - REMOVE THIS
   await fetch(`/api/policies/${policyId}/analyze`, {
     method: 'POST',
   });
   ```
3. Commit the changes:
   ```bash
   git add .
   git commit -m "Remove deprecated client-side analysis trigger"
   git push
   ```

---

## Troubleshooting

### Issue: "Webhook authentication failed"

**Solution**: 
- Verify the `SUPABASE_WEBHOOK_SECRET` in Vercel matches the `webhook_secret` in Supabase Vault
- Check that both are exactly the same (no extra spaces or newlines)

### Issue: "Failed to dispatch analysis job"

**Solution**:
- Verify `RAILWAY_API_URL` is correct and the Railway service is running
- Check that `RAILWAY_API_KEY` is valid
- Test the Railway endpoint directly:
  ```bash
  curl -X POST https://your-railway-app.railway.app/analyze/test-id \
    -H "x-api-key: your-api-key" \
    -H "Content-Type: application/json" \
    -d '{"policy_id": "test-id", "organization_id": "test-org"}'
  ```

### Issue: "Webhook secret not found in vault"

**Solution**:
- Go to Supabase Dashboard > Project Settings > Vault
- Verify the secret is named exactly `webhook_secret` (case-sensitive)
- If missing, add it following Step 2

### Issue: Trigger not firing

**Solution**:
- Check if the trigger exists:
  ```sql
  SELECT * FROM pg_trigger WHERE tgname = 'on_new_policy_insert';
  ```
- If missing, re-run the migration
- Check Supabase logs for any error messages

---

## Monitoring

### View Webhook Logs

**In Vercel:**
1. Go to your project dashboard
2. Click **Logs** in the top menu
3. Filter by `/api/policies/start-analysis`

**In Supabase:**
1. Go to **Database** > **Logs**
2. Look for entries with "Webhook response status"

### Check Policy Status

```sql
-- See all policies and their current status
SELECT 
  id,
  policy_name,
  status,
  analysis_notes,
  created_at,
  updated_at
FROM insurance_policies
ORDER BY created_at DESC;
```

### Monitor Errors in Sentry

1. Go to your Sentry dashboard
2. Look for issues tagged with:
   - `endpoint: /api/policies/start-analysis`
   - `function: trigger_policy_analysis`

---

## Success Criteria

✅ Webhook endpoint returns 200 OK when tested  
✅ Database trigger is created and active  
✅ New policy uploads automatically trigger analysis  
✅ Policy status updates correctly (pending → queued → analyzing)  
✅ No errors in Vercel or Supabase logs  
✅ Old client-side trigger code is removed  

---

## Next Steps

Once this task is complete, proceed to **Task 1.2: Fix Report Delivery & Storage**.
