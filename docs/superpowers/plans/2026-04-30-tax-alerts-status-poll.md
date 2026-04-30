# Tax Alerts in Status Poll — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface `tax_alerts` from the existing `/api/status` poll in a persistent Dashboard card and urgency toasts, with per-session deduplication.

**Architecture:** Frontend-only. `get_status()` already returns `tax_alerts`; the gap is that `updateStatus()` in `app.js` never reads that field. We add a `#tax-alerts-dashboard` mount point in `index.html`, a `renderTaxAlerts()` function that mirrors `renderRecentTransactions()` / `renderRecentAudits()`, and one wiring call in `updateStatus()`. All DOM manipulation uses `createElement` + `textContent` + `appendChild` — no `innerHTML` — to avoid XSS.

**Tech Stack:** Vanilla JS (ES5), HTML5 — no build step, no framework.

**Spec:** `docs/superpowers/specs/2026-04-30-tax-alerts-status-poll-design.md`

---

## File Map

| File | Change |
|---|---|
| `ui/index.html` | Add `#tax-alerts-dashboard` div after the `recent-grid` section (after line 319) |
| `ui/app.js` | Add `seenAlertDeadlines` Set to state (after line 57); add `renderTaxAlerts()` function (after `renderRecentAudits`); add one call in `updateStatus()` (after line 810) |

---

## Task 1: Add the `#tax-alerts-dashboard` mount point to `index.html`

**Files:**
- Modify: `ui/index.html:319`

- [ ] **Step 1: Insert the Tax Alerts card HTML**

In `ui/index.html`, after the closing `</div>` of the `recent-grid` section (line 319, before the `</section>` that closes `tab-dashboard`), insert:

```html
          <!-- Tax Alerts card (populated by renderTaxAlerts in app.js) -->
          <div id="tax-alerts-dashboard" class="hidden" style="margin-top:1.5rem;">
            <h3 style="margin:0 0 0.75rem 0;font-size:0.9rem;font-weight:600;color:#374151;">Upcoming Tax Deadlines</h3>
            <div class="tax-alerts-list"></div>
          </div>
```

The result around that area should look like:

```html
          <div class="recent-grid">
            <div class="recent-section">
              <h3>Recent Transactions</h3>
              <div id="recent-transactions"></div>
            </div>
            <div class="recent-section">
              <h3>Recent Audits</h3>
              <div id="recent-audits"></div>
            </div>
          </div>

          <!-- Tax Alerts card (populated by renderTaxAlerts in app.js) -->
          <div id="tax-alerts-dashboard" class="hidden" style="margin-top:1.5rem;">
            <h3 style="margin:0 0 0.75rem 0;font-size:0.9rem;font-weight:600;color:#374151;">Upcoming Tax Deadlines</h3>
            <div class="tax-alerts-list"></div>
          </div>

        </section>
```

- [ ] **Step 2: Verify the HTML is valid**

Open the page in a browser (`python3 -m http.server 9001` from the repo root, visit `http://localhost:9001/ui/`). The Dashboard tab renders without console errors. The Tax Alerts section is not yet visible — the `hidden` class suppresses it until JS populates it.

- [ ] **Step 3: Commit**

```bash
git add ui/index.html
git commit -m "feat: add tax-alerts-dashboard mount point to dashboard tab"
```

---

## Task 2: Add `seenAlertDeadlines` to the state section in `app.js`

**Files:**
- Modify: `ui/app.js:57`

- [ ] **Step 1: Add the deduplication Set**

In `ui/app.js`, in the state section (section 3, around line 57), add one line after `var latestPresentation = null;`:

```js
var seenAlertDeadlines = new Set();
```

The state block should now look like:

```js
var currentLedgerPage = 1;
var speakReplies = false;
var recognition = null;
var isListening = false;
var latestPresentation = null;
var seenAlertDeadlines = new Set();
```

- [ ] **Step 2: Verify no JS errors**

Reload the page. Open DevTools → Console. No errors on load.

- [ ] **Step 3: Commit**

```bash
git add ui/app.js
git commit -m "feat: add seenAlertDeadlines session Set for toast deduplication"
```

---

## Task 3: Write the `renderTaxAlerts()` function

**Files:**
- Modify: `ui/app.js` — add function after `renderRecentAudits` (after line 877)

- [ ] **Step 1: Add the function**

In `ui/app.js`, after the closing `}` of `renderRecentAudits` (around line 877), insert:

