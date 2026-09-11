document.addEventListener('DOMContentLoaded', () => {
  checkSystemHealth();
  loadDashboardData();
  initCategorySelector();

  const dropZone = document.getElementById('drop-zone');
  const fileInput = document.getElementById('file-input');
  const uploadForm = document.getElementById('upload-form');
  const globalSearchInput = document.getElementById('global-search-input');

  if (dropZone && fileInput) {
    dropZone.addEventListener('click', (e) => {
      // Don't trigger file dialog if process button was clicked directly
      if (e.target.closest('#process-submit-btn')) return;
      fileInput.click();
    });

    dropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));

    dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
      if (e.dataTransfer.files.length > 0) {
        fileInput.files = e.dataTransfer.files;
        updateFileNameDisplay();
      }
    });

    fileInput.addEventListener('change', updateFileNameDisplay);
  }

  if (uploadForm) {
    uploadForm.addEventListener('submit', handleDocumentUpload);
  }

  if (globalSearchInput) {
    globalSearchInput.addEventListener('input', (e) => {
      searchQuery = e.target.value ? e.target.value.toLowerCase().trim() : '';
      renderDocumentsTable();
    });
  }

  // Global click listener to close dropdowns when clicking outside
  document.addEventListener('click', (e) => {
    // Close category dropdown
    const catCol = document.querySelector('.category-select-col');
    const catDropdown = document.getElementById('category-dropdown');
    const catCaret = document.getElementById('tags-caret');
    if (catCol && !catCol.contains(e.target)) {
      if (catDropdown) catDropdown.style.display = 'none';
      if (catCaret) catCaret.classList.remove('open');
    }

    // Close notifications dropdown
    const notifWrapper = document.getElementById('notif-wrapper');
    const notifDropdown = document.getElementById('notif-dropdown');
    if (notifWrapper && !notifWrapper.contains(e.target)) {
      if (notifDropdown) notifDropdown.style.display = 'none';
    }
  });
});

let allDocuments = [];
let activeCategoryFilter = 'all';
let searchQuery = '';

// Category Tags State: Start with zero pre-selected items as requested
let selectedCategories = [];
let activePrimaryCategory = '';

function initCategorySelector() {
  renderCategoryChips();
  updateCategoryDropdownSelection();
}

function renderCategoryChips() {
  const container = document.getElementById('chips-container');
  if (!container) return;

  if (selectedCategories.length === 0) {
    container.innerHTML = '<span style="font-size: 0.82rem; color: var(--text-subtle); padding: 3px 2px;">Select category from dropdown...</span>';
    return;
  }

  container.innerHTML = selectedCategories.map(cat => {
    const isPrimary = cat.id === activePrimaryCategory;
    return `
      <span class="category-chip ${isPrimary ? 'primary-selected' : ''}" onclick="setPrimaryCategory('${cat.id}', event)">
        <span>${escapeHtml(cat.label)}</span>
        <span class="chip-close" title="Remove ${escapeHtml(cat.label)}" onclick="removeCategoryTag('${cat.id}', event)">&times;</span>
      </span>
    `;
  }).join('');
}

function removeCategoryTag(catId, event) {
  if (event) event.stopPropagation();

  selectedCategories = selectedCategories.filter(c => c.id !== catId);

  // If we removed the active primary category, fall back to next available or empty
  if (activePrimaryCategory === catId) {
    activePrimaryCategory = selectedCategories.length > 0 ? selectedCategories[0].id : '';
  }

  const hiddenInput = document.getElementById('selected-document-type');
  if (hiddenInput) hiddenInput.value = activePrimaryCategory || 'invoice';

  renderCategoryChips();
  updateCategoryDropdownSelection();
}

function setPrimaryCategory(catId, event) {
  if (event) event.stopPropagation();
  activePrimaryCategory = catId;

  const hiddenInput = document.getElementById('selected-document-type');
  if (hiddenInput) hiddenInput.value = activePrimaryCategory;

  renderCategoryChips();
  updateCategoryDropdownSelection();
}

