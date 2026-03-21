const chatLog = document.getElementById("chat-log");
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const businessSelect = document.getElementById("business-select");
const switchBusinessButton = document.getElementById("switch-business-button");
const modelModeSelect = document.getElementById("model-mode-select");
const switchModelButton = document.getElementById("switch-model-button");
const modelStatus = document.getElementById("model-status");
const workspaceStatus = document.getElementById("workspace-status");
const bootWarning = document.getElementById("boot-warning");
const sheetLink = document.getElementById("sheet-link");
const docLink = document.getElementById("doc-link");
const voiceButton = document.getElementById("voice-button");
const voiceStatus = document.getElementById("voice-status");
const speakToggle = document.getElementById("speak-toggle");
const metricTransactions = document.getElementById("metric-transactions");
const metricIncome = document.getElementById("metric-income");
const metricExpenses = document.getElementById("metric-expenses");
const metricFlagged = document.getElementById("metric-flagged");
const recentTransactions = document.getElementById("recent-transactions");
const transactionForm = document.getElementById("transaction-form");
const transactionStatus = document.getElementById("transaction-status");
const transactionSubmit = document.getElementById("transaction-submit");
const recentAudits = document.getElementById("recent-audits");
const txDate = document.getElementById("tx-date");
const txType = document.getElementById("tx-type");
const txDescription = document.getElementById("tx-description");
const txCategory = document.getElementById("tx-category");
const txAmount = document.getElementById("tx-amount");
const txReference = document.getElementById("tx-reference");
const txNotes = document.getElementById("tx-notes");

let speakReplies = true;
let recognition = null;
let isListening = false;

txDate.value = new Date().toISOString().slice(0, 10);

function escapeHtml(value) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function businessSheetUrl(spreadsheetId) {
  return spreadsheetId ? `https://docs.google.com/spreadsheets/d/${spreadsheetId}/edit` : "#";
}

function businessDocUrl(documentId) {
  return documentId ? `https://docs.google.com/document/d/${documentId}/edit` : "#";
}

function formatCurrency(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(Number(value || 0));
}

function renderPresentation(presentation) {
  if (!presentation) {
    return "";
  }

  const summary = (presentation.summary_items || [])
    .map(
      (item) => `
        <div class="presentation-stat">
          <span class="presentation-stat-label">${escapeHtml(item.label)}</span>
          <strong class="presentation-stat-value">${escapeHtml(item.value)}</strong>
        </div>
      `,
    )
    .join("");

  const table = presentation.table
    ? `
      <div class="presentation-table-wrap">
        <table class="presentation-table">
          <thead>
            <tr>${presentation.table.columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>
          </thead>
          <tbody>
            ${presentation.table.rows
              .map(
                (row) => `
                  <tr>${row.map((cell) => `<td>${escapeHtml(String(cell ?? ""))}</td>`).join("")}</tr>
                `,
              )
              .join("")}
          </tbody>
        </table>
      </div>
    `
    : "";

  const sources = (presentation.sources || [])
    .map(
      (source) => `
        <a class="presentation-link" href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">
          ${escapeHtml(source.title)}
        </a>
      `,
    )
    .join("");

  const actionLink = presentation.sheet_url
    ? `<a class="presentation-link" href="${escapeHtml(presentation.sheet_url)}" target="_blank" rel="noreferrer">Open updated sheet</a>`
    : "";

  return `
    <section class="presentation-block">
      <h4 class="presentation-title">${escapeHtml(presentation.title || "Accounting Summary")}</h4>
      ${summary ? `<div class="presentation-stats">${summary}</div>` : ""}
      ${table}
      ${sources ? `<div class="presentation-links">${sources}</div>` : ""}
      ${actionLink ? `<div class="presentation-links">${actionLink}</div>` : ""}
    </section>
  `;
}

