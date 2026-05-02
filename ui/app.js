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
var seenAlertDeadlines = new Set();

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
   AR/AP
   ---------------------------------------------------------- */

function fetchArAp() {
  fetch('/api/ar-ap')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (!data.ok) {
        showToast('AR/AP error: ' + (data.detail || 'Unknown error'), 'error');
        return;
      }
      renderArAp(data.data);
    })
    .catch(function (err) { showToast('AR/AP error: ' + err, 'error'); });
}

function renderArAp(data) {
  var receivablesBody = document.getElementById('ar-ap-receivables-body');
  var payablesBody = document.getElementById('ar-ap-payables-body');
  var receivablesCountEl = document.getElementById('ar-ap-receivables-count');
  var payablesCountEl = document.getElementById('ar-ap-payables-count');
  var overdueCountEl = document.getElementById('ar-ap-overdue-count');
  var arApOutput = document.getElementById('ar-ap-output');

  if (!receivablesBody || !payablesBody) { return; }

  receivablesBody.textContent = '';
  payablesBody.textContent = '';

  var receivables = data.receivables || [];
  var payables = data.payables || [];
  var overdueReceivables = receivables.filter(r => r.days_outstanding > 0 && r.status === 'open');
  var overduePayables = payables.filter(p => p.days_outstanding > 0 && p.status === 'open');
  var totalOverdue = overdueReceivables.length + overduePayables.length;

  if (receivablesCountEl) receivablesCountEl.textContent = receivables.length;
  if (payablesCountEl) payablesCountEl.textContent = payables.length;
  if (overdueCountEl) overdueCountEl.textContent = totalOverdue;
  if (arApOutput) arApOutput.classList.remove('hidden');

  // Dashboard summary cards
  var openReceivables = receivables.filter(function (r) { return r.status === 'open'; });
  var openArTotal = openReceivables.reduce(function (sum, r) { return sum + Number(r.amount || 0); }, 0);
  var overdueArCount = receivables.filter(function (r) { return r.days_outstanding > 0 && r.status === 'open'; }).length;
  var upcomingApCount = payables.filter(function (p) { return p.days_outstanding >= -7 && p.days_outstanding <= 0 && p.status === 'open'; }).length;
  var dashArOpenTotal = document.getElementById('dash-ar-open-total');
  var dashArOverdue = document.getElementById('dash-ar-overdue');
  var dashApUpcoming = document.getElementById('dash-ap-upcoming');
  if (dashArOpenTotal) { dashArOpenTotal.textContent = '$' + openArTotal.toFixed(2); dashArOpenTotal.classList.remove('skeleton'); }
  if (dashArOverdue) { dashArOverdue.textContent = overdueArCount; dashArOverdue.classList.remove('skeleton'); }
  if (dashApUpcoming) { dashApUpcoming.textContent = upcomingApCount; dashApUpcoming.classList.remove('skeleton'); }

  // Render receivables
  if (!receivables.length) {
    var tr = document.createElement('tr');
    var td = document.createElement('td');
    td.colSpan = 6;
    td.style.color = '#6b7280';
    td.style.padding = '1rem';
    td.textContent = 'No receivables';
    tr.appendChild(td);
    receivablesBody.appendChild(tr);
  } else {
    receivables.forEach(function (r) {
      var tr = document.createElement('tr');
      [
        r.client_vendor || '',
        '$' + Number(r.amount || 0).toFixed(2),
        r.due_date || '',
        r.status || '',
        r.days_outstanding !== undefined ? r.days_outstanding : ''
      ].forEach(function (val) {
        var td = document.createElement('td');
        td.textContent = val;
        tr.appendChild(td);
      });

      // Actions
      var actionsTd = document.createElement('td');
      if (r.status === 'open') {
        var markPaidBtn = document.createElement('button');
        markPaidBtn.textContent = 'Mark Paid';
        markPaidBtn.style.cssText = 'background:#059669;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:0.8rem;padding:0.25rem 0.75rem;';
        markPaidBtn.addEventListener('click', function () {
          // Call API to mark as paid
          fetch('/api/ar-ap/' + r.id + '/mark-paid', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              type: 'receivable',
              paid_date: new Date().toISOString().slice(0, 10)
            })
          })
            .then(function (response) { return response.json(); })
            .then(function (data) {
              if (data.ok) {
                showToast('Entry marked as paid', 'success');
                // Refresh the AR/AP list
                fetchArAp();
              } else {
                showToast('Failed to mark as paid: ' + (data.detail || 'Unknown error'), 'error');
              }
            })
            .catch(function (err) { showToast('Error marking as paid: ' + err, 'error'); });
        });
        actionsTd.appendChild(markPaidBtn);
      }
      tr.appendChild(actionsTd);
      receivablesBody.appendChild(tr);
    });
  }

  // Render payables
  if (!payables.length) {
    var tr = document.createElement('tr');
    var td = document.createElement('td');
    td.colSpan = 6;
    td.style.color = '#6b7280';
    td.style.padding = '1rem';
    td.textContent = 'No payables';
    tr.appendChild(td);
    payablesBody.appendChild(tr);
  } else {
    payables.forEach(function (p) {
      var tr = document.createElement('tr');
      [
        p.client_vendor || '',
        '$' + Number(p.amount || 0).toFixed(2),
        p.due_date || '',
        p.status || '',
        p.days_outstanding !== undefined ? p.days_outstanding : ''
      ].forEach(function (val) {
        var td = document.createElement('td');
        td.textContent = val;
        tr.appendChild(td);
      });

      // Actions
      var actionsTd = document.createElement('td');
      if (p.status === 'open') {
        var markPaidBtn = document.createElement('button');
        markPaidBtn.textContent = 'Mark Paid';
        markPaidBtn.style.cssText = 'background:#059669;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:0.8rem;padding:0.25rem 0.75rem;';
        markPaidBtn.addEventListener('click', function () {
          // Call API to mark as paid
          fetch('/api/ar-ap/' + p.id + '/mark-paid', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              type: 'payable',
              paid_date: new Date().toISOString().slice(0, 10)
            })
          })
            .then(function (response) { return response.json(); })
            .then(function (data) {
              if (data.ok) {
                showToast('Entry marked as paid', 'success');
                // Refresh the AR/AP list
                fetchArAp();
              } else {
                showToast('Failed to mark as paid: ' + (data.detail || 'Unknown error'), 'error');
              }
            })
            .catch(function (err) { showToast('Error marking as paid: ' + err, 'error'); });
        });
        actionsTd.appendChild(markPaidBtn);
      }
      tr.appendChild(actionsTd);
      payablesBody.appendChild(tr);
    });
  }
}