function toggleCategoryDropdown(event) {
  const dropdown = document.getElementById('category-dropdown');
  const caret = document.getElementById('tags-caret');
  if (!dropdown) return;

  const isVisible = dropdown.style.display === 'flex' || dropdown.style.display === 'block';
  if (isVisible) {
    dropdown.style.display = 'none';
    if (caret) caret.classList.remove('open');
  } else {
    dropdown.style.display = 'flex';
    if (caret) caret.classList.add('open');
  }
}

function onCategoryOptionClick(catVal, catLabel, event) {
  if (event) event.stopPropagation();

  // Check if category already in selected list
  const existingIndex = selectedCategories.findIndex(c => c.id === catVal);
  if (existingIndex >= 0) {
    // If already selected, clicking it again toggles it off
    selectedCategories.splice(existingIndex, 1);
    activePrimaryCategory = selectedCategories.length > 0 ? selectedCategories[0].id : '';
  } else {
    selectedCategories.push({ id: catVal, label: catLabel });
    activePrimaryCategory = catVal;
  }

  const hiddenInput = document.getElementById('selected-document-type');
  if (hiddenInput) hiddenInput.value = activePrimaryCategory || 'invoice';

  renderCategoryChips();
  updateCategoryDropdownSelection();
}

function updateCategoryDropdownSelection() {
  document.querySelectorAll('.category-option-item').forEach(item => {
    const val = item.getAttribute('data-val');
    const isSelected = selectedCategories.some(c => c.id === val);
    const isPrimary = activePrimaryCategory === val;

    const existingCheck = item.querySelector('.fa-check');
    if (existingCheck) existingCheck.remove();

    if (isSelected || isPrimary) {
      item.classList.add('selected');
      const checkIcon = document.createElement('i');
      checkIcon.className = 'fa-solid fa-check';
      checkIcon.style.fontSize = '0.75rem';
      checkIcon.style.color = 'var(--primary)';
      item.appendChild(checkIcon);
    } else {
      item.classList.remove('selected');
    }
  });
}

// Notifications Dropdown Controls
function toggleNotificationsDropdown(event) {
  if (event) event.stopPropagation();
  const dropdown = document.getElementById('notif-dropdown');
  if (!dropdown) return;

  const isVisible = dropdown.style.display === 'block';
  dropdown.style.display = isVisible ? 'none' : 'block';
}

function clearAllNotifications(event) {
  if (event) event.stopPropagation();
  const badge = document.getElementById('notif-badge');
  if (badge) badge.style.display = 'none';

  const list = document.getElementById('notif-items-list');
  if (list) {
    list.innerHTML = `
      <li style="padding: 24px; text-align: center; color: var(--text-muted); font-size: 0.78rem;">
        <i class="fa-regular fa-bell-slash" style="font-size: 1.4rem; color: var(--text-subtle); margin-bottom: 8px; display: block;"></i>
        All notifications caught up.
      </li>
    `;
  }
}

// System Health Check
async function checkSystemHealth() {
  const dot = document.getElementById('health-dot');
  const text = document.getElementById('health-status-text');
  const latency = document.getElementById('health-latency');

  const startTime = performance.now();
  try {
    const res = await fetch('https://findoc-ai-2c11.onrender.com/api/v1/health');
    const endTime = performance.now();
    const pingMs = Math.max(1, Math.round(endTime - startTime));

    if (res.ok) {
      if (dot) dot.style.background = '#10B981';
      if (text) text.textContent = 'API Online';
      if (latency) latency.textContent = `API Online â€¢ Ping ${pingMs}ms`;
    } else {
      if (dot) dot.style.background = '#EF4444';
      if (text) text.textContent = 'API Degraded';
      if (latency) latency.textContent = `Error ${res.status}`;
    }
  } catch (err) {
    if (dot) dot.style.background = '#EF4444';
    if (text) text.textContent = 'API Offline';
    if (latency) latency.textContent = 'Disconnected';
  }
}

