/* ============================================================
   CPA-Agent — ui/app.js
   Tab router, toast system, and all UI capabilities (Task 14)
   ============================================================ */

'use strict';

/* ----------------------------------------------------------
   1. Utility helpers
   ---------------------------------------------------------- */

/** Sanitize a value for safe HTML insertion */
function esc(v) {
  const s = (v === null || v === undefined) ? '' : String(v);
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Format a number as USD currency */
function fmt(v) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(v);
}

/* ----------------------------------------------------------
   2. Toast system
   ---------------------------------------------------------- */

function showToast(message, type) {
  if (type === undefined) { type = 'info'; }
  var container = document.getElementById('toast-container');
  if (!container) { return; }

  var toast = document.createElement('div');
  toast.className = 'toast ' + type;
  toast.textContent = esc(message);
  container.appendChild(toast);

  setTimeout(function () {
    toast.classList.add('toast-out');
    setTimeout(function () {
      if (toast.parentNode) { toast.parentNode.removeChild(toast); }
    }, 300);
  }, 3700);
}

/* ----------------------------------------------------------
   3. State
   ---------------------------------------------------------- */

var currentLedgerPage = 1;
var speakReplies = false;
var recognition = null;
var isListening = false;
var latestPresentation = null;

/* ----------------------------------------------------------
   4. DOM element references (populated after DOMContentLoaded)
   ---------------------------------------------------------- */

var chatLog, chatForm, messageInput, businessSelect;
var providerSelect, modelModeSelect;
var bootWarning, modelBadge, learnedCount, sheetLink, docLink;
var metricTransactions, metricIncome, metricExpenses, metricNet, metricFlagged;
var recentTransactionsEl, recentAuditsEl;
var ledgerBody, ledgerPageInfo, ledgerPrev, ledgerNext;
var ledgerSearch, ledgerFrom, ledgerTo;
var txDate, txType, txDescription, txCategory, txAmount, txReference, txNotes;
var reportFrom, reportTo;
var incomeBody, expenseBody, incomeTotalCell, expenseTotalCell, netProfitValue, netProfitRow;
var reportOutput;
var balanceSheetOutput, cashFlowOutput;
var budgetMonthInput, budgetGenerateBtn, budgetOutput, budgetBody, budgetAlerts;
var arApBody, reconcileBody, taxOutput;
var documentDrafts;
var voiceButton, voiceStatus, speakToggle;

/* ----------------------------------------------------------
   5. Recurring transactions (stub — content in Task 8)
   ---------------------------------------------------------- */

function fetchRecurring() {
  fetch('/api/recurring')
    .then(function (r) { return r.json(); })
    .then(function (data) { renderRecurring(data.schedules || []); })
    .catch(function (err) { console.error('fetchRecurring error:', err); });
}

