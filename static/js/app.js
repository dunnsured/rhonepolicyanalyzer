/* ============================================================
   RhôneRisk Cyber Insurance Policy Analyzer — Frontend App
   ============================================================ */

(function () {
  'use strict';

  // ---- State ------------------------------------------------
  let currentView = 'home';
  let selectedFile = null;
  let analysisId = null;
  let pollTimer = null;
  let elapsedTimer = null;
  let elapsedStart = null;
  let progressSSE = null;
  let monitorSSE = null;

  const STAGE_LABELS = {
    pending:              'Pending',
    extracting:           'Extracting Text',
    parsing:              'Parsing Policy',
    scoring:              'Scoring Coverage',
    post_processing:      'Post-Processing',
    generating_narrative: 'Generating Narrative',
    generating_report:    'Generating Report',
    completed:            'Completed',
    failed:               'Failed',
  };

  const STAGE_ORDER = [
    'extracting', 'parsing', 'scoring',
    'post_processing', 'generating_narrative', 'generating_report',
  ];

  // Timing thresholds (seconds) for color coding
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

  // ---- Navigation -------------------------------------------
  function navigate(view) {
    $$('.view').forEach(v => v.classList.remove('active'));
    const el = $(`#view-${view}`);
    if (el) el.classList.add('active');

    $$('.nav-links a').forEach(a => {
      a.classList.toggle('active', a.dataset.view === view);
    });

    currentView = view;
    window.scrollTo({ top: 0, behavior: 'smooth' });
    history.replaceState(null, '', view === 'home' ? '/' : `#${view}`);

    // Load monitor data when navigating to monitor view
    if (view === 'monitor') loadMonitorData();
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

  // ---- File handling ----------------------------------------
  function setupDropzone() {
    const zone = $('#dropzone');
    const input = $('#file-input');
    const info = $('#file-info');

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
        <span class="file-name">${file.name}</span>
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

  // ---- Submit -----------------------------------------------
  async function submitAnalysis(e) {
    e.preventDefault();
    if (!selectedFile) { toast('Please select a PDF file first.', true); return; }

    const btn = $('#submit-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner spinner-gold"></span> Uploading…';

    const form = new FormData();
    form.append('file', selectedFile);
    form.append('client_name', $('#client_name').value);
    form.append('industry', $('#industry').value);
    form.append('annual_revenue', $('#annual_revenue').value);
    form.append('employee_count', $('#employee_count').value);
    form.append('is_msp', $('#is_msp').checked ? 'true' : 'false');
    form.append('notes', $('#notes').value);

    try {
      const res = await fetch('/api/v1/analyze', { method: 'POST', body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
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
      btn.innerHTML = '⬆ Upload &amp; Analyze';
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
    const stageEl = $('#progress-stage');
    const stageName = stageEl ? stageEl.textContent : '';
    el.textContent = `${stageName}… ${formatElapsed(secs)} elapsed`;
  }

  // ---- Progress SSE Log Stream ------------------------------
  function connectProgressSSE() {
    if (progressSSE) { progressSSE.close(); progressSSE = null; }
    const viewer = $('#progress-log-viewer');
    const dot = $('#log-status-dot');
    if (!viewer || !analysisId) return;

    viewer.innerHTML = '';
    dot.className = 'log-status-dot connected';

    progressSSE = new EventSource(`/api/v1/analyze/${analysisId}/logs`);
    progressSSE.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'close') {
          dot.className = 'log-status-dot disconnected';
          progressSSE.close();
          progressSSE = null;
          return;
        }
        appendLogEntry(viewer, data);
      } catch (e) { /* ignore parse errors */ }
    };
    progressSSE.onerror = () => {
      dot.className = 'log-status-dot disconnected';
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

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
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
      const res = await fetch(`/api/v1/analyze/${analysisId}/status`);
      const data = await res.json();

      renderProgress(data.status, data.progress || 0, data.elapsed_seconds || 0);

      if (data.status === 'completed') {
        clearInterval(pollTimer);
        pollTimer = null;
        stopElapsedTimer();
        const el = $('#progress-elapsed');
        if (el) el.textContent = `Completed in ${formatDuration(data.elapsed_seconds || 0)}`;
        await loadResults();
      } else if (data.status === 'failed') {
        clearInterval(pollTimer);
        pollTimer = null;
        stopElapsedTimer();
        renderError(data.error || 'Analysis failed unexpectedly.');
      }
    } catch (err) {
      console.error('Poll error:', err);
    }
  }

  function renderProgress(status, progress, elapsed) {
    $('#progress-pct').textContent = progress;
    $('#progress-stage').textContent = STAGE_LABELS[status] || status;
    $('#progress-detail').textContent = status === 'completed'
      ? 'Analysis complete! Loading results…'
      : 'This typically takes 1–3 minutes depending on policy length.';
    $('#analysis-id-display').textContent = analysisId;

    const circumference = 2 * Math.PI * 78;
    const offset = circumference - (progress / 100) * circumference;
    $('#progress-ring-fill').style.strokeDasharray = circumference;
    $('#progress-ring-fill').style.strokeDashoffset = offset;

    const currentIdx = STAGE_ORDER.indexOf(status);
    $$('.stage-step').forEach((el, i) => {
      el.classList.remove('active', 'done');
      if (status === 'completed') {
        el.classList.add('done');
      } else if (i < currentIdx) {
        el.classList.add('done');
      } else if (i === currentIdx) {
        el.classList.add('active');
      }
    });
  }

  function renderError(msg) {
    navigate('error');
    $('#error-message').textContent = msg;
  }

  // ---- Results ----------------------------------------------
  async function loadResults() {
    try {
      const res = await fetch(`/api/v1/analyze/${analysisId}`);
      if (!res.ok) throw new Error('Failed to load results');
      const data = await res.json();
      renderResults(data);
      navigate('results');
    } catch (err) {
      renderError(err.message);
    }
  }

  function scoreColor(score) {
    if (score >= 8) return '#059669';
    if (score >= 6) return '#2563eb';
    if (score >= 3) return '#d97706';
    return '#dc2626';
  }

  function ratingClass(rating) {
    if (!rating) return 'rating-average';
    const r = rating.toLowerCase();
    if (r.includes('superior')) return 'rating-superior';
    if (r.includes('average'))  return 'rating-average';
    if (r.includes('basic'))    return 'rating-basic';
    return 'rating-nocoverage';
  }

  function recClass(rec) {
    if (!rec) return 'rec-caution';
    const r = rec.toLowerCase();
    if (r.includes('bind') || r.includes('recommend')) return 'rec-bind';
    if (r.includes('caution') || r.includes('conditional')) return 'rec-caution';
    return 'rec-decline';
  }

  function recIcon(rec) {
    if (!rec) return '⚠️';
    const r = rec.toLowerCase();
    if (r.includes('bind') || r.includes('recommend')) return '✅';
    if (r.includes('caution') || r.includes('conditional')) return '⚠️';
    return '🚫';
  }

  function tierLabel(score) {
    if (score >= 8) return 'Superior';
    if (score >= 5) return 'Average';
    if (score >= 2) return 'Basic';
    return 'No Coverage';
  }

  function tierClass(score) {
    if (score >= 8) return 'superior';
    if (score >= 5) return 'average';
    if (score >= 2) return 'basic';
    return 'nocoverage';
  }

  function renderResults(data) {
    const score = data.overall_score != null ? data.overall_score : 0;
    const color = scoreColor(score);
    const circumference = 2 * Math.PI * 88;
    const offset = circumference - (score / 10) * circumference;

    $('#gauge-fill').style.strokeDasharray = circumference;
    $('#gauge-fill').style.strokeDashoffset = offset;
    $('#gauge-fill').style.stroke = color;
    $('#score-num').textContent = score.toFixed(1);
    $('#score-num').style.color = color;

    const rating = data.overall_rating || 'N/A';
    const badgeEl = $('#rating-badge');
    badgeEl.textContent = rating;
    badgeEl.className = `rating-badge ${ratingClass(rating)}`;

    const rec = data.binding_recommendation || 'N/A';
    const recEl = $('#recommendation');
    recEl.className = `recommendation-card ${recClass(rec)}`;
    recEl.innerHTML = `
      <span class="rec-icon">${recIcon(rec)}</span>
      <div>
        <div style="font-size:13px;opacity:.7;margin-bottom:2px">Binding Recommendation</div>
        <div>${rec}</div>
        ${data.binding_rationale ? `<div style="font-size:13px;font-weight:400;margin-top:6px;opacity:.8">${data.binding_rationale}</div>` : ''}
      </div>
    `;

    const meta = data.policy_metadata;
    if (meta) {
      let metaHtml = '';
      const fields = [
        ['Insurer', meta.insurer],
        ['Policy Number', meta.policy_number],
        ['Policy Period', meta.policy_period],
        ['Named Insured', meta.named_insured],
        ['Aggregate Limit', meta.aggregate_limit],
        ['Retention/Deductible', meta.retention],
      ];
      fields.forEach(([label, val]) => {
        if (val) metaHtml += `<div><strong>${label}:</strong> ${val}</div>`;
      });
      $('#policy-metadata').innerHTML = metaHtml || '<div style="color:var(--gray-400)">No metadata extracted</div>';
    }

    const scores = data.coverage_scores;
    const tbody = $('#coverage-tbody');
    tbody.innerHTML = '';
    if (scores && typeof scores === 'object') {
      const entries = Array.isArray(scores)
        ? scores
        : Object.entries(scores).map(([k, v]) => {
            if (typeof v === 'object' && v !== null) return { name: v.name || k, score: v.score ?? v.value ?? 0, ...v };
            return { name: k, score: v };
          });

      entries.forEach(item => {
        const s = typeof item.score === 'number' ? item.score : parseFloat(item.score) || 0;
        const pct = (s / 10) * 100;
        const cls = tierClass(s);
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${item.name || item.section || item.coverage_name || '—'}</td>
          <td class="score-cell ${cls}">${s.toFixed(1)}</td>
          <td>${tierLabel(s)}</td>
          <td class="score-bar-cell">
            <div class="score-bar"><div class="score-bar-fill" style="width:${pct}%;background:${scoreColor(s)}"></div></div>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    const rfCount = data.red_flag_count != null ? data.red_flag_count : '—';
    $('#red-flag-count').textContent = rfCount;

    const gaps = data.critical_gaps;
    const gapsList = $('#critical-gaps');
    gapsList.innerHTML = '';
    if (gaps && gaps.length) {
      gaps.forEach(g => {
        const text = typeof g === 'string' ? g : (g.description || g.name || JSON.stringify(g));
        const div = document.createElement('div');
        div.className = 'alert-box alert-red';
        div.innerHTML = `<span class="alert-icon">⚠</span><span>${text}</span>`;
        gapsList.appendChild(div);
      });
    } else {
      gapsList.innerHTML = '<p style="color:var(--gray-400);font-size:14px">No critical gaps identified.</p>';
    }

    $('#download-btn').onclick = () => {
      window.open(`/api/v1/analyze/${analysisId}/report`, '_blank');
    };
  }

  // =========================================================
  // MONITORING DASHBOARD
  // =========================================================

  async function loadMonitorData() {
    try {
      const res = await fetch('/api/v1/analyses');
      if (!res.ok) throw new Error('Failed to load analyses');
      const data = await res.json();
      renderMonitorDashboard(data.analyses || []);
    } catch (err) {
      console.error('Monitor load error:', err);
      toast('Failed to load monitoring data.', true);
    }
  }

  function renderMonitorDashboard(analyses) {
    // Summary stats
    const total = analyses.length;
    const completed = analyses.filter(a => a.status === 'completed').length;
    const failed = analyses.filter(a => a.status === 'failed').length;
    const running = total - completed - failed;
    const completedAnalyses = analyses.filter(a => a.status === 'completed' && a.total_duration_seconds > 0);
    const avgTime = completedAnalyses.length > 0
      ? completedAnalyses.reduce((sum, a) => sum + a.total_duration_seconds, 0) / completedAnalyses.length
      : 0;

    $('#stat-total').textContent = total;
    $('#stat-completed').textContent = completed;
    $('#stat-failed').textContent = failed;
    $('#stat-running').textContent = running;
    $('#stat-avg-time').textContent = avgTime > 0 ? formatDuration(avgTime) : '—';

    // History table
    const tbody = $('#history-tbody');
    tbody.innerHTML = '';
    const noHistory = $('#no-history');

    if (analyses.length === 0) {
      noHistory.style.display = 'block';
      return;
    }
    noHistory.style.display = 'none';

    // Populate analysis selector for log viewer
    const select = $('#log-analysis-select');
    const currentVal = select.value;
    select.innerHTML = '<option value="">Select an analysis…</option>';
    analyses.forEach(a => {
      const opt = document.createElement('option');
      opt.value = a.analysis_id;
      opt.textContent = `${a.analysis_id} — ${a.client_name || a.filename || 'Unknown'} (${a.status})`;
      select.appendChild(opt);
    });
    if (currentVal) select.value = currentVal;

    analyses.forEach(a => {
      const tr = document.createElement('tr');
      const timings = a.stage_timings || {};

      function getStageTime(stage) {
        const t = timings[stage];
        if (!t || !t.duration_seconds) return { text: '—', cls: 'timing-na' };
        return {
          text: formatDuration(t.duration_seconds),
          cls: timingClass(stage, t.duration_seconds),
        };
      }

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
        <td><button class="btn btn-sm btn-outline detail-btn" data-id="${a.analysis_id}">View</button></td>
      `;
      tbody.appendChild(tr);
    });

    // Attach detail button handlers
    $$('.detail-btn').forEach(btn => {
      btn.addEventListener('click', () => showDetail(btn.dataset.id));
    });
  }

  function truncate(str, max) {
    return str.length > max ? str.slice(0, max) + '…' : str;
  }

  // ---- Detail Modal -----------------------------------------
  async function showDetail(id) {
    try {
      const res = await fetch(`/api/v1/analyze/${id}/timing`);
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

    // Basic info
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

    // Stage timings
    html += '<div class="detail-section"><h4>Stage Timings</h4>';
    const stages = ['extracting', 'parsing', 'scoring', 'post_processing', 'generating_narrative', 'generating_report'];
    stages.forEach(stage => {
      const t = (data.stage_timings || {})[stage];
      const dur = t ? t.duration_seconds : 0;
      const cls = dur > 0 ? timingClass(stage, dur) : 'timing-na';
      html += `<div class="detail-row"><span class="detail-label">${STAGE_LABELS[stage] || stage}</span><span class="detail-value ${cls}">${dur > 0 ? formatDuration(dur) : '—'}</span></div>`;
    });
    html += '</div>';

    // Token usage
    html += '<div class="detail-section"><h4>Claude API Token Usage</h4>';
    html += `<div class="detail-row"><span class="detail-label">Scoring — Input Tokens</span><span class="detail-value">${data.scoring_input_tokens ? data.scoring_input_tokens.toLocaleString() : '—'}</span></div>`;
    html += `<div class="detail-row"><span class="detail-label">Scoring — Output Tokens</span><span class="detail-value">${data.scoring_output_tokens ? data.scoring_output_tokens.toLocaleString() : '—'}</span></div>`;
    html += `<div class="detail-row"><span class="detail-label">Narrative — Input Tokens</span><span class="detail-value">${data.narrative_input_tokens ? data.narrative_input_tokens.toLocaleString() : '—'}</span></div>`;
    html += `<div class="detail-row"><span class="detail-label">Narrative — Output Tokens</span><span class="detail-value">${data.narrative_output_tokens ? data.narrative_output_tokens.toLocaleString() : '—'}</span></div>`;
    const totalTokens = (data.scoring_input_tokens || 0) + (data.scoring_output_tokens || 0) + (data.narrative_input_tokens || 0) + (data.narrative_output_tokens || 0);
    html += `<div class="detail-row"><span class="detail-label">Total Tokens</span><span class="detail-value" style="font-weight:700">${totalTokens > 0 ? totalTokens.toLocaleString() : '—'}</span></div>`;
    html += '</div>';

    // Error
    if (data.error) {
      html += '<div class="detail-section"><h4>Error</h4>';
      html += `<div class="detail-error">${escapeHtml(data.error)}</div>`;
      html += '</div>';
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

    monitorSSE = new EventSource(`/api/v1/analyze/${id}/logs`);
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

  // ---- Init -------------------------------------------------
  document.addEventListener('DOMContentLoaded', () => {
    // Navigation
    $$('[data-view]').forEach(el => {
      el.addEventListener('click', e => {
        e.preventDefault();
        navigate(el.dataset.view);
      });
    });

    // Handle hash
    const hash = location.hash.replace('#', '');
    if (hash && $(`#view-${hash}`)) navigate(hash);
    else navigate('home');

    // Dropzone
    setupDropzone();

    // Form submit
    $('#analyze-form').addEventListener('submit', submitAnalysis);

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
  });

})();
