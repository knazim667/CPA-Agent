/* ----------------------------------------------------------
   Markdown parsing utilities
   ---------------------------------------------------------- */

(function () {
  /**
   * Add inline markdown formatting to a text element
   * @param {HTMLElement} parent - Parent element
   * @param {string} text - Text with markdown
   */
  function addInlineMarkdown(parent, text) {
    // Split by markdown tokens using capturing group so tokens appear in result array.
    var parts = text.split(/(\*\*[^*\n]+\*\*|\*[^*\n]+\*|`[^`\n]+`)/);
    parts.forEach(function (part) {
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

  /**
   * Build message DOM from text
   * Renders plain or markdown-like agent text into DOM nodes without innerHTML.
   * @param {string} text - Text to render
   * @returns {DocumentFragment}
   */
  function buildMessageDom(text) {
    var frag = document.createDocumentFragment();
    if (!text) { return frag; }

    var paras = text.split(/\n{2,}/);
    paras.forEach(function (para) {
      para = para.trim();
      if (!para) { return; }

      var rawLines = para.split('\n');
      var isAllList = rawLines.every(function (l) { return /^[\-\*] /.test(l); });

      if (isAllList && rawLines.length > 0) {
        var ul = document.createElement('ul');
        rawLines.forEach(function (line) {
          var li = document.createElement('li');
          addInlineMarkdown(li, line.replace(/^[\-\*] /, ''));
          ul.appendChild(li);
        });
        frag.appendChild(ul);
        return;
      }

      var p = document.createElement('p');
      var lineIdx = 0;
      var rawLineLen = rawLines.length;
      rawLines.forEach(function (line, idx) {
        addInlineMarkdown(p, line);
        if (idx < rawLineLen - 1) { p.appendChild(document.createElement('br')); }
      });
      frag.appendChild(p);
    });
    return frag;
  }

  /**
   * Append message to chat log
   * @param {string} role - 'user' or 'agent'
   * @param {string} text - Message text
   * @param {object} presentation - Presentation data (optional)
   */
  function appendMessage(role, text, presentation) {
    var chatLog = document.getElementById('ai-chat-log');
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
      presWrapper.insertAdjacentHTML('beforeend', presHtml);
      wrap.appendChild(presWrapper);
    }

    chatLog.appendChild(wrap);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  /**
   * Render presentation block
   * @param {object} p - Presentation data
   * @returns {string} HTML
   */
  function renderPresentation(p) {
    if (!p) { return ''; }

    var html = '<div class="presentation-block">';

    if (p.type === 'table') {
      if (p.stats && p.stats.length) {
        html += '<div class="presentation-stats">';
        p.stats.forEach(function (stat) {
          html += '<div class="stat-item"><span class="stat-label">' + esc(stat.label) + '</span>';
          html += '<span class="stat-value">' + esc(stat.value) + '</span></div>';
        });
        html += '</div>';
      }
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
      if (p.token) {
        html += '<button class="approval-button" data-token="' + esc(p.token) + '">Approve Draft</button>';
      }
    }

    html += '</div>';
    return html;
  }

  /**
   * Escape HTML to prevent XSS
   * @param {string} v - Value to escape
   * @returns {string}
   */
  function esc(v) {
    if (v === null || v === undefined) { return ''; }
    var s = String(v);
    return s
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Export functions
  window.addInlineMarkdown = addInlineMarkdown;
  window.buildMessageDom = buildMessageDom;
  window.appendMessage = appendMessage;
  window.renderPresentation = renderPresentation;
})();