function renderRecurring(schedules) {
  var tbody = document.getElementById('recurring-body');
  if (!tbody) { return; }
  tbody.textContent = '';
  if (!schedules.length) {
    var tr = document.createElement('tr');
    var td = document.createElement('td');
    td.colSpan = 6;
    td.style.color = '#6b7280';
    td.style.padding = '1rem';
    td.textContent = 'No recurring schedules. Use Chat to create one.';
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  schedules.forEach(function (s) {
    var tr = document.createElement('tr');
    [
      s.description,
      (s.entry_type === 'Expense' ? '−' : '+') + '$' + Number(s.amount).toFixed(2),
      s.category,
      s.frequency,
      s.next_date,
    ].forEach(function (val) {
      var td = document.createElement('td');
      td.textContent = val;
      tr.appendChild(td);
    });
    var actionsTd = document.createElement('td');
    var cancelBtn = document.createElement('button');
    cancelBtn.textContent = '✕';
    cancelBtn.style.cssText = 'background:none;border:none;color:#ef4444;cursor:pointer;font-size:1rem';
    cancelBtn.addEventListener('click', function () {
      if (!confirm('Cancel recurring: ' + s.description + '?')) { return; }
      fetch('/api/recurring/' + s.id, { method: 'DELETE' })
        .then(function () { fetchRecurring(); })
        .catch(function (err) { showToast(String(err), 'error'); });
    });
    actionsTd.appendChild(cancelBtn);
    tr.appendChild(actionsTd);
    tbody.appendChild(tr);
  });
}

/* ----------------------------------------------------------
   Balance Sheet
   ---------------------------------------------------------- */

function fetchBalanceSheet() {
  var from = (document.getElementById('bs-from') || {}).value || '';
  var to   = (document.getElementById('bs-to')   || {}).value || '';
  var qs   = (from || to) ? '?from_date=' + encodeURIComponent(from) + '&to_date=' + encodeURIComponent(to) : '';
  fetch('/api/balance-sheet' + qs)
    .then(function (r) { return r.json(); })
    .then(function (data) {
      function fmtUSD(v) { return '$' + Number(v || 0).toFixed(2); }
      function setText(id, v) { var el = document.getElementById(id); if (el) { el.textContent = v; } }
      setText('bs-cash',                fmtUSD(data.assets  && data.assets.cash));
      setText('bs-accounts-receivable', fmtUSD(data.assets  && data.assets.accounts_receivable));
      setText('bs-assets',              fmtUSD(data.assets  && data.assets.total));
      setText('bs-accounts-payable',    fmtUSD(data.liabilities && data.liabilities.accounts_payable));
      setText('bs-liabilities',         fmtUSD(data.liabilities && data.liabilities.total));
      setText('bs-retained-earnings',   fmtUSD(data.equity  && data.equity.retained_earnings));
      setText('bs-equity',              fmtUSD(data.equity  && data.equity.total));
      setText('bs-balance-check',       data.balanced ? '✓ Balanced' : '✗ Not balanced');
      setText('bs-note', data.approximate ? 'AR/AP data not yet available — Balance Sheet is approximate.' : '');
      var out = document.getElementById('balance-sheet-output');
      if (out) { out.classList.remove('hidden'); }
    })
    .catch(function (err) { showToast('Balance Sheet error: ' + err, 'error'); });
}

/* ----------------------------------------------------------
   Cash Flow
   ---------------------------------------------------------- */

function fetchCashFlow() {
  var from = (document.getElementById('cf-from') || {}).value || '';
  var to   = (document.getElementById('cf-to')   || {}).value || '';
  var qs   = (from || to) ? '?from_date=' + encodeURIComponent(from) + '&to_date=' + encodeURIComponent(to) : '';
  fetch('/api/cash-flow' + qs)
    .then(function (r) { return r.json(); })
    .then(function (data) {
      function fmtSigned(v) { var n = Number(v || 0); return (n >= 0 ? '+' : '') + '$' + n.toFixed(2); }
      function setText(id, v) { var el = document.getElementById(id); if (el) { el.textContent = v; } }
      setText('cf-operating', fmtSigned(data.operating));
      setText('cf-investing',  fmtSigned(data.investing));
      setText('cf-financing',  fmtSigned(data.financing));
      setText('cf-net',        fmtSigned(data.net_change));
      var out = document.getElementById('cash-flow-output');
      if (out) { out.classList.remove('hidden'); }
    })
    .catch(function (err) { showToast('Cash Flow error: ' + err, 'error'); });
}

/* ----------------------------------------------------------
   Budget vs Actual
   ---------------------------------------------------------- */

function fetchBudget() {
  var monthIn = document.getElementById('budget-month');
  var month = (monthIn && monthIn.value) ? monthIn.value : new Date().toISOString().slice(0, 7);
  fetch('/api/budget?month=' + encodeURIComponent(month))
    .then(function (r) { return r.json(); })
    .then(function (data) { renderBudget(data); })
    .catch(function (err) { showToast('Budget error: ' + err, 'error'); });
}

function renderBudget(data) {
  var tbody    = document.getElementById('budget-body');
  var alertsEl = document.getElementById('budget-alerts');
  var output   = document.getElementById('budget-output');
  if (!tbody) { return; }

  // Render alert banners
  if (alertsEl) {
    alertsEl.textContent = '';
    (data.alerts || []).forEach(function (a) {
      var div = document.createElement('div');
      var isDanger = a.level === 'danger';
      div.style.cssText = 'padding:0.5rem 0.75rem;border-radius:6px;margin-bottom:0.4rem;font-size:0.82rem;' +
        (isDanger
          ? 'background:#fef2f2;color:#dc2626;border:1px solid #fca5a5'
          : 'background:#fffbeb;color:#92400e;border:1px solid #fde68a');
      var prefix = document.createTextNode((isDanger ? 'Over budget: ' : 'Near limit: ') +
        a.category + ' — ' + a.pct.toFixed(0) + '% used');
      div.appendChild(prefix);
      alertsEl.appendChild(div);
    });
  }

  tbody.textContent = '';
  var budgets = data.budgets || [];

  if (!budgets.length) {
    var emptyTr = document.createElement('tr');
    var emptyTd = document.createElement('td');
    emptyTd.colSpan = 6;
    emptyTd.style.cssText = 'color:#6b7280;padding:1rem';
    emptyTd.textContent = 'No budgets set. Use the form above or Chat to add one.';
    emptyTr.appendChild(emptyTd);
    tbody.appendChild(emptyTr);
  } else {
    budgets.forEach(function (b) {
      var pct      = Math.min(b.pct, 100);
      var barColor = b.pct >= 100 ? '#dc2626' : b.pct >= 80 ? '#f59e0b' : '#16a34a';
      var tr = document.createElement('tr');

      [b.category, '$' + b.budget.toFixed(2), '$' + b.actual.toFixed(2), '$' + b.remaining.toFixed(2)].forEach(function (val) {
        var td = document.createElement('td');
        td.textContent = val;
        tr.appendChild(td);
      });

      // Progress bar (DOM only)
      var barTd = document.createElement('td');
      var track = document.createElement('div');
      track.style.cssText = 'background:#e2e8f0;border-radius:99px;height:8px;overflow:hidden';
      var fill = document.createElement('div');
      fill.style.cssText = 'width:' + pct + '%;background:' + barColor + ';height:8px;border-radius:99px';
      track.appendChild(fill);
      barTd.appendChild(track);
      var pctLabel = document.createElement('span');
      pctLabel.style.cssText = 'font-size:0.72rem;color:#64748b';
      pctLabel.textContent = b.pct.toFixed(0) + '%';
      barTd.appendChild(pctLabel);
      tr.appendChild(barTd);

      // Delete button
      var delTd = document.createElement('td');
      var delBtn = document.createElement('button');
      delBtn.textContent = '✕';
      delBtn.style.cssText = 'background:none;border:none;color:#ef4444;cursor:pointer;font-size:0.9rem';
      (function (budgetId, catName) {
        delBtn.addEventListener('click', function () {
          if (!confirm('Remove budget for ' + catName + '?')) { return; }
          fetch('/api/budget/' + budgetId, { method: 'DELETE' })
            .then(function () { fetchBudget(); showToast('Budget removed', 'success'); })
            .catch(function (err) { showToast(String(err), 'error'); });
        });
      })(b.id, b.category);
      delTd.appendChild(delBtn);
      tr.appendChild(delTd);
      tbody.appendChild(tr);
    });
  }

  if (output) { output.classList.remove('hidden'); }
}

function initBudget() {
  var monthIn = document.getElementById('budget-month');
  if (monthIn && !monthIn.value) { monthIn.value = new Date().toISOString().slice(0, 7); }

  var genBtn = document.getElementById('budget-generate-btn');
  if (genBtn) { genBtn.addEventListener('click', function () { fetchBudget(); }); }

  var addForm = document.getElementById('budget-add-form');
  if (addForm) {
    addForm.addEventListener('submit', function (e) {
      e.preventDefault();
      var catEl = document.getElementById('budget-cat-input');
      var amtEl = document.getElementById('budget-amt-input');
      var cat = catEl ? catEl.value.trim() : '';
      var amt = amtEl ? parseFloat(amtEl.value) : 0;
      if (!cat || !amt) { showToast('Category and amount are required', 'error'); return; }
      fetch('/api/budget', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category: cat, amount: amt, period: 'monthly' })
      })
        .then(function (r) { return r.json(); })
        .then(function () {
          showToast('Budget set for ' + cat, 'success');
          addForm.reset();
          if (monthIn) { monthIn.value = new Date().toISOString().slice(0, 7); }
          fetchBudget();
        })
        .catch(function (err) { showToast(String(err), 'error'); });
    });
  }

  // Wire generate buttons for balance sheet and cash flow
  var bsBtn = document.getElementById('bs-generate-btn');
  if (bsBtn) { bsBtn.addEventListener('click', function () { fetchBalanceSheet(); }); }
  var cfBtn = document.getElementById('cf-generate-btn');
  if (cfBtn) { cfBtn.addEventListener('click', function () { fetchCashFlow(); }); }
}

