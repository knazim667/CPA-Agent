/* ----------------------------------------------------------
   Voice recognition and synthesis
   ---------------------------------------------------------- */

(function () {
  var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  /**
   * Configure voice functionality
   */
  function configureVoice() {
    var speechRecognition = null;
    var speakReplies = false;
    var recognition = null;
    var isListening = false;

    var voiceButton = document.getElementById('ai-voice-btn');
    var voiceStatus = document.getElementById('ai-voice-status');
    var speakToggle = document.getElementById('ai-speak-toggle');

    /**
     * Speak toggle handler
     */
    if (speakToggle) {
      speakToggle.addEventListener('click', function () {
        speakReplies = !speakReplies;
        speakToggle.style.background = speakReplies ? '#1d4ed8' : '';
        speakToggle.style.color = speakReplies ? '#fff' : '';
        speakToggle.textContent = speakReplies ? 'Voice Replies On' : 'Voice Replies Off';
      });
    }

    /**
     * Voice idle state
     */
    if (voiceStatus) { voiceStatus.textContent = 'Browser voice idle'; }

    /**
     * Check if SpeechRecognition is available
     */
    if (!SpeechRecognition) {
      if (voiceButton) { voiceButton.disabled = true; voiceButton.textContent = 'Voice N/A'; }
      if (voiceStatus) { voiceStatus.textContent = 'Speech recognition not supported'; }
      return;
    }

    /**
     * Initialize SpeechRecognition
     */
    speechRecognition = new SpeechRecognition();
    speechRecognition.continuous = false;
    speechRecognition.interimResults = false;
    speechRecognition.lang = 'en-US';

    /**
     * On result
     */
    speechRecognition.onresult = function (event) {
      var transcript = event.results[0][0].transcript;
      var messageInput = document.getElementById('ai-message-input');
      if (messageInput) { messageInput.value += transcript; }
      if (voiceStatus) { voiceStatus.textContent = 'Heard: ' + transcript; }
    };

    /**
     * On error
     */
    speechRecognition.onerror = function (event) {
      isListening = false;
      if (voiceButton) { voiceButton.textContent = 'Start Voice'; }
      if (voiceStatus) { voiceStatus.textContent = 'Voice error: ' + event.error; }
    };

    /**
     * On end
     */
    speechRecognition.onend = function () {
      isListening = false;
      if (voiceButton) { voiceButton.textContent = 'Start Voice'; }
      if (voiceStatus) { voiceStatus.textContent = 'Voice done'; }
    };

    /**
     * Voice button click handler
     */
    if (voiceButton) {
      voiceButton.addEventListener('click', function () {
        if (isListening) {
          speechRecognition.stop();
          isListening = false;
          voiceButton.textContent = 'Start Voice';
          if (voiceStatus) { voiceStatus.textContent = 'Voice stopped'; }
        } else {
          speechRecognition.start();
          isListening = true;
          voiceButton.textContent = 'Stop Voice';
          if (voiceStatus) { voiceStatus.textContent = 'Listening…'; }
        }
      });
    }

    /**
     * Voice reply handler
     * @param {string} message - Text to speak
     */
    window.speakReply = function (message) {
      if (!speakReplies) { return; }
      if (!window.speechSynthesis) { return; }

      var utterance = new SpeechSynthesisUtterance(message);
      // Try to find a natural-sounding voice
      var voices = window.speechSynthesis.getVoices();
      if (voices.length > 0) {
        utterance.voice = voices.find(function (v) { return v.name.includes('Google') || v.name.includes('Samantha'); }) || voices[0];
      }
      utterance.rate = 1;
      utterance.pitch = 1;
      window.speechSynthesis.speak(utterance);
    };
  }

  /**
   * Initialize voice functionality on DOMContentLoaded
   */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', configureVoice);
  } else {
    configureVoice();
  }
})();
