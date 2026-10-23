// Phase 9 Clinical Knowledge Review & Controlled Promotion Dashboard Frontend Logic

document.addEventListener('DOMContentLoaded', () => {
  // KPI Elements
  const kpiTotal = document.getElementById('val-total-backlog');
  const kpiHighRisk = document.getElementById('val-high-pending');
  const kpiPending = document.getElementById('val-pending');
  const kpiInReview = document.getElementById('val-in-review');
  const kpiApproved = document.getElementById('val-approved');
  const kpiPromoted = document.getElementById('val-promoted');

  // Filter Elements
  const filterSpecialty = document.getElementById('filter-specialty');
  const filterStatus = document.getElementById('filter-status');
  const filterRisk = document.getElementById('filter-risk');
  const filterPriority = document.getElementById('filter-priority');
  const filterReason = document.getElementById('filter-reason');
  const filterDoc = document.getElementById('filter-doc');
  const filterSearch = document.getElementById('filter-search');
  const filterSortBy = document.getElementById('filter-sort-by');
  const refreshBtn = document.getElementById('refresh-btn');

  // Queue List Elements
  const queueList = document.getElementById('queue-list');
  const queueCountBadge = document.getElementById('queue-count-badge');

  // Detail Pane Elements
  const emptyDetailState = document.getElementById('empty-detail-state');
  const detailContent = document.getElementById('detail-content');

  const detailIdBadge = document.getElementById('detail-id-badge');
  const detailRiskBadge = document.getElementById('detail-risk-badge');
  const detailStageBadge = document.getElementById('detail-stage-badge');
  const detailPriorityBadge = document.getElementById('detail-priority-badge');
  const detailReasonBadge = document.getElementById('detail-reason-badge');
  const detailStatusBadge = document.getElementById('detail-status-badge');

  const detailTitle = document.getElementById('detail-title');
  const detailDocBadge = document.getElementById('detail-doc-badge');
  const detailSpecialtyBadge = document.getElementById('detail-specialty-badge');
  const detailCondition = document.getElementById('detail-condition');
  const detailSection = document.getElementById('detail-section');
  const detailPage = document.getElementById('detail-page');
  const detailVersion = document.getElementById('detail-version');

  const detailContextBox = document.getElementById('detail-context-box');
  const detailContextTitle = document.getElementById('detail-context-title');
  const detailContextBody = document.getElementById('detail-context-body');

  const detailSourceText = document.getElementById('detail-source-text');
  const detailExtractedContent = document.getElementById('detail-extracted-content');
  const correctionDisplayBox = document.getElementById('correction-display-box');
  const detailCorrectedValue = document.getElementById('detail-corrected-value');

  // Form Inputs & Buttons
  const reviewerIdInput = document.getElementById('reviewer-id-input');
  const reviewerNameInput = document.getElementById('reviewer-name-input');
  const reviewNotesInput = document.getElementById('review-notes-input');
  const notesReqIndicator = document.getElementById('notes-req-indicator');
  const correctionInput = document.getElementById('correction-input');

  const btnStartReview = document.getElementById('btn-start-review');
  const btnApprove = document.getElementById('btn-approve');
  const btnCorrection = document.getElementById('btn-correction');
  const btnReject = document.getElementById('btn-reject');
  const btnPromote = document.getElementById('btn-promote');
  const actionStatusMsg = document.getElementById('action-status-msg');

  // Modals
  const viewAuditBtn = document.getElementById('view-audit-btn');
  const auditModal = document.getElementById('audit-modal');
  const closeAuditBtn = document.getElementById('close-audit-btn');
  const auditLogBody = document.getElementById('audit-log-body');

  const promotionModal = document.getElementById('promotion-modal');
  const closePromotionBtn = document.getElementById('close-promotion-btn');
  const promotionModalBody = document.getElementById('promotion-modal-body');

  let currentItems = [];
  let selectedItem = null;
  let searchTimeout = null;

  // 1. Fetch KPI Summary
  async function loadSummary() {
    try {
      const res = await fetch('/api/v1/review/summary');
      if (!res.ok) throw new Error('Failed to fetch summary');
      const data = await res.json();
      
      kpiTotal.textContent = data.total_items ?? '--';
      
      const highRiskCount = data.by_risk ? (data.by_risk['HIGH'] || 0) : (data.high_priority_pending || 0);
      kpiHighRisk.textContent = highRiskCount;
      
      kpiPending.textContent = data.pending ?? '--';
      kpiInReview.textContent = data.in_review ?? '--';
      kpiApproved.textContent = (data.approved ?? 0) + (data.eligible_for_production ?? 0);
      kpiPromoted.textContent = data.promoted ?? '--';
    } catch (err) {
      console.error('Summary error:', err);
    }
  }

  // 2. Fetch Queue Items
  async function loadQueue() {
    queueList.innerHTML = '<div class="empty-state">Loading review queue...</div>';
    try {
      const params = new URLSearchParams();
      if (filterSpecialty.value) params.append('specialty', filterSpecialty.value);
      if (filterStatus.value) params.append('status', filterStatus.value);
      if (filterRisk.value) params.append('risk_category', filterRisk.value);
      if (filterPriority.value) params.append('priority', filterPriority.value);
      if (filterReason.value) params.append('reason', filterReason.value);
      if (filterDoc.value) params.append('document_id', filterDoc.value);
      if (filterSearch.value.trim()) params.append('search', filterSearch.value.trim());
      if (filterSortBy.value) params.append('sort_by', filterSortBy.value);
      params.append('limit', '100');

      const res = await fetch(`/api/v1/review/items?${params.toString()}`);
      if (!res.ok) throw new Error('Failed to fetch items');
      const data = await res.json();
      currentItems = data.items || [];
      queueCountBadge.textContent = `${currentItems.length} items`;
      renderQueueList();
    } catch (err) {
      queueList.innerHTML = `<div class="empty-state" style="color: #ef4444;">Error loading queue: ${err.message}</div>`;
    }
  }

  // 3. Render Items List
  function renderQueueList() {
    if (currentItems.length === 0) {
      queueList.innerHTML = '<div class="empty-state">No review items match the current filters.</div>';
      return;
    }

    queueList.innerHTML = '';
    currentItems.forEach(item => {
      const card = document.createElement('div');
      const itemId = item.review_item_id || item.unit_id;
      card.className = `queue-item-card ${selectedItem && (selectedItem.review_item_id || selectedItem.unit_id) === itemId ? 'active' : ''}`;
      card.dataset.itemId = itemId;

      const priorityClass = (item.review_priority || 'LOW').toLowerCase();
      const statusClass = (item.review_status || 'NEEDS_REVIEW').toLowerCase().replace(/_/g, '-');
      const riskClass = (item.risk_category || 'LOW').toLowerCase();

      card.innerHTML = `
        <div class="card-top">
          <span class="badge-code">${itemId}</span>
          <div class="card-badges">
            <span class="badge-risk ${riskClass}">${item.risk_category || 'MED'}</span>
            <span class="badge-priority ${priorityClass}">${item.review_priority || 'MED'}</span>
            <span class="badge-status ${statusClass}">${item.review_status || 'NEEDS_REVIEW'}</span>
          </div>
        </div>
        <div class="card-content-preview">${escapeHtml(item.content)}</div>
        <div class="card-footer">
          <span>${item.specialty || 'General'}</span> •
          <span>${item.document_id}</span> •
          <span>${escapeHtml(item.condition)}</span> •
          <span>p. ${item.page_number}</span>
        </div>
      `;

      card.addEventListener('click', () => selectItem(item));
      queueList.appendChild(card);
    });
  }

  // 4. Select Item & Populate Detail
  function selectItem(item) {
    selectedItem = item;
    const itemId = item.review_item_id || item.unit_id;

    // Highlight active card
    document.querySelectorAll('.queue-item-card').forEach(c => {
      c.classList.toggle('active', c.dataset.itemId === itemId);
    });

    emptyDetailState.classList.add('hidden');
    detailContent.classList.remove('hidden');

    detailIdBadge.textContent = itemId;

    // Risk category badge
    const risk = item.risk_category || 'LOW';
    detailRiskBadge.textContent = `${risk} RISK`;
    detailRiskBadge.className = `badge-risk ${risk.toLowerCase()}`;

    // Two-stage indicator
    if (item.requires_two_stage_approval || risk === 'HIGH') {
      detailStageBadge.classList.remove('hidden');
      detailStageBadge.textContent = item.second_reviewer_id ? 'STAGE 1 COMPLETED' : '2-STAGE REQUIRED';
    } else {
      detailStageBadge.classList.add('hidden');
    }

    // Priority badge
    const p = item.review_priority || 'LOW';
    detailPriorityBadge.textContent = p;
    detailPriorityBadge.className = `badge-priority ${p.toLowerCase()}`;

    detailReasonBadge.textContent = item.review_reason || 'REVIEW_FLAGGED';

    const s = item.review_status || 'NEEDS_REVIEW';
    detailStatusBadge.textContent = s;
    detailStatusBadge.className = `badge-status ${s.toLowerCase().replace(/_/g, '-')}`;

    detailTitle.textContent = `${item.condition} — ${(item.entity_type || 'KNOWLEDGE_UNIT').replace(/_/g, ' ').toUpperCase()}`;
    detailDocBadge.textContent = item.document_id;
    detailSpecialtyBadge.textContent = item.specialty || 'General';
    detailCondition.textContent = item.condition;
    detailSection.textContent = item.section;
    detailPage.textContent = item.page_number;
    detailVersion.textContent = item.version_id || 'v1.0';

    // Flowchart or Table Context
    if (item.flowchart_context) {
      detailContextBox.classList.remove('hidden');
      detailContextTitle.textContent = 'Flowchart Structural Node Context';
      detailContextBody.textContent = item.flowchart_context;
    } else if (item.table_context) {
      detailContextBox.classList.remove('hidden');
      detailContextTitle.textContent = 'Tabular Extraction Context';
      detailContextBody.textContent = item.table_context;
    } else {
      detailContextBox.classList.add('hidden');
      detailContextBody.textContent = '';
    }

    // Immutable Source Text
    detailSourceText.textContent = item.original_source_text || item.content;

    // Extracted Content
    detailExtractedContent.textContent = item.content;

    // Corrected value if any
    if (item.corrected_structured_value) {
      correctionDisplayBox.classList.remove('hidden');
      detailCorrectedValue.textContent = item.corrected_structured_value;
    } else {
      correctionDisplayBox.classList.add('hidden');
      detailCorrectedValue.textContent = '';
    }

    // Populate notes & inputs
    reviewNotesInput.value = item.review_notes || '';
    correctionInput.value = item.corrected_structured_value || '';
    reviewerNameInput.value = item.reviewer_name || '';

    // Mandatory notes indicator for HIGH risk
    if (risk === 'HIGH') {
      notesReqIndicator.classList.remove('hidden');
    } else {
      notesReqIndicator.classList.add('hidden');
    }

    // Button states depending on lifecycle
    updateActionButtons(item);
    hideStatusMsg();
  }

  function updateActionButtons(item) {
    const status = item.review_status || 'NEEDS_REVIEW';
    const isHigh = item.risk_category === 'HIGH' || item.requires_two_stage_approval;

    // Reset default labels
    btnStartReview.disabled = false;
    btnApprove.disabled = false;
    btnCorrection.disabled = false;
    btnReject.disabled = false;
    btnPromote.disabled = false;

    if (status === 'NEEDS_REVIEW' || status === 'PENDING') {
      btnStartReview.style.display = 'inline-block';
      btnStartReview.textContent = 'Start Review';
      btnApprove.textContent = isHigh ? 'Approve (Stage 1)' : 'Approve';
      btnPromote.style.display = 'none';
    } else if (status === 'IN_REVIEW') {
      btnStartReview.style.display = 'none';
      if (isHigh && item.reviewer_id && !item.second_reviewer_id) {
        btnApprove.textContent = 'Approve (Stage 2)';
      } else {
        btnApprove.textContent = isHigh ? 'Approve (Stage 1)' : 'Approve';
      }
      btnPromote.style.display = 'none';
    } else if (status === 'APPROVED' || status === 'ELIGIBLE_FOR_PRODUCTION') {
      btnStartReview.style.display = 'none';
      btnApprove.textContent = 'Approved ✓';
      btnApprove.disabled = true;
      btnPromote.style.display = 'inline-block';
      btnPromote.textContent = 'Promote to Production 🚀';
    } else if (status === 'PROMOTED' || status === 'PRODUCTION_INDEX') {
      btnStartReview.style.display = 'none';
      btnApprove.textContent = 'Approved ✓';
      btnApprove.disabled = true;
      btnPromote.style.display = 'inline-block';
      btnPromote.textContent = 'Promoted in Production ✓';
      btnPromote.disabled = true;
      btnCorrection.disabled = true;
      btnReject.disabled = true;
    } else if (status === 'REJECTED') {
      btnStartReview.style.display = 'none';
      btnApprove.disabled = true;
      btnPromote.style.display = 'none';
      btnReject.textContent = 'Rejected ✗';
      btnReject.disabled = true;
    }
  }

  // 5. Action Execution
  async function performAction(actionType) {
    if (!selectedItem) return;
    const reviewerId = reviewerIdInput.value.trim();
    if (!reviewerId) {
      showStatusMsg('Clinician / Reviewer ID is required.', 'error');
      reviewerIdInput.focus();
      return;
    }

    const reviewerName = reviewerNameInput.value.trim() || undefined;
    const itemId = selectedItem.review_item_id || selectedItem.unit_id;
    const notes = reviewNotesInput.value.trim();

    try {
      let endpoint = '';
      let payload = {};

      if (actionType === 'start') {
        endpoint = `/api/v1/review/items/${itemId}/start`;
        payload = {
          reviewer_id: reviewerId,
          reviewer_name: reviewerName,
          notes: notes || undefined
        };
      } else if (actionType === 'approve') {
        const isHigh = selectedItem.risk_category === 'HIGH' || selectedItem.requires_two_stage_approval;
        if (isHigh && !notes) {
          showStatusMsg('Clinical justification notes are mandatory for HIGH risk approvals.', 'error');
          reviewNotesInput.focus();
          return;
        }
        endpoint = `/api/v1/review/items/${itemId}/approve`;
        payload = {
          reviewer_id: reviewerId,
          reviewer_name: reviewerName,
          review_notes: notes || undefined,
          notes: notes || undefined,
          clinical_rationale: notes || undefined
        };
      } else if (actionType === 'reject') {
        if (!notes) {
          showStatusMsg('Clinical notes are required to document justification for rejection.', 'error');
          reviewNotesInput.focus();
          return;
        }
        endpoint = `/api/v1/review/items/${itemId}/reject`;
        payload = {
          reviewer_id: reviewerId,
          reviewer_name: reviewerName,
          rejection_reason: notes,
          notes: notes
        };
      } else if (actionType === 'correction') {
        const correctedVal = correctionInput.value.trim();
        if (!correctedVal) {
          showStatusMsg('Structured correction text cannot be empty.', 'error');
          correctionInput.focus();
          return;
        }
        endpoint = `/api/v1/review/items/${itemId}/correct`;
        payload = {
          reviewer_id: reviewerId,
          reviewer_name: reviewerName,
          corrected_structured_value: correctedVal,
          notes: notes || undefined
        };
      } else if (actionType === 'promote') {
        endpoint = `/api/v1/review/items/${itemId}/promote`;
        payload = {
          promoter_id: reviewerId,
          promoter_name: reviewerName,
          notes: notes || 'Clinical promotion to production index'
        };
      }

      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Action failed');
      }

      const result = await res.json();

      if (actionType === 'promote') {
        renderPromotionModal(result);
      } else {
        showStatusMsg(`Successfully executed: ${actionType.toUpperCase()}`, 'success');
        selectItem(result);
      }

      await loadSummary();
      await loadQueue();
    } catch (err) {
      showStatusMsg(`Error: ${err.message}`, 'error');
    }
  }

  // 6. Promotion Validation Modal Render
  function renderPromotionModal(result) {
    promotionModal.classList.remove('hidden');
    const passed = result.eligible_for_production && result.indexed_successfully;
    
    let checksHtml = '<div style="margin-bottom: 12px;">';
    checksHtml += `<div style="font-size: 14px; font-weight: 700; color: ${passed ? '#10b981' : '#ef4444'}; margin-bottom: 8px;">`;
    checksHtml += passed ? '✓ Promotion & Incremental Indexing Successful' : '✗ Promotion Blocked';
    checksHtml += `</div>`;
    checksHtml += `<p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">Unit: <code>${result.unit_id}</code> | Index Latency: ${result.indexing_latency_ms?.toFixed(2) || '0'} ms</p>`;

    if (result.validation_checks && result.validation_checks.length > 0) {
      checksHtml += '<table class="audit-table"><thead><tr><th>Check</th><th>Status</th><th>Message</th></tr></thead><tbody>';
      result.validation_checks.forEach(c => {
        const cPassed = c.passed;
        checksHtml += `<tr>
          <td><strong>${c.check_name}</strong></td>
          <td style="color: ${cPassed ? '#10b981' : '#ef4444'}; font-weight: 600;">${cPassed ? 'PASS' : 'FAIL'}</td>
          <td style="font-size: 11px;">${escapeHtml(c.message || '')}</td>
        </tr>`;
      });
      checksHtml += '</tbody></table>';
    }

    if (result.errors && result.errors.length > 0) {
      checksHtml += '<div style="margin-top: 12px; padding: 8px; background: rgba(239, 68, 68, 0.15); border-radius: 4px; color: #f87171; font-size: 12px;">';
      checksHtml += '<strong>Errors:</strong><br>' + result.errors.map(e => `• ${escapeHtml(e)}`).join('<br>');
      checksHtml += '</div>';
    }

    checksHtml += '</div>';
    promotionModalBody.innerHTML = checksHtml;
  }

  // Event Listeners for Actions
  btnStartReview.addEventListener('click', () => performAction('start'));
  btnApprove.addEventListener('click', () => performAction('approve'));
  btnReject.addEventListener('click', () => performAction('reject'));
  btnCorrection.addEventListener('click', () => performAction('correction'));
  btnPromote.addEventListener('click', () => performAction('promote'));

  closePromotionBtn.addEventListener('click', () => {
    promotionModal.classList.add('hidden');
  });

  // 7. Audit Trail Modal
  viewAuditBtn.addEventListener('click', async () => {
    auditModal.classList.remove('hidden');
    auditLogBody.innerHTML = '<div class="empty-state">Loading audit history...</div>';
    try {
      const res = await fetch('/api/v1/review/audit');
      if (!res.ok) throw new Error('Failed to load audit history');
      const data = await res.json();
      if (!data || data.length === 0) {
        auditLogBody.innerHTML = '<div class="empty-state">No audit logs recorded yet.</div>';
        return;
      }

      let html = `
        <table class="audit-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Item ID</th>
              <th>Action</th>
              <th>Reviewer</th>
              <th>Notes / Correction</th>
            </tr>
          </thead>
          <tbody>
      `;
      data.forEach(log => {
        const reviewerDisplay = log.reviewer_name ? `${log.reviewer_name} (${log.reviewer_id})` : log.reviewer_id;
        html += `
          <tr>
            <td style="white-space: nowrap;">${log.timestamp}</td>
            <td><code>${log.review_item_id}</code></td>
            <td><strong style="color: #60a5fa;">${log.action}</strong></td>
            <td>${escapeHtml(reviewerDisplay)}</td>
            <td>${escapeHtml(log.notes || '')} ${log.corrected_value ? `<br><em style="color: #c084fc;">[Correction: ${escapeHtml(log.corrected_value)}]</em>` : ''}</td>
          </tr>
        `;
      });
      html += '</tbody></table>';
      auditLogBody.innerHTML = html;
    } catch (err) {
      auditLogBody.innerHTML = `<div class="empty-state" style="color: #ef4444;">Error: ${err.message}</div>`;
    }
  });

  closeAuditBtn.addEventListener('click', () => {
    auditModal.classList.add('hidden');
  });

  // Helpers
  function showStatusMsg(text, type) {
    actionStatusMsg.textContent = text;
    actionStatusMsg.className = `action-status ${type}`;
    actionStatusMsg.classList.remove('hidden');
  }

  function hideStatusMsg() {
    actionStatusMsg.classList.add('hidden');
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Filters change listeners
  [filterSpecialty, filterStatus, filterRisk, filterPriority, filterReason, filterDoc, filterSortBy].forEach(el => {
    if (el) el.addEventListener('change', loadQueue);
  });

  filterSearch.addEventListener('input', () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(loadQueue, 300);
  });

  refreshBtn.addEventListener('click', () => {
    loadSummary();
    loadQueue();
  });

  // Initial Load
  loadSummary();
  loadQueue();
});