function renderMessage(role, text, presentation = null) {
  const wrapper = document.createElement("article");
  wrapper.className = `message ${role}`;
  wrapper.innerHTML = `
    <div class="message-meta">${role === "user" ? "You" : "CPA-Agent"}</div>
    <div>${escapeHtml(text)}</div>
    ${role === "agent" ? renderPresentation(presentation) : ""}
  `;
  chatLog.appendChild(wrapper);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function renderConversation(conversation, latestPresentation = null) {
  chatLog.innerHTML = "";
  conversation.forEach((entry, index) => {
    if (entry.user_input) {
      renderMessage("user", entry.user_input);
    }
    if (entry.outcome?.message) {
      const isLast = index === conversation.length - 1;
      renderMessage("agent", entry.outcome.message, isLast ? latestPresentation : null);
    }
  });
}

function updateStatus(status, latestPresentation = null) {
  const active = status.active_business;
  const businesses = status.businesses || [];
  const dashboard = status.dashboard || {};
  const modelConfig = status.model_config || {};

  businessSelect.innerHTML = businesses
    .map(
      (business) =>
        `<option value="${escapeHtml(business.business_name)}" ${
          business.key === status.active_business_key ? "selected" : ""
        }>${escapeHtml(business.business_name)}</option>`,
    )
    .join("");

  modelModeSelect.value = modelConfig.reasoning_mode || "fast";
  modelStatus.innerHTML = `
    <strong>${escapeHtml((modelConfig.provider || "ollama").toUpperCase())}</strong><br />
    Mode: ${escapeHtml(modelConfig.reasoning_mode || "fast")}<br />
    Primary: ${escapeHtml(modelConfig.reasoning_model || "Unknown")}<br />
    Audit: ${escapeHtml(modelConfig.reflection_model || "Unknown")}
  `;

  workspaceStatus.innerHTML = `
    <strong>${escapeHtml(active.business_name)}</strong><br />
    State: ${escapeHtml(active.state || "Unknown")}<br />
    Mode: ${escapeHtml(status.input_mode)}<br />
    Sheet: ${active.google_sheet_id ? "Connected" : "Pending"}<br />
    Doc: ${active.google_doc_id ? "Connected" : "Pending"}<br />
    Learned Sources: ${status.learned_source_count ?? 0}
  `;

  sheetLink.href = businessSheetUrl(active.google_sheet_id);
  docLink.href = businessDocUrl(active.google_doc_id);
  sheetLink.textContent = active.google_sheet_id ? "Open ledger sheet" : "Ledger sheet not available yet";
  docLink.textContent = active.google_doc_id ? "Open notes document" : "Notes document not available yet";

  if (status.workspace_boot_error) {
    bootWarning.textContent = `Workspace setup warning: ${status.workspace_boot_error}`;
    bootWarning.classList.remove("hidden");
  } else {
    bootWarning.classList.add("hidden");
  }

  renderConversation(status.conversation || [], latestPresentation);
  metricTransactions.textContent = dashboard.transaction_count ?? 0;
  metricIncome.textContent = formatCurrency(dashboard.income_total ?? 0);
  metricExpenses.textContent = formatCurrency(dashboard.expense_total ?? 0);
  metricFlagged.textContent = dashboard.flagged_actions ?? 0;
  renderRecentTransactions(dashboard.recent_transactions || [], dashboard.ledger_error);
  renderRecentAudits(dashboard.recent_audits || []);
}

function renderRecentTransactions(items, ledgerError) {
  if (ledgerError) {
    recentTransactions.innerHTML = `<div class="recent-item">Ledger unavailable: ${escapeHtml(ledgerError)}</div>`;
    return;
  }
  if (!items.length) {
    recentTransactions.innerHTML = `<div class="recent-item">No transactions yet for this business.</div>`;
    return;
  }
  recentTransactions.innerHTML = items
    .map(
      (item) => `
        <article class="recent-item">
          <div class="recent-topline">
            <span>${escapeHtml(item.description || "Untitled transaction")}</span>
            <span>${formatCurrency(item.amount || 0)}</span>
          </div>
          <div class="recent-meta">
            ${escapeHtml(item.date || "No date")} • ${escapeHtml(item.category || "Uncategorized")} • ${escapeHtml(item.type || "Unknown")}
          </div>
        </article>
      `,
    )
    .join("");
}

function renderRecentAudits(items) {
  if (!items.length) {
    recentAudits.innerHTML = `<div class="recent-item">No write attempts tracked yet.</div>`;
    return;
  }
  recentAudits.innerHTML = items
    .slice()
    .reverse()
    .map((item) => {
      const verification = item.verification || {};
      const status = verification.verified ? "Verified" : "Unverified";
      const rangeName = verification.range_name || "Unknown range";
      return `
        <article class="recent-item">
          <div class="recent-topline">
            <span>${escapeHtml(item.mode || "write")}</span>
            <span>${escapeHtml(status)}</span>
          </div>
          <div class="recent-meta">
            ${escapeHtml(rangeName)}
          </div>
        </article>
      `;
    })
    .join("");
}

async function fetchStatus() {
  const response = await fetch("/api/status");
  const status = await response.json();
  updateStatus(status);
}

async function sendMessage(message) {
  messageInput.value = "";

  const response = await fetch("/api/message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  const payload = await response.json();
  updateStatus(payload.status, payload.presentation);

  if (speakReplies && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(payload.message));
  }
}

async function switchBusiness() {
  switchBusinessButton.disabled = true;
  const response = await fetch("/api/switch-business", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ business_name: businessSelect.value }),
  });
  const payload = await response.json();
  switchBusinessButton.disabled = false;
  if (!response.ok) {
    renderMessage("agent", payload.detail || "Could not switch business.");
    return;
  }
  updateStatus(payload.status);
  renderMessage("agent", payload.message);
}

