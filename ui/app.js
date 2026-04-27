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
var documentDrafts;
var voiceButton, voiceStatus, speakToggle;

/* ----------------------------------------------------------
   5. Tab routing
   ---------------------------------------------------------- */

function initTabs() {
  var tabBtns = document.querySelectorAll('.tab-btn');
  var tabPanes = document.querySelectorAll('.tab-pane');

  tabBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      // Deactivate all buttons and hide all panes
      tabBtns.forEach(function (b) { b.classList.remove('active'); });
      tabPanes.forEach(function (p) { p.classList.add('hidden'); });

      // Activate clicked button
      btn.classList.add('active');

      // Show corresponding pane
      var paneId = 'tab-' + btn.dataset.tab;
      var pane = document.getElementById(paneId);
      if (pane) { pane.classList.remove('hidden'); }

      // Side-effect: load ledger when switching to ledger tab
      if (btn.dataset.tab === 'ledger') {
        fetchLedger(1);
      }
    });
  });
}

/* ----------------------------------------------------------
   6. Settings panel
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
   7. Update status / dashboard
   ---------------------------------------------------------- */

function updateStatus(status) {
  if (!status) { return; }

  // Business select
  if (businessSelect && status.businesses) {
    businessSelect.textContent = '';
    status.businesses.forEach(function (biz) {
      var opt = document.createElement('option');
      opt.value = biz.key;
      opt.textContent = biz.name || biz.key;
      if (biz.key === status.active_business_key) { opt.selected = true; }
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
   8. Recent transactions
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
   9. Recent audits
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
   10. Render conversation
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
   11. Append a single message
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
   12. Render presentation block
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
   13. Provider switch
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
   14. Mode switch
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
   15. Business auto-switch
   ---------------------------------------------------------- */

function initBusinessSwitch() {
  if (!businessSelect) { return; }
  businessSelect.addEventListener('change', function () {
    fetch('/api/switch-business', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ business_key: businessSelect.value })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) { showToast(data.error, 'error'); return; }
        updateStatus(data.status);
      })
      .catch(function (err) { showToast(String(err), 'error'); });
  });
}

/* ----------------------------------------------------------
   16. Fetch ledger
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
          row.category || row[3] || '',
          (row.amount !== undefined) ? fmt(row.amount) : (row[4] || ''),
          row.reference || row[5] || ''
        ];
        cols.forEach(function (col) {
          var td = document.createElement('td');
          td.textContent = col;
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
   17. Transaction form toggle
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
   18. P&L Report
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

  /* 19. CSV export */
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
   20. Document upload
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

  /* 21. Draft approval — delegated */
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
   22 + 23. Chat submit and Cmd+Enter shortcut
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

        /* 25. Voice reply */
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
   24 + 25. Voice recognition and voice reply toggle
   ---------------------------------------------------------- */

function configureVoice() {
  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (voiceStatus) { voiceStatus.textContent = 'Browser voice idle'; }

  /* 25. Speak-toggle */
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
   26. fetchStatus — initial load
   ---------------------------------------------------------- */

function fetchStatus() {
  fetch('/api/status')
    .then(function (r) { return r.json(); })
    .then(function (data) { updateStatus(data); })
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
  initDocuments();
  initChat();
  configureVoice();

  /* Initial data load */
  fetchStatus();
});
