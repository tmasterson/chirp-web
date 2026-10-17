/*
 * Copyright 2026 Tom Masterson <kd7cyu@gmail.com>
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

const state = {
  session: null,
  start: 0,
  limit: 50,
  total: 0,
  pageMemories: [],
  selected: new Set(),
  search: '',
  sort: 'number',
  direction: 'asc',
  hideEmpty: false,
  txFrequencyWorkflow: false,
  columns: { name: true, frequency: true, mode: true, shift: true, tone: true },
  autoBandplanEdits: false,
  memoryRequest: 0,
  busy: false,
  editing: null,
  settings: null,
  settingValues: new Map(),
  sources: [],
  sourceResults: null,
  comparison: null,
  history: { can_undo: false, can_redo: false },
  clipboardId: null,
  tabs: [],
  activeTabId: null,
};

const $ = (selector) => document.querySelector(selector);
const notice = $('#notice');
const PREFERENCES_KEY = 'chirp-web-view-preferences';

function loadPreferences() {
  const raw = localStorage.getItem(PREFERENCES_KEY);
  if (!raw) return;
  const saved = JSON.parse(raw);
  if (typeof saved.hideEmpty === 'boolean') state.hideEmpty = saved.hideEmpty;
  if (typeof saved.txFrequencyWorkflow === 'boolean') {
    state.txFrequencyWorkflow = saved.txFrequencyWorkflow;
  }
  if (typeof saved.autoBandplanEdits === 'boolean') {
    state.autoBandplanEdits = saved.autoBandplanEdits;
  }
  for (const column of Object.keys(state.columns)) {
    if (typeof saved.columns?.[column] === 'boolean') {
      state.columns[column] = saved.columns[column];
    }
  }
}

function savePreferences() {
  try {
    localStorage.setItem(PREFERENCES_KEY, JSON.stringify({
      hideEmpty: state.hideEmpty,
      txFrequencyWorkflow: state.txFrequencyWorkflow,
      autoBandplanEdits: state.autoBandplanEdits,
      columns: state.columns,
    }));
  } catch (error) {
    showNotice(`Could not save view preferences: ${error.message}`, true);
  }
}

function isFilteredView() {
  return Boolean(state.search || state.sort !== 'number' ||
    state.direction !== 'asc' || state.hideEmpty);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...options.headers,
    },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail || response.statusText));
  }
  return body;
}

function showNotice(message, isError = false) {
  notice.textContent = message;
  notice.classList.toggle('error', isError);
  notice.hidden = !message;
}

function setBusy(busy) {
  state.busy = busy;
  $('#downloadButton').disabled = busy;
  $('#uploadButton').disabled = busy || !state.session;
  $('#saveButton').disabled = busy || !state.session;
  $('#imageFile').disabled = busy;
  $('#newConfiguration').disabled = busy;
  $('#configurationTemplate').disabled = busy;
  $('#importFile').disabled = busy;
  $('#exportCsv').disabled = busy || !state.session;
  $('#compareFile').disabled = busy || !state.session;
  $('#printChannels').disabled = busy || !state.session;
  $('#openRecent').disabled = busy || !$('#recentImages').value;
  $('#undoChange').disabled = busy || !state.history.can_undo;
  $('#redoChange').disabled = busy || !state.history.can_redo;
  $('#bandplanSelect').disabled = busy || !state.session;
  $('#radioModel').disabled = busy;
  $('#serialPort').disabled = busy;
  $('#refreshPorts').disabled = busy;
  $('#sourceName').disabled = busy;
  $('#sourceFields').querySelectorAll('input, select').forEach((control) => {
    control.disabled = busy;
  });
  $('#querySource').disabled = busy;
  $('#importSources').disabled = busy || !state.sourceResults ||
    !selectedSourceIndexes().length || !state.session;
  $('#loadSettings').disabled = busy || !state.session?.has_settings;
  $('#applySettings').disabled = busy || !hasChangedSettings();
  const [low] = state.session?.memory_bounds || [0, 0];
  const filtered = isFilteredView();
  $('#previousPage').disabled = busy || state.start <= (filtered ? 0 : low);
  const pageOffset = filtered ? state.start : state.start - low;
  $('#nextPage').disabled = busy ||
    pageOffset + state.pageMemories.length >= state.total;
  $('#channelSearch').disabled = busy || !state.session;
  $('#channelSort').disabled = busy || !state.session;
  $('#channelDirection').disabled = busy || !state.session;
  $('#imageTabs').querySelectorAll('button').forEach((button) => {
    button.disabled = busy;
  });
  $('#hideEmpty').disabled = busy || !state.session;
  $('#txFrequencyWorkflow').disabled = busy || !state.session;
  $('#autoBandplanEdits').disabled = busy || !state.session;
  ['showNameColumn', 'showFrequencyColumn', 'showModeColumn',
    'showShiftColumn', 'showToneColumn'].forEach((id) => {
    $(`#${id}`).disabled = busy || !state.session;
  });
  $('#gotoChannel').disabled = busy || !state.session;
  $('#gotoButton').disabled = busy || !state.session;
  $('#arrangeField').disabled = busy || !state.session;
  $('#selectChannels').disabled = busy || !state.session ||
    !state.session.features.can_delete;
  $('#deleteShift').disabled = busy || !state.session ||
    !state.session.features.can_delete;
  updateBulkControls();
  $('#pasteSelected').disabled = busy || !state.session ||
    !state.clipboardId || $('#pasteChannel').value === '';
  $('#pasteChannel').disabled = busy || !state.session || !state.clipboardId;
}

async function loadRadios() {
  const radios = await api('/api/radios');
  const select = $('#radioModel');
  select.replaceChildren();
  radios.forEach((radio) => {
    const option = document.createElement('option');
    option.value = radio.id;
    option.textContent = radio.name;
    select.append(option);
  });
  if (!radios.length) {
    select.add(new Option('No clone-mode radios available', ''));
  }
}

async function loadPorts() {
  const ports = await api('/api/ports');
  const select = $('#serialPort');
  select.replaceChildren();
  ports.forEach((item) => {
    const option = document.createElement('option');
    option.value = item.port;
    option.textContent = item.description
      ? `${item.port} — ${item.description}`
      : item.port;
    select.append(option);
  });
  if (!ports.length) {
    select.add(new Option('No serial ports detected', ''));
  }
}

async function loadSources() {
  state.sources = await api('/api/sources');
  const select = $('#sourceName');
  select.replaceChildren();
  state.sources.forEach((source) => {
    const option = document.createElement('option');
    option.value = source.id;
    option.textContent = source.name;
    select.append(option);
  });
  if (!state.sources.length) {
    select.add(new Option('No network sources available', ''));
    return;
  }
  updateSourceExample();
}

function updateSourceExample() {
  const source = state.sources.find((item) => item.id === $('#sourceName').value);
  $('#sourceHelp').textContent = source?.help || '';
  renderSourceFields(source);
  state.sourceResults = null;
  $('#sourceResults').hidden = true;
  $('#sourceRows').replaceChildren();
  $('#selectAllSources').checked = false;
  $('#sourceStatus').textContent = 'Enter search parameters and search this source.';
  updateImportButton();
}

function renderSourceFields(source) {
  const container = $('#sourceFields');
  container.replaceChildren();
  (source?.fields || []).forEach((field) => {
    const label = document.createElement('label');
    label.className = 'source-field';
    label.textContent = field.label;
    const control = field.type === 'select'
      ? document.createElement('select')
      : document.createElement('input');
    if (field.type === 'select') {
      field.options.forEach((value) => control.add(new Option(value, value)));
    } else if (field.type === 'boolean') {
      control.type = 'checkbox';
    } else {
      control.type = field.type === 'number' ? 'number' :
        field.type === 'password' ? 'password' : 'text';
      if (field.type === 'number') control.step = 'any';
      control.placeholder = field.placeholder || '';
    }
    control.dataset.sourceField = field.name;
    control.dataset.sourceType = field.type;
    control.required = Boolean(field.required);
    const initial = field.default ?? source?.example?.[field.name];
    if (field.type === 'boolean') control.checked = Boolean(initial);
    else if (initial !== undefined) control.value = String(initial);
    label.append(control);
    container.append(label);
  });
  if (!(source?.fields || []).length) {
    const empty = document.createElement('p');
    empty.className = 'source-help';
    empty.textContent = 'This source does not need additional search parameters.';
    container.append(empty);
  }
}

function sourceParameters(source) {
  const params = {};
  for (const control of $('#sourceFields').querySelectorAll('[data-source-field]')) {
    const key = control.dataset.sourceField;
    const type = control.dataset.sourceType;
    const value = type === 'boolean' ? control.checked : control.value.trim();
    if (control.required && !value) {
      throw new Error(`${control.closest('label').firstChild.textContent} is required.`);
    }
    if (type === 'boolean') {
      params[key] = value;
    } else if (value !== '') {
      if (type === 'number') {
        if (!Number.isFinite(Number(value))) {
          throw new Error(`${control.closest('label').childNodes[0].textContent} must be a number.`);
        }
        params[key] = Number(value);
      } else if (type === 'list') {
        params[key] = value.split(',').map((item) => item.trim()).filter(Boolean);
      } else if (type === 'bands') {
        params[key] = value.split(',').map((range) => {
          const match = range.trim().match(/^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)$/);
          if (!match) throw new Error('Enter bands as comma-separated ranges, for example 144-148, 420-450.');
          const lower = Number(match[1]);
          const upper = Number(match[2]);
          if (lower <= 0 || upper <= lower) throw new Error('Each band range must have a lower frequency below its upper frequency.');
          return [lower * 1_000_000, upper * 1_000_000];
        });
      } else {
        params[key] = value;
      }
    }
  }
  if (source?.id === 'repeaterbook' && params.service) {
    params.service_display = params.service.replace(/\b\w/g, (letter) => letter.toUpperCase());
  }
  return params;
}

function selectedSourceIndexes() {
  return [...$('#sourceRows').querySelectorAll('input[type="checkbox"]:checked')]
    .map((checkbox) => Number(checkbox.value));
}

function updateImportButton() {
  const selectedCount = selectedSourceIndexes().length;
  $('#importSources').disabled = state.busy ||
    !state.sourceResults || !selectedCount || selectedCount > 1000 ||
    !state.session;
  if (selectedCount > 1000) {
    $('#sourceStatus').textContent = 'Select no more than 1,000 repeaters at once.';
  } else if (state.sourceResults) {
    $('#sourceStatus').textContent =
      `${state.sourceResults.count.toLocaleString()} repeaters found from ${state.sourceResults.source}.`;
  }
}

function renderSourceResults(result) {
  const rows = $('#sourceRows');
  rows.replaceChildren();
  result.memories.forEach((memory, index) => {
    const row = document.createElement('tr');
    const selectCell = document.createElement('td');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.value = String(index);
    checkbox.addEventListener('change', updateImportButton);
    selectCell.append(checkbox);
    row.append(selectCell);
    [
      [memory.name || '—', 'channel-name'],
      [formatFrequency(memory.freq), 'frequency'],
      [memory.mode || '—'],
      [memory.duplex ? `${memory.duplex} ${formatFrequency(memory.offset)}` : '—'],
    ].forEach(([value, className]) => {
      const cell = document.createElement('td');
      cell.textContent = value;
      if (className) cell.className = className;
      row.append(cell);
    });
    rows.append(row);
  });
  if (!result.memories.length) {
    rows.innerHTML = '<tr class="empty-state"><td colspan="5">No repeaters found.</td></tr>';
  }
  $('#selectAllSources').checked = false;
  $('#sourceResults').hidden = false;
  $('#sourceStatus').textContent = `${result.count.toLocaleString()} repeaters found from ${result.source}.`;
  updateImportButton();
}

function renderBanks() {
  const container = $('#bankModels');
  const models = state.session?.bank_models || [];
  if (!models.length) {
    container.innerHTML = '<p class="settings-status">This radio does not expose bank assignments.</p>';
    return;
  }

  container.replaceChildren();
  models.forEach((model) => {
    const card = document.createElement('div');
    card.className = 'bank-model';
    const title = document.createElement('h3');
    title.textContent = model.name;
    card.append(title);
    const list = document.createElement('div');
    list.className = 'bank-mappings';
    model.mappings.forEach((mapping) => {
      const item = document.createElement('div');
      item.className = 'bank-mapping';
      const label = document.createElement('strong');
      label.textContent = `${mapping.name ?? String(mapping.index)}`;
      if (mapping.can_rename) {
        const rename = document.createElement('button');
        rename.type = 'button';
        rename.className = 'button button-quiet';
        rename.textContent = 'Rename';
        rename.addEventListener('click', async () => {
          const name = window.prompt('Bank name', mapping.name || '');
          if (name === null || !name.trim()) return;
          try {
            await api('/api/banks', {
              method: 'PATCH',
              body: JSON.stringify({
                model: model.name, bank_index: mapping.index, name,
              }),
            });
            await refreshSession();
            showNotice(`Renamed bank to ${name.trim()}.`);
          } catch (error) { showNotice(error.message, true); }
        });
        item.append(rename);
      }
      const channels = document.createElement('span');
      const memberText = mapping.members.length
        ? mapping.members.map((value) => `#${value}`).join(', ')
        : 'No channels in this bank';
      channels.textContent = memberText;
      item.append(label, channels);
      list.append(item);
    });
    card.append(list);
    container.append(card);
  });
}

function updateBulkControls() {
  const count = state.selected.size;
  $('#deleteSelected').disabled = state.busy || !state.session ||
    !state.session.features.can_delete || count === 0 || count > 200;
  $('#deleteSelected').textContent = count > 200
    ? 'Select 200 or fewer'
    : `Delete selected${count ? ` (${count})` : ''}`;
  const visible = state.pageMemories;
  $('#selectChannels').checked = visible.length > 0 &&
    visible.every((memory) => state.selected.has(memory.number));
  $('#selectChannels').indeterminate = visible.some((memory) =>
    state.selected.has(memory.number)) && !$('#selectChannels').checked;
  $('#txFrequencyWorkflow').checked = state.txFrequencyWorkflow;
  $('#autoBandplanEdits').checked = state.autoBandplanEdits;
  const columnControls = {
    name: ['showNameColumn', 'channel-name-column'],
    frequency: ['showFrequencyColumn', 'frequency-column'],
    mode: ['showModeColumn', 'mode-column'],
    shift: ['showShiftColumn', 'shift-column'],
    tone: ['showToneColumn', 'tone-column'],
  };
  Object.entries(columnControls).forEach(([column, [id, selector]]) => {
    $(`#${id}`).checked = state.columns[column];
    document.querySelectorAll(`.${selector}`).forEach((cell) => {
      cell.hidden = !state.columns[column];
    });
  });
  const canAct = Boolean(state.session && count && count <= 200);
  const numericSelection = [...state.selected].every(
    (number) => typeof number === 'number');
  const selectedNumbers = [...state.selected].sort((a, b) => a - b);
  const canArrange = canAct && numericSelection && !isFilteredView() &&
    selectedNumbers.at(-1) - selectedNumbers[0] + 1 === count;
  $('#moveUp').disabled = state.busy || !canAct ||
    !numericSelection || isFilteredView();
  $('#moveDown').disabled = state.busy || !canAct ||
    !numericSelection || isFilteredView();
  $('#insertChannel').disabled = state.busy || !state.session ||
    isFilteredView();
  const canEditMany = Boolean(
    state.session && count > 1 && count <= 200 && numericSelection);
  $('#editSelected').disabled = state.busy || !canEditMany;
  $('#arrangeField').disabled = state.busy || !canArrange;
  $('#sortSelected').disabled = state.busy || !canArrange;
  $('#clusterSelected').disabled = state.busy || !canArrange;
  $('#copySelected').disabled = state.busy || !canAct;
  $('#cutSelected').disabled = state.busy || !canAct;
  $('#pasteSelected').disabled = state.busy || !state.session ||
    !state.clipboardId || $('#pasteChannel').value === '';
  $('#pasteChannel').disabled = state.busy || !state.session ||
    !state.clipboardId;
  document.querySelectorAll('.tx-frequency-column').forEach((column) => {
    column.hidden = !state.txFrequencyWorkflow;
  });
}

function renderSession() {
  const details = $('#sessionInfo');
  const saveButton = $('#saveButton');
  if (!state.session) {
    details.hidden = true;
    saveButton.disabled = true;
    $('#uploadButton').disabled = true;
    $('#channelTitle').textContent = 'Your channels';
    $('#channelCount').textContent = 'Open an image to begin';
    $('#memoryRows').innerHTML = '<tr class="empty-state"><td colspan="9">Your channel list will appear here after you open an image.</td></tr>';
    $('#pageLabel').textContent = '—';
    $('#exportCsv').disabled = true;
    $('#loadSettings').disabled = true;
    $('#applySettings').disabled = true;
    renderBanks();
    updateImportButton();
    setBusy(false);
    return;
  }
  details.hidden = false;
  details.textContent = `${state.session.name} · ${state.session.filename}${state.session.dirty ? ' · Unsaved changes' : ''}`;
  saveButton.disabled = state.busy;
  $('#exportCsv').disabled = state.busy;
  $('#uploadButton').disabled = state.busy || !state.session.supports_upload;
  $('#channelTitle').textContent = state.session.name;
  $('#channelCount').textContent = `${state.total.toLocaleString()} channels`;
  $('#loadSettings').disabled = state.busy || !state.session.has_settings;
  $('#applySettings').disabled = state.busy || !hasChangedSettings();
  renderBanks();
  const planSelect = $('#bandplanSelect');
  const editorPlanSelect = $('#editorBandplan');
  [planSelect, editorPlanSelect].forEach((select) => {
    select.replaceChildren();
    (state.session.features.bandplans || []).forEach((plan) => {
      select.add(new Option(plan.name, plan.id));
    });
    select.value = state.session.features.bandplan || 'north_america';
  });
  updateHistory();
  updateImportButton();
}

async function updateHistory() {
  try {
    state.history = await api('/api/session/history');
    $('#undoChange').disabled = state.busy || !state.history.can_undo;
    $('#redoChange').disabled = state.busy || !state.history.can_redo;
  } catch (error) {
    showNotice(error.message, true);
  }
}

function formatFrequency(value) {
  if (value === null || value === undefined || Number(value) === 0) return '—';
  return (Number(value) / 1_000_000).toFixed(6);
}

function txFrequency(memory) {
  if (memory.empty || !memory.freq) return null;
  if (memory.duplex === 'split') return memory.offset;
  if (memory.duplex === 'off') return null;
  return (memory.freq || 0) +
    (memory.offset || 0) * (memory.duplex === '-' ? -1 : 1);
}

function renderMemories(memories) {
  const rows = $('#memoryRows');
  rows.replaceChildren();
  memories.forEach((memory) => {
    const row = document.createElement('tr');
    const selectCell = document.createElement('td');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = state.selected.has(memory.number);
    checkbox.disabled = !state.session.features.can_delete;
    checkbox.setAttribute('aria-label', `Select channel ${memory.number}`);
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) state.selected.add(memory.number);
      else state.selected.delete(memory.number);
      updateBulkControls();
    });
    selectCell.append(checkbox);
    row.append(selectCell);
    const channelName = memory.empty ? 'Empty' : (memory.name || '—');
    const values = [
      [String(memory.number)],
      [channelName, 'channel-name channel-name-column'],
      [formatFrequency(memory.freq), 'frequency frequency-column'],
      [formatFrequency(txFrequency(memory)), 'tx-frequency-column'],
      [memory.mode || '—', 'mode-column'],
      [memory.duplex ? `${memory.duplex} ${formatFrequency(memory.offset)}` : '—', 'shift-column'],
      [memory.tmode || '—', 'tone-column'],
    ];
    values.forEach(([value, className]) => {
      const cell = document.createElement('td');
      cell.textContent = value;
      if (className) cell.className = className;
      if (className === 'tx-frequency-column') {
        cell.hidden = !state.txFrequencyWorkflow;
      }
      row.append(cell);
    });
    const actionCell = document.createElement('td');
    const edit = document.createElement('button');
    edit.className = 'edit-button';
    edit.type = 'button';
    edit.textContent = 'Edit';
    edit.addEventListener('click', () => openEditor(memory));
    actionCell.append(edit);
    row.append(actionCell);
    rows.append(row);
  });
  if (!memories.length) {
    rows.innerHTML = '<tr class="empty-state"><td colspan="9">No channels match this view.</td></tr>';
  }
  updateBulkControls();
}

async function loadMemories() {
  if (!state.session) return;
  const request = ++state.memoryRequest;
  const params = new URLSearchParams({
    start: String(state.start),
    limit: String(state.limit),
    search: state.search,
    sort: state.sort,
    direction: state.direction,
    hide_empty: String(state.hideEmpty),
  });
  const result = await api(`/api/memories?${params}`);
  if (request !== state.memoryRequest) return;
  state.pageMemories = result.memories;
  state.total = result.total;
  renderMemories(result.memories);
  const first = result.memories[0]?.number ?? result.start;
  const last = result.memories.at(-1)?.number ?? result.end - 1;
  const filtered = isFilteredView();
  $('#pageLabel').textContent = result.memories.length
    ? `${first}–${last} ${filtered ? `(${state.start + 1}–${result.end} shown)` : ''} of ${result.total}`
    : `0 of ${result.total}`;
  $('#channelCount').textContent = state.search
    ? `${result.total.toLocaleString()} matching channels`
    : `${result.total.toLocaleString()} channels`;
  const [low] = state.session.memory_bounds;
  $('#previousPage').disabled = state.busy || state.start <=
    (filtered ? 0 : low);
  const offset = filtered ? state.start : state.start - low;
  $('#nextPage').disabled = state.busy ||
    offset + result.memories.length >= result.total;
  updateBulkControls();
}

async function refreshSession() {
  state.session = await api('/api/session');
  state.selected.clear();
  state.start = isFilteredView()
    ? 0 : state.session.memory_bounds[0];
  state.settings = null;
  state.settingValues.clear();
  $('#settingsGroups').replaceChildren();
  $('#settingsChanged').hidden = true;
  $('#settingsStatus').textContent = state.session.has_settings
    ? 'Load this radio’s settings to view and edit them.'
    : 'This radio driver does not expose general settings.';
  renderSession();
  renderBanks();
  await loadMemories();
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',', 2)[1]);
    reader.onerror = () => reject(new Error('Unable to read the selected file.'));
    reader.readAsDataURL(file);
  });
}

function openRecentDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('chirp-web-images', 2);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains('images')) {
        db.createObjectStore('images', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('tabs')) {
        db.createObjectStore('tabs', { keyPath: 'id' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function readTabs() {
  const db = await openRecentDatabase();
  const tabs = await new Promise((resolve, reject) => {
    const request = db.transaction('tabs').objectStore('tabs').getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  db.close();
  return tabs.sort((a, b) => a.updated - b.updated);
}

async function saveTabSnapshot(tab) {
  const updated = Date.now();
  const snapshot = await api('/api/session/save?preserve_dirty=true', {
    method: 'POST',
  });
  const db = await openRecentDatabase();
  await new Promise((resolve, reject) => {
    const transaction = db.transaction('tabs', 'readwrite');
    transaction.objectStore('tabs').put({
      ...tab,
      filename: snapshot.filename,
      data_base64: snapshot.data_base64,
      updated,
    });
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error);
  });
  db.close();
  Object.assign(tab, snapshot);
  tab.updated = updated;
}

async function touchTab(tab) {
  tab.updated = Date.now();
  const db = await openRecentDatabase();
  await new Promise((resolve, reject) => {
    const transaction = db.transaction('tabs', 'readwrite');
    transaction.objectStore('tabs').put(tab);
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error);
  });
  db.close();
}

function renderTabs() {
  const container = $('#imageTabs');
  container.replaceChildren();
  state.tabs.forEach((tab) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'image-tab';
    button.setAttribute('aria-current',
      tab.id === state.activeTabId ? 'page' : 'false');
    button.textContent = `${tab.filename}${state.session?.dirty &&
      tab.id === state.activeTabId ? ' •' : ''}`;
    button.title = 'Switch to image tab';
    button.addEventListener('click', () => switchTab(tab.id));
    container.append(button);
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'image-tab-close';
    close.disabled = state.busy;
    close.textContent = '×';
    close.setAttribute('aria-label', `Close ${tab.filename}`);
    close.addEventListener('click', (event) => {
      event.stopPropagation();
      closeTab(tab.id);
    });
    container.append(close);
  });
}

async function addCurrentTab(filename) {
  const tab = { id: crypto.randomUUID(), filename, updated: Date.now() };
  state.tabs.push(tab);
  state.activeTabId = tab.id;
  await saveTabSnapshot(tab);
  renderTabs();
}

async function switchTab(id) {
  const target = state.tabs.find((tab) => tab.id === id);
  if (!target || id === state.activeTabId || state.busy) return;
  const current = state.tabs.find((tab) => tab.id === state.activeTabId);
  try {
    setBusy(true);
    if (current && state.session) await saveTabSnapshot(current);
    await api('/api/session/open', {
      method: 'POST',
      body: JSON.stringify({
        filename: target.filename,
        data_base64: target.data_base64,
        confirm_replace: true,
      }),
    });
    await touchTab(target);
    state.activeTabId = id;
    await refreshSession();
    renderTabs();
    showNotice(`Switched to ${target.filename}.`);
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
    renderSession();
  }
}

async function closeTab(id) {
  const tab = state.tabs.find((item) => item.id === id);
  if (!tab || state.busy) return;
  try {
    if (id === state.activeTabId && state.session?.dirty &&
        !window.confirm(`Close ${tab.filename} and discard its unsaved changes?`)) {
      return;
    }
    const db = await openRecentDatabase();
    await new Promise((resolve, reject) => {
      const transaction = db.transaction('tabs', 'readwrite');
      transaction.objectStore('tabs').delete(id);
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error);
    });
    db.close();
    state.tabs = state.tabs.filter((item) => item.id !== id);
    if (id === state.activeTabId) {
      state.activeTabId = null;
      if (state.tabs.length) {
        await switchTab(state.tabs.at(-1).id);
      } else {
        await api('/api/session/close', { method: 'POST' });
        state.session = null;
        renderSession();
      }
    }
    renderTabs();
  } catch (error) { showNotice(error.message, true); }
}

async function saveRecentImage(file) {
  const db = await openRecentDatabase();
  await new Promise((resolve, reject) => {
    const transaction = db.transaction('images', 'readwrite');
    const store = transaction.objectStore('images');
    store.put({
      id: crypto.randomUUID(), name: file.name, blob: file,
      saved: Date.now(),
    });
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error);
  });
  const all = await new Promise((resolve, reject) => {
    const request = db.transaction('images').objectStore('images').getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  all.sort((a, b) => b.saved - a.saved);
  const stale = all.slice(5);
  if (stale.length) {
    await new Promise((resolve, reject) => {
      const transaction = db.transaction('images', 'readwrite');
      stale.forEach((item) => transaction.objectStore('images').delete(item.id));
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error);
    });
  }
  db.close();
  await loadRecentImages();
}

async function getRecentImage(id) {
  const db = await openRecentDatabase();
  const item = await new Promise((resolve, reject) => {
    const request = db.transaction('images').objectStore('images').get(id);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  db.close();
  if (!item) throw new Error('The recent image is no longer available.');
  return new File([item.blob], item.name);
}

async function loadRecentImages() {
  const db = await openRecentDatabase();
  const all = await new Promise((resolve, reject) => {
    const request = db.transaction('images').objectStore('images').getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  db.close();
  all.sort((a, b) => b.saved - a.saved);
  const select = $('#recentImages');
  select.replaceChildren(new Option(
    all.length ? 'Choose a recent image…' : 'No recent images', ''));
  all.forEach((item) => select.add(new Option(item.name, item.id)));
  $('#openRecent').disabled = !select.value;
}

async function loadConfigurations() {
  const templates = await api('/api/configurations');
  const select = $('#configurationTemplate');
  select.replaceChildren(...templates.map((item) =>
    new Option(item.name, item.id)));
}

$('#newConfiguration').addEventListener('click', async () => {
  try {
    setBusy(true);
    const currentTab = state.tabs.find((tab) => tab.id === state.activeTabId);
    if (currentTab && state.session) await saveTabSnapshot(currentTab);
    await api('/api/session/new', {
      method: 'POST',
      body: JSON.stringify({
        template_id: $('#configurationTemplate').value,
        confirm_replace: Boolean(state.session),
      }),
    });
    await refreshSession();
    await addCurrentTab(state.session.filename);
    showNotice(`Created ${state.session.filename}.`);
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
    renderSession();
  }
});

$('#imageFile').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  event.target.value = '';
  if (!file) return;
  if (file.size > 20 * 1024 * 1024) {
    showNotice('Choose an image smaller than 20 MB.', true);
    return;
  }
  try {
    setBusy(true);
    showNotice('Opening radio image…');
    const currentTab = state.tabs.find((tab) => tab.id === state.activeTabId);
    if (currentTab && state.session) await saveTabSnapshot(currentTab);
    await api('/api/session/open', {
      method: 'POST',
      body: JSON.stringify({
        filename: file.name,
        data_base64: await readFileAsBase64(file),
        confirm_replace: Boolean(state.session),
      }),
    });
    try {
      await saveRecentImage(file);
    } catch (error) {
      showNotice(`Image opened, but the browser could not save it to recents: ${error.message}`, true);
    }
    await refreshSession();
    await addCurrentTab(file.name);
    renderSession();
    showNotice('Radio image opened. Your edits remain on this computer.');
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
    renderSession();
  }
});

$('#openRecent').addEventListener('click', async () => {
  try {
    const file = await getRecentImage($('#recentImages').value);
    setBusy(true);
    const currentTab = state.tabs.find((tab) => tab.id === state.activeTabId);
    if (currentTab && state.session) await saveTabSnapshot(currentTab);
    await api('/api/session/open', {
      method: 'POST',
      body: JSON.stringify({
        filename: file.name,
        data_base64: await readFileAsBase64(file),
        confirm_replace: Boolean(state.session),
      }),
    });
    await refreshSession();
    await addCurrentTab(file.name);
    showNotice('Recent image reopened.');
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
    renderSession();
  }
});

$('#recentImages').addEventListener('change', () => {
  $('#openRecent').disabled = !$('#recentImages').value || state.busy;
});

$('#compareFile').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  event.target.value = '';
  if (!file) return;
  if (file.size > 20 * 1024 * 1024) {
    showNotice('Choose an image smaller than 20 MB.', true);
    return;
  }
  try {
    setBusy(true);
    const result = await api('/api/session/compare', {
      method: 'POST',
      body: JSON.stringify({
        filename: file.name, data_base64: await readFileAsBase64(file),
      }),
    });
    state.comparison = result;
    $('#compareTitle').textContent = `Compare: ${file.name}`;
    const rows = $('#compareRows');
    rows.replaceChildren();
    result.memories.forEach((memory) => {
      const row = document.createElement('tr');
      const select = document.createElement('td');
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.value = String(memory.number);
      checkbox.addEventListener('change', updateCopyCompared);
      select.append(checkbox);
      row.append(select);
      [
        String(memory.number), memory.name || '—',
        formatFrequency(memory.freq), memory.mode || '—',
        memory.duplex ? `${memory.duplex} ${formatFrequency(memory.offset)}` : '—',
      ].forEach((value) => {
        const cell = document.createElement('td');
        cell.textContent = value;
        row.append(cell);
      });
      rows.append(row);
    });
    $('#comparePanel').hidden = false;
    updateCopyCompared();
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
  }
});

function updateCopyCompared() {
  const count = $('#compareRows').querySelectorAll('input:checked').length;
  $('#copyCompared').disabled = !state.comparison || count === 0 || count > 1000 ||
    state.busy;
  $('#copyCompared').textContent = count
    ? `Copy selected (${count})` : 'Copy selected';
}

$('#copyCompared').addEventListener('click', async () => {
  const selected = [...$('#compareRows').querySelectorAll('input:checked')]
    .map((box) => Number(box.value));
  if (!state.comparison || !selected.length) return;
  try {
    setBusy(true);
    const result = await api('/api/sources/import', {
      method: 'POST',
      body: JSON.stringify({
        query_id: state.comparison.query_id, selected,
      }),
    });
    await refreshSession();
    $('#comparePanel').hidden = true;
    state.comparison = null;
    showNotice(`${result.imported} channel${result.imported === 1 ? '' : 's'} copied into empty slots.`);
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
    renderSession();
  }
});

$('#importFile').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  event.target.value = '';
  if (!file) return;
  if (file.size > 20 * 1024 * 1024) {
    showNotice('Choose a channel file smaller than 20 MB.', true);
    return;
  }
  if (!state.session) {
    showNotice('Open a destination image before merging channels.', true);
    return;
  }
  try {
    setBusy(true);
    const result = await api('/api/session/import', {
      method: 'POST',
      body: JSON.stringify({
        filename: file.name,
        data_base64: await readFileAsBase64(file),
      }),
    });
    state.selected.clear();
    await refreshSession();
    const rejected = result.rejected.length
      ? ` ${result.rejected.length} incompatible channel${result.rejected.length === 1 ? '' : 's'} skipped.`
      : '';
    const warnings = result.warnings.length
      ? ` Driver warnings: ${result.warnings.join('; ')}`
      : '';
    showNotice(`${result.imported} of ${result.source_count} channel${result.source_count === 1 ? '' : 's'} merged into empty slots.${rejected}${warnings}`);
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
    renderSession();
  }
});

$('#exportCsv').addEventListener('click', async () => {
  try {
    const response = await fetch('/api/session/export.csv');
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || response.statusText);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'channels.csv';
    link.click();
    URL.revokeObjectURL(url);
    showNotice('Channel list exported as CSV.');
  } catch (error) {
    showNotice(error.message, true);
  }
});

function downloadData(filename, dataBase64) {
  const binary = atob(dataBase64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  const url = URL.createObjectURL(new Blob([bytes], { type: 'application/octet-stream' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

$('#saveButton').addEventListener('click', async () => {
  try {
    const result = await api('/api/session/save', { method: 'POST' });
    downloadData(result.filename, result.data_base64);
    state.session.dirty = false;
    renderSession();
    showNotice('Image saved to your computer.');
  } catch (error) {
    showNotice(error.message, true);
  }
});

function showProgress(job) {
  $('#transferProgress').hidden = false;
  $('#progressBar').style.width = `${job.progress}%`;
  $('#progressMessage').textContent = job.message;
  $('#progressPercent').textContent = `${job.progress}%`;
}

async function watchTransfer(job) {
  showProgress(job);
  while (job.state === 'running') {
    await new Promise((resolve) => setTimeout(resolve, 650));
    job = await api(`/api/transfers/${job.id}`);
    showProgress(job);
  }
  if (job.state === 'failed') throw new Error(job.error || 'Radio transfer failed.');
  await refreshSession();
  return job;
}

$('#downloadButton').addEventListener('click', async () => {
  if (!$('#radioModel').value || !$('#serialPort').value) {
    showNotice('Select a radio model and serial port first.', true);
    return;
  }
  const confirmReplace = Boolean(state.session?.dirty);
  if (confirmReplace && !window.confirm(
      'Reading from the radio will replace your unsaved image changes. Continue?')) {
    return;
  }
  try {
    setBusy(true);
    $('#transferProgress').hidden = false;
    const job = await api('/api/transfers/download', {
      method: 'POST',
      body: JSON.stringify({
        radio_id: $('#radioModel').value,
        port: $('#serialPort').value,
        confirm_replace: confirmReplace,
      }),
    });
    await watchTransfer(job);
    showNotice('Radio read complete. Review the channel list and save the image.');
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
    renderSession();
  }
});

$('#uploadButton').addEventListener('click', async () => {
  if (!state.session || !$('#serialPort').value) {
    showNotice('Open a radio image and select a serial port first.', true);
    return;
  }
  if (!state.session.supports_upload) {
    showNotice('This file format cannot be written to a radio.', true);
    return;
  }
  if (!window.confirm(`Write ${state.session.name} to the connected radio? This replaces the radio's current channel programming.`)) {
    return;
  }
  try {
    setBusy(true);
    $('#transferProgress').hidden = false;
    const job = await api('/api/transfers/upload', {
      method: 'POST',
      body: JSON.stringify({ port: $('#serialPort').value, confirm: true }),
    });
    await watchTransfer(job);
    showNotice('Radio write complete.');
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
    renderSession();
  }
});

$('#bandplanSelect').addEventListener('change', async () => {
  try {
    const result = await api('/api/bandplans', {
      method: 'PATCH',
      body: JSON.stringify({ name: $('#bandplanSelect').value }),
    });
    state.session.features.bandplan = result.selected;
    $('#editorBandplan').value = result.selected;
    showNotice('Bandplan updated for frequency defaults.');
  } catch (error) {
    showNotice(error.message, true);
  }
});

$('#editorBandplan').addEventListener('change', async () => {
  try {
    const result = await api('/api/bandplans', {
      method: 'PATCH',
      body: JSON.stringify({ name: $('#editorBandplan').value }),
    });
    state.session.features.bandplan = result.selected;
    $('#bandplanSelect').value = result.selected;
  } catch (error) { showNotice(error.message, true); }
});

async function applyBandplanDefaults(showConfirmation = true) {
  const frequency = Number($('#editFields [name="freq"]')?.value);
  if (!frequency) {
    if (showConfirmation) showNotice('Enter a receive frequency first.', true);
    return false;
  }
  try {
    const defaults = await api('/api/bandplans/defaults', {
      method: 'POST',
      body: JSON.stringify({ frequency }),
    });
    const setIfAvailable = (field, value) => {
      const control = $(`#editFields [name="${field}"]`);
      if (!control || value === null || value === undefined || value === '') return;
      if (control.tagName === 'SELECT' &&
          ![...control.options].some((option) => option.value === String(value))) {
        return;
      }
      control.value = String(value);
    };
    setIfAvailable('mode', defaults.mode);
    setIfAvailable('duplex', defaults.duplex);
    setIfAvailable('offset', defaults.offset / 1_000_000);
    const txFrequencyControl = $('#editFields [name="txfreq"]');
    if (txFrequencyControl && defaults.offset) {
      const transmitHz = defaults.duplex === 'split'
        ? defaults.offset
        : frequency * 1_000_000 +
          defaults.offset * (defaults.duplex === '-' ? -1 : 1);
      setIfAvailable('txfreq', (transmitHz / 1_000_000).toFixed(6));
    }
    setIfAvailable('tuning_step', defaults.tuning_step);
    if (defaults.tones.length && state.session.features.valid_tones.length) {
      setIfAvailable('rtone', defaults.tones[0]);
      if (state.session.features.valid_tmodes.includes('Tone')) {
        setIfAvailable('tmode', 'Tone');
      }
    }
    if (showConfirmation) {
     showNotice(
       `Applied available defaults for ${defaults.name}. Review before saving.`);
    }
    return true;
  } catch (error) {
    showNotice(error.message, true);
    return false;
  }
}

$('#applyBandplanDefaults').addEventListener('click', () => {
  applyBandplanDefaults();
});

$('#undoChange').addEventListener('click', async () => {
  try {
    await api('/api/session/undo', { method: 'POST' });
    await refreshSession();
    showNotice('Last channel change undone.');
  } catch (error) { showNotice(error.message, true); }
});

$('#redoChange').addEventListener('click', async () => {
  try {
    await api('/api/session/redo', { method: 'POST' });
    await refreshSession();
    showNotice('Channel change redone.');
  } catch (error) { showNotice(error.message, true); }
});

$('#printChannels').addEventListener('click', async () => {
  if (!state.session) return;
  try {
    const [low, high] = state.session.memory_bounds;
    const memories = [];
    for (let start = low; start <= high; start += 200) {
      const result = await api(`/api/memories?start=${start}&limit=200`);
      memories.push(...result.memories.filter((memory) => !memory.empty));
    }
    const content = $('#printContent');
    content.replaceChildren();
    const heading = document.createElement('h1');
    heading.textContent = `${state.session.name} — ${state.session.filename}`;
    content.append(heading);
    const table = document.createElement('table');
    table.innerHTML = '<thead><tr><th>CH</th><th>NAME</th><th>FREQUENCY</th><th>MODE</th><th>DUPLEX</th><th>TONE</th><th>COMMENT</th></tr></thead>';
    const body = document.createElement('tbody');
    memories.forEach((memory) => {
      const row = document.createElement('tr');
      [
        memory.number, memory.name, formatFrequency(memory.freq), memory.mode,
        memory.duplex ? `${memory.duplex} ${formatFrequency(memory.offset)}` : '',
        memory.tmode, memory.comment,
      ].forEach((value) => {
        const cell = document.createElement('td');
        cell.textContent = value ?? '';
        row.append(cell);
      });
      body.append(row);
    });
    table.append(body);
    content.append(table);
    window.print();
  } catch (error) { showNotice(error.message, true); }
});

$('#refreshPorts').addEventListener('click', async () => {
  try {
    await loadPorts();
    showNotice('Serial port list refreshed.');
  } catch (error) {
    showNotice(error.message, true);
  }
});

$('#sourceName').addEventListener('change', updateSourceExample);
$('#querySource').addEventListener('click', async () => {
  let params;
  try {
    const source = state.sources.find((item) => item.id === $('#sourceName').value);
    params = sourceParameters(source);
  } catch (error) {
    showNotice(error.message, true);
    return;
  }
  try {
    setBusy(true);
    $('#sourceStatus').textContent = 'Searching the network source…';
    const result = await api(`/api/sources/${encodeURIComponent($('#sourceName').value)}/query`, {
      method: 'POST',
      body: JSON.stringify({ params }),
    });
    state.sourceResults = result;
    renderSourceResults(result);
    showNotice(`${result.count.toLocaleString()} repeaters found.`);
  } catch (error) {
    $('#sourceStatus').textContent = error.message;
    showNotice(error.message, true);
  } finally {
    setBusy(false);
    updateImportButton();
  }
});

$('#selectAllSources').addEventListener('change', (event) => {
  $('#sourceRows').querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
    checkbox.checked = event.target.checked;
  });
  updateImportButton();
});

$('#importSources').addEventListener('click', async () => {
  if (!state.sourceResults) return;
  const selected = selectedSourceIndexes();
  if (!selected.length) return;
  try {
    setBusy(true);
    const result = await api('/api/sources/import', {
      method: 'POST',
      body: JSON.stringify({
        query_id: state.sourceResults.query_id,
        selected,
      }),
    });
    await refreshSession();
    state.start = result.start;
    await loadMemories();
    state.sourceResults = null;
    $('#sourceResults').hidden = true;
    $('#sourceStatus').textContent = `${result.imported} repeater${result.imported === 1 ? '' : 's'} imported.`;
    const skipped = result.rejected.length
      ? ` ${result.rejected.length} incompatible repeater${result.rejected.length === 1 ? '' : 's'} skipped: ${result.rejected.slice(0, 3).map((item) => `#${item.index + 1}: ${item.reason}`).join('; ')}.`
      : '';
    const warningText = result.warnings.length
      ? ` Driver warnings: ${result.warnings.join('; ')}`
      : '';
    showNotice(`${result.imported} repeater${result.imported === 1 ? '' : 's'} added to empty channels.${skipped}${warningText}`);
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
    renderSession();
  }
});

function appendControl(container, labelText, field, value, choices, options = {}) {
  const label = document.createElement('label');
  label.textContent = labelText;
  if (options.wide) label.classList.add('wide');
  const control = choices ? document.createElement('select') : document.createElement('input');
  control.name = field;
  if (choices) {
    choices.forEach((choice) => {
      const option = document.createElement('option');
      option.value = String(choice);
      option.textContent = String(choice || 'None');
      control.append(option);
    });
  } else {
    control.type = options.type || 'text';
    if (options.step) control.step = options.step;
    if (options.maxLength) control.maxLength = options.maxLength;
  }
  control.value = value === null || value === undefined ? '' : String(value);
  control.disabled = options.disabled || false;
  label.append(control);
  container.append(label);
}

function openEditor(memory) {
  state.editing = memory;
  state.editingNumbers = null;
  $('#editTitle').textContent = `Channel ${memory.number}`;
  const fields = $('#editFields');
  fields.replaceChildren();
  const features = state.session.features;
  const immutable = new Set(memory.immutable || []);
  const add = (text, key, val, choices, config = {}) =>
    appendControl(fields, text, key, val, choices, {
      ...config,
      disabled: immutable.has(key),
    });

  if (features.has_name) add('Name', 'name', memory.name, null, { maxLength: features.valid_name_length });
  add('Receive frequency (MHz)', 'freq', memory.freq ? (memory.freq / 1e6).toFixed(6) : '', null, { type: 'number', step: '0.000001' });
  $('#editFields [name="freq"]').addEventListener('change', () => {
    if (state.autoBandplanEdits) applyBandplanDefaults(false);
  });
  if (features.has_mode) add('Mode', 'mode', memory.mode, features.valid_modes);
  if (state.txFrequencyWorkflow) {
    const txfreq = txFrequency(memory);
    add('Transmit frequency (MHz)', 'txfreq',
      txfreq ? (txfreq / 1e6).toFixed(6) : '', null,
      { type: 'number', step: '0.000001' });
  } else {
    add('Duplex', 'duplex', memory.duplex, features.valid_duplexes);
    if (features.has_offset) add('Offset (MHz)', 'offset', memory.offset ? (memory.offset / 1e6).toFixed(6) : '', null, { type: 'number', step: '0.000001' });
  }
  if (features.valid_tmodes.length) add('Tone mode', 'tmode', memory.tmode, features.valid_tmodes);
  if (features.valid_tones.length) {
    add('Transmit tone', 'rtone', memory.rtone, features.valid_tones);
    if (features.has_ctone) add('Receive tone', 'ctone', memory.ctone, features.valid_tones);
  }
  if (features.has_dtcs) add('DTCS code', 'dtcs', memory.dtcs, features.valid_dtcs_codes);
  if (features.has_rx_dtcs) add('Receive DTCS', 'rx_dtcs', memory.rx_dtcs, features.valid_dtcs_codes);
  if (features.has_dtcs_polarity) add('DTCS polarity', 'dtcs_polarity', memory.dtcs_polarity, features.valid_dtcs_pols);
  if (features.has_cross) add('Cross mode', 'cross_mode', memory.cross_mode, features.valid_cross_modes);
  if (features.has_tuning_step) add('Tuning step (kHz)', 'tuning_step', memory.tuning_step, features.valid_tuning_steps);
  if (features.has_variable_power) {
    add('Transmit power (W)', 'power', memory.power, null,
      { type: 'number', step: 'any' });
  } else if (features.valid_power_levels.length) {
    const options = features.valid_power_levels.map((level) => String(level.value));
    const controlLabels = features.valid_power_levels.map((level) => level.label);
    add('Transmit power', 'power', memory.power, options);
    const powerControl = fields.querySelector('[name="power"]');
    [...powerControl.options].forEach((option, index) => {
      option.textContent = controlLabels[index];
    });
  }
  add('Scan skip', 'skip', memory.skip, features.valid_skips);
  if (features.has_comment) add('Comment', 'comment', memory.comment, null, { wide: true });
  const extraFields = $('#editExtraFields');
  extraFields.replaceChildren();
  const extraControls = (nodes, parent) => nodes.forEach((node) => {
    if (node.type === 'group') {
      const group = document.createElement('fieldset');
      group.className = 'settings-group';
      const legend = document.createElement('legend');
      legend.textContent = node.label;
      group.append(legend);
      extraControls(node.children, group);
      parent.append(group);
      return;
    }
    const label = document.createElement('label');
    label.textContent = node.label;
    let control;
    if (node.type === 'list') {
      control = document.createElement('select');
      node.options.forEach((optionValue) => {
        control.add(new Option(String(optionValue), String(optionValue)));
      });
      control.value = node.value;
    } else {
      control = document.createElement('input');
      if (node.type === 'boolean') {
        control.type = 'checkbox';
        control.checked = node.value;
      } else {
        control.type = node.type === 'integer' || node.type === 'float'
          ? 'number' : 'text';
        control.value = node.value;
        if (node.type === 'integer') control.step = String(node.step || 1);
        if (node.type === 'float') control.step = 'any';
        if (node.min !== undefined) control.min = node.min;
        if (node.max !== undefined) control.max = node.max;
        if (node.type === 'string' && node.max !== undefined) {
          control.maxLength = node.max;
        }
      }
    }
    control.dataset.extraPath = JSON.stringify(node.path);
    control.dataset.extraType = node.type;
    control.disabled = !node.mutable || memory.empty;
    label.append(control);
    if (node.warning) {
      const hint = document.createElement('small');
      hint.textContent = node.warning;
      label.append(hint);
    }
    parent.append(label);
  });
  extraControls(memory.extra || [], extraFields);
  $('#editExtra').hidden = !extraFields.querySelector('[data-extra-path]');
  const bankFields = $('#editBankFields');
  bankFields.replaceChildren();
  const bankModels = state.session.bank_models || [];
  $('#editBanks').hidden = typeof memory.number !== 'number' ||
    !bankModels.some((model) => model.mappings.length);
  bankModels.forEach((model) => {
    model.mappings.forEach((mapping) => {
      const label = document.createElement('label');
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.checked = mapping.members.includes(memory.number);
      checkbox.disabled = memory.empty;
      checkbox.addEventListener('change', async () => {
        const requested = checkbox.checked;
        checkbox.disabled = true;
        try {
          await api(`/api/memories/${encodeURIComponent(memory.number)}/banks`, {
            method: 'PATCH',
            body: JSON.stringify({
              model: model.name,
              bank_index: mapping.index,
              enabled: requested,
            }),
          });
          const result = await api('/api/banks');
          state.session.bank_models = result.models;
          state.session.dirty = true;
          renderSession();
          showNotice(`Channel ${memory.number} ${requested ? 'added to' : 'removed from'} ${mapping.name || `bank ${mapping.index}`}. Save the image to keep the change.`);
        } catch (error) {
          checkbox.checked = !requested;
          showNotice(error.message, true);
        } finally {
          checkbox.disabled = memory.empty;
        }
      });
      label.append(checkbox, document.createTextNode(
        `${model.name}: ${mapping.name || `Bank ${mapping.index}`}`));
      bankFields.append(label);
      if (model.can_index && mapping.members.includes(memory.number)) {
        const position = document.createElement('input');
        position.type = 'number';
        position.min = String(model.index_bounds[0]);
        position.max = String(model.index_bounds[1]);
        position.value = String(mapping.positions[String(memory.number)] ?? 0);
        position.setAttribute('aria-label', `${mapping.name} channel position`);
        position.addEventListener('change', async () => {
          try {
            await api('/api/banks', {
              method: 'PATCH',
              body: JSON.stringify({
                model: model.name, bank_index: mapping.index,
                memory_number: memory.number, index: Number(position.value),
              }),
            });
            await refreshSession();
            showNotice(`Channel ${memory.number} bank position updated.`);
          } catch (error) { showNotice(error.message, true); }
        });
        bankFields.append(position);
      }
    });
  });
  $('#editDialog').showModal();
}

function hasChangedSettings() {
  return [...$('#settingsGroups').querySelectorAll('[data-setting-path]')]
    .some((control) => {
      const key = control.dataset.settingPath;
      return JSON.stringify(readSettingControl(control)) !==
        JSON.stringify(state.settingValues.get(key));
    });
}

function readSettingControl(control) {
  if (control.type === 'checkbox') return control.checked;
  if (control.dataset.settingType === 'list') return JSON.parse(control.value);
  if (control.dataset.settingType === 'integer') return Number.parseInt(control.value, 10);
  if (control.dataset.settingType === 'float') return Number(control.value);
  return control.value;
}

function renderSettingNode(node, parent) {
  if (node.type === 'group') {
    const group = document.createElement('fieldset');
    group.className = 'settings-group';
    const legend = document.createElement('legend');
    legend.textContent = node.label;
    group.append(legend);
    if (node.description) {
      const description = document.createElement('p');
      description.textContent = node.description;
      group.append(description);
    }
    const fields = document.createElement('div');
    fields.className = 'settings-fields';
    node.children.forEach((child) => renderSettingNode(child, fields));
    group.append(fields);
    parent.append(group);
    return;
  }

  const field = document.createElement('label');
  field.className = 'settings-field';
  field.textContent = node.label;
  let control;
  if (node.type === 'list') {
    control = document.createElement('select');
    node.options.forEach((optionValue) => {
      const option = document.createElement('option');
      option.value = JSON.stringify(optionValue);
      option.textContent = String(optionValue);
      control.append(option);
    });
    control.value = JSON.stringify(node.value);
  } else {
    control = document.createElement('input');
    if (node.type === 'boolean') {
      control.type = 'checkbox';
      control.checked = node.value;
    } else if (node.type === 'integer' || node.type === 'float') {
      control.type = 'number';
      control.step = node.type === 'integer' ? String(node.step || 1) : 'any';
      if (node.min !== undefined) control.min = node.min;
      if (node.max !== undefined) control.max = node.max;
      control.value = String(node.value);
    } else {
      control.type = 'text';
      control.value = node.value;
      if (node.max !== undefined) control.maxLength = node.max;
    }
  }
  control.dataset.settingPath = JSON.stringify(node.path);
  control.dataset.settingType = node.type;
  control.disabled = !node.mutable;
  control.addEventListener('input', updateSettingsChanged);
  control.addEventListener('change', updateSettingsChanged);
  field.append(control);
  if (node.description || node.warning) {
    const help = document.createElement('small');
    help.textContent = [node.description, node.warning].filter(Boolean).join(' ');
    field.append(help);
  }
  parent.append(field);
  state.settingValues.set(control.dataset.settingPath, node.value);
}

function updateSettingsChanged() {
  const changed = hasChangedSettings();
  $('#settingsChanged').hidden = !changed;
  $('#applySettings').disabled = state.busy || !changed;
}

async function loadSettings() {
  const result = await api('/api/settings');
  state.settings = result;
  state.settingValues.clear();
  const groups = $('#settingsGroups');
  groups.replaceChildren();
  if (!result.supported || !result.groups.length) {
    $('#settingsStatus').textContent = result.supported
      ? 'This driver reports no editable general settings.'
      : 'This radio driver does not expose general settings.';
    updateSettingsChanged();
    return;
  }
  result.groups.forEach((group) => renderSettingNode(group, groups));
  $('#settingsStatus').textContent = 'Edit the available options, then apply them to the open radio image.';
  updateSettingsChanged();
}

$('#loadSettings').addEventListener('click', async () => {
  try {
    $('#settingsStatus').textContent = 'Reading settings from the open radio image…';
    await loadSettings();
  } catch (error) {
    $('#settingsStatus').textContent = error.message;
    showNotice(error.message, true);
  }
});

$('#applySettings').addEventListener('click', async () => {
  const changes = [...$('#settingsGroups').querySelectorAll('[data-setting-path]')]
    .filter((control) => JSON.stringify(readSettingControl(control)) !==
      JSON.stringify(state.settingValues.get(control.dataset.settingPath)))
    .map((control) => ({
      path: JSON.parse(control.dataset.settingPath),
      value: readSettingControl(control),
    }));
  if (!changes.length) return;
  const apply = async (confirmWarnings) => api('/api/settings', {
    method: 'PATCH',
    body: JSON.stringify({ changes, confirm_warnings: confirmWarnings }),
  });
  const button = $('#applySettings');
  button.disabled = true;
  try {
    let result;
    try {
      result = await apply(false);
    } catch (error) {
      if (!error.message.startsWith('Radio setting warning: ') ||
          !window.confirm(error.message)) {
        throw error;
      }
      result = await apply(true);
    }
    state.session.dirty = true;
    await loadSettings();
    renderSession();
    showNotice(result.warnings.length
      ? `Settings applied with a warning: ${result.warnings.join('; ')}`
      : 'Settings applied to the open image. Save the image or write it to the radio.');
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    updateSettingsChanged();
    renderSession();
  }
});

function closeEditor() {
  $('#editDialog').close();
  state.editing = null;
  state.editingNumbers = null;
  $('#saveMemory').textContent = 'Save channel';
}

$('#closeEditor').addEventListener('click', closeEditor);
$('#cancelEdit').addEventListener('click', closeEditor);
$('#editForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!state.editing) return;
  const submit = $('#saveMemory');
  submit.disabled = true;
  const values = {};
  new FormData(event.currentTarget).forEach((value, key) => {
    if (key === 'power' && value === '') return;
    if (key === 'txfreq' && value === '') return;
    if (key === 'extra') return;
    if (key === 'freq' || key === 'offset' || key === 'txfreq') {
      values[key] = Math.round(Number(value) * 1_000_000);
    } else if (key === 'dtcs' || key === 'rx_dtcs') {
      values[key] = Number(value);
    } else if (key === 'rtone' || key === 'ctone' || key === 'tuning_step') {
      values[key] = Number(value);
    } else if (key === 'power') {
      values[key] = Number(value);
    } else {
      values[key] = value;
    }
  });
  const extraChanges = [...$('#editExtraFields').querySelectorAll(
    '[data-extra-path]')].filter((control) => !control.disabled).map((control) => {
    const type = control.dataset.extraType;
    let value;
    if (type === 'boolean') value = control.checked;
    else if (type === 'integer') value = Number.parseInt(control.value, 10);
    else if (type === 'float') value = Number(control.value);
    else value = control.value;
    return { path: JSON.parse(control.dataset.extraPath), value };
  });
  if (extraChanges.length) values.extra_changes = extraChanges;
  try {
    const bulkNumbers = state.editingNumbers;
    const result = bulkNumbers
      ? await api('/api/memories/bulk', {
        method: 'PATCH',
        body: JSON.stringify({ numbers: bulkNumbers, changes: values }),
      })
      : await api(
        `/api/memories/${encodeURIComponent(state.editing.number)}`, {
          method: 'PATCH',
          body: JSON.stringify(values),
        });
    state.session.dirty = true;
    await loadMemories();
    closeEditor();
    const warnings = result.warnings || [];
    showNotice(warnings.length
      ? `Saved with driver warnings: ${warnings.join('; ')}`
      : bulkNumbers
        ? `Updated ${result.updated} selected channels.`
        : `Channel ${state.editing?.number ?? result.memory.number} saved.`);
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    submit.disabled = false;
    renderSession();
  }
});

$('#previousPage').addEventListener('click', async () => {
  const filtered = isFilteredView();
  state.start = Math.max(filtered ? 0 : state.session.memory_bounds[0],
    state.start - state.limit);
  try { await loadMemories(); } catch (error) { showNotice(error.message, true); }
});
$('#nextPage').addEventListener('click', async () => {
  state.start += state.limit;
  try { await loadMemories(); } catch (error) { showNotice(error.message, true); }
});

let searchTimer;
$('#channelSearch').addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    state.search = $('#channelSearch').value.trim();
    state.start = isFilteredView()
      ? 0 : state.session.memory_bounds[0];
    state.selected.clear();
    try { await loadMemories(); } catch (error) { showNotice(error.message, true); }
  }, 250);
});
$('#channelSort').addEventListener('change', async () => {
  state.sort = $('#channelSort').value;
  state.start = isFilteredView()
    ? 0 : state.session.memory_bounds[0];
  state.selected.clear();
  try { await loadMemories(); } catch (error) { showNotice(error.message, true); }
});
$('#channelDirection').addEventListener('change', async () => {
  state.direction = $('#channelDirection').value;
  state.start = 0;
  state.selected.clear();
  try { await loadMemories(); } catch (error) { showNotice(error.message, true); }
});
$('#hideEmpty').addEventListener('change', async () => {
  state.hideEmpty = $('#hideEmpty').checked;
  savePreferences();
  state.start = isFilteredView() ? 0 : state.session.memory_bounds[0];
  state.selected.clear();
  try { await loadMemories(); } catch (error) { showNotice(error.message, true); }
});
$('#txFrequencyWorkflow').addEventListener('change', () => {
  state.txFrequencyWorkflow = $('#txFrequencyWorkflow').checked;
  savePreferences();
  renderMemories(state.pageMemories);
});
$('#autoBandplanEdits').addEventListener('change', () => {
  state.autoBandplanEdits = $('#autoBandplanEdits').checked;
  savePreferences();
});
[
  ['name', 'showNameColumn'],
  ['frequency', 'showFrequencyColumn'],
  ['mode', 'showModeColumn'],
  ['shift', 'showShiftColumn'],
  ['tone', 'showToneColumn'],
].forEach(([column, id]) => {
  $(`#${id}`).addEventListener('change', () => {
    state.columns[column] = $(`#${id}`).checked;
    savePreferences();
    updateBulkControls();
  });
});
$('#editSelected').addEventListener('click', () => {
  const numbers = [...state.selected];
  if (numbers.length < 2 || numbers.length > 200) return;
  const memory = state.pageMemories.find(
    (item) => state.selected.has(item.number) && !item.empty);
  if (!memory) {
    showNotice('Select a channel visible on the current page to edit.', true);
    return;
  }
  openEditor(memory);
  state.editingNumbers = numbers;
  $('#editBanks').hidden = true;
  $('#editTitle').textContent = `Edit ${numbers.length} selected channels`;
  $('#saveMemory').textContent = `Save to ${numbers.length} channels`;
});

async function arrangeSelection(operation) {
  const numbers = [...state.selected];
  if (numbers.length < 2 || numbers.length > 200) return;
  try {
    setBusy(true);
    const result = await api('/api/memories/arrange', {
      method: 'POST',
      body: JSON.stringify({
        numbers,
        operation,
        field: $('#arrangeField').value,
        direction: 'asc',
      }),
    });
    await refreshSession();
    renderTabs();
    showNotice(operation === 'cluster'
      ? `${result.arranged} selected channels clustered into the gaps.`
      : `${result.arranged} selected channels sorted.`);
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
    renderSession();
  }
}
$('#sortSelected').addEventListener('click', () => arrangeSelection('sort'));
$('#clusterSelected').addEventListener(
  'click', () => arrangeSelection('cluster'));
$('#gotoButton').addEventListener('click', async () => {
  const number = Number.parseInt($('#gotoChannel').value, 10);
  if (!Number.isInteger(number) ||
      number < state.session.memory_bounds[0] ||
      number > state.session.memory_bounds[1]) {
    showNotice('Enter a channel number within the radio memory bounds.', true);
    return;
  }
  state.search = '';
  $('#channelSearch').value = '';
  state.sort = 'number';
  state.direction = 'asc';
  $('#channelSort').value = 'number';
  $('#channelDirection').value = 'asc';
  state.hideEmpty = false;
  $('#hideEmpty').checked = false;
  savePreferences();
  state.start = number;
  try { await loadMemories(); } catch (error) { showNotice(error.message, true); }
});
$('#gotoChannel').addEventListener('keydown', (event) => {
  if (event.key === 'Enter') $('#gotoButton').click();
});

async function applyChannelOperation(path, payload, message) {
  try {
    setBusy(true);
    await api(path, { method: 'POST', body: JSON.stringify(payload) });
    await refreshSession();
    renderTabs();
    showNotice(message);
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
    renderSession();
  }
}

$('#moveUp').addEventListener('click', () => applyChannelOperation(
  '/api/memories/move',
  { numbers: [...state.selected], direction: 'up' },
  'Selected channels moved up.'));
$('#moveDown').addEventListener('click', () => applyChannelOperation(
  '/api/memories/move',
  { numbers: [...state.selected], direction: 'down' },
  'Selected channels moved down.'));
$('#insertChannel').addEventListener('click', () => {
  const number = Number.parseInt(
    $('#gotoChannel').value || String(state.selected.values().next().value ??
      state.pageMemories[0]?.number), 10);
  if (!Number.isInteger(number)) return;
  applyChannelOperation('/api/memories/insert', { number },
    `Inserted an empty row at channel ${number}.`);
});
$('#copySelected').addEventListener('click', async () => {
  try {
    const result = await api('/api/memories/copy', {
      method: 'POST',
      body: JSON.stringify({ numbers: [...state.selected] }),
    });
    state.clipboardId = result.clipboard_id;
    showNotice(`${result.count} channel${result.count === 1 ? '' : 's'} copied. Choose a destination and paste.`);
    setBusy(false);
  } catch (error) { showNotice(error.message, true); }
});
$('#cutSelected').addEventListener('click', async () => {
  if (!window.confirm(`Cut ${state.selected.size} selected channels?`)) return;
  try {
    const result = await api('/api/memories/copy', {
      method: 'POST',
      body: JSON.stringify({ numbers: [...state.selected], cut: true }),
    });
    state.clipboardId = result.clipboard_id;
    state.selected.clear();
    await refreshSession();
    showNotice(`${result.count} channel${result.count === 1 ? '' : 's'} cut to the clipboard.`);
  } catch (error) { showNotice(error.message, true); }
});
$('#pasteChannel').addEventListener('input', () => setBusy(state.busy));
$('#pasteSelected').addEventListener('click', async () => {
  const start = Number.parseInt($('#pasteChannel').value, 10);
  if (!Number.isInteger(start) || !state.clipboardId) return;
  try {
    try {
      await api('/api/memories/paste', {
        method: 'POST',
        body: JSON.stringify({
          clipboard_id: state.clipboardId, start, overwrite: false,
        }),
      });
    } catch (error) {
      if (!error.message.includes('Confirm overwrite') ||
          !window.confirm('Paste will overwrite existing channels. Continue?')) {
        throw error;
      }
      await api('/api/memories/paste', {
        method: 'POST',
        body: JSON.stringify({
          clipboard_id: state.clipboardId, start, overwrite: true,
        }),
      });
    }
    await refreshSession();
    showNotice('Clipboard channels pasted.');
  } catch (error) {
    showNotice(error.message, true);
  }
});
$('#selectChannels').addEventListener('change', (event) => {
  state.pageMemories.forEach((memory) => {
    if (event.target.checked) state.selected.add(memory.number);
    else state.selected.delete(memory.number);
  });
  renderMemories(state.pageMemories);
});
$('#deleteSelected').addEventListener('click', async () => {
  const numbers = [...state.selected];
  if (!numbers.length || numbers.length > 200) return;
  const shift = $('#deleteShift').value;
  if (!window.confirm(`Erase ${numbers.length} selected channel${numbers.length === 1 ? '' : 's'}${shift ? ' and shift later channels up' : ''}? You can undo this before opening another image.`)) return;
  try {
    setBusy(true);
    const result = await api('/api/memories/delete', {
      method: 'POST',
      body: JSON.stringify({ numbers, shift }),
    });
    state.selected.clear();
    if (state.start && state.start >= state.total - 1) {
      state.start = Math.max(0, state.start - state.limit);
    }
    await refreshSession();
    showNotice(`${result.deleted} channel${result.deleted === 1 ? '' : 's'} erased. Save the image to keep the changes.`);
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
    renderSession();
  }
});

async function initialize() {
  try {
    try {
      loadPreferences();
    } catch (error) {
      showNotice(`Saved view preferences could not be loaded: ${error.message}`,
        true);
    }
    await Promise.all([
      loadRadios(), loadPorts(), loadSources(), loadConfigurations(),
    ]);
    try {
      await loadRecentImages();
      state.tabs = await readTabs();
      renderTabs();
    } catch (error) {
      showNotice(`Browser recents are unavailable: ${error.message}`, true);
    }
    if (state.tabs.length) {
      await switchTab(state.tabs.at(-1).id);
    } else {
      try {
        await refreshSession();
        renderSession();
      } catch {
        state.session = null;
        renderSession();
      }
    }
  } catch (error) {
    showNotice(error.message, true);
  }
}

initialize();
