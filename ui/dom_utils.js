/* CPA-Agent — DOM utility functions: toast, escapeHtml, renderContent */
'use strict';

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

function escapeHtml(v) {
  if (v === null || v === undefined) { return ''; }
  var s = String(v);
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

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
