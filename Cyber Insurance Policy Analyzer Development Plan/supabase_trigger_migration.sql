-- supabase/migrations/20260216000001_add_auto_analyze_trigger.sql
-- 
-- This migration creates a database trigger that automatically calls a webhook
-- when a new policy is inserted into the insurance_policies table.
--
-- Prerequisites:
-- 1. The http extension must be enabled in Supabase
-- 2. The webhook secret must be stored in Supabase Vault
-- 3. The Vercel webhook endpoint must be deployed and accessible

-- Enable the http extension if not already enabled
CREATE EXTENSION IF NOT EXISTS http;

-- Create the function that will be called by the trigger
CREATE OR REPLACE FUNCTION trigger_policy_analysis() 
RETURNS TRIGGER AS $$
DECLARE
  webhook_url TEXT := 'https://your-vercel-project.vercel.app/api/policies/start-analysis';
  webhook_secret TEXT;
  http_response http_response;
BEGIN
  -- Retrieve the webhook secret from Supabase Vault
  -- Make sure you've added this secret via: Supabase Dashboard > Project Settings > Vault
  SELECT decrypted_secret INTO webhook_secret 
  FROM vault.decrypted_secrets 
  WHERE name = 'webhook_secret';

  -- If secret is not found, log an error and exit
  IF webhook_secret IS NULL THEN
    RAISE WARNING 'Webhook secret not found in vault. Skipping webhook call.';
    RETURN NEW;
  END IF;

  -- Perform the HTTP POST request to the Vercel webhook endpoint
  -- This is a non-blocking call that happens after the INSERT completes
  SELECT * INTO http_response FROM http((
    'POST',
    webhook_url,
    ARRAY[
      http_header('Content-Type', 'application/json'),
      http_header('x-webhook-secret', webhook_secret)
    ],
    'application/json',
    json_build_object(
      'type', TG_OP,
      'table', TG_TABLE_NAME,
      'record', row_to_json(NEW)
    )::text
  )::http_request);

  -- Log the response status for debugging
  -- You can view these logs in Supabase Dashboard > Database > Logs
  RAISE LOG 'Webhook response status: %', http_response.status;

  -- If the webhook fails, log a warning but don't fail the transaction
  IF http_response.status NOT BETWEEN 200 AND 299 THEN
    RAISE WARNING 'Webhook call failed with status %: %', 
      http_response.status, 
      http_response.content;
  END IF;

  RETURN NEW;
EXCEPTION
  WHEN OTHERS THEN
    -- Catch any errors and log them, but don't fail the INSERT operation
    RAISE WARNING 'Error calling webhook: %', SQLERRM;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create the trigger that fires AFTER INSERT on the insurance_policies table
-- This trigger will call the function above for each new row inserted
DROP TRIGGER IF EXISTS on_new_policy_insert ON insurance_policies;

CREATE TRIGGER on_new_policy_insert
  AFTER INSERT ON insurance_policies
  FOR EACH ROW
  EXECUTE FUNCTION trigger_policy_analysis();

-- Add a comment to document the trigger
COMMENT ON TRIGGER on_new_policy_insert ON insurance_policies IS 
  'Automatically triggers policy analysis by calling the Vercel webhook endpoint when a new policy is inserted';

-- Grant necessary permissions
-- The trigger function runs with SECURITY DEFINER, so it needs access to vault
GRANT USAGE ON SCHEMA vault TO postgres;
GRANT SELECT ON vault.decrypted_secrets TO postgres;

-- Create an index on the status column for better query performance
CREATE INDEX IF NOT EXISTS idx_insurance_policies_status 
  ON insurance_policies(status);

-- Create an index on the created_at column for time-based queries
CREATE INDEX IF NOT EXISTS idx_insurance_policies_created_at 
  ON insurance_policies(created_at DESC);
