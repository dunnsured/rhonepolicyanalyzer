// rhonerisk-crm/src/app/api/policies/start-analysis/route.ts
import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import * as Sentry from '@sentry/nextjs';

/**
 * Webhook endpoint that receives notifications from Supabase when a new policy is inserted.
 * This endpoint validates the webhook, updates the policy status, and dispatches the analysis job to Railway.
 */

// Environment variables validation
const WEBHOOK_SECRET = process.env.SUPABASE_WEBHOOK_SECRET;
const RAILWAY_API_URL = process.env.RAILWAY_API_URL;
const RAILWAY_API_KEY = process.env.RAILWAY_API_KEY;
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;

// Validate required environment variables at module load time
if (!WEBHOOK_SECRET) {
  throw new Error('SUPABASE_WEBHOOK_SECRET is not configured');
}
if (!RAILWAY_API_URL) {
  throw new Error('RAILWAY_API_URL is not configured');
}
if (!RAILWAY_API_KEY) {
  throw new Error('RAILWAY_API_KEY is not configured');
}
if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) {
  throw new Error('Supabase credentials are not configured');
}

// Initialize Supabase client with service role key for admin operations
const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, {
  auth: {
    autoRefreshToken: false,
    persistSession: false
  }
});

/**
 * Interface for the Supabase webhook payload
 */
interface SupabaseWebhookPayload {
  type: 'INSERT' | 'UPDATE' | 'DELETE';
  table: string;
  record: {
    id: string;
    organization_id: string;
    policy_name: string;
    file_path: string;
    status: string;
    created_at: string;
    [key: string]: any;
  };
  old_record?: any;
}

/**
 * Update policy status in the database
 */
async function updatePolicyStatus(
  policyId: string,
  status: string,
  notes?: string
): Promise<void> {
  const updateData: any = { status };
  if (notes) {
    updateData.analysis_notes = notes;
  }

  const { error } = await supabase
    .from('insurance_policies')
    .update(updateData)
    .eq('id', policyId);

  if (error) {
    console.error('Failed to update policy status:', error);
    Sentry.captureException(error, {
      extra: { policyId, status, notes }
    });
    throw new Error(`Database update failed: ${error.message}`);
  }
}

/**
 * Dispatch analysis job to Railway API
 */
async function dispatchAnalysisJob(policyId: string, organizationId: string): Promise<void> {
  const endpoint = `${RAILWAY_API_URL}/analyze/${policyId}`;
  
  console.log(`Dispatching analysis job for policy ${policyId} to ${endpoint}`);

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': RAILWAY_API_KEY!,
    },
    body: JSON.stringify({
      policy_id: policyId,
      organization_id: organizationId,
    }),
    // Set a reasonable timeout (30 seconds)
    signal: AbortSignal.timeout(30000),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Railway API returned ${response.status}: ${errorText}`);
  }

  const result = await response.json();
  console.log(`Analysis job dispatched successfully:`, result);
}

/**
 * POST handler for the webhook endpoint
 */
export async function POST(req: NextRequest) {
  const startTime = Date.now();
  let policyId: string | undefined;

  try {
    // 1. Verify the webhook secret
    const secret = req.headers.get('x-webhook-secret');
    
    if (!secret || secret !== WEBHOOK_SECRET) {
      console.error('Webhook authentication failed: Invalid or missing secret');
      Sentry.captureMessage('Webhook authentication failed', {
        level: 'warning',
        extra: {
          hasSecret: !!secret,
          ip: req.headers.get('x-forwarded-for') || req.headers.get('x-real-ip'),
        }
      });
      return new NextResponse('Unauthorized', { status: 401 });
    }

    // 2. Parse and validate the payload
    let payload: SupabaseWebhookPayload;
    try {
      payload = await req.json();
    } catch (error) {
      console.error('Failed to parse webhook payload:', error);
      return new NextResponse('Invalid JSON payload', { status: 400 });
    }

    // Validate payload structure
    if (!payload.record || !payload.record.id) {
      console.error('Invalid payload structure:', payload);
      return new NextResponse('Missing required fields in payload', { status: 400 });
    }

    policyId = payload.record.id;
    const organizationId = payload.record.organization_id;
    const policyName = payload.record.policy_name || 'Unnamed Policy';

    console.log(`Received webhook for policy ${policyId} (${policyName})`);

    // 3. Validate that the policy has a file uploaded
    if (!payload.record.file_path) {
      console.error(`Policy ${policyId} has no file_path`);
      await updatePolicyStatus(
        policyId,
        'failed',
        'No policy document uploaded. Please upload a PDF file.'
      );
      return new NextResponse('Policy has no file uploaded', { status: 400 });
    }

    // 4. Update policy status to 'queued'
    await updatePolicyStatus(policyId, 'queued', 'Analysis job queued for processing.');

    // 5. Dispatch the analysis job to Railway API
    try {
      await dispatchAnalysisJob(policyId, organizationId);
    } catch (dispatchError: any) {
      console.error('Failed to dispatch analysis job:', dispatchError);
      
      // Update status to 'failed' with error details
      await updatePolicyStatus(
        policyId,
        'failed',
        `Failed to start analysis: ${dispatchError.message}`
      );

      // Capture in Sentry for monitoring
      Sentry.captureException(dispatchError, {
        extra: {
          policyId,
          organizationId,
          policyName,
          railwayApiUrl: RAILWAY_API_URL,
        }
      });

      return new NextResponse(
        JSON.stringify({
          error: 'Failed to dispatch analysis job',
          details: dispatchError.message
        }),
        { 
          status: 500,
          headers: { 'Content-Type': 'application/json' }
        }
      );
    }

    // 6. Success response
    const duration = Date.now() - startTime;
    console.log(`Webhook processed successfully in ${duration}ms`);

    return NextResponse.json({
      success: true,
      message: 'Analysis job dispatched successfully',
      policy_id: policyId,
      status: 'queued',
      duration_ms: duration,
    });

  } catch (error: any) {
    // Catch-all error handler
    console.error('Unexpected error in webhook handler:', error);
    
    Sentry.captureException(error, {
      extra: {
        policyId,
        duration_ms: Date.now() - startTime,
      }
    });

    // Try to update the policy status if we have a policy ID
    if (policyId) {
      try {
        await updatePolicyStatus(
          policyId,
          'failed',
          `Internal error: ${error.message}`
        );
      } catch (updateError) {
        console.error('Failed to update policy status after error:', updateError);
      }
    }

    return new NextResponse(
      JSON.stringify({
        error: 'Internal server error',
        message: error.message,
      }),
      { 
        status: 500,
        headers: { 'Content-Type': 'application/json' }
      }
    );
  }
}

/**
 * GET handler - returns endpoint information (for health checks)
 */
export async function GET() {
  return NextResponse.json({
    endpoint: 'start-analysis',
    description: 'Webhook endpoint for Supabase policy insertion triggers',
    method: 'POST',
    authentication: 'x-webhook-secret header required',
    status: 'operational',
  });
}
