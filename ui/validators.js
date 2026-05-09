/* ----------------------------------------------------------
   Form validation utilities
   ---------------------------------------------------------- */

(function () {
  /**
   * Validate email address
   * @param {string} email - Email to validate
   * @returns {boolean}
   */
  function validateEmail(email) {
    if (!email) { return false; }
    var emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  }

  /**
   * Validate required field
   * @param {string} value - Value to validate
   * @returns {boolean}
   */
  function validateRequired(value) {
    if (!value || value.trim() === '') { return false; }
    return true;
  }

  /**
   * Validate positive number
   * @param {number} value - Value to validate
   * @returns {boolean}
   */
  function validatePositiveNumber(value) {
    var num = parseFloat(value);
    return !isNaN(num) && num > 0;
  }

  /**
   * Validate date field
   * @param {string} dateStr - Date string (YYYY-MM-DD)
   * @param {string} minDate - Minimum date
   * @param {string} maxDate - Maximum date
   * @returns {object} { valid: boolean, error: string }
   */
  function validateDate(dateStr, minDate, maxDate) {
    var error = '';

    if (!dateStr) {
      error = 'Date is required';
      return { valid: false, error: error };
    }

    if (minDate && new Date(dateStr) < new Date(minDate)) {
      error = 'Date must be at least ' + minDate;
      return { valid: false, error: error };
    }

    if (maxDate && new Date(dateStr) > new Date(maxDate)) {
      error = 'Date must be no later than ' + maxDate;
      return { valid: false, error: error };
    }

    return { valid: true, error: '' };
  }

  /**
   * Validate transaction form
   * @param {object} formData - Form data
   * @returns {object} { valid: boolean, errors: object }
   */
  function validateTransactionForm(formData) {
    var errors = {};

    // Date
    var dateValidation = validateDate(formData.date);
    if (!dateValidation.valid) {
      errors.date = dateValidation.error;
    }

    // Amount
    if (!validatePositiveNumber(formData.amount)) {
      errors.amount = 'Amount must be a positive number';
    }

    // Description
    if (!validateRequired(formData.description)) {
      errors.description = 'Description is required';
    }

    // Reference (optional but must be valid if provided)
    if (formData.reference && !validateRequired(formData.reference)) {
      errors.reference = 'Reference is required if provided';
    }

    return {
      valid: Object.keys(errors).length === 0,
      errors: errors
    };
  }

  /**
   * Validate user form
   * @param {object} formData - Form data
   * @returns {object} { valid: boolean, errors: object }
   */
  function validateUserForm(formData) {
    var errors = {};

    // Username
    if (!validateRequired(formData.username)) {
      errors.username = 'Username is required';
    } else if (formData.username.length < 3) {
      errors.username = 'Username must be at least 3 characters';
    }

    // Email
    if (!validateEmail(formData.email)) {
      errors.email = 'Invalid email address';
    }

    // Password (only for new users)
    if (!formData.username) { // Only validate if creating new user
      if (!validateRequired(formData.password)) {
        errors.password = 'Password is required';
      } else if (formData.password.length < 8) {
        errors.password = 'Password must be at least 8 characters';
      }
    }

    return {
      valid: Object.keys(errors).length === 0,
      errors: errors
    };
  }

  /**
   * Validate budget form
   * @param {object} formData - Form data
   * @returns {object} { valid: boolean, errors: object }
   */
  function validateBudgetForm(formData) {
    var errors = {};

    // Category
    if (!validateRequired(formData.category)) {
      errors.category = 'Category is required';
    }

    // Amount
    if (!validatePositiveNumber(formData.amount)) {
      errors.amount = 'Amount must be a positive number';
    }

    return {
      valid: Object.keys(errors).length === 0,
      errors: errors
    };
  }

  // Export validators
  window.validateEmail = validateEmail;
  window.validateRequired = validateRequired;
  window.validatePositiveNumber = validatePositiveNumber;
  window.validateDate = validateDate;
  window.validateTransactionForm = validateTransactionForm;
  window.validateUserForm = validateUserForm;
  window.validateBudgetForm = validateBudgetForm;
})();