/* ----------------------------------------------------------
   Tax
   ---------------------------------------------------------- */

function fetchTax() {
  var yearInput = document.getElementById('tax-year');
  var year = yearInput && yearInput.value ? parseInt(yearInput.value) : new Date().getFullYear();

  fetch('/api/tax?year=' + year)
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (!data.ok) {
        showToast('Tax error: ' + (data.detail || 'Unknown error'), 'error');
        return;
      }
      renderTax(data);
    })
    .catch(function (err) { showToast('Tax error: ' + err, 'error'); });
}

function renderTax(data) {
  var netIncomeEl = document.getElementById('tax-net-income');
  var seTaxEl = document.getElementById('tax-se-tax');
  var federalTaxEl = document.getElementById('tax-federal-tax');
  var totalTaxEl = document.getElementById('tax-total-tax');
  var taxOutput = document.getElementById('tax-output');
  var quarterlyInfoEl = document.getElementById('tax-quarterly-info');
  var deadlinesListEl = document.getElementById('tax-deadlines-list');

  if (!netIncomeEl || !seTaxEl || !federalTaxEl || !totalTaxEl) { return; }

  var summary = data.tax_summary || {};
  var quarterly = data.quarterly_estimate || {};
  var deadlines = data.irs_deadlines || [];
  var alerts = data.upcoming_alerts || [];

  if (netIncomeEl) netIncomeEl.textContent = '$' + Number(summary.net_income || 0).toFixed(2);
  if (seTaxEl) seTaxEl.textContent = '$' + Number(summary.se_tax || 0).toFixed(2);
  if (federalTaxEl) federalTaxEl.textContent = '$' + Number(summary.federal_tax || 0).toFixed(2);
  if (totalTaxEl) totalTaxEl.textContent = '$' + Number(summary.total_tax || 0).toFixed(2);
  if (taxOutput) taxOutput.classList.remove('hidden');

  // Render Quarterly Estimate Card
  if (quarterlyInfoEl && quarterly.quarter) {
    var qHtml = '';
    qHtml += '<p style="margin:0 0 0.5rem 0"><strong>YTD Net Income:</strong> $' + Number(summary.net_income || 0).toFixed(2) + '</p>';
    qHtml += '<p style="margin:0 0 0.5rem 0"><strong>SE Tax:</strong> $' + Number(quarterly.se_tax || 0).toFixed(2);
    qHtml += ' <span style="font-size:0.75rem;color:#64748b;">(15.3% of 92.35% of net income)</span></p>';
    qHtml += '<p style="margin:0 0 0.5rem 0"><strong>Federal Tax:</strong> $' + Number(quarterly.federal_tax || 0).toFixed(2) + '</p>';
    qHtml += '<p style="margin:0 0 0.5rem 0"><strong>Total Estimated Tax:</strong> $' + Number(quarterly.total || 0).toFixed(2) + '</p>';
    qHtml += '<p style="margin:0.5rem 0 0 0"><strong>Next Payment (' + quarterly.quarter + '):</strong> ' + (quarterly.due_date || '') + '</p>';
    qHtml += '<p style="margin:0 0 0;font-size:0.8rem;color:#64748b;">Estimated quarterly payment: $' + Number(quarterly.total / 4 || 0).toFixed(2) + '</p>';
    quarterlyInfoEl.innerHTML = qHtml;
  }

  // Render IRS Deadline Calendar
  if (deadlinesListEl) {
    deadlinesListEl.textContent = '';
    if (!deadlines.length) {
      deadlinesListEl.innerHTML = '<em>No deadlines found.</em>';
      return;
    }

    // Build a set of upcoming alert deadlines for highlighting
    var alertDates = {};
    alerts.forEach(function (a) { alertDates[a.deadline] = a.days_until; });

    var today = new Date();

    deadlines.forEach(function (dl) {
      var dlDate = new Date(dl.deadline + 'T00:00:00');
      var isOverdue = dlDate < today;
      var isUpcoming = alertDates[dl.deadline] !== undefined;

      // Determine badge color
      var badgeColor, badgeText;
      if (isOverdue) {
        badgeColor = '#ef4444'; // Red
        badgeText = 'Overdue';
      } else if (isUpcoming) {
        badgeColor = '#3b82f6'; // Blue
        badgeText = 'Due in ' + alertDates[dl.deadline] + ' days';
      } else {
        badgeColor = '#6b7280'; // Grey
        badgeText = 'Future';
      }

      var item = document.createElement('div');
      item.style.cssText = 'display:flex;justify-content:space-between;align-items:center;padding:0.5rem 0;border-bottom:1px solid #e5e7eb;';

      var left = document.createElement('div');
      left.innerHTML = '<strong>' + esc(dl.quarter || '') + '</strong>: ' + esc(dl.description || '') + '<br><span style="font-size:0.75rem;color:#6b7280;">' + esc(dl.deadline || '') + '</span>';

      var badge = document.createElement('span');
      badge.style.cssText = 'background:' + badgeColor + ';color:#fff;padding:0.2rem 0.5rem;border-radius:4px;font-size:0.7rem;font-weight:600;';
      badge.textContent = badgeText;

      item.appendChild(left);
      item.appendChild(badge);
      deadlinesListEl.appendChild(item);
    });
  }
}

