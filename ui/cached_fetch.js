/* ----------------------------------------------------------
   Cached fetch for API responses
   ---------------------------------------------------------- */

(function () {
  var cache = new Map();
  var ttlCache = new Map();
  var ttlEntries = [];

  /**
   * Get cached response
   * @param {string} url - Request URL
   * @param {number} ttl - Time to live in ms (default: 5000)
   * @returns {object|null} Cached response or null
   */
  function getCached(url, ttl) {
    var entry = cache.get(url);
    if (!entry) { return null; }

    var elapsed = Date.now() - entry.timestamp;
    if (elapsed < ttl) {
      return entry.data;
    }

    // Expired entry
    cache.delete(url);
    return null;
  }

  /**
   * Set cached response with TTL
   * @param {string} url - Request URL
   * @param {object} data - Response data
   * @param {number} ttl - Time to live in ms (default: 5000)
   */
  function setCached(url, data, ttl) {
    cache.set(url, { data: data, timestamp: Date.now() });

    // Add to TTL cache for cleanup
    ttlEntries.push({ url: url, ttl: ttl });
  }

  /**
   * Fetch with caching
   * @param {string} url - Request URL
   * @param {object} init - Fetch init options
   * @returns {Promise<Response>}
   */
  function fetchCached(url, init) {
    // Try cache first
    var ttl = init && init.ttl;
    var cached = getCached(url, ttl);
    if (cached) {
      return Promise.resolve({
        ok: true,
        json: function() { return Promise.resolve(cached); },
        text: function() { return Promise.resolve(JSON.stringify(cached)); }
      });
    }

    // Fetch from server
    return fetch(url, init).then(function (response) {
      if (response.ok) {
        var data = response.json ? response.json() : response.text().then(function(t) { try { return JSON.parse(t); } catch(e) { return t; } });
        setCached(url, data, ttl || 5000);
      }
      return response;
    });
  }

  /**
   * Cleanup expired TTL entries
   */
  function cleanupTTL() {
    ttlEntries.sort(function(a, b) {
      var aExp = Date.now() - a.ttl;
      var bExp = Date.now() - b.ttl;
      return aExp - bExp;
    });

    var cleaned = false;
    ttlEntries.forEach(function(entry) {
      if (Date.now() > entry.ttl) {
        cache.delete(entry.url);
        ttlEntries = ttlEntries.filter(function(e) { return e.url !== entry.url; });
        cleaned = true;
      }
    });

    if (cleaned) {
      cleanupTTL();
    }
  }

  /**
   * Cleanup every 30 seconds
   */
  setInterval(cleanupTTL, 30000);

  // Export functions
  window.fetchCached = fetchCached;
  window.getCached = getCached;
  window.setCached = setCached;

})();
