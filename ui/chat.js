/* ----------------------------------------------------------
   Chat rendering (modular version)
   ---------------------------------------------------------- */

'use strict';

/* ----------------------------------------------------------
   1. Import and setup
   ---------------------------------------------------------- */

(function () {
  // Get DOM elements
  var chatLog = document.getElementById('ai-chat-log');
  var chatForm = document.getElementById('ai-chat-form');
  var messageInput = document.getElementById('ai-message-input');

  if (!chatLog || !chatForm || !messageInput) { return; }

  /* ----------------------------------------------------------
     2. Chat submit handler
     ---------------------------------------------------------- */

  chatForm.addEventListener('submit', function (e) {
    e.preventDefault();
    var text = messageInput.value.trim();
    if (!text) { return; }

    appendMessage('user', text, null);
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

        // Append agent message with presentation
        appendMessage('agent', data.message || '', presentation);

        // Refresh dashboard metrics after response
        fetchStatus();
      })
      .catch(function (err) {
        appendMessage('agent', 'Error: ' + err, null);
      });
  });

  /* ----------------------------------------------------------
     3. Cmd+Enter shortcut
     ---------------------------------------------------------- */

  messageInput.addEventListener('keydown', function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      chatForm.requestSubmit();
    }
  });

  /* ----------------------------------------------------------
     4. Append message function (uses markdown.js)
     ---------------------------------------------------------- */

  function appendMessage(role, text, presentation) {
    var msgHtml = '';

    if (role === 'agent') {
      // Use markdown parser
      msgHtml = '<div class="message agent"><div class="message-content">' +
        renderContent(text) +
        '</div></div>';
    } else {
      msgHtml = '<div class="message user"><div class="message-content">' +
        esc(text) +
        '</div></div>';
    }

    var wrap = document.createElement('div');
    wrap.className = 'message-wrap ' + role;
    wrap.insertAdjacentHTML('beforeend', msgHtml);

    if (presentation) {
      var presHtml = renderPresentation(presentation);
      var presWrapper = document.createElement('div');
      presWrapper.insertAdjacentHTML('beforeend', presHtml);
      wrap.appendChild(presWrapper);
    }

    chatLog.appendChild(wrap);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  /* ----------------------------------------------------------
     5. Render content with markdown formatting
     ---------------------------------------------------------- */

  function renderContent(text) {
    if (!text) { return ''; }

    // Parse markdown-like formatting
    var html = '';
    var lines = text.split('\n');

    var hasList = false;
    var listLines = [];
    var paraLines = [];
    var currentPara = '';

    lines.forEach(function (line) {
      var trimmed = line.trim();
      if (!trimmed) { return; }

      // Check if list item
      if (/^[\-\*] /.test(trimmed)) {
        hasList = true;
        listLines.push(trimmed.replace(/^[\-\*] /, ''));
      } else {
        if (currentPara) {
          currentPara += '\n' + trimmed;
        } else {
          paraLines.push(trimmed);
        }
      }
    });

    // Render paragraph
    if (currentPara) {
      html += renderParagraph(currentPara);
    }
    paraLines.forEach(function (line) {
      html += renderParagraph(line);
    });

    // Render list
    if (hasList) {
      html += renderList(listLines);
    }

    return html;
  }

  function renderParagraph(text) {
    var html = '<p>';
    // Simple markdown parsing
    var parts = text.split(/(\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`)/);
    parts.forEach(function (part) {
      if (!part) { return; }
      if (part.slice(0, 2) === '**' && part.slice(-2) === '**' && part.length > 4) {
        html += '<strong>' + part.slice(2, -2) + '</strong>';
      } else if (part.charAt(0) === '*' && part.slice(-1) === '*' && part.length > 2) {
        html += '<em>' + part.slice(1, -1) + '</em>';
      } else if (part.charAt(0) === '`' && part.slice(-1) === '`' && part.length > 2) {
        html += '<code>' + part.slice(1, -1) + '</code>';
      } else {
        html += escapeHtml(part);
      }
    });
    html += '</p>';
    return html;
  }

  function renderList(lines) {
    var html = '<ul>';
    lines.forEach(function (line) {
      html += '<li>' + escapeHtml(line) + '</li>';
    });
    html += '</ul>';
    return html;
  }

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
     6. Render presentation block
     ---------------------------------------------------------- */

  function renderPresentation(p) {
    if (!p) { return ''; }

    var html = '<div class="presentation-block">';

    if (p.type === 'table') {
      if (p.stats && p.stats.length) {
        html += '<div class="presentation-stats">';
        p.stats.forEach(function (stat) {
          html += '<div class="stat-item"><span class="stat-label">' + escapeHtml(stat.label) + '</span>';
          html += '<span class="stat-value">' + escapeHtml(stat.value) + '</span></div>';
        });
        html += '</div>';
      }
      if (p.headers && p.rows) {
        html += '<div class="table-wrap"><table><thead><tr>';
        p.headers.forEach(function (h) {
          html += '<th>' + escapeHtml(h) + '</th>';
        });
        html += '</tr></thead><tbody>';
        p.rows.forEach(function (row) {
          html += '<tr>';
          row.forEach(function (cell) {
            html += '<td>' + escapeHtml(cell) + '</td>';
          });
          html += '</tr>';
        });
        html += '</tbody></table></div>';
      }
    } else if (p.type === 'document_draft') {
      if (p.headers && p.rows) {
        html += '<div class="table-wrap"><table><thead><tr>';
        p.headers.forEach(function (h) {
          html += '<th>' + escapeHtml(h) + '</th>';
        });
        html += '</tr></thead><tbody>';
        p.rows.forEach(function (row) {
          html += '<tr>';
          row.forEach(function (cell) {
            html += '<td>' + escapeHtml(cell) + '</td>';
          });
          html += '</tr>';
        });
        html += '</tbody></table></div>';
      }
      if (p.token) {
        html += '<button class="approval-button" data-token="' + escapeHtml(p.token) + '">Approve Draft</button>';
      }
    }

    html += '</div>';
    return html;
  }

  /* ----------------------------------------------------------
     7. Voice reply (will be integrated from voice.js)
     ---------------------------------------------------------- */

  function speakReply(message) {
    if (!window.speechSynthesis) { return; }
    var utterance = new SpeechSynthesisUtterance(message);
    var voices = window.speechSynthesis.getVoices();
    if (voices.length > 0) {
      utterance.voice = voices.find(function (v) { return v.name.includes('Google'); }) || voices[0];
    }
    utterance.rate = 1;
    utterance.pitch = 1;
    window.speechSynthesis.speak(utterance);
  }

  // Export appendMessage for external use
  window.appendMessage = appendMessage;
  window.speakReply = speakReply;

})();