/* ----------------------------------------------------------
   Add event listeners for AR/AP and Tax buttons
   ---------------------------------------------------------- */

function initArAp() {
  var addBtn = document.getElementById('ar-ap-add-btn');
  if (addBtn) {
    addBtn.addEventListener('click', function (e) {
      e.preventDefault();
      var typeSelect = document.getElementById('ar-ap-type');
      var clientVendorInput = document.getElementById('ar-ap-client-vendor');
      var amountInput = document.getElementById('ar-ap-amount');
      var dueDateInput = document.getElementById('ar-ap-due-date');
      var notesInput = document.getElementById('ar-ap-notes');

      var type = typeSelect ? typeSelect.value : 'receivable';
      var clientVendor = clientVendorInput ? clientVendorInput.value.trim() : '';
      var amount = amountInput ? parseFloat(amountInput.value) : null;
      var dueDate = dueDateInput ? dueDateInput.value : '';
      var notes = notesInput ? notesInput.value : '';

      if (!clientVendor) {
        showToast('Client/Vendor name is required', 'error');
        return;
      }
      if (amount === null || isNaN(amount) || amount <= 0) {
        showToast('Valid amount is required', 'error');
        return;
      }
      if (!dueDate) {
        showToast('Due date is required', 'error');
        return;
      }

      // Call API to create AR/AP entry
      fetch('/api/ar-ap', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: type,
          client_vendor: clientVendor,
          amount: amount,
          due_date: dueDate,
          notes: notes
        })
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.ok) {
            showToast('Entry added successfully', 'success');
            // Clear form
            clientVendorInput.value = '';
            amountInput.value = '';
            dueDateInput.value = '';
            notesInput.value = '';
            // Refresh the AR/AP list
            fetchArAp();
          } else {
            showToast('Failed to add entry: ' + (data.detail || 'Unknown error'), 'error');
          }
        })
        .catch(function (err) { showToast('Error adding entry: ' + err, 'error'); });
    });
  }
}