async function switchModelMode() {
  switchModelButton.disabled = true;
  const response = await fetch("/api/model-mode", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode: modelModeSelect.value }),
  });
  const payload = await response.json();
  switchModelButton.disabled = false;
  if (!response.ok) {
    renderMessage("agent", payload.detail || "Could not update model mode.");
    return;
  }
  updateStatus(payload.status);
  renderMessage("agent", payload.message);
}

async function submitTransaction(event) {
  event.preventDefault();
  transactionSubmit.disabled = true;
  transactionStatus.textContent = "Running reflection and posting...";

  const response = await fetch("/api/record-transaction", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      date: txDate.value,
      description: txDescription.value.trim(),
      category: txCategory.value.trim(),
      amount: Number(txAmount.value),
      entry_type: txType.value,
      reference: txReference.value.trim(),
      notes: txNotes.value.trim(),
    }),
  });

  const payload = await response.json();
  updateStatus(payload.status, payload.presentation);
  transactionStatus.textContent = payload.message;
  transactionSubmit.disabled = false;
  if (payload.ok) {
    txDescription.value = "";
    txCategory.value = "";
    txAmount.value = "";
    txReference.value = "";
    txNotes.value = "";
  }
  if (speakReplies && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(payload.message));
  }
}

function configureVoiceRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    voiceButton.disabled = true;
    voiceStatus.textContent = "Browser voice not supported";
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = "en-US";
  recognition.interimResults = false;
  recognition.continuous = false;

  recognition.onstart = () => {
    isListening = true;
    voiceButton.textContent = "Stop Voice";
    voiceStatus.textContent = "Listening...";
  };

  recognition.onend = () => {
    isListening = false;
    voiceButton.textContent = "Start Voice";
    voiceStatus.textContent = "Browser voice idle";
  };

  recognition.onerror = (event) => {
    voiceStatus.textContent = `Voice error: ${event.error}`;
  };

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript.trim();
    messageInput.value = transcript;
  };
}

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message) {
    return;
  }
  await sendMessage(message);
});

switchBusinessButton.addEventListener("click", switchBusiness);
switchModelButton.addEventListener("click", switchModelMode);
transactionForm.addEventListener("submit", submitTransaction);

voiceButton.addEventListener("click", () => {
  if (!recognition) {
    return;
  }
  if (isListening) {
    recognition.stop();
  } else {
    recognition.start();
  }
});

speakToggle.addEventListener("click", () => {
  speakReplies = !speakReplies;
  speakToggle.classList.toggle("active", speakReplies);
  speakToggle.textContent = speakReplies ? "Voice Replies On" : "Voice Replies Off";
  if (!speakReplies && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
});

configureVoiceRecognition();
fetchStatus();
