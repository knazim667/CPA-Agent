/* ----------------------------------------------------------
   Presentation block rendering
   ---------------------------------------------------------- */

(function () {
  /**
   * Render presentation block from data
   * @param {object} p - Presentation data with type, stats, headers, rows, token
   * @returns {string} HTML for presentation block
   */
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
        html += '<button class="approval-button" data-token="' + esc(p.token) + '">Approve Draft</button>';
      }
    }

    html += '</div>';
    return html;
  }

  /**
   * Escape HTML to prevent XSS
   * @param {string} v - Value to escape
   * @returns {string} Escaped value
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

  /**
   * Format USD currency
   * @param {number} v - Value to format
   * @returns {string} Formatted USD value
   */
  function fmt(v) {
    var USD_FMT = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
    return USD_FMT.format(Number(v) || 0);
  }

  /**
   * Format signed USD currency
   * @param {number} v - Value to format
   * @returns {string} Formatted signed USD value
   */
  function fmtSigned(v) {
    var USD_FMT = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
    var n = Number(v || 0);
    return (n >= 0 ? '+' : '-') + USD_FMT.format(Math.abs(n));
  }

  // Export functions
  window.renderPresentation = renderPresentation;
  window.speakReply = speakReply; // Will be defined in voice.js
})();
