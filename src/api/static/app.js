// ICMR STW Evidence Assistant — Frontend Interaction Logic

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("chat-form");
  const input = document.getElementById("query-input");
  const viewport = document.getElementById("messages-viewport");
  const sendBtn = document.getElementById("send-button");
  const debugToggle = document.getElementById("debug-checkbox");
  const welcomeCard = document.getElementById("welcome-card");
  const specialtySelect = document.getElementById("specialty-select");
  const conditionSelect = document.getElementById("condition-select");
  const openExplorerBtn = document.getElementById("open-explorer-btn");
  const closeExplorerBtn = document.getElementById("close-explorer-btn");
  const explorerModal = document.getElementById("explorer-modal");
  const explorerBody = document.getElementById("explorer-body");

  let specialtiesData = [];

  // Load Specialties & Conditions
  async function loadSpecialties() {
    try {
      const resp = await fetch("/api/v1/specialties");
      if (!resp.ok) return;
      specialtiesData = await resp.json();

      specialtySelect.innerHTML = '<option value="">All Specialties</option>';
      specialtiesData.forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s.specialty;
        opt.textContent = `${s.specialty} (${s.total_documents} STWs)`;
        specialtySelect.appendChild(opt);
      });
      updateConditionOptions();
    } catch (e) {
      console.warn("Could not load specialties:", e);
    }
  }

  function updateConditionOptions() {
    const selectedSpec = specialtySelect.value;
    conditionSelect.innerHTML = '<option value="">All Conditions</option>';
    let conditions = [];
    if (selectedSpec) {
      const found = specialtiesData.find((s) => s.specialty === selectedSpec);
      if (found && found.conditions) conditions = found.conditions;
    } else {
      specialtiesData.forEach((s) => {
        if (s.conditions) conditions.push(...s.conditions);
      });
      conditions = Array.from(new Set(conditions)).sort();
    }
    conditions.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c;
      opt.textContent = c;
      conditionSelect.appendChild(opt);
    });
  }

  specialtySelect.addEventListener("change", updateConditionOptions);
  loadSpecialties();

  // Document Explorer Modal
  if (openExplorerBtn && explorerModal) {
    openExplorerBtn.addEventListener("click", async () => {
      explorerModal.style.display = "flex";
      explorerBody.innerHTML = '<div style="color: #94a3b8; font-size: 0.9rem;">Loading guidelines tree...</div>';
      try {
        const resp = await fetch("/api/v1/explorer");
        if (!resp.ok) throw new Error("Failed to load guidelines");
        const docs = await resp.json();
        renderExplorer(docs);
      } catch (e) {
        explorerBody.innerHTML = `<div style="color: #ef4444;">Error: ${escapeHtml(e.message)}</div>`;
      }
    });

    closeExplorerBtn.addEventListener("click", () => {
      explorerModal.style.display = "none";
    });

    explorerModal.addEventListener("click", (e) => {
      if (e.target === explorerModal) explorerModal.style.display = "none";
    });
  }

  function renderExplorer(docs) {
    if (!docs || docs.length === 0) {
      explorerBody.innerHTML = '<div style="color: #94a3b8;">No documents found in index.</div>';
      return;
    }

    const cards = docs.map((d) => {
      const statusClass = d.review_status === "APPROVED" ? "status-approved" : "status-needs-review";
      const statusLabel = d.review_status === "APPROVED" ? "VERIFIED PRODUCTION" : "IN REVIEW (QUARANTINED)";
      const sections = (d.sections || []).slice(0, 5).map((sec) => `<li>• ${escapeHtml(sec)}</li>`).join("");
      return `
        <div class="explorer-card">
          <div class="explorer-card-header">
            <span class="explorer-spec-badge">${escapeHtml(d.specialty)}</span>
            <span class="explorer-status-badge ${statusClass}">${escapeHtml(statusLabel)}</span>
          </div>
          <div class="explorer-card-title">${escapeHtml(d.condition)}</div>
          <div class="explorer-card-meta">
            <span>Doc ID: ${escapeHtml(d.document_id)}</span> &bull;
            <span>Ver: ${escapeHtml(d.version_id)}</span> &bull;
            <span>${d.total_pages} page(s)</span>
          </div>
          <ul class="explorer-sections-list">
            ${sections}
            ${d.sections && d.sections.length > 5 ? `<li style="color:#64748b;">+ ${d.sections.length - 5} more sections...</li>` : ""}
          </ul>
        </div>
      `;
    }).join("");

    explorerBody.innerHTML = `<div class="explorer-grid">${cards}</div>`;
  }

  // Auto-resize textarea
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
  });

  // Enter to send (Shift+Enter for newline)
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.dispatchEvent(new Event("submit"));
    }
  });

  // Sample chips
  document.querySelectorAll(".sample-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const q = chip.getAttribute("data-query");
      if (q) {
        input.value = q;
        input.focus();
        form.dispatchEvent(new Event("submit"));
      }
    });
  });

  // Form submit handler
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const query = input.value.trim();
    if (!query) return;

    // Remove welcome card if present
    if (welcomeCard && welcomeCard.parentNode) {
      welcomeCard.remove();
    }

    // Append user message bubble
    appendUserMessage(query);
    input.value = "";
    input.style.height = "auto";
    sendBtn.disabled = true;

    // Append loading row
    const loadingRow = appendLoadingIndicator();

    try {
      const payload = {
        query: query,
        top_k: 5,
        debug: debugToggle.checked,
      };
      if (specialtySelect && specialtySelect.value) {
        payload.specialty = specialtySelect.value;
      }
      if (conditionSelect && conditionSelect.value) {
        payload.condition = conditionSelect.value;
      }

      const resp = await fetch("/api/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      loadingRow.remove();

      if (!resp.ok) {
        const errorData = await resp.json().catch(() => ({}));
        appendAssistantCard({
          status: "ERROR",
          answer: `Server error (${resp.status}): ${errorData.detail || "Request failed."}`,
          key_points: [],
          cautions: ["Please check system connection."],
          citations: [],
          abstained: true,
        });
        return;
      }

      const data = await resp.json();
      appendAssistantCard(data);
    } catch (err) {
      loadingRow.remove();
      appendAssistantCard({
        status: "ERROR",
        answer: `Network failure: ${err.message}`,
        key_points: [],
        cautions: ["Could not connect to API server."],
        citations: [],
        abstained: true,
      });
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  });

  function appendUserMessage(text) {
    const row = document.createElement("div");
    row.className = "message-row user";
    row.innerHTML = `<div class="user-bubble">${escapeHtml(text)}</div>`;
    viewport.appendChild(row);
    scrollToBottom();
  }

  function appendLoadingIndicator() {
    const row = document.createElement("div");
    row.className = "loading-row";
    row.innerHTML = `
      <div class="loading-spinner"></div>
      <span>Searching ICMR STW evidence and synthesizing...</span>
    `;
    viewport.appendChild(row);
    scrollToBottom();
    return row;
  }

  function appendAssistantCard(data) {
    const row = document.createElement("div");
    row.className = "message-row assistant";

    const statusClass = (data.status || "grounded").toLowerCase();
    const statusLabel = data.status || "GROUNDED";

    // Key points list
    let keyPointsHtml = "";
    if (data.key_points && data.key_points.length > 0) {
      const items = data.key_points.map((kp) => `<li>${escapeHtml(kp)}</li>`).join("");
      keyPointsHtml = `
        <div class="structured-section">
          <div class="section-label">Key Clinical Points</div>
          <ul class="structured-list">${items}</ul>
        </div>
      `;
    }

    // Cautions list
    let cautionsHtml = "";
    if (data.cautions && data.cautions.length > 0) {
      const items = data.cautions.map((c) => `<li>${escapeHtml(c)}</li>`).join("");
      cautionsHtml = `
        <div class="structured-section">
          <div class="section-label">Important Cautions & Alerts</div>
          <ul class="structured-list caution-list">${items}</ul>
        </div>
      `;
    }

    // Version warning
    let versionWarningHtml = "";
    if (data.version_warning) {
      versionWarningHtml = `
        <div class="version-banner">
          <strong>Version Alert:</strong> ${escapeHtml(data.version_warning)}
        </div>
      `;
    }

    // Citations cards
    let citationsHtml = "";
    if (data.citations && data.citations.length > 0) {
      const cards = data.citations
        .map((c) => {
          return `
            <div class="citation-card" title="Click to view details">
              <div class="citation-tagline">
                <span class="citation-doc">${escapeHtml(c.document_id)}</span>
                <span class="citation-location">Page ${escapeHtml(String(c.page_number))}</span>
              </div>
              <div style="font-weight: 500; font-size: 0.8rem; color: #cbd5e1;">${escapeHtml(c.condition)} — ${escapeHtml(c.section)}</div>
              <div class="citation-snippet">"${escapeHtml(c.source_text_reference)}"</div>
            </div>
          `;
        })
        .join("");

      citationsHtml = `
        <div class="citations-wrapper">
          <div class="citations-header">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
            </svg>
            Verified ICMR Citations (${data.citations.length})
          </div>
          <div class="citation-cards-grid">${cards}</div>
        </div>
      `;
    }

    // Debug info accordion
    let debugHtml = "";
    if (data.debug_info) {
      debugHtml = `
        <details style="font-size: 0.75rem; color: #94a3b8; margin-top: 8px;">
          <summary style="cursor: pointer;">Debug Diagnostics</summary>
          <pre style="background: rgba(0,0,0,0.3); padding: 8px; border-radius: 4px; overflow-x: auto; margin-top: 4px;">${escapeHtml(JSON.stringify(data.debug_info, null, 2))}</pre>
        </details>
      `;
    }

    row.innerHTML = `
      <div class="assistant-card">
        <div class="card-header-bar">
          <span class="status-badge ${statusClass}">${escapeHtml(statusLabel)}</span>
          <span style="font-size: 0.75rem; color: #64748b;">ICMR Grounded Decision Support</span>
        </div>
        ${versionWarningHtml}
        <div class="answer-body">${escapeHtml(data.answer)}</div>
        ${keyPointsHtml}
        ${cautionsHtml}
        ${citationsHtml}
        ${debugHtml}
        <div class="disclaimer-footer">
          ${escapeHtml(data.clinical_disclaimer || "ICMR STW clinical decision support — not independent medical advice.")}
        </div>
      </div>
    `;

    viewport.appendChild(row);
    scrollToBottom();
  }

  function scrollToBottom() {
    viewport.scrollTop = viewport.scrollHeight;
  }

  function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }
});