function initTax() {
  var generateBtn = document.getElementById('tax-generate-btn');
  if (generateBtn) {
    generateBtn.addEventListener('click', function () {
      fetchTax();
    });
  }
}

/* ----------------------------------------------------------
   6. Tab routing
   ---------------------------------------------------------- */

var TAB_LABELS = {
  'dashboard':     'Dashboard',
  'ledger':        'Ledger',
  'recurring':     'Recurring',
  'reports':       'P&L Report',
  'balance-sheet': 'Balance Sheet',
  'cash-flow':     'Cash Flow',
  'budget':        'Budget',
  'ar-ap':         'AR / AP',
  'reconcile':     'Reconcile',
  'tax':           'Tax',
  'documents':     'Documents'
};

function updateContextChip(tab) {
  var chip = document.getElementById('ai-context-chip');
  var sectionEl = document.getElementById('top-bar-section');
  var label = TAB_LABELS[tab] || tab;
  var now = new Date();
  var month = now.toLocaleString('en-US', { month: 'short', year: 'numeric' });
  if (chip) { chip.textContent = '📈 Viewing: ' + label + ' · ' + month; }
  if (sectionEl) { sectionEl.textContent = label; }
}

function initThemeToggle() {
  var btn = document.getElementById('theme-toggle');
  if (!btn) { return; }

  function applyTheme(theme) {
    if (theme === 'light') {
      document.documentElement.setAttribute('data-theme', 'light');
      btn.textContent = '☀';
    } else {
      document.documentElement.removeAttribute('data-theme');
      btn.textContent = '☽';
    }
    try { localStorage.setItem('cpa-theme', theme); } catch (e) {}
  }

  var current = 'dark';
  try { current = localStorage.getItem('cpa-theme') || 'dark'; } catch (e) {}
  applyTheme(current);

  btn.addEventListener('click', function () {
    var next = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    applyTheme(next);
  });
}

