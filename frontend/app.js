/**
 * Temporal Workflow Visualizer & Editor — Frontend Application
 */

const API_BASE = 'http://localhost:5001';

// ============================================================
// STATE
// ============================================================
const state = {
  currentView: 'analyze',
  currentWorkflow: null,   // the full workflow JSON from analysis
  currentWorkflowName: null, // the name stored in the database
  workflows: [],           // list of analyzed workflows
  components: [],          // reusable components
  chatSessionId: crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(),
  pendingChanges: null,    // changes from editor waiting to be applied
};

// ============================================================
// NAVIGATION
// ============================================================
document.querySelectorAll('.nav-item').forEach(btn => {
  btn.addEventListener('click', () => {
    const view = btn.dataset.view;
    switchView(view);
  });
});

function switchView(view) {
  state.currentView = view;
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  document.querySelector(`.nav-item[data-view="${view}"]`)?.classList.add('active');
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById(`view-${view}`)?.classList.add('active');
}

// ============================================================
// API HELPERS
// ============================================================
async function apiPost(endpoint, body) {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

async function apiGet(endpoint) {
  const res = await fetch(`${API_BASE}${endpoint}`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

// ============================================================
// TOAST NOTIFICATIONS
// ============================================================
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; toast.style.transform = 'translateX(40px)'; setTimeout(() => toast.remove(), 300); }, 4000);
}

function setStatus(elementId, message, type) {
  const el = document.getElementById(elementId);
  el.className = `status-bar ${type}`;
  el.classList.remove('hidden');
  if (type === 'loading') {
    el.innerHTML = `<div class="spinner"></div> ${message}`;
  } else {
    el.textContent = message;
  }
}

function hideStatus(elementId) {
  document.getElementById(elementId)?.classList.add('hidden');
}

