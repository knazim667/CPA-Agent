/* ----------------------------------------------------------
   CSV/PDF export utilities
   ---------------------------------------------------------- */

(function () {
  /**
   * Convert data to CSV format
   * @param {Array} rows - Array of row arrays
   * @param {Array} headers - Column headers
   * @returns {string} CSV string
   */
  function toCSV(rows, headers) {
    var csv = '';

    // Add headers
    if (headers && headers.length) {
      csv += headers.map(escapeCsv).join(',');
      csv += '\n';
    }

    // Add rows
    if (rows && rows.length) {
      csv += rows.map(function (row) {
        return row.map(escapeCsv).join(',');
      }).join('\n');
    }

    return csv;
  }

  /**
   * Escape value for CSV
   * @param {string} value - Value to escape
   * @returns {string} Escaped value
   */
  function escapeCsv(value) {
    if (value === null || value === undefined) { return ''; }
    var str = String(value);
    // Escape quotes and wrap in quotes if contains comma or quote
    if (str.indexOf(',') !== -1 || str.indexOf('"') !== -1) {
      return '"' + str.replace(/"/g, '""') + '"';
    }
    return str;
  }

  /**
   * Download CSV file
   * @param {string} data - CSV data
   * @param {string} filename - Filename
   */
  function downloadCSV(data, filename) {
    var blob = new Blob([data], { type: 'text/csv;charset=utf-8;' });
    var url = URL.createObjectURL(blob);
    var link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  /**
   * Export ledger to CSV
   * @param {Array} rows - Ledger rows
   * @param {object} options - Export options
   */
  function exportLedgerCSV(rows, options) {
    var headers = options && options.includeHeaders ? ['Date', 'Type', 'Description', 'Category', 'Amount', 'Reference'] : [];
    var filename = options && options.filename || 'ledger.csv';
    var csv = toCSV(rows, headers);
    downloadCSV(csv, filename);
  }

  /**
   * Export P&L to CSV
   * @param {Array} income - Income rows
   * @param {Array} expenses - Expense rows
   * @param {number} incomeTotal - Total income
   * @param {number} expenseTotal - Total expenses
   * @param {string} period - Period (YYYY-MM-DD to YYYY-MM-DD)
   */
  function exportPnLCSV(income, expenses, incomeTotal, expenseTotal, period) {
    var headers = ['Date', 'Description', 'Category', 'Amount'];
    var allRows = [];

    // Add income rows
    income.forEach(function (row) {
      allRows.push([row.date, row.description, row.category, row.amount]);
    });

    // Add expenses
    expenses.forEach(function (row) {
      allRows.push([row.date, row.description, row.category, row.amount]);
    });

    // Calculate totals
    var totalIncome = income.reduce(function (sum, row) { return sum + (parseFloat(row.amount) || 0); }, 0);
    var totalExpenses = expenses.reduce(function (sum, row) { return sum + (parseFloat(row.amount) || 0); }, 0);
    var netProfit = totalIncome - totalExpenses;

    var csv = toCSV(allRows, headers);
    csv += '\n';
    csv += 'Total Income: ' + formatCurrency(totalIncome) + '\n';
    csv += 'Total Expenses: ' + formatCurrency(totalExpenses) + '\n';
    csv += 'Net Profit: ' + formatCurrency(netProfit);

    var filename = 'pl_' + period.replace(/-/g, '') + '.csv';
    downloadCSV(csv, filename);
  }

  /**
   * Format currency
   * @param {number} value - Value to format
   * @returns {string} Formatted currency
   */
  function formatCurrency(value) {
    var USD_FMT = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
    return USD_FMT.format(Number(value) || 0);
  }

  /**
   * Export to PDF (delegates to backend)
   * @param {string} endpoint - API endpoint
   * @param {object} params - Query parameters
   */
  function exportToPDF(endpoint, params) {
    // Redirect to backend PDF endpoint
    var url = endpoint + '?' + Object.entries(params)
      .map(function (e) { return encodeURIComponent(e[0]) + '=' + encodeURIComponent(e[1]); })
      .join('&');
    window.location.href = url;
  }

  /**
   * Batch export multiple formats
   * @param {object} data - Export data
   * @param {object} options - Options
   */
  function batchExport(data, options) {
    var requests = [];

    if (options.csv) {
      requests.push(toCSV(data.rows || []));
    }

    if (options.pdf) {
      requests.push(delegatedPDF(data.filename || 'export.pdf'));
    }

    return requests;
  }

  /**
   * Delegate PDF export to backend
   * @param {string} filename - PDF filename
   * @returns {string} URL for PDF
   */
  function delegatedPDF(filename) {
    return 'Fetching PDF from backend...';
  }

  // Export functions
  window.toCSV = toCSV;
  window.escapeCsv = escapeCsv;
  window.downloadCSV = downloadCSV;
  window.exportLedgerCSV = exportLedgerCSV;
  window.exportPnLCSV = exportPnLCSV;
  window.exportToPDF = exportToPDF;
  window.batchExport = batchExport;
})();
