const stateKey = 'solution_chat_state_v1';
const messagesKey = 'solution_chat_messages_v1';

const chatContainer = document.getElementById('chatContainer');
const chatForm = document.getElementById('chatForm');
const chatInput = document.getElementById('chatInput');
const resetBtn = document.getElementById('resetBtn');

const settingsBtn = document.getElementById('settingsBtn');
const settingsDialog = document.getElementById('settingsDialog');
const saveSettingsBtn = document.getElementById('saveSettingsBtn');
const clearSettingsBtn = document.getElementById('clearSettingsBtn');
const downloadTemplateBtn = document.getElementById('downloadTemplateBtn');
const blocksFile = document.getElementById('blocksFile');
const blocksInfo = document.getElementById('blocksInfo');
const apiKeyInput = document.getElementById('apiKey');
const technicalChecksInput = document.getElementById('technicalChecks');

let workflowState = JSON.parse(sessionStorage.getItem(stateKey) || '{"phase":"clarification","base_request":"","requirement_messages":[]}');
let messages = JSON.parse(sessionStorage.getItem(messagesKey) || '[]');

function saveLocal() {
  sessionStorage.setItem(stateKey, JSON.stringify(workflowState));
  sessionStorage.setItem(messagesKey, JSON.stringify(messages));
}

function addMessage(role, content) {
  messages.push({ role, content });
  saveLocal();
  renderMessages();
}

function renderMessages() {
  chatContainer.innerHTML = '';
  for (const m of messages) {
    const div = document.createElement('div');
    div.className = `msg ${m.role}`;
    div.textContent = m.content;
    chatContainer.appendChild(div);
  }
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

async function loadSettings() {
  const res = await fetch('/api/settings');
  const data = await res.json();
  apiKeyInput.value = data.api_key || '';
  technicalChecksInput.value = data.technical_checks || '';
  blocksInfo.textContent = `Loaded blocks from catalog: ${data.blocks_count}`;
}

settingsBtn.addEventListener('click', async () => {
  await loadSettings();
  settingsDialog.showModal();
});

saveSettingsBtn.addEventListener('click', async () => {
  await fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKeyInput.value, technical_checks: technicalChecksInput.value }),
  });

  if (blocksFile.files.length > 0) {
    const fd = new FormData();
    fd.append('file', blocksFile.files[0]);
    const r = await fetch('/api/blocks/upload', { method: 'POST', body: fd });
    const blockResp = await r.json();
    if (!r.ok) {
      alert(blockResp.error || 'Unable to upload blocks CSV');
      return;
    }
  }

  await loadSettings();
  alert('Settings saved successfully');
});

clearSettingsBtn.addEventListener('click', async () => {
  await fetch('/api/settings/clear', { method: 'POST' });
  apiKeyInput.value = '';
  technicalChecksInput.value = '';
  await loadSettings();
});

downloadTemplateBtn.addEventListener('click', () => {
  window.location.href = '/api/blocks/template';
});

chatForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  chatInput.value = '';
  addMessage('user', text);

  const r = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_input: text, state: workflowState }),
  });
  const data = await r.json();
  if (!r.ok) {
    addMessage('assistant', data.error || 'Unknown error');
    return;
  }

  workflowState = data.state;
  for (const msg of data.assistant_messages) {
    addMessage('assistant', msg);
  }
});

resetBtn.addEventListener('click', () => {
  workflowState = { phase: 'clarification', base_request: '', requirement_messages: [] };
  messages = [];
  saveLocal();
  renderMessages();
});

renderMessages();
