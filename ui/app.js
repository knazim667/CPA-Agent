/* 401 interceptor — redirect to /login on any unauthenticated API response */
(function () {
  var _origFetch = window.fetch;
  window.fetch = function () {
    return _origFetch.apply(this, arguments).then(function (r) {
      if (r.status === 401 &&
          !r.url.includes('/api/auth/') &&
          !r.url.includes('/login')) {
        window.location.href = '/login';
      }
      return r;
    });
  };
}());

/* 404 interceptor — fallback to main page */
(function () {
  var _origFetch = window.fetch;
  window.fetch = function () {
    var _orig = _origFetch.apply(this, arguments);
    return _orig.then(function (r) {
      if (r.status === 404 && r.url.includes('/api/') && r.url.startsWith('/api/')) {
        var lastSlash = r.url.lastIndexOf('/');
        var path = r.url.substring(0, lastSlash);
        window.location.href = path + '/';
      }
      return r;
    }).catch(function () {
      return r;
    });
  };
}());

/* CPA-Agent — Main entry point */
'use strict';

/* ----------------------------------------------------------
   1. Import modules
   ---------------------------------------------------------- */

// Load UI modules
(function () {
  if (typeof window === 'undefined') { return; }

  // Import state management
  if (typeof getState === 'undefined') {
    var stateModule = document.createElement('script');
    stateModule.src = '/js/ui/state.js';
    document.head.appendChild(stateModule);
  }

  // Import caching layer
  if (typeof fetchCached === 'undefined') {
    var cacheModule = document.createElement('script');
    cacheModule.src = '/js/ui/cached_fetch.js';
    document.head.appendChild(cacheModule);
  }

  // Import debounce utilities
  if (typeof debounceLedgerSearch === 'undefined') {
    var debounceModule = document.createElement('script');
    debounceModule.src = '/js/ui/debounce.js';
    document.head.appendChild(debounceModule);
  }

  // Import validators
  if (typeof validateTransactionForm === 'undefined') {
    var validatorsModule = document.createElement('script');
    validatorsModule.src = '/js/ui/validators.js';
    document.head.appendChild(validatorsModule);
  }

  // Import presentation renderer
  if (typeof renderPresentation === 'undefined') {
    var presentationModule = document.createElement('script');
    presentationModule.src = '/js/ui/presentation.js';
    document.head.appendChild(presentationModule);
  }

  // Import markdown parser
  if (typeof appendMessage === 'undefined') {
    var markdownModule = document.createElement('script');
    markdownModule.src = '/js/ui/markdown.js';
    document.head.appendChild(markdownModule);
  }

  // Import voice functionality
  if (typeof speakReply === 'undefined') {
    var voiceModule = document.createElement('script');
    voiceModule.src = '/js/ui/voice.js';
    document.head.appendChild(voiceModule);
  }

  // Import router
  if (typeof switchTab === 'undefined') {
    var routerModule = document.createElement('script');
    routerModule.src = '/js/ui/router.js';
    document.head.appendChild(routerModule);
  }

  // Import export utilities
  if (typeof toCSV === 'undefined') {
    var exportModule = document.createElement('script');
    exportModule.src = '/js/ui/export.js';
    document.head.appendChild(exportModule);
  }

  // Load chat module after other modules are loaded
  var chatModule = document.createElement('script');
  chatModule.src = '/js/ui/chat.js';
  chatModule.onload = initApp;
  document.head.appendChild(chatModule);
})();

/* ----------------------------------------------------------
   2. Toast system
   ---------------------------------------------------------- */

function showToast(message, type) {
  if (type === undefined) { type = 'info'; }
  var container = document.getElementById('toast-container');
  if (!container) { return; }

  var toast = document.createElement('div');
  toast.className = 'toast ' + type;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(function () {
    toast.classList.add('toast-out');
    setTimeout(function () {
      if (toast.parentNode) { toast.parentNode.removeChild(toast); }
    }, 300);
  }, 3500);
}

/* ----------------------------------------------------------
   3. Init helpers
   ---------------------------------------------------------- */

function initToast() {
  // Toast functionality handled by chat.js now
}

function initTheme() {
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
          var chatLog = document.getElementById('ai-chat-log');
          if (chatLog) { chatLog.textContent = ''; }
          showToast('Conversation cleared', 'success');
        })
        .catch(function (err) { showToast('Clear failed: ' + err.message, 'error'); });
    });
  }
}

/* ----------------------------------------------------------
   4. Settings panel
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
   5. Business switch
   ---------------------------------------------------------- */

function initBusinessSwitch() {
  var businessSelect = document.getElementById('business-select');
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
        if (data.status) { updateStatus(data.status); }
        showToast('Switched to ' + businessSelect.value, 'success');
      })
      .catch(function (err) { showToast(String(err), 'error'); });
  });
}