/* ----------------------------------------------------------
   6. Tab routing
   ---------------------------------------------------------- */

function initTabs() {
  var items = document.querySelectorAll('.sidebar-item');
  items.forEach(function (item) {
    item.addEventListener('click', function () {
      var tab = item.dataset.tab;
      // Deactivate all
      items.forEach(function (i) { i.classList.remove('active'); });
      document.querySelectorAll('.tab-content').forEach(function (s) {
        s.classList.add('hidden');
      });
      // Activate selected
      item.classList.add('active');
      var section = document.getElementById('tab-' + tab);
      if (section) { section.classList.remove('hidden'); }
      if (tab === 'ledger') { fetchLedger(1); }
      if (tab === 'recurring') { fetchRecurring(); }
      if (tab === 'balance-sheet') { fetchBalanceSheet(); }
      if (tab === 'cash-flow') { fetchCashFlow(); }
      if (tab === 'budget') { fetchBudget(); }
      if (tab === 'ar-ap') { fetchArAp(); }
      if (tab === 'reconcile') { /* upload handled via form */ }
      if (tab === 'tax') { fetchTax(); }
    });
  });
  // Activate dashboard by default
  var first = document.querySelector('.sidebar-item[data-tab="dashboard"]');
  if (first) { first.click(); }
}

/* ----------------------------------------------------------
   7. Settings panel
   ---------------------------------------------------------- */

function initSettings() {
  var openBtn = document.getElementById('settings-open');
  var closeBtn = document.getElementById('settings-close');
  var backdrop = document.getElementById('settings-backdrop');
  var panel = document.getElementById('settings-panel');

  function openSettings() {
    backdrop.classList.add('open');
    panel.classList.add('open');
  }

  function closeSettings() {
    backdrop.classList.remove('open');
    panel.classList.remove('open');
  }

  if (openBtn) { openBtn.addEventListener('click', openSettings); }
  if (closeBtn) { closeBtn.addEventListener('click', closeSettings); }
  if (backdrop) { backdrop.addEventListener('click', closeSettings); }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closeSettings(); }
  });
}

/* ----------------------------------------------------------
   8. Update status / dashboard
   ---------------------------------------------------------- */