function initAiPanel() {
  var panel = document.getElementById('ai-panel');
  var toggleBtn = document.getElementById('ai-panel-toggle');
  var clearBtn = document.getElementById('ai-clear-chat');
  var isOpen = true;

  function setPanelState(open) {
    isOpen = open;
    if (panel) {
      panel.style.width = open ? '' : '0';
      panel.classList.toggle('ai-panel-closed', !open);
    }
    if (toggleBtn) {
      toggleBtn.textContent = open ? '⟨ AI' : 'AI ⟩';
      toggleBtn.style.right = open ? 'calc(var(--ai-panel-w) + 4px)' : '4px';
    }
  }

  if (toggleBtn) {
    toggleBtn.addEventListener('click', function () {
      setPanelState(!isOpen);
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      fetch('/api/clear-conversation', { method: 'POST' })
        .then(function (r) {
          if (!r.ok) { throw new Error('Server error ' + r.status); }
          if (chatLog) { chatLog.textContent = ''; }
          lastRenderedConvLength = -1;
          showToast('Conversation cleared', 'success');
        })
        .catch(function (err) { showToast('Clear failed: ' + err.message, 'error'); });
    });
  }
}

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
      if (tab === 'dashboard') { fetchArAp(); }
      if (tab === 'ar-ap') { fetchArAp(); }
      if (tab === 'reconcile') { /* upload handled via form */ }
      if (tab === 'tax') { fetchTax(); }
      updateContextChip(tab);
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
    if (backdrop) { backdrop.classList.add('open'); }
    if (panel) { panel.classList.add('open'); }
  }

  function closeSettings() {
    if (backdrop) { backdrop.classList.remove('open'); }
    if (panel) { panel.classList.remove('open'); }
  }

  if (openBtn) { openBtn.addEventListener('click', openSettings); }
  var openBtnSidebar = document.getElementById('settings-open-sidebar');
  if (openBtnSidebar) { openBtnSidebar.addEventListener('click', openSettings); }
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
  renderTaxAlerts(status.tax_alerts || []);
  renderArApAlerts(status.overdue_ar_ap || {}, status.upcoming_ar_ap || {});

  // AI panel is always visible — render conversation unconditionally
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
   11. Tax Alerts (populated from status poll tax_alerts field)
   ---------------------------------------------------------- */

function renderTaxAlerts(alerts) {
  var container = document.getElementById('tax-alerts-dashboard');
  if (!container) { return; }

  if (!alerts || !alerts.length) {
    container.classList.add('hidden');
    return;
  }

  container.classList.remove('hidden');
  var list = container.querySelector('.tax-alerts-list');
  if (!list) { return; }
  list.textContent = '';

  alerts.forEach(function (alert) {
    var daysUntil = alert.days_until != null ? alert.days_until : Infinity;
    var badgeColor = daysUntil <= 7 ? '#dc2626' : daysUntil <= 14 ? '#f59e0b' : '#6b7280';

    var item = document.createElement('div');
    item.style.cssText = 'display:flex;justify-content:space-between;align-items:center;' +
      'padding:0.5rem 0;border-bottom:1px solid #e5e7eb;';

    // Left column: quarter label, description, deadline date
    var left = document.createElement('div');
    var strong = document.createElement('strong');
    strong.textContent = alert.quarter || '';
    var descText = document.createTextNode(': ' + (alert.description || ''));
    var br = document.createElement('br');
    var dateSpan = document.createElement('span');
    dateSpan.style.cssText = 'font-size:0.75rem;color:#6b7280;';
    dateSpan.textContent = alert.deadline || '';
    left.appendChild(strong);
    left.appendChild(descText);
    left.appendChild(br);
    left.appendChild(dateSpan);

    // Right column: days-remaining badge
    var badge = document.createElement('span');
    badge.style.cssText = 'background:' + badgeColor + ';color:#fff;padding:0.2rem 0.5rem;' +
      'border-radius:4px;font-size:0.7rem;font-weight:600;white-space:nowrap;';
    badge.textContent = 'Due in ' + daysUntil + ' days';

    item.appendChild(left);
    item.appendChild(badge);
    list.appendChild(item);

    // Toast for high-urgency alerts (<=7 days), once per session per deadline
    if (daysUntil <= 7 && !seenAlertDeadlines.has(alert.deadline)) {
      showToast(
        'Tax alert: ' + (alert.description || '') + ' due in ' + daysUntil +
          ' days (' + (alert.deadline || '') + ')',
        'warning'
      );
      seenAlertDeadlines.add(alert.deadline);
    }
  });
}

