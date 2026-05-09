/* ----------------------------------------------------------
   Ledger rendering with pagination
   ---------------------------------------------------------- */

'use strict';

(function () {
  var currentLedgerPage = 1;
  var PAGE_SIZE = 20;

  /* ----------------------------------------------------------
     Ledger fetch with caching
     ---------------------------------------------------------- */

  function fetchLedger(page) {
    currentLedgerPage = page || 1;
    var search = (document.getElementById('ledger-search') || {}).value || '';
    var from = (document.getElementById('ledger-from') || {}).value || '';
    var to = (document.getElementById('ledger-to') || {}).value || '';

    // Use cached fetch if available
    var url = '/api/ledger?page=' + currentLedgerPage +
      '&page_size=' + PAGE_SIZE +
      '&search=' + encodeURIComponent(search) +
      '&from_date=' + encodeURIComponent(from) +
      '&to_date=' + encodeURIComponent(to);

    fetchCached(url)
      .then(function (data) {
        renderLedger(data);
      })
      .catch(function (err) {
        showToast('Ledger error: ' + err, 'error');
      });
  }

  /* ----------------------------------------------------------
     Render ledger rows
     ---------------------------------------------------------- */

  function renderLedger(data) {
    var ledgerBody = document.getElementById('ledger-body');
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
        (row.amount !== undefined) ? formatCurrency(row.amount) : (row[4] || ''),
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
    var totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    var ledgerPageInfo = document.getElementById('ledger-page-info');
    var ledgerPrev = document.getElementById('ledger-prev');
    var ledgerNext = document.getElementById('ledger-next');

    if (ledgerPageInfo) {
      ledgerPageInfo.textContent = 'Page ' + currentLedgerPage + ' of ' + totalPages;
    }
    if (ledgerPrev) { ledgerPrev.disabled = currentLedgerPage <= 1; }
    if (ledgerNext) { ledgerNext.disabled = currentLedgerPage >= totalPages; }
  }

  /* ----------------------------------------------------------
     Render category cell with editable badge
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
        // Save category rule to backend
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
     Format currency
     ---------------------------------------------------------- */

  function formatCurrency(value) {
    var USD_FMT = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
    return USD_FMT.format(Number(value) || 0);
  }

  /* ----------------------------------------------------------
     Initialize ledger controls
     ---------------------------------------------------------- */

  function initLedger() {
    var ledgerPrev = document.getElementById('ledger-prev');
    var ledgerNext = document.getElementById('ledger-next');
    var filterBtn = document.getElementById('ledger-filter-btn');

    if (ledgerPrev) {
      ledgerPrev.addEventListener('click', function () {
        fetchLedger(currentLedgerPage - 1);
      });
    }
    if (ledgerNext) {
      ledgerNext.addEventListener('click', function () {
        fetchLedger(currentLedgerPage + 1);
      });
    }
    if (filterBtn) {
      filterBtn.addEventListener('click', function () {
        fetchLedger(1);
      });
    }
  }

  // Export functions
  window.fetchLedger = fetchLedger;
  window.renderLedger = renderLedger;
  window.renderCategoryCell = renderCategoryCell;
  window.formatCurrency = formatCurrency;
  window.initLedger = initLedger;
})();