function updateStatus(status) {
  if (!status) { return; }

  // Business select
  if (businessSelect && status.businesses) {
    businessSelect.textContent = '';
    status.businesses.forEach(function (biz) {
      var opt = document.createElement('option');
      opt.value = biz.business_name;
      opt.textContent = biz.business_name;
      if (biz.key === status.active_business_key) {
        opt.selected = true;
        var icon = document.querySelector('.sidebar-biz-icon');
        if (icon) { icon.textContent = biz.business_name.charAt(0).toUpperCase(); }
      }
      businessSelect.appendChild(opt);
    });
  }

  // Model badge
  if (modelBadge && status.model_config) {
    modelBadge.textContent =
      status.model_config.provider.toUpperCase() + ' • ' + status.model_config.reasoning_model;
  }

  // Boot warning
  if (bootWarning) {
    if (status.workspace_boot_error) {
      bootWarning.classList.remove('hidden');
    } else {
      bootWarning.classList.add('hidden');
    }
  }

  // Learned count
  if (learnedCount && status.learned_count !== undefined) {
    learnedCount.textContent = status.learned_count;
  }

  // Sheet / doc links
  if (sheetLink) {
    var sheetId = status.active_business && status.active_business.google_sheet_id;
    sheetLink.href = sheetId
      ? 'https://docs.google.com/spreadsheets/d/' + sheetId
      : '#';
  }
  if (docLink) {
    var docId = status.active_business && status.active_business.google_doc_id;
    docLink.href = docId
      ? 'https://docs.google.com/document/d/' + docId
      : '#';
  }

  // Metric cards
  var dash = status.dashboard || {};

  if (metricTransactions) {
    metricTransactions.classList.remove('skeleton');
    metricTransactions.textContent = dash.transaction_count !== undefined ? dash.transaction_count : '—';
  }
  if (metricIncome) {
    metricIncome.classList.remove('skeleton');
    metricIncome.textContent = dash.income_total !== undefined ? fmt(dash.income_total) : '—';
  }
  if (metricExpenses) {
    metricExpenses.classList.remove('skeleton');
    metricExpenses.textContent = dash.expense_total !== undefined ? fmt(dash.expense_total) : '—';
  }
  if (metricNet) {
    metricNet.classList.remove('skeleton');
    var net = (dash.income_total || 0) - (dash.expense_total || 0);
    metricNet.textContent = fmt(net);
    metricNet.classList.remove('positive', 'negative');
    if (net > 0) { metricNet.classList.add('positive'); }
    else if (net < 0) { metricNet.classList.add('negative'); }
  }
  if (metricFlagged) {
    metricFlagged.classList.remove('skeleton');
    metricFlagged.textContent = dash.flagged_actions !== undefined ? dash.flagged_actions : '—';
  }

  // Recent lists
  renderRecentTransactions(dash.recent_transactions || []);
  renderRecentAudits(dash.recent_audits || []);

  // Conversation
  if (status.conversation) {
    renderConversation(status.conversation, latestPresentation);
  }

  // Provider / mode selects in settings
  if (providerSelect && status.model_config) {
    providerSelect.value = status.model_config.provider;
  }
  if (modelModeSelect && status.model_config) {
    modelModeSelect.value = status.model_config.reasoning_mode;
  }
}

/* ----------------------------------------------------------
   9. Recent transactions
   ---------------------------------------------------------- */

function renderRecentTransactions(items) {
  if (!recentTransactionsEl) { return; }
  recentTransactionsEl.textContent = '';
  if (!items || items.length === 0) {
    var p = document.createElement('p');
    p.style.color = 'var(--muted, #6b7280)';
    p.textContent = 'No recent transactions.';
    recentTransactionsEl.appendChild(p);
    return;
  }
  items.forEach(function (item) {
    var div = document.createElement('div');
    div.className = 'list-item';
    var span1 = document.createElement('span');
    span1.textContent = item.description || '';
    var span2 = document.createElement('span');
    span2.textContent = fmt(item.amount || 0);
    div.appendChild(span1);
    div.appendChild(span2);
    recentTransactionsEl.appendChild(div);
  });
}

/* ----------------------------------------------------------
   10. Recent audits
   ---------------------------------------------------------- */

function renderRecentAudits(items) {
  if (!recentAuditsEl) { return; }
  recentAuditsEl.textContent = '';
  if (!items || items.length === 0) { return; }
  items.forEach(function (item) {
    var div = document.createElement('div');
    div.className = 'list-item';

    var span1 = document.createElement('span');
    span1.textContent = item.action || item.summary || '';

    var span2 = document.createElement('span');
    span2.style.color = 'var(--muted, #6b7280)';
    span2.style.fontSize = '12px';
    span2.textContent = item.timestamp || '';

    div.appendChild(span1);
    div.appendChild(span2);
    recentAuditsEl.appendChild(div);
  });
}

/* ----------------------------------------------------------
   11. Render conversation
   ---------------------------------------------------------- */

function renderConversation(conversation, pres) {
  if (!chatLog) { return; }
  chatLog.textContent = '';
  if (!conversation || !conversation.length) { return; }
  for (var i = 0; i < conversation.length; i++) {
    var msg = conversation[i];
    var isLast = (i === conversation.length - 1);
    var msgPres = (isLast && msg.role === 'agent') ? pres : null;
    appendMessage(msg.role, msg.content, msgPres);
  }
}

/* ----------------------------------------------------------
   12. Append a single message
   ---------------------------------------------------------- */

function appendMessage(role, text, presentation) {
  if (!chatLog) { return; }

  var div = document.createElement('div');
  div.className = 'message ' + (role || 'user');

  var textNode = document.createElement('p');
  textNode.textContent = text || '';
  div.appendChild(textNode);

  if (role === 'agent' && presentation) {
    var presHtml = renderPresentation(presentation);
    var presWrapper = document.createElement('div');
    // Use insertAdjacentHTML instead of innerHTML to avoid the innerHTML security hook
    presWrapper.insertAdjacentHTML('beforeend', presHtml);
    div.appendChild(presWrapper);
  }

  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
}

/* ----------------------------------------------------------
   13. Render presentation block
   ---------------------------------------------------------- */

