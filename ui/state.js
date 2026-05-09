/* ----------------------------------------------------------
   Application state management
   ---------------------------------------------------------- */

(function () {
  /**
   * Application state
   */
  var state = {
    currentLedgerPage: 1,
    speakReplies: false,
    recognition: null,
    isListening: false,
    latestPresentation: null,
    seenAlertDeadlines: new Set(),
    MAX_SEEN_ALERTS: 50,
    currentUserRole: null,
    wizardStep: 1,
    wizardTotalSteps: 5,
    wizardBizKey: null,
    onboardingWizardShown: false
  };

  /**
   * Get current state
   * @returns {object}
   */
  function getState() {
    return state;
  }

  /**
   * Set state value
   * @param {string} key - State key
   * @param {*} value - Value to set
   */
  function setState(key, value) {
    state[key] = value;
  }

  /**
   * Get current ledger page
   * @returns {number}
   */
  function getCurrentLedgerPage() {
    return state.currentLedgerPage;
  }

  /**
   * Set current ledger page
   * @param {number} page - Page number
   */
  function setCurrentLedgerPage(page) {
    state.currentLedgerPage = page;
  }

  /**
   * Toggle speech replies
   * @returns {boolean}
   */
  function toggleSpeakReplies() {
    state.speakReplies = !state.speakReplies;
    return state.speakReplies;
  }

  /**
   * Get latest presentation
   * @returns {object|null}
   */
  function getLatestPresentation() {
    return state.latestPresentation;
  }

  /**
   * Set latest presentation
   * @param {object} presentation - Presentation object
   */
  function setLatestPresentation(presentation) {
    state.latestPresentation = presentation;
  }

  /**
   * Track seen alert deadlines
   * @param {string} deadline - Alert deadline
   * @returns {boolean} Whether this was a new alert
   */
  function trackSeenAlert(deadline) {
    if (!state.seenAlertDeadlines.has(deadline)) {
      state.seenAlertDeadlines.add(deadline);
      if (state.seenAlertDeadlines.size > state.MAX_SEEN_ALERTS) {
        state.seenAlertDeadlines.clear();
      }
      return true;
    }
    return false;
  }

  /**
   * Check if alert has been seen
   * @param {string} deadline - Alert deadline
   * @returns {boolean}
   */
  function hasSeenAlert(deadline) {
    return state.seenAlertDeadlines.has(deadline);
  }

  /**
   * Get current wizard step
   * @returns {number}
   */
  function getWizardStep() {
    return state.wizardStep;
  }

  /**
   * Set wizard step
   * @param {number} step - Step number
   */
  function setWizardStep(step) {
    state.wizardStep = step;
  }

  /**
   * Get current business key
   * @returns {string|null}
   */
  function getWizardBizKey() {
    return state.wizardBizKey;
  }

  /**
   * Set current business key
   * @param {string} bizKey - Business key
   */
  function setWizardBizKey(bizKey) {
    state.wizardBizKey = bizKey;
  }

  /**
   * Check if onboarding wizard has been shown
   * @returns {boolean}
   */
  function isOnboardingWizardShown() {
    return state.onboardingWizardShown;
  }

  /**
   * Mark onboarding wizard as shown
   */
  function markOnboardingWizardShown() {
    state.onboardingWizardShown = true;
  }

  /**
   * Get current user role
   * @returns {string|null}
   */
  function getCurrentUserRole() {
    return state.currentUserRole;
  }

  /**
   * Set current user role
   * @param {string} role - User role
   */
  function setCurrentUserRole(role) {
    state.currentUserRole = role;
  }

  /**
   * Get voice recognition instance
   * @returns {SpeechRecognition|null}
   */
  function getRecognition() {
    return state.recognition;
  }

  /**
   * Set voice recognition instance
   * @param {SpeechRecognition|null} rec - Recognition instance
   */
  function setRecognition(rec) {
    state.recognition = rec;
  }

  /**
   * Check if voice is listening
   * @returns {boolean}
   */
  function isListening() {
    return state.isListening;
  }

  /**
   * Set listening state
   * @param {boolean} listening - Whether listening
   */
  function setListening(listening) {
    state.isListening = listening;
  }

  // Export state functions
  window.getState = getState;
  window.setState = setState;
  window.getCurrentLedgerPage = getCurrentLedgerPage;
  window.setCurrentLedgerPage = setCurrentLedgerPage;
  window.toggleSpeakReplies = toggleSpeakReplies;
  window.getLatestPresentation = getLatestPresentation;
  window.setLatestPresentation = setLatestPresentation;
  window.trackSeenAlert = trackSeenAlert;
  window.hasSeenAlert = hasSeenAlert;
  window.getWizardStep = getWizardStep;
  window.setWizardStep = setWizardStep;
  window.getWizardBizKey = getWizardBizKey;
  window.setWizardBizKey = setWizardBizKey;
  window.isOnboardingWizardShown = isOnboardingWizardShown;
  window.markOnboardingWizardShown = markOnboardingWizardShown;
  window.getCurrentUserRole = getCurrentUserRole;
  window.setCurrentUserRole = setCurrentUserRole;
  window.getRecognition = getRecognition;
  window.setRecognition = setRecognition;
  window.isListening = isListening;
  window.setListening = setListening;
})();