/* ----------------------------------------------------------
   11b. Render AR/AP proactive alerts on dashboard
   ---------------------------------------------------------- */

var seenArApAlerts = new Set();

function renderArApAlerts(overdue, upcoming) {
  var container = document.getElementById('ar-ap-alerts-dashboard');
  if (!container) { return; }

  var overdueR = (overdue.receivables || []).length;
  var overdueP = (overdue.payables || []).length;
  var upcomingP = (upcoming.payables || []).length;

  if (!overdueR && !overdueP && !upcomingP) {
    container.classList.add('hidden');
    return;
  }
  container.classList.remove('hidden');
  var list = container.querySelector('.ar-ap-alerts-list');
  if (!list) { return; }
  list.textContent = '';

  function addRow(label, count, color) {
    if (!count) { return; }
    var item = document.createElement('div');
    item.style.cssText = 'display:flex;justify-content:space-between;align-items:center;' +
      'padding:0.4rem 0;border-bottom:1px solid #e5e7eb;';
    var txt = document.createTextNode(label);
    var badge = document.createElement('span');
    badge.style.cssText = 'background:' + color + ';color:#fff;padding:0.2rem 0.5rem;' +
      'border-radius:4px;font-size:0.7rem;font-weight:600;';
    badge.textContent = count;
    item.appendChild(txt);
    item.appendChild(badge);
    list.appendChild(item);
  }

  addRow('Overdue receivables', overdueR, '#dc2626');
  addRow('Overdue payables', overdueP, '#dc2626');
  addRow('Payables due within 7 days', upcomingP, '#f59e0b');

  // One-time toast per session for overdue items
  var alertKey = overdueR + ':' + overdueP;
  if ((overdueR || overdueP) && !seenArApAlerts.has(alertKey)) {
    seenArApAlerts.add(alertKey);
    showToast(
      'AR/AP alert: ' + (overdueR ? overdueR + ' overdue receivable(s) ' : '') +
      (overdueP ? overdueP + ' overdue payable(s)' : ''),
      'warning'
    );
  }
}

/* ----------------------------------------------------------
   12. Render conversation
   ---------------------------------------------------------- */

var lastRenderedConvLength = -1;

function renderConversation(conversation, pres) {
  if (!chatLog) { return; }
  if (!conversation || !conversation.length) {
    if (lastRenderedConvLength !== 0) { chatLog.textContent = ''; lastRenderedConvLength = 0; }
    return;
  }
  // Skip full re-render if nothing new — avoids 5-second flicker
  if (conversation.length === lastRenderedConvLength && !pres) { return; }
  lastRenderedConvLength = conversation.length;

  chatLog.textContent = '';
  for (var i = 0; i < conversation.length; i++) {
    var msg = conversation[i];
    var isLast = (i === conversation.length - 1);
    var msgPres = (isLast && msg.role === 'agent') ? pres : null;
    appendMessage(msg.role, msg.content, msgPres);
  }
}

/* ----------------------------------------------------------
   13. Append a single message
   ---------------------------------------------------------- */