/* ----------------------------------------------------------
   6. Provider switch
   ---------------------------------------------------------- */

function initProviderSwitch() {
  var applyProvider = document.getElementById('apply-provider');
  if (!applyProvider) { return; }

  applyProvider.addEventListener('click', function () {
    fetch('/api/provider', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: document.getElementById('provider-select')?.value || '' })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) { showToast(data.error, 'error'); return; }
        if (data.status) { updateStatus(data.status); }
        showToast('Provider switched', 'success');
      })
      .catch(function (err) { showToast(String(err), 'error'); });
  });
}

/* ----------------------------------------------------------
   7. Mode switch
   ---------------------------------------------------------- */

function initModeSwitch() {
  var applyMode = document.getElementById('apply-mode');
  if (!applyMode) { return; }

  applyMode.addEventListener('click', function () {
    fetch('/api/model-mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: document.getElementById('model-mode-select')?.value || '' })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.error) { showToast(data.error, 'error'); return; }
        if (data.status) { updateStatus(data.status); }
        showToast('Mode updated', 'success');
      })
      .catch(function (err) { showToast(String(err), 'error'); });
  });
}

/* ----------------------------------------------------------
   8. Mode selector
   ---------------------------------------------------------- */

function initModeSelector() {
  var modelModeSelect = document.getElementById('model-mode-select');
  if (!modelModeSelect) { return; }

  // Default to full for new users
  if (!modelModeSelect.value) {
    modelModeSelect.value = 'full';
  }

  // Update status when mode changes
  modelModeSelect.addEventListener('change', function () {
    var provider = document.getElementById('provider-select')?.value;
    if (!provider) { return; }

    // Update model config
    fetch('/api/model-mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: modelModeSelect.value, provider: provider })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.status) { updateStatus(data.status); }
      })
      .catch(function () {});
  });
}

/* ----------------------------------------------------------
   9. Update status
   ---------------------------------------------------------- */

function updateStatus(status) {
  if (!status) { return; }

  // Business select
  var businessSelect = document.getElementById('business-select');
  if (businessSelect && status.businesses) {
    businessSelect.textContent = '';
    status.businesses.forEach(function (biz) {
      var opt = document.createElement('option');
      opt.value = biz.business_name;
      opt.textContent = biz.business_name;
      if (biz.key === status.active_business_key) {
        opt.selected = true;
      }
      businessSelect.appendChild(opt);
    });
  }

  // Model badge
  var modelBadge = document.getElementById('model-badge');
  if (modelBadge && status.model_config) {
    modelBadge.textContent =
      status.model_config.provider.toUpperCase() + ' • ' + status.model_config.reasoning_model;
  }

  // Boot warning
  var bootWarning = document.getElementById('boot-warning');
  if (bootWarning) {
    if (status.workspace_boot_error) {
      bootWarning.classList.remove('hidden');
    } else {
      bootWarning.classList.add('hidden');
    }
  }

  // Learned count
  var learnedCount = document.getElementById('learned-count');
  if (learnedCount && status.learned_count !== undefined) {
    learnedCount.textContent = status.learned_count;
  }

  // Sheet / doc links
  var sheetLink = document.getElementById('sheet-link');
  var docLink = document.getElementById('doc-link');

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

  // Provider / mode selects in settings
  if (providerSelect) { providerSelect.value = status.model_config?.provider || ''; }
  if (modelModeSelect) { modelModeSelect.value = status.model_config?.reasoning_mode || 'full'; }
}

function formatCurrency(value) {
  var USD_FMT = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
  return USD_FMT.format(Number(value) || 0);
}

/* ----------------------------------------------------------
   10. Fetch status
   ---------------------------------------------------------- */

function fetchStatus() {
  // Use cached fetch for /api/status
  fetch('/api/status')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      updateStatus(data);
      // If ledger tab is active, fetch ledger
      var ledgerItem = document.querySelector('.sidebar-item[data-tab="ledger"]');
      if (ledgerItem && ledgerItem.classList.contains('active')) {
        fetchLedger(1);
      }
    })
    .catch(function (err) {
      var bootWarning = document.getElementById('boot-warning');
      if (bootWarning) { bootWarning.classList.remove('hidden'); }
      console.error('fetchStatus error:', err);
    });
}

/* ----------------------------------------------------------
   11. Init all subsystems
   ---------------------------------------------------------- */

