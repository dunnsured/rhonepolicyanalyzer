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

    // Update URL hash
    history.replaceState(null, '', view === 'home' ? '/' : `#${view}`);
  }

  // ---- Toast ------------------------------------------------
  function toast(msg, isError) {
    const el = $('#toast');
    el.textContent = msg;
    el.classList.toggle('error', !!isError);
    el.classList.add('show');
    setTimeout(() => el.classList.remove('show'), 4000);
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
    } catch (err) {
      toast(err.message, true);
    } finally {
      btn.disabled = false;
      btn.innerHTML = '⬆ Upload &amp; Analyze';
    }
  }

  // ---- Polling ----------------------------------------------
  function startPolling() {
    renderProgress('pending', 0);
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollStatus, 3000);
    pollStatus(); // immediate first call
  }

  async function pollStatus() {
    if (!analysisId) return;
    try {
      const res = await fetch(`/api/v1/analyze/${analysisId}/status`);
      const data = await res.json();

      renderProgress(data.status, data.progress || 0);

      if (data.status === 'completed') {
        clearInterval(pollTimer);
        pollTimer = null;
        // Fetch full results
        await loadResults();
      } else if (data.status === 'failed') {
        clearInterval(pollTimer);
        pollTimer = null;
        renderError(data.error || 'Analysis failed unexpectedly.');
      }
    } catch (err) {
      console.error('Poll error:', err);
    }
  }

  function renderProgress(status, progress) {
    $('#progress-pct').textContent = progress;
    $('#progress-stage').textContent = STAGE_LABELS[status] || status;
    $('#progress-detail').textContent = status === 'completed'
      ? 'Analysis complete! Loading results…'
      : 'This typically takes 1–3 minutes depending on policy length.';
    $('#analysis-id-display').textContent = analysisId;

    // Ring
    const circumference = 2 * Math.PI * 78;
    const offset = circumference - (progress / 100) * circumference;
    $('#progress-ring-fill').style.strokeDasharray = circumference;
    $('#progress-ring-fill').style.strokeDashoffset = offset;

    // Stage steps
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
    // Score gauge
    const score = data.overall_score != null ? data.overall_score : 0;
    const color = scoreColor(score);
    const circumference = 2 * Math.PI * 88;
    const offset = circumference - (score / 10) * circumference;

    $('#gauge-fill').style.strokeDasharray = circumference;
    $('#gauge-fill').style.strokeDashoffset = offset;
    $('#gauge-fill').style.stroke = color;
    $('#score-num').textContent = score.toFixed(1);
    $('#score-num').style.color = color;

    // Rating badge
    const rating = data.overall_rating || 'N/A';
    const badgeEl = $('#rating-badge');
    badgeEl.textContent = rating;
    badgeEl.className = `rating-badge ${ratingClass(rating)}`;

    // Binding recommendation
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

    // Policy metadata
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

    // Coverage scores
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
          <td>${item.name || item.section || '—'}</td>
          <td class="score-cell ${cls}">${s.toFixed(1)}</td>
          <td>${tierLabel(s)}</td>
          <td class="score-bar-cell">
            <div class="score-bar"><div class="score-bar-fill" style="width:${pct}%;background:${scoreColor(s)}"></div></div>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    // Red flags
    const rfCount = data.red_flag_count != null ? data.red_flag_count : '—';
    $('#red-flag-count').textContent = rfCount;

    // Critical gaps
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

    // Download button
    $('#download-btn').onclick = () => {
      window.open(`/api/v1/analyze/${analysisId}/report`, '_blank');
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
    $('#new-analysis-btn') && $('#new-analysis-btn').addEventListener('click', () => {
      analysisId = null;
      selectedFile = null;
      navigate('analyze');
    });

    // Error retry
    $('#error-retry') && $('#error-retry').addEventListener('click', () => navigate('analyze'));
  });

})();