// Fetch documents from GET https://findoc-ai-2c11.onrender.com/api/v1/documents
async function loadDashboardData() {
  try {
    const res = await fetch('https://findoc-ai-2c11.onrender.com/api/v1/documents');
    if (!res.ok) return;

    allDocuments = await res.json();
    renderDocumentsTable();
  } catch (err) {
    console.error('Failed to load document dataset from backend API:', err);
  }
}

// Category Tab Filter
function filterCategory(cat, element) {
  activeCategoryFilter = cat;

  document.querySelectorAll('.filter-pill').forEach(pill => pill.classList.remove('active'));
  if (element) element.classList.add('active');

  renderDocumentsTable();
}

// Render Table matching screenshot columns
function renderDocumentsTable() {
  const tableBody = document.getElementById('dashboard-table-body');
  if (!tableBody) return;

  const filtered = allDocuments.filter(doc => {
    let matchesCategory = true;
    if (activeCategoryFilter === 'invoice') {
      matchesCategory = doc.document_type === 'invoice';
    } else if (activeCategoryFilter === 'profit_and_loss') {
      matchesCategory = doc.document_type === 'profit_and_loss';
    } else if (activeCategoryFilter === 'balance_sheet') {
      matchesCategory = doc.document_type === 'balance_sheet' || doc.document_type === 'cash_flow_statement';
    }

    const nameStr = (doc.document_name || '').toLowerCase();
    const typeStr = (doc.document_type || '').toLowerCase();
    const matchesSearch = !searchQuery || nameStr.includes(searchQuery) || typeStr.includes(searchQuery);

    return matchesCategory && matchesSearch;
  });

  if (filtered.length === 0) {
    tableBody.innerHTML = `
      <tr>
        <td colspan="7" style="text-align: center; padding: 40px; color: var(--text-muted);">
          <div style="font-size: 1.1rem; font-weight: 700; color: var(--text-main); margin-bottom: 4px;">Workspace Empty</div>
          <div style="font-size: 0.82rem;">No document records found matching selected filter. Upload a financial document to begin.</div>
        </td>
      </tr>
    `;
    return;
  }

  tableBody.innerHTML = filtered.map((doc, index) => {
    const isPass = doc.processing_status === 'PASS' || doc.processing_status === 'COMPLETED' || (doc.validation && doc.validation.overall_status === 'PASS');
    const isFail = doc.processing_status === 'FAILED' || (doc.validation && doc.validation.overall_status === 'FAIL');
    
    let statusBadge = '<span class="badge-status processed"><i class="fa-solid fa-check"></i> PROCESSED</span>';
    if (isFail) {
      statusBadge = '<span class="badge-status failed"><i class="fa-solid fa-xmark"></i> FAILED</span>';
    } else if (!isPass) {
      statusBadge = '<span class="badge-status processing"><i class="fa-solid fa-circle-notch fa-spin"></i> PROCESSING</span>';
    }

    const formattedDate = doc.created_at ? new Date(doc.created_at).toLocaleString() : '-';
    const batchId = `Batch_${String(Math.floor(index / 10) + 1).padStart(3, '0')}`;

    return `
      <tr>
        <td>
          <div class="table-doc-name">
            <i class="fa-regular fa-file-lines table-doc-icon"></i>
            <span>${escapeHtml(doc.document_name)}</span>
          </div>
        </td>
        <td style="font-weight: 600; color: var(--text-muted);">${formatCategoryName(doc.document_type)}</td>
        <td style="font-weight: 600;">${doc.page_count || 1}</td>
        <td>${statusBadge}</td>
        <td style="font-size: 0.78rem; color: var(--text-muted);">${formattedDate}</td>
        <td>
          <div class="table-action-group">
            <a href="view.html?doc=${encodeURIComponent(doc.document_name)}" class="table-icon-btn" title="View Document">
              <i class="fa-regular fa-eye"></i>
            </a>
            <a href="view.html?doc=${encodeURIComponent(doc.document_name)}" class="table-icon-btn" title="Inspect Settings">
              <i class="fa-solid fa-gear"></i>
            </a>
          </div>
        </td>
        <td>
          <span class="batch-group-pill">${batchId}</span>
        </td>
      </tr>
    `;
  }).join('');
}