function init() {
  // Get DOM references
  var chatLog = document.getElementById('ai-chat-log');
  var chatForm = document.getElementById('ai-chat-form');
  var messageInput = document.getElementById('ai-message-input');
  var aiPanelToggle = document.getElementById('ai-panel-toggle');
  var aiClearChat = document.getElementById('ai-clear-chat');
  var voiceButton = document.getElementById('ai-voice-btn');
  var voiceStatus = document.getElementById('ai-voice-status');
  var speakToggle = document.getElementById('ai-speak-toggle');

  // Check if elements exist before using them
  if (!chatForm || !messageInput) { return; }

  // Init chat form
  chatForm.addEventListener('submit', function (e) {
    e.preventDefault();
    var text = messageInput.value.trim();
    if (!text) { return; }

    // Use appendMessage from markdown.js
    if (typeof appendMessage === 'function') {
      appendMessage('user', text, null);
    } else {
      var wrap = document.createElement('div');
      wrap.className = 'message-wrap user';
      wrap.innerHTML = '<div class="message user"><p>' + escapeHtml(text) + '</p></div>';
      chatLog.appendChild(wrap);
    }

    messageInput.value = '';

    // Send to server
    fetch('/api/message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        // Get latest presentation for agent response
        var presentation = data.presentation || null;

        // Append agent message
        if (typeof appendMessage === 'function') {
          appendMessage('agent', data.message || '', presentation);
        } else {
          var presHtml = presentation ? renderPresentation(presentation) : '';
          var agentWrap = document.createElement('div');
          agentWrap.className = 'message-wrap agent';
          agentWrap.innerHTML =
            '<div class="message agent">' +
            (presHtml ? '<div class="presentation">' + presHtml + '</div>' : '') +
            '<div class="message-content">' + renderContent(data.message || '') + '</div>' +
            '</div>';
          chatLog.appendChild(agentWrap);
        }

        // Refresh dashboard metrics after response
        fetchStatus();
      })
      .catch(function (err) {
        if (typeof appendMessage === 'function') {
          appendMessage('agent', 'Error: ' + err, null);
        }
      });
  });

  // Cmd+Enter shortcut
  messageInput.addEventListener('keydown', function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      chatForm.requestSubmit();
    }
  });

  // AI panel toggle
  if (aiPanelToggle) {
    aiPanelToggle.addEventListener('click', function () {
      var panel = document.getElementById('ai-panel');
      var isOpen = panel.style.width !== '0';
      panel.style.width = isOpen ? '0' : '';
      aiPanelToggle.textContent = isOpen ? 'AI ⟩' : '⟨ AI';
    });
  }

  // Clear chat
  if (aiClearChat) {
    aiClearChat.addEventListener('click', function () {
      fetch('/api/clear-conversation', { method: 'POST' })
        .then(function (r) {
          if (!r.ok) { throw new Error('Server error ' + r.status); }
          var chatLog = document.getElementById('ai-chat-log');
          if (chatLog) { chatLog.textContent = ''; }
          showToast('Conversation cleared', 'success');
        })
        .catch(function (err) { showToast('Clear failed: ' + err.message, 'error'); });
  });
}

  // Theme toggle
  var themeToggle = document.getElementById('theme-toggle');
  if (themeToggle) {
    themeToggle.addEventListener('click', function () {
      var theme = document.documentElement.getAttribute('data-theme');
      var next = theme === 'light' ? 'dark' : 'light';
      if (next === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
        themeToggle.textContent = '☀';
      } else {
        document.documentElement.removeAttribute('data-theme');
        themeToggle.textContent = '☽';
      }
      try { localStorage.setItem('cpa-theme', next); } catch (e) {}
    });
  }

  // Settings
  initSettings();

  // Business switch
  initBusinessSwitch();

  // Provider switch
  initProviderSwitch();

  // Mode switch
  initModeSwitch();

  // Mode selector
  initModeSelector();

  // Fetch initial status
  fetchStatus();
}

/* ----------------------------------------------------------
   Utility: Escape HTML
   ---------------------------------------------------------- */

function escapeHtml(v) {
  if (v === null || v === undefined) { return ''; }
  var s = String(v);
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ----------------------------------------------------------
   Utility: Render content with markdown
   ---------------------------------------------------------- */

function renderContent(text) {
  if (!text) { return ''; }

  var html = '';
  var lines = text.split('\n');
  var currentPara = '';

  lines.forEach(function (line) {
    var trimmed = line.trim();
    if (!trimmed) { return; }

    if (/^[\-\*] /.test(trimmed)) {
      if (currentPara) {
        html += '<p>' + escapeHtml(currentPara) + '</p>';
        currentPara = '';
      }
      html += '<ul><li>' + escapeHtml(trimmed.replace(/^[\-\*] /, '')) + '</li></ul>';
    } else {
      currentPara += '\n' + trimmed;
    }
  });

  if (currentPara) {
    html += '<p>' + escapeHtml(currentPara) + '</p>';
  }

  return html;
}

/* ----------------------------------------------------------
   DOMContentLoaded
   ---------------------------------------------------------- */

document.addEventListener('DOMContentLoaded', init);