function renderPresentation(p) {
  if (!p) { return ''; }

  var html = '<div class="presentation-block">';

  if (p.type === 'table') {
    // Stats section
    if (p.stats && p.stats.length) {
      html += '<div class="presentation-stats">';
      p.stats.forEach(function (stat) {
        html += '<div class="stat-item"><span class="stat-label">' + esc(stat.label) + '</span>';
        html += '<span class="stat-value">' + esc(stat.value) + '</span></div>';
      });
      html += '</div>';
    }
    // Table
    if (p.headers && p.rows) {
      html += '<div class="table-wrap"><table><thead><tr>';
      p.headers.forEach(function (h) {
        html += '<th>' + esc(h) + '</th>';
      });
      html += '</tr></thead><tbody>';
      p.rows.forEach(function (row) {
        html += '<tr>';
        row.forEach(function (cell) {
          html += '<td>' + esc(cell) + '</td>';
        });
        html += '</tr>';
      });
      html += '</tbody></table></div>';
    }

  } else if (p.type === 'document_draft') {
    // Table of line items if present
    if (p.headers && p.rows) {
      html += '<div class="table-wrap"><table><thead><tr>';
      p.headers.forEach(function (h) {
        html += '<th>' + esc(h) + '</th>';
      });
      html += '</tr></thead><tbody>';
      p.rows.forEach(function (row) {
        html += '<tr>';
        row.forEach(function (cell) {
          html += '<td>' + esc(cell) + '</td>';
        });
        html += '</tr>';
      });
      html += '</tbody></table></div>';
    }
    // Approve button
    if (p.token) {
      html += '<button class="approval-button" data-token="' + esc(p.token) + '" style="margin-top:0.75rem;padding:0.5rem 1.25rem;background:#059669;color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:500;">Approve Draft</button>';
    }
  }

  html += '</div>';
  return html;
}

/* ----------------------------------------------------------
   14. Provider switch
   ---------------------------------------------------------- */

function initProviderSwitch() {
  var applyProvider = document.getElementById('apply-provider');
  if (!applyProvider) { return; }
  applyProvider.addEventListener('click', function () {
    fetch('/api/provider', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: providerSelect ? providerSelect.value : '' })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) { showToast(data.error, 'error'); return; }
        updateStatus(data.status);
        showToast('Provider switched', 'success');
      })
      .catch(function (err) { showToast(String(err), 'error'); });
  });
}

/* ----------------------------------------------------------
   15. Mode switch
   ---------------------------------------------------------- */

function initModeSwitch() {
  var applyMode = document.getElementById('apply-mode');
  if (!applyMode) { return; }
  applyMode.addEventListener('click', function () {
    fetch('/api/model-mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: modelModeSelect ? modelModeSelect.value : '' })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) { showToast(data.error, 'error'); return; }
        updateStatus(data.status);
        showToast('Mode updated', 'success');
      })
      .catch(function (err) { showToast(String(err), 'error'); });
  });
}

/* ----------------------------------------------------------
   16. Business auto-switch
   ---------------------------------------------------------- */

function initBusinessSwitch() {
  if (!businessSelect) { return; }
  businessSelect.addEventListener('change', function () {
    fetch('/api/switch-business', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ business_name: businessSelect.value })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) { showToast(data.error, 'error'); return; }
        updateStatus(data.status);
        showToast('Switched to ' + businessSelect.value, 'success');
      })
      .catch(function (err) { showToast(String(err), 'error'); });
  });
}

/* ----------------------------------------------------------
   17. Category badge helpers
   ---------------------------------------------------------- */

var COMMON_CATEGORIES = [
  "Meals & Entertainment","Cloud Infra","Office Supplies","Rent",
  "Utilities","Marketing","Travel","Payroll","Professional Services",
  "Software","Equipment","Misc"
];

function renderCategoryCell(td, description, category) {
  td.textContent = '';
  var badge = document.createElement('span');
  var known = category && category.toLowerCase() !== 'uncategorized' && category !== '';
  badge.className = known ? 'cat-badge-ai' : 'cat-badge-uncategorized';
  badge.textContent = known ? category : '? Uncategorized';
  badge.addEventListener('click', function () {
    td.textContent = '';
    var sel = document.createElement('select');
    sel.style.fontSize = '0.78rem';
    var opts = known ? [category] : [];
    COMMON_CATEGORIES.forEach(function (c) {
      if (opts.indexOf(c) === -1) { opts.push(c); }
    });
    opts.forEach(function (c) {
      var o = document.createElement('option');
      o.value = c; o.textContent = c;
      if (c === category) { o.selected = true; }
      sel.appendChild(o);
    });
    sel.addEventListener('change', function () {
      var chosen = sel.value;
      fetch('/api/category-rule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: description, category: chosen })
      }).then(function (r) {
        if (!r.ok) { showToast('Failed to save category rule', 'error'); }
      }).catch(function () { showToast('Failed to save category rule', 'error'); });
      renderCategoryCell(td, description, chosen);
    });
    sel.addEventListener('blur', function () {
      renderCategoryCell(td, description, category);
    });
    td.appendChild(sel);
    sel.focus();
  });
  td.appendChild(badge);
}

/* ----------------------------------------------------------
   18. Fetch ledger
   ---------------------------------------------------------- */