```js
/* ----------------------------------------------------------
   Tax Alerts (populated from status poll tax_alerts field)
   ---------------------------------------------------------- */

function renderTaxAlerts(alerts) {
  var container = document.getElementById('tax-alerts-dashboard');
  if (!container) { return; }

  if (!alerts || !alerts.length) {
    container.classList.add('hidden');
    return;
  }

  container.classList.remove('hidden');
  var list = container.querySelector('.tax-alerts-list');
  if (!list) { return; }
  list.textContent = '';

  alerts.forEach(function (alert) {
    var daysUntil = alert.days_until;
    var badgeColor = daysUntil <= 7 ? '#dc2626' : daysUntil <= 14 ? '#f59e0b' : '#6b7280';

    var item = document.createElement('div');
    item.style.cssText = 'display:flex;justify-content:space-between;align-items:center;' +
      'padding:0.5rem 0;border-bottom:1px solid #e5e7eb;';

    // Left column: quarter label, description, deadline date
    var left = document.createElement('div');
    var strong = document.createElement('strong');
    strong.textContent = alert.quarter || '';
    var descText = document.createTextNode(': ' + (alert.description || ''));
    var br = document.createElement('br');
    var dateSpan = document.createElement('span');
    dateSpan.style.cssText = 'font-size:0.75rem;color:#6b7280;';
    dateSpan.textContent = alert.deadline || '';
    left.appendChild(strong);
    left.appendChild(descText);
    left.appendChild(br);
    left.appendChild(dateSpan);

    // Right column: days-remaining badge
    var badge = document.createElement('span');
    badge.style.cssText = 'background:' + badgeColor + ';color:#fff;padding:0.2rem 0.5rem;' +
      'border-radius:4px;font-size:0.7rem;font-weight:600;white-space:nowrap;';
    badge.textContent = 'Due in ' + daysUntil + ' days';

    item.appendChild(left);
    item.appendChild(badge);
    list.appendChild(item);

    // Toast for high-urgency alerts (<=7 days), once per session per deadline
    if (daysUntil <= 7 && !seenAlertDeadlines.has(alert.deadline)) {
      showToast(
        'Tax alert: ' + (alert.description || '') + ' due in ' + daysUntil +
          ' days (' + (alert.deadline || '') + ')',
        'warning'
      );
      seenAlertDeadlines.add(alert.deadline);
    }
  });
}
```

- [ ] **Step 2: Manually verify the function in the browser DevTools console**

With the page open on the Dashboard tab, paste each call into DevTools Console and observe the card below "Recent Audits":

```js
// Card should disappear / stay hidden
renderTaxAlerts([]);

// Card shows, grey badge, no toast (46 days away)
renderTaxAlerts([{quarter:'Q3', description:'Q3 Estimated Tax Payment', deadline:'2026-09-15', days_until:46}]);

// Card shows, amber badge, no toast (12 days away)
renderTaxAlerts([{quarter:'Q2', description:'Q2 Estimated Tax Payment', deadline:'2026-06-15', days_until:12}]);

// Card shows, red badge + warning toast fires once
renderTaxAlerts([{quarter:'Q2', description:'Q2 Estimated Tax Payment', deadline:'2026-06-15', days_until:5}]);

// Same deadline again — toast must NOT fire a second time
renderTaxAlerts([{quarter:'Q2', description:'Q2 Estimated Tax Payment', deadline:'2026-06-15', days_until:5}]);
```

After the last call, run in console:
```js
seenAlertDeadlines.has('2026-06-15')  // must be true
```

- [ ] **Step 3: Commit**

```bash
git add ui/app.js
git commit -m "feat: add renderTaxAlerts function with dashboard card and deduped toasts"
```

---

## Task 4: Wire `renderTaxAlerts()` into `updateStatus()`

**Files:**
- Modify: `ui/app.js:810`

- [ ] **Step 1: Add the wiring call**

In `ui/app.js`, inside `updateStatus()`, after the line `renderRecentAudits(dash.recent_audits || []);` (line 810), add:

```js
  renderTaxAlerts(status.tax_alerts || []);
```

The surrounding block should now look like:

```js
  // Recent lists
  renderRecentTransactions(dash.recent_transactions || []);
  renderRecentAudits(dash.recent_audits || []);
  renderTaxAlerts(status.tax_alerts || []);

  // Conversation
  if (status.conversation) {
```

- [ ] **Step 2: Verify end-to-end with the live server**

Start the web app:

```bash
cd /Users/muhammadnazam/Documents/CPA-Agent
source .venv/bin/activate
uvicorn web_app:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000`. Navigate to the Dashboard tab. Verify:

1. Open DevTools → Network, filter for `status`. Confirm the response JSON includes a `tax_alerts` array.
2. If any deadline is within 30 days, the "Upcoming Tax Deadlines" card is visible with correct badge colours.
3. Wait 6 seconds for the next poll — the card refreshes but no duplicate toasts fire.
4. If no deadlines are within 30 days, the card remains hidden.

- [ ] **Step 3: Verify missing `tax_alerts` field does not crash**

In DevTools Console, call:

```js
updateStatus({});
```

Expected: no JS exception thrown. The tax alerts card stays in its current state.

- [ ] **Step 4: Commit**

```bash
git add ui/app.js
git commit -m "feat: wire renderTaxAlerts into updateStatus status poll"
```

---

## Task 5: Final verification

- [ ] **Step 1: Run the backend test suite**

```bash
cd /Users/muhammadnazam/Documents/CPA-Agent
source .venv/bin/activate
pytest tests/ -v
```

Expected: all tests pass. (No new tests needed — JS verified manually; `TaxEngine.get_upcoming_alerts()` already covered by `tests/test_tax_engine.py`.)

- [ ] **Step 2: Confirm git log**

```bash
git log --oneline -5
```

Expected (newest first):

```
<hash> feat: wire renderTaxAlerts into updateStatus status poll
<hash> feat: add renderTaxAlerts function with dashboard card and deduped toasts
<hash> feat: add seenAlertDeadlines session Set for toast deduplication
<hash> feat: add tax-alerts-dashboard mount point to dashboard tab
<hash> docs: add tax alerts status poll design spec
```
