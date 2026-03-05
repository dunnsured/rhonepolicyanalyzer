/* ============================================================
   RhôneRisk Cyber Insurance Policy Analyzer — Frontend App
   v2.0 — Conversion optimization: teaser/paywall, pricing,
   Stripe checkout, onboarding, credit system, admin gating.
   ============================================================ */

(function () {
  'use strict';

  // ---- Auth State --------------------------------------------
  let authToken = null;
  let currentUser = null;
  let userCredits = 0;

  // ---- App State ---------------------------------------------
  let currentView = 'home';
  let selectedFile = null;
  let analysisId = null;
  let pollTimer = null;
  let elapsedTimer = null;
  let elapsedStart = null;
  let progressSSE = null;
  let monitorSSE = null;
  let onboardingStep = 1;

  const STAGE_LABELS = {
    pending:              'Preparing...',
    extracting:           'Extracting Text from PDF',
    parsing:              'Parsing Policy Structure',
    scoring:              'Scoring 21 Coverage Sections',
    post_processing:      'Detecting Red Flags & Gaps',
    generating_narrative: 'Generating Analysis Narrative',
    generating_report:    'Building PDF Report',
    completed:            'Analysis Complete!',
    failed:               'Analysis Failed',
  };

  const STAGE_ORDER = [
    'extracting', 'parsing', 'scoring',
    'post_processing', 'generating_narrative', 'generating_report',
  ];

  const TIMING_THRESHOLDS = {
    extracting:           { green: 10, yellow: 30 },
    parsing:              { green: 10, yellow: 30 },
    scoring:              { green: 60, yellow: 120 },
    post_processing:      { green: 5,  yellow: 15 },
    generating_narrative: { green: 60, yellow: 120 },
    generating_report:    { green: 10, yellow: 30 },
    total:                { green: 180, yellow: 300 },
  };

  // ---- DOM helpers ------------------------------------------
  const $ = (sel, ctx) => (ctx || document).querySelector(sel);
  const $$ = (sel, ctx) => [...(ctx || document).querySelectorAll(sel)];

  // ---- Auth helpers -----------------------------------------
  function getStoredSession() {
    try {
      const s = localStorage.getItem('rhone_session');
      return s ? JSON.parse(s) : null;
    } catch { return null; }
  }

  function storeSession(session) {
    if (session) {
      localStorage.setItem('rhone_session', JSON.stringify(session));
    } else {
      localStorage.removeItem('rhone_session');
    }
  }

  function authFetch(url, opts = {}) {
    if (!opts.headers) opts.headers = {};
    if (authToken) {
      opts.headers['Authorization'] = `Bearer ${authToken}`;
    }
    return fetch(url, opts);
  }

  function isAdmin() {
    return currentUser && currentUser.email && currentUser.email.endsWith('@rhonerisk.com');
  }

  function updateAuthUI() {
    const authBtns = $('#nav-auth-buttons');
    const userMenu = $('#nav-user-menu');
    const authOnlyEls = $$('.auth-only');
    const guestCtas = $$('.guest-cta');
    const authCtas = $$('.auth-cta');

    if (currentUser && authToken) {
      authBtns.style.display = 'none';
      userMenu.style.display = 'flex';
      const name = currentUser.display_name || currentUser.email?.split('@')[0] || 'User';
      $('#nav-user-name').textContent = name;
      $('#nav-user-email').textContent = currentUser.email || '';
      $('#user-avatar').textContent = (name[0] || 'U').toUpperCase();
      authOnlyEls.forEach(el => el.style.display = '');
      guestCtas.forEach(el => el.style.display = 'none');
      authCtas.forEach(el => el.style.display = '');

      // Hide Monitor from non-admin users
      const monitorLink = $('a[data-view="monitor"]');
      if (monitorLink) {
        monitorLink.style.display = isAdmin() ? '' : 'none';
      }

      // Update credits badge
      updateCreditsDisplay();
    } else {
      authBtns.style.display = 'flex';
      userMenu.style.display = 'none';
      authOnlyEls.forEach(el => el.style.display = 'none');
      guestCtas.forEach(el => el.style.display = '');
      authCtas.forEach(el => el.style.display = 'none');
    }
  }

  function updateCreditsDisplay() {
    const badge = $('#nav-credits-badge');
    if (badge) {
      badge.textContent = `${userCredits} credit${userCredits !== 1 ? 's' : ''}`;
      badge.className = 'nav-credits-badge' + (userCredits <= 0 ? ' credits-zero' : '');
    }
    const dashBadge = $('#dash-credits-badge');
    if (dashBadge) {
      dashBadge.textContent = `${userCredits} credit${userCredits !== 1 ? 's' : ''}`;
    }
    // Update analyze page credit info
    const creditText = $('#credit-info-text');
    if (creditText) {
      if (userCredits > 0) {
        creditText.textContent = `${userCredits} credit${userCredits !== 1 ? 's' : ''} available`;
        creditText.parentElement.classList.remove('credits-empty');
      } else {
        creditText.textContent = 'No credits — purchase required after free analysis';
        creditText.parentElement.classList.add('credits-empty');
      }
    }
  }

  async function fetchCredits() {
    if (!authToken) return;
    try {
      const res = await authFetch('/api/v1/billing/credits');
      if (res.ok) {
        const data = await res.json();
        userCredits = data.credits || 0;
        updateCreditsDisplay();
      }
    } catch { /* ignore */ }
  }

  async function initAuth() {
    const session = getStoredSession();
    if (session && session.access_token) {
      try {
        const res = await fetch('/api/v1/auth/me', {
          headers: { 'Authorization': `Bearer ${session.access_token}` }
        });
        if (res.ok) {
          const data = await res.json();
          authToken = session.access_token;
          currentUser = data.user || data;
          storeSession(session);
          updateAuthUI();
          fetchCredits();
          return true;
        } else {
          if (session.refresh_token) {
            const refreshed = await refreshSession(session.refresh_token);
            if (refreshed) {
              updateAuthUI();
              fetchCredits();
              return true;
            }
          }
          storeSession(null);
          authToken = null;
          currentUser = null;
          updateAuthUI();
          return false;
        }
      } catch {
        storeSession(null);
        authToken = null;
        currentUser = null;
        updateAuthUI();
        return false;
      }
    }
    updateAuthUI();
    return false;
  }

  async function refreshSession(refreshToken) {
    try {
      const res = await fetch('/api/v1/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (res.ok) {
        const data = await res.json();
        authToken = data.access_token;
        currentUser = data.user;
        storeSession({
          access_token: data.access_token,
          refresh_token: data.refresh_token,
          user: data.user,
        });
        return true;
      }
    } catch { /* ignore */ }
    return false;
  }

  async function handleLogin(e) {
    e.preventDefault();
    const email = $('#login-email').value.trim();
    const password = $('#login-password').value;
    const errorEl = $('#login-error');
    const btn = $('#login-btn');

    errorEl.style.display = 'none';
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner spinner-gold"></span> Signing in...';

    try {
      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Login failed');
      }
      authToken = data.access_token;
      currentUser = data.user;
      storeSession({
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        user: data.user,
      });
      updateAuthUI();
      fetchCredits();
      toast('Signed in successfully!');
      navigate('dashboard');
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.style.display = 'block';
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Sign In';
    }
  }

  async function handleRegister(e) {
    e.preventDefault();
    const name = $('#register-name').value.trim();
    const email = $('#register-email').value.trim();
    const password = $('#register-password').value;
    const phone = $('#register-phone') ? $('#register-phone').value.trim() : '';
    const smsOptIn = $('#register-sms-optin') ? $('#register-sms-optin').checked : false;
    const errorEl = $('#register-error');
    const successEl = $('#register-success');
    const btn = $('#register-btn');

    errorEl.style.display = 'none';
    successEl.style.display = 'none';

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner spinner-gold"></span> Creating account...';

    try {
      const res = await fetch('/api/v1/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          password,
          display_name: name,
          phone: phone,
          sms_opt_in: smsOptIn,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Registration failed');
      }

      if (data.access_token) {
        authToken = data.access_token;
        currentUser = data.user;
        storeSession({
          access_token: data.access_token,
          refresh_token: data.refresh_token,
          user: data.user,
        });
        updateAuthUI();
        fetchCredits();
        toast('Account created! Welcome to RhoneRisk.');

        // Show onboarding for first-time users
        if (!localStorage.getItem('rhone_onboarded')) {
          showOnboarding();
        }
        navigate('dashboard');
      } else {
        successEl.innerHTML = 'Account created! Please check your email to confirm your account, then <a href="#login" data-view="login">sign in</a>.';
        successEl.style.display = 'block';
        const link = successEl.querySelector('a');
        if (link) link.addEventListener('click', (ev) => { ev.preventDefault(); navigate('login'); });
      }
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.style.display = 'block';
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Create Account &amp; Start Free';
    }
  }

  function handleLogout() {
    authToken = null;
    currentUser = null;
    userCredits = 0;
    storeSession(null);
    updateAuthUI();
    toast('Signed out successfully.');
    navigate('home');
  }

  // ---- Onboarding Modal -------------------------------------
  function showOnboarding() {
    const modal = $('#onboarding-modal');
    if (!modal) return;
    onboardingStep = 1;
    updateOnboardingStep();
    modal.style.display = 'flex';
  }

  function updateOnboardingStep() {
    $$('.onboarding-step').forEach(s => {
      s.classList.toggle('active', parseInt(s.dataset.step) === onboardingStep);
    });
    $$('.onboarding-dot').forEach(d => {
      d.classList.toggle('active', parseInt(d.dataset.dot) === onboardingStep);
    });
    const nextBtn = $('#btn-onboarding-next');
    if (nextBtn) {
      nextBtn.textContent = onboardingStep >= 3 ? 'Get Started' : 'Next';
    }
  }

  function closeOnboarding() {
    const modal = $('#onboarding-modal');
    if (modal) modal.style.display = 'none';
    localStorage.setItem('rhone_onboarded', '1');
  }

  // ---- Navigation -------------------------------------------
  function navigate(view) {
    // Auth guard: protected views require login
    const protectedViews = ['dashboard', 'analyze', 'progress', 'results', 'teaser', 'monitor'];
    if (protectedViews.includes(view) && !authToken) {
      toast('Please sign in to access this feature.', true);
      navigate('login');
      return;
    }

    // Admin guard: monitor requires @rhonerisk.com
    if (view === 'monitor' && !isAdmin()) {
      toast('Monitor dashboard is restricted to admin users.', true);
      navigate('dashboard');
      return;
    }

    $$('.view').forEach(v => v.classList.remove('active'));
    const el = $(`#view-${view}`);
    if (el) el.classList.add('active');

    $$('.nav-links a').forEach(a => {
      a.classList.toggle('active', a.dataset.view === view);
    });

    currentView = view;
    window.scrollTo({ top: 0, behavior: 'smooth' });

    if (['home', 'login', 'register', 'pricing'].includes(view)) {
      history.replaceState(null, '', view === 'home' ? '/' : `#${view}`);
    } else {
      history.replaceState(null, '', `#${view}`);
    }

    if (view === 'dashboard') loadDashboard();
    if (view === 'monitor') loadMonitorData();
    if (view === 'analyze') fetchCredits();
  }

  // ---- Toast ------------------------------------------------
  function toast(msg, isError) {
    const el = $('#toast');
    el.textContent = msg;
    el.classList.toggle('error', !!isError);
    el.classList.add('show');
    setTimeout(() => el.classList.remove('show'), 4000);
  }

  // ---- Formatting helpers -----------------------------------
  function formatDuration(seconds) {
    if (seconds == null || seconds <= 0) return '—';
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return `${m}m ${s}s`;
  }

  function formatElapsed(seconds) {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}m ${String(s).padStart(2, '0')}s`;
  }

  function timingClass(stage, seconds) {
    if (seconds == null || seconds <= 0) return 'timing-na';
    const t = TIMING_THRESHOLDS[stage] || TIMING_THRESHOLDS.total;
    if (seconds <= t.green) return 'timing-fast';
    if (seconds <= t.yellow) return 'timing-slow';
    return 'timing-very-slow';
  }

  function statusBadge(status) {
    let cls = 'status-pending';
    if (status === 'completed') cls = 'status-completed';
    else if (status === 'failed') cls = 'status-failed';
    else if (['extracting','parsing','scoring','post_processing','generating_narrative','generating_report','running'].includes(status)) cls = 'status-running';
    return `<span class="status-badge ${cls}">${status}</span>`;
  }

  function truncate(str, max) {
    return str.length > max ? str.slice(0, max) + '...' : str;
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  // ---- File handling ----------------------------------------
  function setupDropzone() {
    const zone = $('#dropzone');
    const input = $('#file-input');
    const info = $('#file-info');
    if (!zone || !input) return;

    function showFile(file) {
      if (!file) return;
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        toast('Only PDF files are accepted.', true);
        return;
      }
      if (file.size > 50 * 1024 * 1024) {
        toast('File too large. Maximum size is 50 MB.', true);
        return;
      }
      selectedFile = file;
      zone.classList.add('has-file');
      info.innerHTML = `
        <span class="file-name">${escapeHtml(file.name)}</span>
        <span class="file-size">(${(file.size / 1024 / 1024).toFixed(1)} MB)</span>
        <button class="remove-file" id="remove-file">Remove</button>
      `;
      info.style.display = 'flex';
      $('#remove-file').addEventListener('click', removeFile);
    }

    function removeFile(e) {
      e && e.stopPropagation();
      selectedFile = null;
      zone.classList.remove('has-file');
      info.style.display = 'none';
      info.innerHTML = '';
      input.value = '';
    }

    input.addEventListener('change', () => showFile(input.files[0]));
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      if (e.dataTransfer.files.length) showFile(e.dataTransfer.files[0]);
    });
  }

  // ---- Submit Analysis --------------------------------------
  async function submitAnalysis(e) {
    e.preventDefault();
    if (!authToken) { toast('Please sign in first.', true); navigate('login'); return; }
    if (!selectedFile) { toast('Please select a PDF file first.', true); return; }

    const btn = $('#submit-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner spinner-gold"></span> Uploading...';

    const form = new FormData();
    form.append('file', selectedFile);
    form.append('client_name', ($('#client_name') || {}).value || '');
    form.append('industry', ($('#industry') || {}).value || '');
    form.append('annual_revenue', ($('#annual_revenue') || {}).value || '');
    form.append('employee_count', ($('#employee_count') || {}).value || '');
    form.append('is_msp', ($('#is_msp') || {}).checked ? 'true' : 'false');
    form.append('notes', ($('#notes') || {}).value || '');

    try {
      const res = await authFetch('/api/v1/analyze', { method: 'POST', body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        if (res.status === 401) { handleLogout(); throw new Error('Session expired. Please sign in again.'); }
        throw new Error(err.detail || `Upload failed (${res.status})`);
      }
      const data = await res.json();
      analysisId = data.analysis_id;
      navigate('progress');
      startPolling();
      startElapsedTimer();
      connectProgressSSE();
    } catch (err) {
      toast(err.message, true);
    } finally {
      btn.disabled = false;
      btn.innerHTML = '&#11014; Upload &amp; Analyze';
    }
  }

  // ---- Elapsed Timer ----------------------------------------
  function startElapsedTimer() {
    elapsedStart = Date.now();
    if (elapsedTimer) clearInterval(elapsedTimer);
    elapsedTimer = setInterval(updateElapsed, 1000);
    updateElapsed();
  }

  function stopElapsedTimer() {
    if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null; }
  }

  function updateElapsed() {
    if (!elapsedStart) return;
    const el = $('#progress-elapsed');
    if (!el) return;
    const secs = (Date.now() - elapsedStart) / 1000;
    el.textContent = `Elapsed: ${formatElapsed(secs)}`;
  }

  // ---- Progress SSE Log Stream ------------------------------
  function connectProgressSSE() {
    if (progressSSE) { progressSSE.close(); progressSSE = null; }
    const viewer = $('#progress-log-viewer');
    const dot = $('#log-status-dot');
    if (!viewer || !analysisId) return;

    viewer.innerHTML = '';
    if (dot) dot.className = 'log-status-dot connected';

    const url = `/api/v1/analyze/${analysisId}/logs` + (authToken ? `?token=${encodeURIComponent(authToken)}` : '');
    progressSSE = new EventSource(url);
    progressSSE.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'close') {
          if (dot) dot.className = 'log-status-dot disconnected';
          progressSSE.close();
          progressSSE = null;
          return;
        }
        appendLogEntry(viewer, data);
      } catch (e) { /* ignore parse errors */ }
    };
    progressSSE.onerror = () => {
      if (dot) dot.className = 'log-status-dot disconnected';
    };
  }

  function appendLogEntry(viewer, entry) {
    const div = document.createElement('div');
    div.className = 'log-entry';
    const ts = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '';
    const levelCls = `log-level-${(entry.level || 'info').toLowerCase()}`;
    div.innerHTML = `<span class="log-time">${ts}</span> <span class="${levelCls}">[${entry.level}]</span> <span class="log-stage">${entry.stage || ''}</span> <span class="log-msg">${escapeHtml(entry.message || '')}</span>`;
    viewer.appendChild(div);
    viewer.scrollTop = viewer.scrollHeight;
  }

  // ---- Polling ----------------------------------------------
  function startPolling() {
    renderProgress('pending', 0, 0);
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollStatus, 3000);
    pollStatus();
  }

  async function pollStatus() {
    if (!analysisId) return;
    try {
      const res = await authFetch(`/api/v1/analyze/${analysisId}/status`);
      if (res.status === 401) { handleLogout(); return; }
      const data = await res.json();

      renderProgress(data.status, data.progress || 0, data.elapsed_seconds || 0);

      if (data.status === 'completed') {
        clearInterval(pollTimer);
        pollTimer = null;
        stopElapsedTimer();
        const el = $('#progress-elapsed');
        if (el) el.textContent = `Completed in ${formatDuration(data.elapsed_seconds || 0)}`;

        // Refresh credits after analysis
        await fetchCredits();

        // Check if analysis is unlocked or needs teaser
        await showCompletedAnalysis();
      } else if (data.status === 'failed') {
        clearInterval(pollTimer);
        pollTimer = null;
        stopElapsedTimer();
        const errMsg = data.error || 'Analysis failed.';
        $('#error-message').textContent = errMsg;
        navigate('error');
      }
    } catch (err) {
      /* ignore transient errors */
    }
  }

  async function showCompletedAnalysis() {
    // Check teaser status
    try {
      const res = await authFetch(`/api/v1/analyze/${analysisId}/teaser`);
      if (res.ok) {
        const teaser = await res.json();
        if (teaser.unlocked) {
          // Already unlocked — show full results
          await loadResults();
          setTimeout(() => navigate('results'), 1500);
        } else {
          // Show teaser view
          renderTeaser(teaser);
          setTimeout(() => navigate('teaser'), 1500);
        }
      } else {
        // Fallback: try loading full results directly
        await loadResults();
        setTimeout(() => navigate('results'), 1500);
      }
    } catch {
      // Fallback
      await loadResults();
      setTimeout(() => navigate('results'), 1500);
    }
  }

  function renderProgress(status, progress, elapsed) {
    const pct = Math.round(progress);
    const ring = $('#progress-ring-fill');
    const pctEl = $('#progress-pct');
    const stageEl = $('#progress-stage');
    const detailEl = $('#progress-detail');
    const idEl = $('#analysis-id-display');

    if (ring) {
      const circ = 2 * Math.PI * 78;
      ring.style.strokeDashoffset = circ - (circ * pct / 100);
    }
    if (pctEl) pctEl.textContent = pct;
    if (stageEl) stageEl.textContent = STAGE_LABELS[status] || status;
    if (detailEl) detailEl.textContent = status === 'completed' ? 'Analysis complete!' : 'Processing...';
    if (idEl && analysisId) idEl.textContent = analysisId;

    // Update step dots
    const steps = $$('.stage-step');
    const idx = STAGE_ORDER.indexOf(status);
    steps.forEach((step, i) => {
      step.classList.remove('active', 'done');
      if (i < idx) step.classList.add('done');
      else if (i === idx) step.classList.add('active');
    });
    if (status === 'completed') steps.forEach(s => s.classList.add('done'));
  }

  // ---- Teaser View ------------------------------------------
  function renderTeaser(data) {
    const score = data.overall_score || 0;
    const rating = data.rating || '—';

    // Score gauge
    const fill = $('#teaser-gauge-fill');
    if (fill) {
      const circ = 2 * Math.PI * 88;
      fill.style.strokeDashoffset = circ - (circ * score / 10);
      fill.style.stroke = score >= 7 ? 'var(--green)' : score >= 4 ? 'var(--gold)' : 'var(--red)';
    }
    const scoreNum = $('#teaser-score-num');
    if (scoreNum) scoreNum.textContent = score.toFixed(1);

    // Rating badge
    const badge = $('#teaser-rating-badge');
    if (badge) {
      badge.textContent = rating;
      badge.className = 'rating-badge';
      if (rating.toLowerCase().includes('superior')) badge.classList.add('rating-superior');
      else if (rating.toLowerCase().includes('average')) badge.classList.add('rating-average');
      else if (rating.toLowerCase().includes('basic')) badge.classList.add('rating-basic');
      else badge.classList.add('rating-none');
    }

    // Stats
    const rfEl = $('#teaser-red-flags');
    if (rfEl) rfEl.textContent = data.red_flag_count || 0;
    const gapEl = $('#teaser-gaps');
    if (gapEl) gapEl.textContent = data.critical_gap_count || 0;
    const recEl = $('#teaser-recommendation');
    if (recEl) {
      const rec = data.binding_recommendation || '—';
      recEl.textContent = typeof rec === 'string' ? rec : (rec.recommendation || '—');
    }

    // Client name
    const clientEl = $('#teaser-client-name');
    if (clientEl) clientEl.textContent = data.client_name ? `Analysis for ${data.client_name}` : 'Your analysis results are ready';

    // Credit info on unlock button
    const creditSpan = $('#teaser-credit-remaining');
    if (creditSpan) {
      creditSpan.textContent = userCredits > 0 ? `(${userCredits} available)` : '(0 available)';
    }

    // Update button states
    const creditBtn = $('#btn-unlock-credit');
    if (creditBtn) {
      creditBtn.disabled = userCredits <= 0;
      if (userCredits <= 0) {
        creditBtn.textContent = 'No Credits Available';
        creditBtn.classList.add('btn-disabled');
      }
    }
  }

  async function unlockWithCredit() {
    if (!analysisId) return;
    try {
      const res = await authFetch(`/api/v1/billing/unlock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ analysis_id: analysisId }),
      });
      const data = await res.json();
      if (data.success) {
        // Show unlock animation
        showUnlockAnimation();
        // Update credits
        if (data.credits_remaining !== undefined) {
          userCredits = data.credits_remaining;
          updateCreditsDisplay();
        }
        // Load full results
        await loadResults();
        setTimeout(() => {
          hideUnlockAnimation();
          navigate('results');
        }, 2000);
      } else {
        toast(data.error || 'Failed to unlock report.', true);
      }
    } catch (err) {
      toast('Failed to unlock report. Please try again.', true);
    }
  }

  async function unlockWithPurchase() {
    if (!analysisId || !authToken) return;
    try {
      const res = await authFetch('/api/v1/billing/create-checkout-session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          plan: 'single',
          analysis_id: analysisId,
        }),
      });
      const data = await res.json();
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      } else {
        toast(data.error || 'Failed to create checkout session.', true);
      }
    } catch (err) {
      toast('Failed to start checkout. Please try again.', true);
    }
  }

  function showUnlockAnimation() {
    const overlay = $('#unlock-overlay');
    if (overlay) overlay.style.display = 'flex';
  }

  function hideUnlockAnimation() {
    const overlay = $('#unlock-overlay');
    if (overlay) overlay.style.display = 'none';
  }

  // ---- Pricing / Checkout -----------------------------------
  async function handleCheckout(plan) {
    if (!authToken) {
      toast('Please sign in or create an account first.', true);
      navigate('register');
      return;
    }

    try {
      const res = await authFetch('/api/v1/billing/create-checkout-session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan }),
      });
      const data = await res.json();
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      } else {
        toast(data.error || 'Failed to create checkout session.', true);
      }
    } catch (err) {
      toast('Failed to start checkout. Please try again.', true);
    }
  }

  // ---- Load Results -----------------------------------------
  async function loadResults() {
    if (!analysisId) return;
    try {
      const res = await authFetch(`/api/v1/analyze/${analysisId}`);
      if (res.status === 401) { handleLogout(); return; }
      if (!res.ok) throw new Error('Failed to load results');
      const data = await res.json();
      renderResults(data);
    } catch (err) {
      toast('Failed to load analysis results.', true);
    }
  }

  function renderResults(data) {
    // Score gauge
    const score = data.overall_score || 0;
    const fill = $('#gauge-fill');
    if (fill) {
      const circ = 2 * Math.PI * 88;
      fill.style.strokeDashoffset = circ - (circ * score / 10);
      fill.style.stroke = score >= 7 ? 'var(--green)' : score >= 4 ? 'var(--gold)' : 'var(--red)';
    }
    const scoreNum = $('#score-num');
    if (scoreNum) scoreNum.textContent = score.toFixed(1);

    // Rating badge
    const badge = $('#rating-badge');
    const rating = data.overall_rating || '—';
    if (badge) {
      badge.textContent = rating;
      badge.className = 'rating-badge';
      if (rating.toLowerCase().includes('superior')) badge.classList.add('rating-superior');
      else if (rating.toLowerCase().includes('average')) badge.classList.add('rating-average');
      else if (rating.toLowerCase().includes('basic')) badge.classList.add('rating-basic');
      else badge.classList.add('rating-none');
    }

    // Recommendation
    const rec = data.binding_recommendation || {};
    const recEl = $('#recommendation');
    if (recEl) {
      const recText = rec.recommendation || rec || '—';
      const rationale = rec.rationale || '';
      let recClass = 'rec-caution';
      let icon = '&#9888;&#65039;';
      const recLower = (typeof recText === 'string' ? recText : '').toLowerCase();
      if (recLower.includes('bind') && !recLower.includes('not') && !recLower.includes('caution') && !recLower.includes('modif')) {
        recClass = 'rec-bind'; icon = '&#9989;';
      } else if (recLower.includes('declin') || recLower.includes('not bind') || recLower.includes('do not')) {
        recClass = 'rec-decline'; icon = '&#10060;';
      }
      recEl.className = `recommendation-card ${recClass}`;
      recEl.innerHTML = `<span class="rec-icon">${icon}</span><div><strong>${escapeHtml(typeof recText === 'string' ? recText : JSON.stringify(recText))}</strong>${rationale ? `<p style="margin-top:8px;font-size:14px;opacity:.85">${escapeHtml(rationale)}</p>` : ''}</div>`;
    }

    // Policy metadata
    const meta = data.policy_metadata || {};
    const metaEl = $('#policy-metadata');
    if (metaEl) {
      const items = [
        ['Insurer', meta.insurer],
        ['Policy Form', meta.policy_form],
        ['Effective', meta.effective_date],
        ['Aggregate Limit', meta.aggregate_limit],
        ['Retention', meta.retention],
      ].filter(([,v]) => v);
      metaEl.innerHTML = items.map(([k,v]) => `<span><strong>${k}:</strong> ${escapeHtml(String(v))}</span>`).join(' &nbsp;|&nbsp; ');
    }

    // Coverage scores
    const tbody = $('#coverage-tbody');
    if (tbody && data.coverage_scores) {
      tbody.innerHTML = '';
      data.coverage_scores.forEach(c => {
        const s = c.score || 0;
        const tier = c.tier || '—';
        const pct = (s / 10) * 100;
        let color = 'var(--red)';
        if (s >= 7) color = 'var(--green)';
        else if (s >= 4) color = 'var(--gold)';
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${escapeHtml(c.coverage_name || c.section_key || '—')}</td>
          <td style="font-weight:700">${s.toFixed(1)}</td>
          <td><span class="tier-badge tier-${tier.toLowerCase().replace(/\s/g,'-')}">${tier}</span></td>
          <td><div class="score-bar"><div class="score-bar-fill" style="width:${pct}%;background:${color}"></div></div></td>
        `;
        tbody.appendChild(tr);
      });
    }

    // Red flags & gaps
    const rfEl = $('#red-flag-count');
    if (rfEl) rfEl.textContent = data.red_flag_count || 0;
    const gapsEl = $('#critical-gaps');
    if (gapsEl && data.critical_gaps) {
      gapsEl.innerHTML = data.critical_gaps.map(g => `<div class="gap-item">&#9888; ${escapeHtml(g)}</div>`).join('');
    }

    // Download button
    const dlBtn = $('#download-btn');
    if (dlBtn) {
      dlBtn.onclick = () => {
        window.open(`/api/v1/analyze/${analysisId}/report?token=${encodeURIComponent(authToken)}`, '_blank');
      };
    }
  }

  // ---- Dashboard (per-user) ---------------------------------
  async function loadDashboard() {
    if (!authToken) return;
    try {
      const res = await authFetch('/api/v1/dashboard');
      if (res.status === 401) { handleLogout(); return; }
      if (!res.ok) throw new Error('Failed to load dashboard');
      const data = await res.json();
      renderDashboard(data);
    } catch (err) {
      toast('Failed to load dashboard data.', true);
    }
  }

  function renderDashboard(data) {
    const user = data.user || {};
    const stats = data.stats || {};
    const recent = data.recent_analyses || [];

    // Welcome section
    const nameEl = $('#dash-user-name');
    if (nameEl) nameEl.textContent = user.display_name || user.email?.split('@')[0] || 'User';

    const subtitleEl = $('#dash-subtitle');
    if (subtitleEl) {
      const parts = [];
      if (user.member_since) parts.push(`Member since ${user.member_since}`);
      if (stats.total_analyses > 0) {
        parts.push(`${stats.total_analyses} ${stats.total_analyses === 1 ? 'analysis' : 'analyses'} run`);
      }
      subtitleEl.textContent = parts.length > 0
        ? parts.join(' \u00B7 ')
        : "Here's an overview of your policy analysis activity.";
    }

    // Stats cards
    const setVal = (id, val) => { const el = $(`#${id}`); if (el) el.textContent = val; };
    setVal('dash-total', stats.total_analyses || 0);
    setVal('dash-completed', stats.completed || 0);
    setVal('dash-failed', stats.failed || 0);
    setVal('dash-avg-score', stats.average_score != null ? `${stats.average_score}/10` : '\u2014');

    // Recent analyses table
    const tbody = $('#dash-analyses-tbody');
    const table = $('#dash-analyses-table');
    const emptyState = $('#dash-empty');

    if (!recent.length) {
      if (table) table.style.display = 'none';
      if (emptyState) emptyState.style.display = 'block';
      return;
    }

    if (table) table.style.display = '';
    if (emptyState) emptyState.style.display = 'none';
    if (!tbody) return;

    tbody.innerHTML = '';
    recent.forEach(a => {
      const tr = document.createElement('tr');

      // Score pill
      let scoreHtml = '<span class="dash-score dash-score-na">\u2014</span>';
      if (a.overall_score != null) {
        const s = a.overall_score;
        const cls = s >= 7 ? 'dash-score-high' : s >= 4 ? 'dash-score-mid' : 'dash-score-low';
        scoreHtml = `<span class="dash-score ${cls}">${s.toFixed(1)}</span>`;
      }

      // Rating badge
      let ratingHtml = '<span class="dash-rating dash-rating-none">\u2014</span>';
      if (a.overall_rating) {
        const r = a.overall_rating.toLowerCase();
        let cls = 'dash-rating-none';
        if (r.includes('superior')) cls = 'dash-rating-superior';
        else if (r.includes('average')) cls = 'dash-rating-average';
        else if (r.includes('basic')) cls = 'dash-rating-basic';
        ratingHtml = `<span class="dash-rating ${cls}">${escapeHtml(a.overall_rating)}</span>`;
      }

      // Red flags
      let flagsHtml = '<span class="dash-flags dash-flags-ok">0</span>';
      if (a.red_flag_count != null && a.red_flag_count > 0) {
        flagsHtml = `<span class="dash-flags dash-flags-warn">\u26A0 ${a.red_flag_count}</span>`;
      } else if (a.status !== 'completed') {
        flagsHtml = '<span class="dash-flags" style="color:var(--gray-400)">\u2014</span>';
      }

      // Date
      let dateStr = '\u2014';
      if (a.start_time) {
        try {
          const d = new Date(a.start_time);
          dateStr = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        } catch { dateStr = '\u2014'; }
      }

      // Actions
      let actionsHtml = '';
      if (a.status === 'completed') {
        actionsHtml += `<button class="btn btn-sm btn-outline dash-view-btn" data-id="${a.analysis_id}">View</button>`;
        if (a.has_report) {
          actionsHtml += `<a href="/api/v1/analyze/${a.analysis_id}/report?token=${encodeURIComponent(authToken)}" download class="btn btn-sm btn-primary" style="text-decoration:none" title="Download PDF">&#8595; PDF</a>`;
        }
      } else if (a.status === 'failed') {
        actionsHtml = `<span style="font-size:12px;color:var(--red)">Failed</span>`;
      } else {
        actionsHtml = `<span style="font-size:12px;color:var(--amber)">In progress...</span>`;
      }

      tr.innerHTML = `
        <td style="font-weight:600">${escapeHtml(a.client_name || '\u2014')}</td>
        <td title="${escapeHtml(a.filename || '')}">${truncate(a.filename || '\u2014', 25)}</td>
        <td>${statusBadge(a.status)}</td>
        <td>${scoreHtml}</td>
        <td>${ratingHtml}</td>
        <td>${flagsHtml}</td>
        <td style="white-space:nowrap;font-size:13px;color:var(--gray-500)">${dateStr}</td>
        <td><div class="dash-actions">${actionsHtml}</div></td>
      `;
      tbody.appendChild(tr);
    });

    // Wire up view buttons
    $$('.dash-view-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        analysisId = btn.dataset.id;
        // Check if unlocked
        try {
          const res = await authFetch(`/api/v1/analyze/${analysisId}/teaser`);
          if (res.ok) {
            const teaser = await res.json();
            if (teaser.unlocked) {
              await loadResults();
              navigate('results');
            } else {
              renderTeaser(teaser);
              navigate('teaser');
            }
          } else {
            await loadResults();
            navigate('results');
          }
        } catch {
          await loadResults();
          navigate('results');
        }
      });
    });
  }

  // ---- Monitor Dashboard ------------------------------------
  async function loadMonitorData() {
    if (!authToken) return;
    try {
      const res = await authFetch('/api/v1/analyses');
      if (res.status === 401) { handleLogout(); return; }
      if (!res.ok) throw new Error('Failed to load analyses');
      const data = await res.json();
      renderMonitorDashboard(data);
    } catch (err) {
      toast('Failed to load monitoring data.', true);
    }
  }

  function renderMonitorDashboard(analyses) {
    const list = analyses.analyses || analyses || [];

    // Stats
    const total = list.length;
    const completed = list.filter(a => a.status === 'completed').length;
    const failed = list.filter(a => a.status === 'failed').length;
    const running = total - completed - failed;
    const completedList = list.filter(a => a.status === 'completed' && a.total_duration_seconds > 0);
    const avgTime = completedList.length > 0
      ? completedList.reduce((s, a) => s + a.total_duration_seconds, 0) / completedList.length
      : 0;

    const setVal = (id, val) => { const el = $(`#${id}`); if (el) el.textContent = val; };
    setVal('stat-total', total);
    setVal('stat-completed', completed);
    setVal('stat-failed', failed);
    setVal('stat-running', running);
    setVal('stat-avg-time', avgTime > 0 ? formatDuration(avgTime) : '—');

    // Table
    const tbody = $('#history-tbody');
    const noHistory = $('#no-history');
    if (!list.length) {
      if (tbody) tbody.innerHTML = '';
      if (noHistory) noHistory.style.display = 'block';
      return;
    }
    if (noHistory) noHistory.style.display = 'none';

    // Log selector
    const logSelect = $('#log-analysis-select');
    if (logSelect) {
      const prevVal = logSelect.value;
      logSelect.innerHTML = '<option value="">Select an analysis...</option>';
      list.forEach(a => {
        const opt = document.createElement('option');
        opt.value = a.analysis_id;
        opt.textContent = `${a.analysis_id} — ${a.client_name || a.filename || 'Unknown'}`;
        logSelect.appendChild(opt);
      });
      if (prevVal) logSelect.value = prevVal;
    }

    if (!tbody) return;
    tbody.innerHTML = '';

    list.forEach(a => {
      const tr = document.createElement('tr');
      const getStageTime = (stage) => {
        const t = (a.stage_timings || {})[stage];
        const dur = t ? (t.duration_seconds || 0) : 0;
        return {
          text: dur > 0 ? formatDuration(dur) : '—',
          cls: dur > 0 ? timingClass(stage, dur) : 'timing-na',
        };
      };

      const ext = getStageTime('extracting');
      const par = getStageTime('parsing');
      const sco = getStageTime('scoring');
      const pp  = getStageTime('post_processing');
      const nar = getStageTime('generating_narrative');
      const rep = getStageTime('generating_report');
      const tot = {
        text: a.total_duration_seconds > 0 ? formatDuration(a.total_duration_seconds) : '—',
        cls: a.total_duration_seconds > 0 ? timingClass('total', a.total_duration_seconds) : 'timing-na',
      };

      tr.innerHTML = `
        <td><code>${a.analysis_id}</code></td>
        <td>${escapeHtml(a.client_name || '—')}</td>
        <td title="${escapeHtml(a.filename || '')}">${truncate(a.filename || '—', 20)}</td>
        <td>${statusBadge(a.status)}</td>
        <td class="${tot.cls}">${tot.text}</td>
        <td class="${ext.cls}">${ext.text}</td>
        <td class="${par.cls}">${par.text}</td>
        <td class="${sco.cls}">${sco.text}</td>
        <td class="${pp.cls}">${pp.text}</td>
        <td class="${nar.cls}">${nar.text}</td>
        <td class="${rep.cls}">${rep.text}</td>
        <td style="white-space:nowrap">
          <button class="btn btn-sm btn-outline detail-btn" data-id="${a.analysis_id}">View</button>
          ${a.status === 'completed' ? `<a href="/api/v1/analyze/${a.analysis_id}/report?token=${encodeURIComponent(authToken)}" download class="btn btn-sm btn-primary" style="margin-left:6px;text-decoration:none" title="Download PDF report">&#8595; PDF</a>` : ''}
        </td>
      `;
      tbody.appendChild(tr);
    });

    $$('.detail-btn').forEach(btn => {
      btn.addEventListener('click', () => showDetail(btn.dataset.id));
    });
  }

  // ---- Detail Modal -----------------------------------------
  async function showDetail(id) {
    try {
      const res = await authFetch(`/api/v1/analyze/${id}/timing`);
      if (res.status === 401) { handleLogout(); return; }
      if (!res.ok) throw new Error('Failed to load details');
      const data = await res.json();
      renderDetailModal(data);
    } catch (err) {
      toast('Failed to load analysis details.', true);
    }
  }

  function renderDetailModal(data) {
    const overlay = $('#detail-overlay');
    const content = $('#detail-content');

    let html = '';

    const rows = [
      ['Analysis ID', data.analysis_id],
      ['Client', data.client_name || '—'],
      ['File', data.filename || '—'],
      ['File Size', data.file_size_bytes ? `${(data.file_size_bytes / 1024).toFixed(0)} KB` : '—'],
      ['Pages', data.page_count || '—'],
      ['Status', data.status],
      ['Started', data.start_time ? new Date(data.start_time).toLocaleString() : '—'],
      ['Ended', data.end_time ? new Date(data.end_time).toLocaleString() : '—'],
      ['Total Duration', formatDuration(data.total_duration_seconds)],
    ];

    rows.forEach(([label, value]) => {
      html += `<div class="detail-row"><span class="detail-label">${label}</span><span class="detail-value">${value}</span></div>`;
    });

    html += '<div class="detail-section"><h4>Stage Timings</h4>';
    const stages = ['extracting', 'parsing', 'scoring', 'post_processing', 'generating_narrative', 'generating_report'];
    stages.forEach(stage => {
      const t = (data.stage_timings || {})[stage];
      const dur = t ? t.duration_seconds : 0;
      const cls = dur > 0 ? timingClass(stage, dur) : 'timing-na';
      html += `<div class="detail-row"><span class="detail-label">${STAGE_LABELS[stage] || stage}</span><span class="detail-value ${cls}">${dur > 0 ? formatDuration(dur) : '—'}</span></div>`;
    });
    html += '</div>';

    html += '<div class="detail-section"><h4>Claude API Token Usage</h4>';
    html += `<div class="detail-row"><span class="detail-label">Scoring — Input Tokens</span><span class="detail-value">${data.scoring_input_tokens ? data.scoring_input_tokens.toLocaleString() : '—'}</span></div>`;
    html += `<div class="detail-row"><span class="detail-label">Scoring — Output Tokens</span><span class="detail-value">${data.scoring_output_tokens ? data.scoring_output_tokens.toLocaleString() : '—'}</span></div>`;
    html += `<div class="detail-row"><span class="detail-label">Narrative — Input Tokens</span><span class="detail-value">${data.narrative_input_tokens ? data.narrative_input_tokens.toLocaleString() : '—'}</span></div>`;
    html += `<div class="detail-row"><span class="detail-label">Narrative — Output Tokens</span><span class="detail-value">${data.narrative_output_tokens ? data.narrative_output_tokens.toLocaleString() : '—'}</span></div>`;
    const totalTokens = (data.scoring_input_tokens || 0) + (data.scoring_output_tokens || 0) + (data.narrative_input_tokens || 0) + (data.narrative_output_tokens || 0);
    html += `<div class="detail-row"><span class="detail-label">Total Tokens</span><span class="detail-value" style="font-weight:700">${totalTokens > 0 ? totalTokens.toLocaleString() : '—'}</span></div>`;
    html += '</div>';

    if (data.error) {
      html += '<div class="detail-section"><h4>Error</h4>';
      html += `<div class="detail-error">${escapeHtml(data.error)}</div>`;
      html += '</div>';
    }

    if (data.status === 'completed') {
      html += `<div style="margin-top:20px;text-align:center"><a href="/api/v1/analyze/${data.analysis_id}/report?token=${encodeURIComponent(authToken)}" download class="btn btn-primary" style="text-decoration:none">&#8595;&nbsp; Download PDF Report</a></div>`;
    }

    content.innerHTML = html;
    overlay.style.display = 'flex';
  }

  // ---- Monitor Log Viewer -----------------------------------
  function connectMonitorSSE(id) {
    if (monitorSSE) { monitorSSE.close(); monitorSSE = null; }
    const viewer = $('#monitor-log-viewer');
    const dot = $('#monitor-log-status-dot');
    if (!viewer || !id) return;

    viewer.innerHTML = '';
    dot.className = 'log-status-dot connected';

    const url = `/api/v1/analyze/${id}/logs` + (authToken ? `?token=${encodeURIComponent(authToken)}` : '');
    monitorSSE = new EventSource(url);
    monitorSSE.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'close') {
          dot.className = 'log-status-dot disconnected';
          monitorSSE.close();
          monitorSSE = null;
          return;
        }
        appendLogEntry(viewer, data);
      } catch (e) { /* ignore */ }
    };
    monitorSSE.onerror = () => {
      dot.className = 'log-status-dot disconnected';
    };
  }

  // ---- Handle URL params (checkout success, etc.) -----------
  function handleUrlParams() {
    const hash = location.hash;
    const params = new URLSearchParams(hash.includes('?') ? hash.split('?')[1] : '');

    // Handle checkout success redirect
    const sessionId = params.get('session_id');
    if (sessionId) {
      const aid = params.get('analysis_id');
      if (aid) {
        // Single report purchase success
        analysisId = aid;
        toast('Payment successful! Loading your full report...');
        fetchCredits();
        loadResults().then(() => navigate('results'));
      } else {
        // Subscription purchase success
        toast('Subscription activated! Credits have been added to your account.');
        fetchCredits();
      }
      // Clean up URL
      history.replaceState(null, '', hash.split('?')[0]);
    }
  }

  // ---- Init -------------------------------------------------
  document.addEventListener('DOMContentLoaded', async () => {
    // Initialize auth
    await initAuth();

    // Navigation — all [data-view] elements
    $$('[data-view]').forEach(el => {
      el.addEventListener('click', e => {
        e.preventDefault();
        navigate(el.dataset.view);
      });
    });

    // Auth forms
    const loginForm = $('#login-form');
    if (loginForm) loginForm.addEventListener('submit', handleLogin);

    const registerForm = $('#register-form');
    if (registerForm) registerForm.addEventListener('submit', handleRegister);

    const logoutBtn = $('#logout-btn');
    if (logoutBtn) logoutBtn.addEventListener('click', handleLogout);

    // Dropzone
    setupDropzone();

    // Form submit
    const analyzeForm = $('#analyze-form');
    if (analyzeForm) analyzeForm.addEventListener('submit', submitAnalysis);

    // New analysis from results
    if ($('#new-analysis-btn')) {
      $('#new-analysis-btn').addEventListener('click', () => {
        analysisId = null;
        selectedFile = null;
        navigate('analyze');
      });
    }

    // Error retry
    if ($('#error-retry')) {
      $('#error-retry').addEventListener('click', () => navigate('analyze'));
    }

    // Dashboard: refresh button
    if ($('#dash-refresh-btn')) {
      $('#dash-refresh-btn').addEventListener('click', loadDashboard);
    }

    // Monitor: refresh button
    if ($('#refresh-history-btn')) {
      $('#refresh-history-btn').addEventListener('click', loadMonitorData);
    }

    // Monitor: log analysis selector
    if ($('#log-analysis-select')) {
      $('#log-analysis-select').addEventListener('change', (e) => {
        const id = e.target.value;
        if (id) {
          connectMonitorSSE(id);
        } else {
          if (monitorSSE) { monitorSSE.close(); monitorSSE = null; }
          const viewer = $('#monitor-log-viewer');
          if (viewer) viewer.innerHTML = '<div class="log-placeholder">Select an analysis above to view its logs.</div>';
          const dot = $('#monitor-log-status-dot');
          if (dot) dot.className = 'log-status-dot disconnected';
        }
      });
    }

    // Detail modal close
    if ($('#close-detail-btn')) {
      $('#close-detail-btn').addEventListener('click', () => {
        $('#detail-overlay').style.display = 'none';
      });
    }
    if ($('#detail-overlay')) {
      $('#detail-overlay').addEventListener('click', (e) => {
        if (e.target === $('#detail-overlay')) {
          $('#detail-overlay').style.display = 'none';
        }
      });
    }

    // Teaser unlock buttons
    if ($('#btn-unlock-credit')) {
      $('#btn-unlock-credit').addEventListener('click', unlockWithCredit);
    }
    if ($('#btn-unlock-purchase')) {
      $('#btn-unlock-purchase').addEventListener('click', unlockWithPurchase);
    }

    // Pricing checkout buttons
    $$('.btn-checkout').forEach(btn => {
      btn.addEventListener('click', () => {
        const plan = btn.dataset.plan;
        if (plan) handleCheckout(plan);
      });
    });

    // Onboarding modal
    if ($('#btn-onboarding-next')) {
      $('#btn-onboarding-next').addEventListener('click', () => {
        if (onboardingStep >= 3) {
          closeOnboarding();
        } else {
          onboardingStep++;
          updateOnboardingStep();
        }
      });
    }
    if ($('#btn-onboarding-skip')) {
      $('#btn-onboarding-skip').addEventListener('click', closeOnboarding);
    }
    // Click dots to navigate
    $$('.onboarding-dot').forEach(dot => {
      dot.addEventListener('click', () => {
        onboardingStep = parseInt(dot.dataset.dot);
        updateOnboardingStep();
      });
    });
    // Close onboarding on overlay click
    if ($('#onboarding-modal')) {
      $('#onboarding-modal').addEventListener('click', (e) => {
        if (e.target === $('#onboarding-modal')) closeOnboarding();
      });
    }

    // Handle URL params (checkout success redirects)
    handleUrlParams();

    // Handle hash — if logged in and no specific hash, go to dashboard
    const hash = location.hash.replace('#', '').split('?')[0];
    if (hash && $(`#view-${hash}`)) {
      navigate(hash);
    } else if (authToken) {
      navigate('dashboard');
    } else {
      navigate('home');
    }
  });

})();
