/* ----------------------------------------------------------
   Tab router and navigation
   ---------------------------------------------------------- */

(function () {
  var TAB_LABELS = {
    'dashboard':     'Dashboard',
    'ledger':        'Ledger',
    'recurring':     'Recurring',
    'reports':       'P&L Report',
    'balance-sheet': 'Balance Sheet',
    'cash-flow':     'Cash Flow',
    'budget':        'Budget',
    'ar-ap':         'AR / AP',
    'reconcile':     'Reconcile',
    'tax':           'Tax',
    'documents':     'Documents'
  };

  /**
   * Update context chip with current tab name
   * @param {string} tab - Tab name
   */
  function updateContextChip(tab) {
    var chip = document.getElementById('ai-context-chip');
    var sectionEl = document.getElementById('top-bar-section');
    var label = TAB_LABELS[tab] || tab;
    var now = new Date();
    var month = now.toLocaleString('en-US', { month: 'short', year: 'numeric' });

    if (chip) { chip.textContent = '📈 Viewing: ' + label + ' · ' + month; }
    if (sectionEl) { sectionEl.textContent = label; }
  }

  /**
   * Switch to a specific tab
   * @param {string} tab - Tab name
   */
  function switchTab(tab) {
    var items = document.querySelectorAll('.sidebar-item');
    var tabContent = document.querySelectorAll('.tab-content');

    // Deactivate all
    items.forEach(function (item) {
      item.classList.remove('active');
    });
    tabContent.forEach(function (s) {
      s.classList.add('hidden');
    });

    // Activate selected
    var activeItem = document.querySelector('.sidebar-item[data-tab="' + tab + '"]');
    if (activeItem) {
      activeItem.classList.add('active');
      var section = document.getElementById('tab-' + tab);
      if (section) { section.classList.remove('hidden'); }
    }

    // Load data for tab
    if (tab === 'ledger') { fetchLedger(1); }
    if (tab === 'recurring') { fetchRecurring(); }
    if (tab === 'balance-sheet') { fetchBalanceSheet(); }
    if (tab === 'cash-flow') { fetchCashFlow(); }
    if (tab === 'budget') { fetchBudget(); }
    if (tab === 'dashboard') { fetchArAp(); }
    if (tab === 'ar-ap') { fetchArAp(); }
    if (tab === 'tax') { fetchTax(); }
    if (tab === 'users') { fetchUsers(); }
    if (tab === 'profile') { fetchProfileTab(); }

    // Update context chip
    updateContextChip(tab);
  }

  /**
   * Add event listeners to sidebar items
   * @param {NodeList} items - Sidebar items
   */
  function initSidebar(items) {
    items.forEach(function (item) {
      item.addEventListener('click', function () {
        switchTab(item.dataset.tab);
      });
    });

    // Activate dashboard by default
    var first = document.querySelector('.sidebar-item[data-tab="dashboard"]');
    if (first) { first.click(); }
  }

  /**
   * Initialize tab routing
   */
  function initRouter() {
    var sidebarItems = document.querySelectorAll('.sidebar-item');
    if (sidebarItems.length) {
      initSidebar(sidebarItems);
    }
  }

  // Export functions
  window.switchTab = switchTab;
  window.initRouter = initRouter;
  window.TAB_LABELS = TAB_LABELS;
})();