// ============================================================
// ANALYZE WORKFLOW
// ============================================================
document.getElementById('btn-analyze').addEventListener('click', async () => {
  const name = document.getElementById('input-workflow-name').value.trim();
  const dir = document.getElementById('input-directory-path').value.trim();

  if (!name || !dir) {
    showToast('Please fill in both workflow name and directory path', 'error');
    return;
  }

  const btn = document.getElementById('btn-analyze');
  btn.disabled = true;
  setStatus('analyze-status', 'Analyzing workflow with AI... This may take a minute.', 'loading');

  try {
    const result = await apiPost('/api/analyze', { workflow_name: name, directory_path: dir });
    state.currentWorkflow = result.data;
    state.currentWorkflowName = name;
    setStatus('analyze-status', 'Analysis complete! Switch to Visualize to see the flow.', 'success');
    showToast('Workflow analyzed successfully!', 'success');
    loadWorkflowList();
    loadComponents();
    // Auto-switch to visualize
    setTimeout(() => switchView('visualize'), 800);
    renderWorkflow();
  } catch (err) {
    setStatus('analyze-status', `Error: ${err.message}`, 'error');
    showToast(`Analysis failed: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
  }
});

// ============================================================
// RENDER WORKFLOW FLOW DIAGRAM
// ============================================================
function renderWorkflow() {
  const canvas = document.getElementById('workflow-canvas');
  const editCanvas = document.getElementById('edit-workflow-canvas');

  if (!state.currentWorkflow?.workflow) {
    return;
  }

  const wf = state.currentWorkflow.workflow;

  // Update header
  document.getElementById('viz-title').textContent = wf.name || 'Workflow';
  document.getElementById('viz-subtitle').textContent = wf.description || wf.filePath || '';

  const html = buildFlowHTML(wf);
  canvas.innerHTML = html;
  editCanvas.innerHTML = html;
}

function buildFlowHTML(wf) {
  let html = '<div class="flow-container">';

  // START node
  html += buildStartNode(wf);
  html += connector();

  // Input schema
  if (wf.input?.fields?.length) {
    html += buildInputNode(wf.input);
    html += connector();
  }

  // Steps
  const steps = wf.steps || [];
  for (let i = 0; i < steps.length; i++) {
    html += buildStepNode(steps[i]);
    if (i < steps.length - 1) html += connector();
  }

  // END node
  html += connector();
  html += buildEndNode(wf);

  html += '</div>';
  return html;
}

function buildStartNode(wf) {
  return `<div class="flow-node flow-node-start">
    <div class="node-type-badge badge-start">Start</div>
    <div class="node-name">${esc(wf.name)}</div>
    <div class="node-meta">${esc(wf.className || '')}</div>
  </div>`;
}

function buildEndNode(wf) {
  const out = wf.output;
  let desc = '';
  if (out?.fields) desc = `Returns: ${out.fields.join(', ')}`;
  if (out?.description) desc = out.description;
  return `<div class="flow-node flow-node-end">
    <div class="node-type-badge badge-start">End</div>
    <div class="node-desc">${esc(desc)}</div>
  </div>`;
}

function buildInputNode(input) {
  let fieldsHtml = '';
  if (input.fields) {
    fieldsHtml = '<div class="input-schema">';
    for (const f of input.fields) {
      fieldsHtml += `<div class="schema-field">
        <span class="schema-field-name">${esc(f.name)}</span>
        <span class="schema-field-type">${esc(f.type)}</span>
        ${f.default ? `<span class="schema-field-default">= ${esc(f.default)}</span>` : ''}
      </div>`;
    }
    fieldsHtml += '</div>';
  }
  return `<div class="flow-node flow-node-signal">
    <div class="node-type-badge badge-signal">Input</div>
    <div class="node-name">${esc(input.dataclass || 'Input')}</div>
    ${fieldsHtml}
  </div>`;
}

function buildStepNode(step) {
  switch (step.type) {
    case 'activity': return buildActivityNode(step);
    case 'conditional': return buildConditionalNode(step);
    case 'parallel': return buildParallelNode(step);
    case 'signal': return buildSignalNode(step);
    case 'timer': return buildTimerNode(step);
    case 'childWorkflow': return buildChildWorkflowNode(step);
    default: return buildActivityNode(step);
  }
}

function buildActivityNode(step) {
  let meta = '';
  if (step.timeout) meta += `⏱ ${step.timeout}`;
  if (step.retryPolicy) meta += ` · ↻ ${step.retryPolicy.maxAttempts || '?'} retries`;
  return `<div class="flow-node flow-node-activity">
    <div class="node-type-badge badge-activity">Activity</div>
    <div class="node-name">${esc(step.name)}</div>
    <div class="node-desc">${esc(step.description || '')}</div>
    ${meta ? `<div class="node-meta">${meta}</div>` : ''}
  </div>`;
}

function buildConditionalNode(step) {
  let html = `<div class="flow-node flow-node-conditional">
    <div class="node-type-badge badge-condition">Condition</div>
    <div class="node-name" style="font-size:12px">${esc(step.condition || step.name || 'if')}</div>
    <div class="node-desc">${esc(step.description || '')}</div>
  </div>`;

  html += '<div class="branch-container" style="margin-top:8px">';

  // True branch
  html += '<div class="branch-path">';
  html += '<div class="branch-label branch-label-true">True</div>';
  const trueBranch = step.trueBranch || [];
  for (const s of trueBranch) {
    html += connector();
    html += buildStepNode(s);
  }
  if (!trueBranch.length) {
    html += connector();
    html += '<div class="flow-node flow-node-activity" style="opacity:0.4"><div class="node-desc">No action</div></div>';
  }
  html += '</div>';

  // False branch
  html += '<div class="branch-path">';
  html += '<div class="branch-label branch-label-false">False</div>';
  const falseBranch = step.falseBranch || [];
  for (const s of falseBranch) {
    html += connector();
    html += buildStepNode(s);
  }
  if (!falseBranch.length) {
    html += connector();
    html += '<div class="flow-node flow-node-activity" style="opacity:0.4"><div class="node-desc">No action</div></div>';
  }
  html += '</div>';

  html += '</div>';
  return html;
}

function buildParallelNode(step) {
  let html = `<div class="flow-node flow-node-parallel-group">
    <div class="parallel-label">⚡ Parallel Execution</div>
    <div class="parallel-tasks">`;
  for (const t of (step.tasks || [])) {
    html += buildStepNode(t);
  }
  html += '</div></div>';
  return html;
}

function buildSignalNode(step) {
  return `<div class="flow-node flow-node-signal">
    <div class="node-type-badge badge-signal">Signal</div>
    <div class="node-name">${esc(step.name)}</div>
    <div class="node-desc">${esc(step.description || '')}</div>
  </div>`;
}

function buildTimerNode(step) {
  return `<div class="flow-node flow-node-signal">
    <div class="node-type-badge badge-signal">Timer</div>
    <div class="node-name">${esc(step.name || 'Sleep')}</div>
    <div class="node-desc">${esc(step.description || '')}</div>
  </div>`;
}

function buildChildWorkflowNode(step) {
  return `<div class="flow-node flow-node-activity">
    <div class="node-type-badge badge-parallel">Child Workflow</div>
    <div class="node-name">${esc(step.name)}</div>
    <div class="node-desc">${esc(step.description || '')}</div>
  </div>`;
}

function connector() {
  return '<div class="flow-connector"></div>';
}

function esc(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = String(str);
  return div.innerHTML;
}

// ============================================================
// WORKFLOW LIST (sidebar)
// ============================================================
async function loadWorkflowList() {
  try {
    const data = await apiGet('/api/workflows');
    state.workflows = data.workflows || [];
    renderWorkflowList();
  } catch (err) {
    // silent — sidebar just stays empty
  }
}

function renderWorkflowList() {
  const container = document.getElementById('workflow-list');
  if (!state.workflows.length) {
    container.innerHTML = '<div class="empty-state-mini">No workflows analyzed yet</div>';
    return;
  }
  container.innerHTML = state.workflows.map(w => `
    <button class="workflow-list-item ${state.currentWorkflowName === w.name ? 'active' : ''}"
            onclick="selectWorkflow('${esc(w.name)}')">${esc(w.name)}</button>
  `).join('');
}

window.selectWorkflow = async function(name) {
  try {
    const data = await apiGet(`/api/workflows/${encodeURIComponent(name)}`);
    state.currentWorkflow = data.workflow_json;
    state.currentWorkflowName = name;
    renderWorkflow();
    renderWorkflowList();
    // Pre-fill trigger form
    const wf = state.currentWorkflow?.workflow;
    if (wf) {
      document.getElementById('trigger-workflow-name').value = wf.name || '';
      document.getElementById('trigger-task-queue').value = wf.taskQueue || '';
    }
    switchView('visualize');
  } catch (err) {
    showToast(`Failed to load workflow: ${err.message}`, 'error');
  }
};

// ============================================================
// COMPONENTS
// ============================================================
async function loadComponents() {
  try {
    const data = await apiGet('/api/components');
    state.components = data.components || [];
    renderComponents();
  } catch (err) {
    // silent
  }
}

function renderComponents() {
  const container = document.getElementById('components-grid');
  if (!state.components.length) {
    container.innerHTML = `<div class="empty-state">
      <svg viewBox="0 0 64 64" fill="none" class="empty-icon">
        <rect x="4" y="12" width="24" height="20" rx="4" stroke="currentColor" stroke-width="2"/>
        <rect x="36" y="12" width="24" height="20" rx="4" stroke="currentColor" stroke-width="2"/>
        <rect x="4" y="40" width="24" height="20" rx="4" stroke="currentColor" stroke-width="2"/>
        <rect x="36" y="40" width="24" height="20" rx="4" stroke="currentColor" stroke-width="2"/>
      </svg>
      <p>No components discovered</p>
      <span>Analyze a workflow to discover reusable components</span>
    </div>`;
    return;
  }
  container.innerHTML = state.components.map(c => {
    const deps = (c.dependencies || []).map(d => `<span class="dep-tag">${esc(d)}</span>`).join('');
    return `<div class="component-card">
      <div class="comp-type">${esc(c.type)}</div>
      <div class="comp-name">${esc(c.name)}</div>
      <div class="comp-desc">${esc(c.description)}</div>
      <div class="comp-path">${esc(c.file_path)}${c.line_start ? `:${c.line_start}-${c.line_end}` : ''}</div>
      ${deps ? `<div class="comp-deps">${deps}</div>` : ''}
    </div>`;
  }).join('');
}

// ============================================================
// CHAT / EDIT
// ============================================================
document.getElementById('btn-send-chat').addEventListener('click', sendChatMessage);
document.getElementById('chat-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChatMessage(); }
});

async function sendChatMessage() {
  const input = document.getElementById('chat-input');
  const message = input.value.trim();
  if (!message) return;

  const wfName = state.currentWorkflowName || state.currentWorkflow?.workflow?.name;
  if (!wfName) {
    showToast('Please analyze a workflow first before editing', 'error');
    return;
  }

  // Render user message
  appendChatMessage('user', message);
  input.value = '';

  // Loading indicator
  const loadingId = appendChatMessage('assistant', '<div class="spinner"></div> Thinking...');

  try {
    const result = await apiPost('/api/chat', {
      message,
      workflow_name: wfName,
      session_id: state.chatSessionId,
    });

    // Replace loading with response
    removeChatMessage(loadingId);

    const data = result.data;
    let responseHtml = `<p>${esc(data.explanation || 'Changes generated.')}</p>`;

    if (data.reusedComponents?.length) {
      responseHtml += `<p style="font-size:11px;color:var(--accent-emerald)">♻ Reused: ${data.reusedComponents.join(', ')}</p>`;
    }

    if (data.changes?.length) {
      responseHtml += `<p style="margin-top:8px"><strong>${data.changes.length} file(s) to change.</strong></p>`;
      state.pendingChanges = data.changes;
      responseHtml += `<button onclick="showChangesModal()" style="margin-top:8px;padding:6px 14px;background:var(--accent-emerald);border:none;border-radius:6px;color:#fff;cursor:pointer;font-size:12px;font-weight:600">Review & Apply Changes</button>`;
    }

    appendChatMessage('assistant', responseHtml, true);

  } catch (err) {
    removeChatMessage(loadingId);
    appendChatMessage('assistant', `<p style="color:var(--accent-rose)">Error: ${esc(err.message)}</p>`, true);
  }
}

let chatMsgCounter = 0;
function appendChatMessage(role, content, isHtml = false) {
  const id = `msg-${++chatMsgCounter}`;
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = `chat-message ${role}`;
  div.id = id;
  div.innerHTML = `
    <div class="message-avatar">${role === 'assistant' ? 'AI' : 'You'}</div>
    <div class="message-content">${isHtml ? content : `<p>${esc(content)}</p>`}</div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return id;
}

function removeChatMessage(id) {
  document.getElementById(id)?.remove();
}

// ============================================================
// CHANGES MODAL
// ============================================================
window.showChangesModal = function() {
  if (!state.pendingChanges) return;
  const body = document.getElementById('changes-body');
  body.innerHTML = state.pendingChanges.map(c => `
    <div class="change-item">
      <span class="change-file">${esc(c.file || c.filePath)}</span>
      <span class="change-action ${c.action}">${esc(c.action)}</span>
      <div class="change-desc">${esc(c.description)}</div>
    </div>
  `).join('');
  document.getElementById('changes-modal').classList.remove('hidden');
};

document.getElementById('btn-close-modal').addEventListener('click', () => {
  document.getElementById('changes-modal').classList.add('hidden');
});

document.getElementById('btn-discard-changes').addEventListener('click', () => {
  state.pendingChanges = null;
  document.getElementById('changes-modal').classList.add('hidden');
  showToast('Changes discarded', 'info');
});

document.getElementById('btn-apply-changes').addEventListener('click', async () => {
  if (!state.pendingChanges) return;
  try {
    await apiPost('/api/apply', { changes: state.pendingChanges });
    showToast('Changes applied successfully!', 'success');
    state.pendingChanges = null;
    document.getElementById('changes-modal').classList.add('hidden');
    appendChatMessage('assistant', '<p style="color:var(--accent-emerald)">✓ Changes applied to disk. You may want to re-analyze the workflow to see the updated visualization.</p>', true);
  } catch (err) {
    showToast(`Failed to apply: ${err.message}`, 'error');
  }
});

document.querySelector('.modal-overlay')?.addEventListener('click', () => {
  document.getElementById('changes-modal').classList.add('hidden');
});

// ============================================================
// TRIGGER WORKFLOW
// ============================================================
document.getElementById('btn-trigger').addEventListener('click', async () => {
  const name = document.getElementById('trigger-workflow-name').value.trim();
  const queue = document.getElementById('trigger-task-queue').value.trim();
  const inputRaw = document.getElementById('trigger-input').value.trim();

  if (!name || !queue) {
    showToast('Workflow name and task queue are required', 'error');
    return;
  }

  let inputData = {};
  if (inputRaw) {
    try {
      inputData = JSON.parse(inputRaw);
    } catch (e) {
      showToast('Invalid JSON input', 'error');
      return;
    }
  }

  const btn = document.getElementById('btn-trigger');
  btn.disabled = true;
  setStatus('trigger-status', 'Starting workflow...', 'loading');

  try {
    const result = await apiPost('/api/trigger', {
      workflow_name: name,
      task_queue: queue,
      input: inputData,
    });

    setStatus('trigger-status', `Workflow started! ID: ${result.workflow_id}`, 'success');
    const resultEl = document.getElementById('trigger-result');
    resultEl.classList.remove('hidden');
    resultEl.textContent = JSON.stringify(result, null, 2);
    showToast('Workflow triggered successfully!', 'success');

    // Poll status
    if (result.workflow_id) pollWorkflowStatus(result.workflow_id);
  } catch (err) {
    setStatus('trigger-status', `Error: ${err.message}`, 'error');
    showToast(`Trigger failed: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
  }
});

async function pollWorkflowStatus(workflowId) {
  const resultEl = document.getElementById('trigger-result');
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 2000));
    try {
      const st = await apiGet(`/api/trigger/${encodeURIComponent(workflowId)}/status`);
      resultEl.textContent = JSON.stringify(st, null, 2);
      if (st.status && !st.status.includes('RUNNING')) break;
    } catch {
      break;
    }
  }
}

// ============================================================
// INIT
// ============================================================
loadWorkflowList();
loadComponents();