// File Selection Display
function updateFileNameDisplay() {
  const fileInput = document.getElementById('file-input');
  const infoBox = document.getElementById('file-selected-info');
  const textDisplay = document.getElementById('file-name-text');

  if (fileInput && fileInput.files.length > 0) {
    textDisplay.textContent = `${fileInput.files[0].name} (${(fileInput.files[0].size / 1024).toFixed(1)} KB)`;
    infoBox.style.display = 'block';
  }
}

// Upload Form Submission (POST https://findoc-ai-2c11.onrender.com/api/v1/documents/process)
async function handleDocumentUpload(e) {
  e.preventDefault();

  const fileInput = document.getElementById('file-input');
  const docTypeInput = document.getElementById('selected-document-type');
  const submitBtn = document.getElementById('process-submit-btn');
  const progressBox = document.getElementById('processing-box');
  const alertContainer = document.getElementById('alert-container');

  if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
    showAlert('Please select or drag a document file (.pdf, .jpg, .png) to process.', 'rose');
    return;
  }

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  formData.append('document_type', docTypeInput ? docTypeInput.value : activePrimaryCategory);

  progressBox.style.display = 'flex';
  if (submitBtn) submitBtn.disabled = true;
  if (alertContainer) alertContainer.innerHTML = '';

  try {
    const res = await fetch('https://findoc-ai-2c11.onrender.com/api/v1/documents/process', {
      method: 'POST',
      body: formData
    });

    const data = await res.json();

    if (!res.ok) {
      const errMsg = data.error ? data.error.message : 'Document processing failed.';
      showAlert(`Processing Error: ${errMsg}`, 'rose');
    } else {
      showAlert(`Document '${data.document_name}' processed successfully as '${formatCategoryName(data.document_type)}'! Opening result workspace...`, 'emerald');
      await loadDashboardData();
      setTimeout(() => {
        window.location.href = `view.html?doc=${encodeURIComponent(data.document_name)}`;
      }, 700);
    }
  } catch (err) {
    console.error('Processing request error:', err);
    showAlert(`Connection Error: ${err.message || 'Failed to connect to backend server endpoint.'}`, 'rose');
  } finally {
    progressBox.style.display = 'none';
    if (submitBtn) submitBtn.disabled = false;
  }
}

function formatCategoryName(type) {
  switch (type) {
    case 'invoice': return 'Invoice';
    case 'balance_sheet': return 'Balance Sheet';
    case 'profit_and_loss': return 'Profit & Loss';
    case 'cash_flow_statement': return 'Cash Flow';
    case 'po': return 'Purchase Order';
    case 'receipt': return 'Receipt';
    case 'other': return 'Other';
    case 'unknown': return 'Unknown';
    default: return type || 'Document';
  }
}

function showAlert(message, theme) {
  const alertContainer = document.getElementById('alert-container');
  if (!alertContainer) return;

  const bg = theme === 'emerald' ? 'var(--status-pass-bg)' : 'var(--status-fail-bg)';
  const border = theme === 'emerald' ? 'var(--status-pass-border)' : 'var(--status-fail-border)';
  const text = theme === 'emerald' ? 'var(--status-pass-text)' : 'var(--status-fail-text)';

  alertContainer.innerHTML = `
    <div style="background: ${bg}; border: 1px solid ${border}; color: ${text}; padding: 12px 16px; border-radius: var(--radius-md); font-size: 0.85rem; font-weight: 700; margin-top: 14px;">
      ${message}
    </div>
  `;
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
}