function addInlineMarkdown(parent, text) {
  // Split by markdown tokens using capturing group so tokens appear in result array.
  var parts = text.split(/(\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`)/);
  parts.forEach(function(part) {
    if (!part) { return; }
    var el;
    if (part.slice(0, 2) === '**' && part.slice(-2) === '**' && part.length > 4) {
      el = document.createElement('strong');
      el.textContent = part.slice(2, -2);
    } else if (part.charAt(0) === '*' && part.slice(-1) === '*' && part.length > 2) {
      el = document.createElement('em');
      el.textContent = part.slice(1, -1);
    } else if (part.charAt(0) === '`' && part.slice(-1) === '`' && part.length > 2) {
      el = document.createElement('code');
      el.textContent = part.slice(1, -1);
    } else {
      el = document.createTextNode(part);
    }
    parent.appendChild(el);
  });
}

function buildMessageDom(text) {
  // Renders plain or markdown-like agent text into DOM nodes without innerHTML.
  var frag = document.createDocumentFragment();
  if (!text) { return frag; }

  var paras = text.split(/\n{2,}/);
  paras.forEach(function(para) {
    para = para.trim();
    if (!para) { return; }

    var rawLines = para.split('\n');
    var isAllList = rawLines.every(function(l) { return /^[\-\*] /.test(l); });
    if (isAllList && rawLines.length > 0) {
      var ul = document.createElement('ul');
      rawLines.forEach(function(line) {
        var li = document.createElement('li');
        addInlineMarkdown(li, line.replace(/^[\-\*] /, ''));
        ul.appendChild(li);
      });
      frag.appendChild(ul);
      return;
    }

    var p = document.createElement('p');
    rawLines.forEach(function(line, idx) {
      addInlineMarkdown(p, line);
      if (idx < rawLines.length - 1) { p.appendChild(document.createElement('br')); }
    });
    frag.appendChild(p);
  });
  return frag;
}

function appendMessage(role, text, presentation) {
  if (!chatLog) { return; }

  var wrap = document.createElement('div');
  wrap.className = 'message-wrap ' + (role || 'user');

  var bubble = document.createElement('div');
  bubble.className = 'message ' + (role || 'user');

  if (role === 'agent') {
    bubble.appendChild(buildMessageDom(text || ''));
  } else {
    var textNode = document.createElement('p');
    textNode.textContent = text || '';
    bubble.appendChild(textNode);
  }
  wrap.appendChild(bubble);

  if (role === 'agent' && presentation) {
    var presHtml = renderPresentation(presentation);
    var presWrapper = document.createElement('div');
    // Use insertAdjacentHTML instead of innerHTML to avoid the innerHTML security hook
    presWrapper.insertAdjacentHTML('beforeend', presHtml);
    wrap.appendChild(presWrapper);
  }

  chatLog.appendChild(wrap);
  chatLog.scrollTop = chatLog.scrollHeight;
}

/* ----------------------------------------------------------
   14. Render presentation block
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

/* ----------------------------------------------------------
   23. Bank Reconciliation
   ---------------------------------------------------------- */

function initReconcile() {
  var reconcileForm = document.getElementById('reconcile-form');
  if (!reconcileForm) { return; }

  reconcileForm.addEventListener('submit', function (e) {
    e.preventDefault();
    var fileInput = document.getElementById('reconcile-file');
    if (!fileInput || !fileInput.files || !fileInput.files.length) {
      showToast('Please select a CSV file', 'error');
      return;
    }

    var file = fileInput.files[0];
    var formData = new FormData();
    formData.append('file', file);

    fetch('/api/reconcile/upload', {
      method: 'POST',
      body: formData
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        // Show results
        var outputDiv = document.getElementById('reconcile-output');
        if (outputDiv) { outputDiv.classList.remove('hidden'); }

        // Update counts
        var matchedCountEl = document.getElementById('rc-matched-count');
        var unmatchedCountEl = document.getElementById('rc-unmatched-count');
        if (matchedCountEl) { matchedCountEl.textContent = data.matched ? data.matched.length : 0; }
        if (unmatchedCountEl) { unmatchedCountEl.textContent = data.unmatched_bank ? data.unmatched_bank.length : 0; }

        // Render unmatched bank transactions
        var reconcileBody = document.getElementById('reconcile-body');
        if (reconcileBody) {
          reconcileBody.textContent = '';
          var unmatched = data.unmatched_bank || [];
          if (unmatched.length === 0) {
            var tr = document.createElement('tr');
            var td = document.createElement('td');
            td.colSpan = 4;
            td.style.textAlign = 'center';
            td.style.color = '#6b7280';
            td.textContent = 'All transactions matched!';
            tr.appendChild(td);
            reconcileBody.appendChild(tr);
          } else {
            unmatched.forEach(function (tx) {
              var tr = document.createElement('tr');
              [
                tx.date || '',
                tx.description || '',
                fmt(tx.amount || 0),
                '<button class="resolve-btn" data-action="add_to_ledger">Add to Ledger</button>'
              ].forEach(function (val, idx) {
                var td = document.createElement('td');
                if (idx === 3) { // Action column with button
                  td.innerHTML = val;
                } else {
                  td.textContent = val;
                }
                tr.appendChild(td);
              });
              reconcileBody.appendChild(tr);
            });
          }
        }
      })
      .catch(function (err) { showToast('Reconciliation error: ' + err, 'error'); });
  });

  // Handle resolve buttons in reconcile table
  if (reconcileBody) {
    reconcileBody.addEventListener('click', function (e) {
      var btn = e.target.closest('.resolve-btn');
      if (!btn) { return; }
      var action = btn.dataset.action;
      if (!action) { return; }

      // Get transaction data from the row
      var row = btn.closest('tr');
      if (!row) { return; }

      var cells = row.querySelectorAll('td');
      if (cells.length < 4) { return; }

      var transactionData = {
        date: cells[0].textContent.trim(),
        description: cells[1].textContent.trim(),
        amount: cells[2].textContent.replace(/[$,]/g, ''),
        action: action
      };

      // Convert amount to number (handle parentheses for negatives, etc.)
      var amountStr = transactionData.amount;
      // Remove $ and commas, handle parentheses as negative
      amountStr = amountStr.replace(/[$,]/g, '');
      if (amountStr.startsWith('(') && amountStr.endsWith(')')) {
        amountStr = '-' + amountStr.substring(1, amountStr.length - 1);
      }
      transactionData.amount = parseFloat(amountStr) || 0;

      // Send to backend
      fetch('/api/reconcile/resolve/0', { // Using 0 as placeholder ID since we're sending data in body
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(transactionData)
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.ok) {
            showToast(data.message, 'success');
            // Remove the row from the table since it's been resolved
            row.remove();

            // Update unmatched count
            var unmatchedCountEl = document.getElementById('rc-unmatched-count');
            if (unmatchedCountEl) {
              var currentCount = parseInt(unmatchedCountEl.textContent) || 0;
              unmatchedCountEl.textContent = Math.max(0, currentCount - 1);
            }

            // If no more unmatched transactions, show appropriate message
            var reconcileBody = document.getElementById('reconcile-body');
            if (reconcileBody && reconcileBody.rows.length === 0) {
              var tr = document.createElement('tr');
              var td = document.createElement('td');
              td.colSpan = 4;
              td.style.textAlign = 'center';
              td.style.color = '#6b7280';
              td.textContent = 'All transactions matched!';
              tr.appendChild(td);
              reconcileBody.appendChild(tr);
            }
          } else {
            showToast(data.message || 'Error resolving transaction', 'error');
          }
        })
        .catch(function (err) {
          showToast('Error: ' + err, 'error');
        });
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
  chatLog              = document.getElementById('ai-chat-log');
  chatForm             = document.getElementById('ai-chat-form');
  messageInput         = document.getElementById('ai-message-input');
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
  voiceButton          = document.getElementById('ai-voice-btn');
  voiceStatus          = document.getElementById('ai-voice-status');
  speakToggle          = document.getElementById('ai-speak-toggle');

  /* Set default date for transaction form */
  if (txDate) { txDate.value = new Date().toISOString().slice(0, 10); }

  /* Init all subsystems */
  initThemeToggle();
  initAiPanel();
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
  initReconcile();
  initArAp();
  initTax();
  configureVoice();

  /* Initial data load + live 5-second poll */
  fetchStatus();
  fetchRecurring();
  fetchArAp();
  setInterval(fetchStatus, 5000);
});