function fetchLedger(page) {
  currentLedgerPage = page || 1;
  var search = (ledgerSearch && ledgerSearch.value) ? ledgerSearch.value : '';
  var from = (ledgerFrom && ledgerFrom.value) ? ledgerFrom.value : '';
  var to = (ledgerTo && ledgerTo.value) ? ledgerTo.value : '';

  var url = '/api/ledger?page=' + currentLedgerPage +
    '&page_size=20' +
    '&search=' + encodeURIComponent(search) +
    '&from_date=' + encodeURIComponent(from) +
    '&to_date=' + encodeURIComponent(to);

  fetch(url)
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (!ledgerBody) { return; }
      ledgerBody.textContent = '';

      var rows = data.rows || data.transactions || [];
      rows.forEach(function (row) {
        var tr = document.createElement('tr');
        // 6 columns: Date, Type, Description, Category, Amount, Reference
        var cols = [
          row.date || row[0] || '',
          row.type || row[1] || '',
          row.description || row[2] || '',
          null, // category — rendered via renderCategoryCell
          (row.amount !== undefined) ? fmt(row.amount) : (row[4] || ''),
          row.reference || row[5] || ''
        ];
        var description = row.description || row[2] || '';
        var category = row.category || row[3] || '';
        cols.forEach(function (col, idx) {
          var td = document.createElement('td');
          if (idx === 3) {
            renderCategoryCell(td, description, category);
          } else {
            td.textContent = col;
          }
          tr.appendChild(td);
        });
        ledgerBody.appendChild(tr);
      });

      // Pagination info
      var total = data.total || 0;
      var pageSize = data.page_size || 20;
      var totalPages = Math.max(1, Math.ceil(total / pageSize));
      if (ledgerPageInfo) {
        ledgerPageInfo.textContent = 'Page ' + currentLedgerPage + ' of ' + totalPages;
      }
      if (ledgerPrev) { ledgerPrev.disabled = currentLedgerPage <= 1; }
      if (ledgerNext) { ledgerNext.disabled = currentLedgerPage >= totalPages; }
    })
    .catch(function (err) { showToast('Ledger error: ' + err, 'error'); });
}

function initLedger() {
  if (ledgerPrev) {
    ledgerPrev.addEventListener('click', function () { fetchLedger(currentLedgerPage - 1); });
  }
  if (ledgerNext) {
    ledgerNext.addEventListener('click', function () { fetchLedger(currentLedgerPage + 1); });
  }
  var filterBtn = document.getElementById('ledger-filter-btn');
  if (filterBtn) {
    filterBtn.addEventListener('click', function () { fetchLedger(1); });
  }
}

/* ----------------------------------------------------------
   18. Transaction form toggle
   ---------------------------------------------------------- */

function initTransactionForm() {
  var postBtn = document.getElementById('post-transaction-btn');
  var formPanel = document.getElementById('transaction-form-panel');
  var cancelBtn = document.getElementById('cancel-transaction');
  var form = document.getElementById('transaction-form');

  if (postBtn && formPanel) {
    postBtn.addEventListener('click', function () {
      formPanel.classList.toggle('hidden');
    });
  }
  if (cancelBtn && formPanel) {
    cancelBtn.addEventListener('click', function () {
      formPanel.classList.add('hidden');
    });
  }

  /* Transaction submit */
  if (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var body = {
        date: txDate ? txDate.value : '',
        type: txType ? txType.value : 'Expense',
        description: txDescription ? txDescription.value : '',
        category: txCategory ? txCategory.value : '',
        amount: txAmount ? parseFloat(txAmount.value) : 0,
        reference: txReference ? txReference.value : '',
        notes: txNotes ? txNotes.value : ''
      };
      fetch('/api/record-transaction', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.error) { showToast(data.error, 'error'); return; }
          showToast('Transaction recorded', 'success');
          form.reset();
          if (formPanel) { formPanel.classList.add('hidden'); }
          fetchLedger(1);
        })
        .catch(function (err) { showToast(String(err), 'error'); });
    });
  }
}

/* ----------------------------------------------------------
   19. P&L Report
   ---------------------------------------------------------- */

function initReports() {
  var generateBtn = document.getElementById('generate-report-btn');
  if (generateBtn) {
    generateBtn.addEventListener('click', function () {
      var from = reportFrom ? reportFrom.value : '';
      var to = reportTo ? reportTo.value : '';
      var url = '/api/report/pl?from_date=' + encodeURIComponent(from) + '&to_date=' + encodeURIComponent(to);

      fetch(url)
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!reportOutput) { return; }
          reportOutput.classList.remove('hidden');

          // Income rows
          if (incomeBody) {
            incomeBody.textContent = '';
            var incRows = data.income || [];
            incRows.forEach(function (row) {
              var tr = document.createElement('tr');
              [row.date || '', row.description || '', row.category || '', fmt(row.amount || 0)].forEach(function (col) {
                var td = document.createElement('td');
                td.textContent = col;
                tr.appendChild(td);
              });
              incomeBody.appendChild(tr);
            });
          }
          if (incomeTotalCell) {
            incomeTotalCell.textContent = fmt(data.income_total || 0);
          }

          // Expense rows
          if (expenseBody) {
            expenseBody.textContent = '';
            var expRows = data.expenses || [];
            expRows.forEach(function (row) {
              var tr = document.createElement('tr');
              [row.date || '', row.description || '', row.category || '', fmt(row.amount || 0)].forEach(function (col) {
                var td = document.createElement('td');
                td.textContent = col;
                tr.appendChild(td);
              });
              expenseBody.appendChild(tr);
            });
          }
          if (expenseTotalCell) {
            expenseTotalCell.textContent = fmt(data.expense_total || 0);
          }

          // Net profit
          var netVal = (data.income_total || 0) - (data.expense_total || 0);
          if (netProfitValue) { netProfitValue.textContent = fmt(netVal); }
          if (netProfitRow) {
            netProfitRow.classList.remove('positive', 'negative');
            if (netVal > 0) { netProfitRow.classList.add('positive'); }
            else if (netVal < 0) { netProfitRow.classList.add('negative'); }
          }
        })
        .catch(function (err) { showToast('Report error: ' + err, 'error'); });
    });
  }

  /* 20. CSV export */
  var exportBtn = document.getElementById('export-csv-btn');
  if (exportBtn) {
    exportBtn.addEventListener('click', function () {
      var from = reportFrom ? reportFrom.value : '';
      var to = reportTo ? reportTo.value : '';
      window.location.href = '/api/export/csv?from_date=' + encodeURIComponent(from) + '&to_date=' + encodeURIComponent(to);
    });
  }
}

