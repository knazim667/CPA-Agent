# Tax Alerts in Status Poll — Design Spec

**Date:** 2026-04-30
**Status:** Approved

---

## Problem

`get_status()` in `main.py` already returns a `tax_alerts` field (populated by `TaxEngine.get_upcoming_alerts()`). The UI polls `/api/status` every 5 seconds via `setInterval(fetchStatus, 5000)`. However, `updateStatus()` in `ui/app.js` never reads `status.tax_alerts`, so upcoming IRS deadlines are silently discarded on every poll.

---

## Goal

Surface tax alerts from the status poll in two ways:
1. A **persistent dashboard card** that refreshes on every poll — visible whenever the user looks at the Dashboard tab.
2. A **toast notification** for high-urgency alerts (≤ 7 days), deduplicated so each deadline only toasts once per page session.

---

## Scope

Frontend only. No backend changes required.

Files changed:
- `ui/index.html` — add `#tax-alerts-dashboard` mount point
- `ui/app.js` — add state, `renderTaxAlerts()` function, and one wiring line in `updateStatus()`

---

## Architecture

### Data flow

```
setInterval(fetchStatus, 5000)
  → GET /api/status
  → updateStatus(data)
  → renderTaxAlerts(data.tax_alerts || [])
      → re-render #tax-alerts-dashboard card
      → for each alert where days_until ≤ 7 and deadline ∉ seenAlertDeadlines:
            showToast(…, 'warning')
            seenAlertDeadlines.add(deadline)
```

### Components

| Component | Location | Purpose |
|---|---|---|
| `seenAlertDeadlines` | `app.js` state section (§3) | `Set<string>` — tracks deadlines that have already triggered a toast this session |
| `#tax-alerts-dashboard` | `index.html` Dashboard tab | Mount point for the alerts card; hidden when alerts array is empty |
| `renderTaxAlerts(alerts)` | `app.js` | Renders card rows + conditional toasts |
| `updateStatus()` call site | `app.js` | One new line: `renderTaxAlerts(status.tax_alerts \|\| [])` |

---

## UI Details

### Dashboard card

- Positioned below the recent audits section in the Dashboard tab
- Hidden via `classList.add('hidden')` when `alerts` is empty (consistent with all other UI panels)
- Each row shows: quarter label, description, deadline date, days-remaining badge
- Badge color coding (consistent with the Tax tab's existing `renderTax()` function):
  - **Red** — `days_until <= 7`
  - **Amber** — `days_until 8–14`
  - **Grey** — `days_until > 14`

### Toast

- Type: `'warning'` (yellow)
- Message format: `"Tax alert: {description} due in {days_until} days ({deadline})"`
- Fires only when `days_until <= 7`
- Deduplication: deadline string added to `seenAlertDeadlines` after first toast; subsequent polls skip it

---

## Edge Cases

| Scenario | Behavior |
|---|---|
| `status.tax_alerts` missing (old API) | `status.tax_alerts \|\| []` → card hidden, no crash |
| No alerts returned | Card hidden entirely |
| Same alert on next poll | Toast already in `seenAlertDeadlines` → skipped |
| Alert moves from >7 to ≤7 days mid-session | Toast fires on the first poll where `days_until` crosses the threshold, then deduplicated |
| Page refresh | `seenAlertDeadlines` is cleared (session-scoped `Set`) |

---

## Testing

No new test files. Manual verification covers:

1. `renderTaxAlerts([])` → card hidden
2. `renderTaxAlerts([{days_until: 12, ...}])` → card visible, amber badge, no toast
3. `renderTaxAlerts([{days_until: 5, ...}])` → card visible, red badge, warning toast fires
4. Second call with same `days_until ≤ 7` alert → toast does not fire again
5. `status.tax_alerts` absent from payload → no JS error, card stays hidden

Backend coverage for `TaxEngine.get_upcoming_alerts()` already exists in `tests/test_tax_engine.py`.

---

## Out of Scope

- Backend changes
- New API endpoints
- Persistent alert dismissal across sessions
- Push notifications
