/* CPA-Agent — Settings panel, theme, and system-control initialisation */
'use strict';

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
    toggleBtn.addEventListener('click', function () { setPanelState(!isOpen); });
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
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { closeSettings(); } });
}

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

function initProviderSwitch() {
  var applyProvider = document.getElementById('apply-provider');
  if (!applyProvider) { return; }

  applyProvider.addEventListener('click', function () {
    var sel = document.getElementById('provider-select');
    fetch('/api/provider', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: sel ? sel.value : '' })
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

function initModeSwitch() {
  var applyMode = document.getElementById('apply-mode');
  if (!applyMode) { return; }

  applyMode.addEventListener('click', function () {
    var sel = document.getElementById('model-mode-select');
    fetch('/api/model-mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: sel ? sel.value : '' })
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

function initModeSelector() {
  var modelModeSelect = document.getElementById('model-mode-select');
  if (!modelModeSelect) { return; }

  if (!modelModeSelect.value) { modelModeSelect.value = 'full'; }

  modelModeSelect.addEventListener('change', function () {
    var provider = document.getElementById('provider-select');
    if (!provider || !provider.value) { return; }
    fetch('/api/model-mode', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: modelModeSelect.value, provider: provider.value })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) { if (data.status) { updateStatus(data.status); } })
      .catch(function () {});
  });
}