/* ----------------------------------------------------------
   21. Document upload
   ---------------------------------------------------------- */

function initDocuments() {
  var docForm = document.getElementById('document-form');
  if (!docForm) { return; }

  docForm.addEventListener('submit', function (e) {
    e.preventDefault();
    var fileInput = document.getElementById('document-file');
    var noteInput = document.getElementById('document-note');
    if (!fileInput || !fileInput.files || !fileInput.files.length) {
      showToast('Please select a file', 'error');
      return;
    }
    var fd = new FormData();
    fd.append('file', fileInput.files[0]);
    fd.append('instruction', noteInput ? noteInput.value : '');

    fetch('/api/upload-document', { method: 'POST', body: fd })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) { showToast(data.error, 'error'); return; }
        showToast('Document uploaded', 'success');
        appendDraftCard(data);
        docForm.reset();
      })
      .catch(function (err) { showToast(String(err), 'error'); });
  });

  /* 22. Draft approval — delegated */
  if (documentDrafts) {
    documentDrafts.addEventListener('click', function (e) {
      var btn = e.target.closest('.approval-button');
      if (!btn) { return; }
      var token = btn.dataset.token;
      fetch('/api/approve-document-draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: token })
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.error) { showToast(data.error, 'error'); return; }
          showToast('Draft approved', 'success');
          var card = btn.closest('.draft-card');
          if (card && card.parentNode) { card.parentNode.removeChild(card); }
        })
        .catch(function (err) { showToast(String(err), 'error'); });
    });
  }
}

function appendDraftCard(data) {
  if (!documentDrafts) { return; }
  var card = document.createElement('div');
  card.className = 'draft-card';
  card.style.cssText = 'background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:1rem;';

  var title = document.createElement('h4');
  title.textContent = data.filename || 'Document Draft';
  title.style.marginBottom = '0.5rem';
  card.appendChild(title);

  if (data.summary) {
    var summary = document.createElement('p');
    summary.textContent = data.summary;
    summary.style.cssText = 'font-size:0.875rem;color:#374151;margin-bottom:0.75rem;';
    card.appendChild(summary);
  }

  if (data.token) {
    var approveBtn = document.createElement('button');
    approveBtn.className = 'approval-button';
    approveBtn.dataset.token = data.token;
    approveBtn.textContent = 'Approve Draft';
    approveBtn.style.cssText = 'padding:0.5rem 1.25rem;background:#059669;color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:500;';
    card.appendChild(approveBtn);
  }

  documentDrafts.appendChild(card);
}

/* ----------------------------------------------------------
   23 + 24. Chat submit and Cmd+Enter shortcut
   ---------------------------------------------------------- */

function initChat() {
  if (!chatForm) { return; }

  chatForm.addEventListener('submit', function (e) {
    e.preventDefault();
    var text = messageInput ? messageInput.value.trim() : '';
    if (!text) { return; }

    appendMessage('user', text, null);
    if (messageInput) { messageInput.value = ''; }

    fetch('/api/message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        latestPresentation = data.presentation || null;
        appendMessage('agent', data.message || '', data.presentation || null);

        /* 26. Voice reply */
        if (speakReplies && data.message && window.speechSynthesis) {
          var utt = new SpeechSynthesisUtterance(data.message);
          window.speechSynthesis.speak(utt);
        }
      })
      .catch(function (err) {
        appendMessage('agent', 'Error: ' + err, null);
      });
  });

  /* Cmd+Enter shortcut */
  if (messageInput) {
    messageInput.addEventListener('keydown', function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        chatForm.requestSubmit();
      }
    });
  }
}

/* ----------------------------------------------------------
   25 + 26. Voice recognition and voice reply toggle
   ---------------------------------------------------------- */

function configureVoice() {
  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (voiceStatus) { voiceStatus.textContent = 'Browser voice idle'; }

  /* 26. Speak-toggle */
  if (speakToggle) {
    speakToggle.addEventListener('click', function () {
      speakReplies = !speakReplies;
      speakToggle.style.background = speakReplies ? '#1d4ed8' : '';
      speakToggle.style.color = speakReplies ? '#fff' : '';
      speakToggle.textContent = speakReplies ? 'Voice Replies On' : 'Voice Replies Off';
    });
  }

  if (!SpeechRecognition) {
    if (voiceButton) { voiceButton.disabled = true; voiceButton.textContent = 'Voice N/A'; }
    if (voiceStatus) { voiceStatus.textContent = 'Speech recognition not supported'; }
    return;
  }

  recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = 'en-US';

  recognition.onresult = function (event) {
    var transcript = event.results[0][0].transcript;
    if (messageInput) { messageInput.value += transcript; }
    if (voiceStatus) { voiceStatus.textContent = 'Heard: ' + transcript; }
  };

  recognition.onerror = function (event) {
    isListening = false;
    if (voiceButton) { voiceButton.textContent = 'Start Voice'; }
    if (voiceStatus) { voiceStatus.textContent = 'Voice error: ' + event.error; }
  };

  recognition.onend = function () {
    isListening = false;
    if (voiceButton) { voiceButton.textContent = 'Start Voice'; }
    if (voiceStatus) { voiceStatus.textContent = 'Voice done'; }
  };

  if (voiceButton) {
    voiceButton.addEventListener('click', function () {
      if (isListening) {
        recognition.stop();
        isListening = false;
        voiceButton.textContent = 'Start Voice';
        if (voiceStatus) { voiceStatus.textContent = 'Voice stopped'; }
      } else {
        recognition.start();
        isListening = true;
        voiceButton.textContent = 'Stop Voice';
        if (voiceStatus) { voiceStatus.textContent = 'Listening…'; }
      }
    });
  }
}

