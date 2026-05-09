/* ----------------------------------------------------------
   Debounce utilities
   ---------------------------------------------------------- */

(function () {
  /**
   * Create a debounced function
   * @param {function} fn - Function to debounce
   * @param {number} wait - Delay in ms
   * @returns {function}
   */
  function debounce(fn, wait) {
    var timeout;
    return function () {
      var args = arguments;
      var context = this;
      clearTimeout(timeout);
      timeout = setTimeout(function () {
        fn.apply(context, args);
      }, wait);
    };
  }

  /**
   * Throttle function
   * @param {function} fn - Function to throttle
   * @param {number} limit - Minimum time between calls in ms
   * @returns {function}
   */
  function throttle(fn, limit) {
    var lastCall;
    var now;
    var timeout;
    return function () {
      var args = arguments;
      var context = this;
      now = Date.now();

      if (!lastCall || now - lastCall >= limit) {
        fn.apply(context, args);
        lastCall = now;
      } else {
        timeout = setTimeout(function () {
          fn.apply(context, args);
          lastCall = Date.now();
        }, limit - (now - lastCall));
      }
    };
  }

  /**
   * Debounced version of fetchLedger with 300ms delay
   * @param {string} url - Ledger API URL
   * @param {string} page - Page number
   */
  window.debounceLedgerSearch = debounce(function (url, page) {
    fetch(url + '&page=' + page)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        // Update ledger display
        document.getElementById('ledger-body').innerHTML = renderLedgerRows(data.rows || []);
        document.getElementById('ledger-page-info').textContent =
          'Page ' + page + ' of ' + Math.ceil((data.total || 0) / 20);
      })
      .catch(function (err) { console.error('Ledger search error:', err); });
  }, 300);

  /**
   * Debounced version of fetchBudget with 1s delay
   * @param {string} month - Month in YYYY-MM format
   */
  window.debounceBudgetFetch = debounce(function (month) {
    fetch('/api/budget?month=' + encodeURIComponent(month))
      .then(function (r) { return r.json(); })
      .then(function (data) { renderBudget(data); })
      .catch(function (err) { console.error('Budget error:', err); });
  }, 1000);

  /**
   * Debounced version of fetchTax with 500ms delay
   * @param {string} year - Tax year
   */
  window.debounceTaxFetch = debounce(function (year) {
    fetch('/api/tax?year=' + year)
      .then(function (r) { return r.json(); })
      .then(function (data) { renderTax(data); })
      .catch(function (err) { console.error('Tax error:', err); });
  }, 500);

})();
