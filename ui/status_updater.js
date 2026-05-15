/* CPA-Agent — Status polling and dashboard metric updates */
'use strict';

function formatCurrency(value) {
  var USD_FMT = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
  return USD_FMT.format(Number(value) || 0);
}

function updateStatus(status) {
  if (!status) { return; }

  var businessSelect = document.getElementById('business-select');
  if (businessSelect && status.businesses) {
    businessSelect.textContent = '';
    status.businesses.forEach(function (biz) {
      var opt = document.createElement('option');
      opt.value = biz.business_name;
      opt.textContent = biz.business_name;
      if (biz.key === status.active_business_key) { opt.selected = true; }
      businessSelect.appendChild(opt);
    });
  }

  var modelBadge = document.getElementById('model-badge');
  if (modelBadge && status.model_config) {
    modelBadge.textContent =
      status.model_config.provider.toUpperCase() + ' • ' + status.model_config.reasoning_model;
  }

  var bootWarning = document.getElementById('boot-warning');
  if (bootWarning) {
    if (status.workspace_boot_error) {
      bootWarning.classList.remove('hidden');
    } else {
      bootWarning.classList.add('hidden');
    }
  }

  var learnedCount = document.getElementById('learned-count');
  if (learnedCount && status.learned_count !== undefined) {
    learnedCount.textContent = status.learned_count;
  }

  var sheetLink = document.getElementById('sheet-link');
  var docLink = document.getElementById('doc-link');
  if (sheetLink) {
    var sheetId = status.active_business && status.active_business.google_sheet_id;
    sheetLink.href = sheetId ? 'https://docs.google.com/spreadsheets/d/' + sheetId : '#';
  }
  if (docLink) {
    var docId = status.active_business && status.active_business.google_doc_id;
    docLink.href = docId ? 'https://docs.google.com/document/d/' + docId : '#';
  }

  var dash = status.dashboard || {};

  var metricTransactions = document.getElementById('metric-transactions');
  if (metricTransactions) {
    metricTransactions.classList.remove('skeleton');
    metricTransactions.textContent = dash.transaction_count !== undefined ? dash.transaction_count : '—';
  }

  var metricIncome = document.getElementById('metric-income');
  if (metricIncome) {
    metricIncome.classList.remove('skeleton');
    metricIncome.textContent = formatCurrency(dash.income_total);
  }

  var metricExpenses = document.getElementById('metric-expenses');
  if (metricExpenses) {
    metricExpenses.classList.remove('skeleton');
    metricExpenses.textContent = formatCurrency(dash.expense_total);
  }

  var metricNet = document.getElementById('metric-net');
  if (metricNet) {
    metricNet.classList.remove('skeleton');
    var net = (dash.income_total || 0) - (dash.expense_total || 0);
    metricNet.textContent = formatCurrency(net);
    metricNet.classList.remove('positive', 'negative');
    if (net > 0) { metricNet.classList.add('positive'); }
    else if (net < 0) { metricNet.classList.add('negative'); }
  }

  var metricFlagged = document.getElementById('metric-flagged');
  if (metricFlagged) {
    metricFlagged.classList.remove('skeleton');
    metricFlagged.textContent = dash.flagged_actions !== undefined ? dash.flagged_actions : '—';
  }

  var providerSelect = document.getElementById('provider-select');
  var modelModeSelect = document.getElementById('model-mode-select');
  if (providerSelect) { providerSelect.value = status.model_config ? status.model_config.provider || '' : ''; }
  if (modelModeSelect) { modelModeSelect.value = status.model_config ? status.model_config.reasoning_mode || 'full' : 'full'; }
}

function fetchStatus() {
  fetch('/api/status')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      updateStatus(data);
      var ledgerItem = document.querySelector('.sidebar-item[data-tab="ledger"]');
      if (ledgerItem && ledgerItem.classList.contains('active')) {
        if (typeof fetchLedger === 'function') { fetchLedger(1); }
      }
    })
    .catch(function (err) {
      var bootWarning = document.getElementById('boot-warning');
      if (bootWarning) { bootWarning.classList.remove('hidden'); }
      console.error('fetchStatus error:', err);
    });
}
