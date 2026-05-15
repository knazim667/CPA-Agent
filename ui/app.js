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
   Dynamic module loader (low-overhead fallback if index.html
   <script> tags are absent)
   ---------------------------------------------------------- */

(function () {
  if (typeof window === 'undefined') { return; }

  function lazyLoad(test, src) {
    if (typeof test === 'undefined') {
      var s = document.createElement('script');
      s.src = src;
      document.head.appendChild(s);
    }
  }

  lazyLoad(typeof getState,              '/js/ui/state.js');
  lazyLoad(typeof fetchCached,           '/js/ui/cached_fetch.js');
  lazyLoad(typeof debounceLedgerSearch,  '/js/ui/debounce.js');
  lazyLoad(typeof validateTransactionForm, '/js/ui/validators.js');
  lazyLoad(typeof renderPresentation,    '/js/ui/presentation.js');
  lazyLoad(typeof appendMessage,         '/js/ui/markdown.js');
  lazyLoad(typeof speakReply,            '/js/ui/voice.js');
  lazyLoad(typeof switchTab,             '/js/ui/router.js');
  lazyLoad(typeof toCSV,                 '/js/ui/export.js');

  var chatModule = document.createElement('script');
  chatModule.src = '/js/ui/chat.js';
  chatModule.onload = function () { if (typeof initApp === 'function') { initApp(); } };
  document.head.appendChild(chatModule);
}());

/* ----------------------------------------------------------
   Main init — wires all UI subsystems together
   ---------------------------------------------------------- */

function init() {
  var chatLog = document.getElementById('ai-chat-log');
  var chatForm = document.getElementById('ai-chat-form');
  var messageInput = document.getElementById('ai-message-input');
  var aiPanelToggle = document.getElementById('ai-panel-toggle');
  var aiClearChat = document.getElementById('ai-clear-chat');

  if (!chatForm || !messageInput) { return; }

  chatForm.addEventListener('submit', function (e) {
    e.preventDefault();
    var text = messageInput.value.trim();
    if (!text) { return; }

    if (typeof appendMessage === 'function') {
      appendMessage('user', text, null);
    } else {
      var wrap = document.createElement('div');
      wrap.className = 'message-wrap user';
      wrap.innerHTML = '<div class="message user"><p>' + escapeHtml(text) + '</p></div>';
      chatLog.appendChild(wrap);
    }

    messageInput.value = '';

    fetch('/api/message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var presentation = data.presentation || null;

        if (typeof appendMessage === 'function') {
          appendMessage('agent', data.message || '', presentation);
        } else {
          var presHtml = (typeof renderPresentation === 'function' && presentation)
            ? renderPresentation(presentation) : '';
          var agentWrap = document.createElement('div');
          agentWrap.className = 'message-wrap agent';
          agentWrap.innerHTML =
            '<div class="message agent">' +
            (presHtml ? '<div class="presentation">' + presHtml + '</div>' : '') +
            '<div class="message-content">' + renderContent(data.message || '') + '</div>' +
            '</div>';
          chatLog.appendChild(agentWrap);
        }

        fetchStatus();
      })
      .catch(function (err) {
        if (typeof appendMessage === 'function') { appendMessage('agent', 'Error: ' + err, null); }
      });
  });

  messageInput.addEventListener('keydown', function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { chatForm.requestSubmit(); }
  });

  if (aiPanelToggle) {
    aiPanelToggle.addEventListener('click', function () {
      var panel = document.getElementById('ai-panel');
      var isOpen = panel.style.width !== '0';
      panel.style.width = isOpen ? '0' : '';
      aiPanelToggle.textContent = isOpen ? 'AI ⟩' : '⟨ AI';
    });
  }

  if (aiClearChat) {
    aiClearChat.addEventListener('click', function () {
      fetch('/api/clear-conversation', { method: 'POST' })
        .then(function (r) {
          if (!r.ok) { throw new Error('Server error ' + r.status); }
          var log = document.getElementById('ai-chat-log');
          if (log) { log.textContent = ''; }
          showToast('Conversation cleared', 'success');
        })
        .catch(function (err) { showToast('Clear failed: ' + err.message, 'error'); });
    });
  }

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

  initSettings();
  initBusinessSwitch();
  initProviderSwitch();
  initModeSwitch();
  initModeSelector();
  fetchStatus();
}

/* ----------------------------------------------------------
   DOMContentLoaded
   ---------------------------------------------------------- */

document.addEventListener('DOMContentLoaded', init);