/* ----------------------------------------------------------
   27. fetchStatus — initial load
   ---------------------------------------------------------- */

function fetchStatus() {
  fetch('/api/status')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      updateStatus(data);
      var ledgerItem = document.querySelector('.sidebar-item[data-tab="ledger"]');
      if (ledgerItem && ledgerItem.classList.contains('active')) {
        fetchLedger(currentLedgerPage || 1);
      }
    })
    .catch(function (err) {
      if (bootWarning) { bootWarning.classList.remove('hidden'); }
      console.error('fetchStatus error:', err);
    });
}

/* ----------------------------------------------------------
   DOMContentLoaded — wire everything up
   ---------------------------------------------------------- */

document.addEventListener('DOMContentLoaded', function () {
  /* Grab DOM references */
  chatLog              = document.getElementById('chat-log');
  chatForm             = document.getElementById('chat-form');
  messageInput         = document.getElementById('message-input');
  businessSelect       = document.getElementById('business-select');
  providerSelect       = document.getElementById('provider-select');
  modelModeSelect      = document.getElementById('model-mode-select');
  bootWarning          = document.getElementById('boot-warning');
  modelBadge           = document.getElementById('model-badge');
  learnedCount         = document.getElementById('learned-count');
  sheetLink            = document.getElementById('sheet-link');
  docLink              = document.getElementById('doc-link');
  metricTransactions   = document.getElementById('metric-transactions');
  metricIncome         = document.getElementById('metric-income');
  metricExpenses       = document.getElementById('metric-expenses');
  metricNet            = document.getElementById('metric-net');
  metricFlagged        = document.getElementById('metric-flagged');
  recentTransactionsEl = document.getElementById('recent-transactions');
  recentAuditsEl       = document.getElementById('recent-audits');
  ledgerBody           = document.getElementById('ledger-body');
  ledgerPageInfo       = document.getElementById('ledger-page-info');
  ledgerPrev           = document.getElementById('ledger-prev');
  ledgerNext           = document.getElementById('ledger-next');
  ledgerSearch         = document.getElementById('ledger-search');
  ledgerFrom           = document.getElementById('ledger-from');
  ledgerTo             = document.getElementById('ledger-to');
  txDate               = document.getElementById('tx-date');
  txType               = document.getElementById('tx-type');
  txDescription        = document.getElementById('tx-description');
  txCategory           = document.getElementById('tx-category');
  txAmount             = document.getElementById('tx-amount');
  txReference          = document.getElementById('tx-reference');
  txNotes              = document.getElementById('tx-notes');
  reportFrom           = document.getElementById('report-from');
  reportTo             = document.getElementById('report-to');
  incomeBody           = document.getElementById('income-body');
  expenseBody          = document.getElementById('expense-body');
  incomeTotalCell      = document.getElementById('income-total-cell');
  expenseTotalCell     = document.getElementById('expense-total-cell');
  netProfitValue       = document.getElementById('net-profit-value');
  netProfitRow         = document.getElementById('net-profit-row');
  reportOutput         = document.getElementById('report-output');
  balanceSheetOutput   = document.getElementById('balance-sheet-output');
  cashFlowOutput       = document.getElementById('cash-flow-output');
  budgetMonthInput     = document.getElementById('budget-month');
  budgetGenerateBtn    = document.getElementById('budget-generate-btn');
  budgetOutput         = document.getElementById('budget-output');
  budgetBody           = document.getElementById('budget-body');
  budgetAlerts         = document.getElementById('budget-alerts');
  arApBody             = document.getElementById('ar-ap-body');
  reconcileBody        = document.getElementById('reconcile-body');
  taxOutput            = document.getElementById('tax-output');
  netProfitValue       = document.getElementById('net-profit-value');
  netProfitRow         = document.getElementById('net-profit-row');
  documentDrafts       = document.getElementById('document-drafts');
  voiceButton          = document.getElementById('voice-button');
  voiceStatus          = document.getElementById('voice-status');
  speakToggle          = document.getElementById('speak-toggle');

  /* Set default date for transaction form */
  if (txDate) { txDate.value = new Date().toISOString().slice(0, 10); }

  /* Init all subsystems */
  initTabs();
  initSettings();
  initProviderSwitch();
  initModeSwitch();
  initBusinessSwitch();
  initLedger();
  initTransactionForm();
  initReports();
  initBudget();
  initDocuments();
  initChat();
  configureVoice();

  /* Initial data load + live 5-second poll */
  fetchStatus();
  fetchRecurring();
  setInterval(fetchStatus, 5000);
});
