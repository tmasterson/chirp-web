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
  filters: [],
  filterMatch: 'all',
  sort: 'number',
  direction: 'asc',
  hideEmpty: false,
  txFrequencyWorkflow: false,
  columns: {
    name: true, frequency: true, mode: true, shift: true, tone: true,
    power: false, comment: false, extra: false,
  },
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
  language: 'en',
  sourceJob: null,
  transferJob: null,
  focusedMemory: null,
  columnRadioId: null,
};

const $ = (selector) => document.querySelector(selector);
const notice = $('#notice');
const PREFERENCES_KEY = 'chirp-web-view-preferences';
const CONNECTION_PREFERENCES_KEY = 'chirp-web-connection-preferences';
const CONNECTION_PROFILES_KEY = 'chirp-web-connection-profiles';
const IMAGE_EXTENSIONS = /\.(img|csv|icf|dat|icf_ll)$/i;
const translations = {
  en: {
    pageTitle: 'CHIRP Web',
    localSession: 'LOCAL SESSION',
    about: 'About',
    aboutChirp: 'About CHIRP Web',
    checkReleases: 'Check for releases',
    introEyebrow: 'RADIO PROGRAMMING, SIMPLIFIED',
    introTitle: 'Make your next channel change count.',
    introText: 'Work with a radio image, shape your channel list, and transfer it when you’re ready.',
    chooseFile: 'Choose a file',
    fileTypes: 'IMG, CSV, ICF and supported formats · up to 20 MB',
    mergeFile: 'Merge channels from file',
    compareFile: 'Compare / copy from image',
    connectionProfiles: 'Connection profiles',
    chooseProfile: 'Choose a profile…',
    useProfile: 'Use',
    delete: 'Delete',
    profileNamePlaceholder: 'Profile name',
    profileNotes: 'Notes',
    profileNotesPlaceholder: 'Notes (stored only in this browser)',
    saveProfile: 'Save profile',
    exportProfiles: 'Export profiles',
    importProfiles: 'Import profiles',
    sourceHistoryEyebrow: 'SOURCE ACTIVITY',
    sourceHistory: 'Recent source jobs',
    refresh: 'Refresh',
    retry: 'Retry',
    sourceJobRestarted: 'Source job restarted.',
    sourceHistoryEmpty: 'No recent source jobs.',
    footer: 'CHIRP Web · Your radio data stays on this computer.',
    profileSaved: 'Connection profile saved.',
    profileDeleted: 'Connection profile deleted.',
    profileLoaded: 'Connection profile loaded.',
    profilesImported: 'Connection profiles imported.',
    profilesExported: 'Connection profiles exported.',
    profileNameRequired: 'Enter a profile name.',
    droppedOpen: 'Opening dropped image…',
    droppedImport: 'Merging dropped channels…',
    droppedCompare: 'Comparing dropped image…',
    invalidImageFile: 'Choose a supported image file (IMG, CSV, ICF, or DAT).',
    imageTooLarge: 'Choose an image smaller than 20 MB.',
    importTooLarge: 'Choose a channel file smaller than 20 MB.',
    openDestinationFirst: 'Open a destination image before merging channels.',
    shortcutOpen: 'Open image file picker.',
    shortcutSave: 'Saving image.',
    shortcutSearch: 'Channel search focused.',
    shortcutUndo: 'Undoing latest change.',
    shortcutRedo: 'Redoing latest change.',
    shortcutSelect: 'Visible channels selected.',
    shortcutCopy: 'Copying selected channels.',
    shortcutCut: 'Cutting selected channels.',
    shortcutPaste: 'Paste destination focused.',
    manualPort: 'Or enter a serial port',
    manualPortPlaceholder: '/dev/ttyUSB0 or COM3',
    scanUsb: 'Scan for USB radios',
    scanningUsb: 'Scanning USB ports…',
    scanComplete: 'USB scan complete.',
    languageChanged: 'Language updated.',
    supportReport: 'Support report',
    recoveryExport: 'Export recovery',
    recoveryRestore: 'Restore recovery',
    cancel: 'Cancel',
    downloadReport: 'Download report',
    reportReady: 'Support report downloaded.',
    recoveryExported: 'Recovery file downloaded.',
    recoveryRestored: 'Recovery restored.',
    sourceSearching: 'Searching the network source…',
    sourceCancelled: 'Source search cancelled.',
    cancelSearch: 'Cancel search',
    readRadio: 'Read radio',
    writeRadio: 'Write to radio',
    searchSource: 'Search source',
  },
  es: {
    pageTitle: 'CHIRP Web',
    localSession: 'SESIÓN LOCAL',
    about: 'Acerca de',
    aboutChirp: 'Acerca de CHIRP Web',
    checkReleases: 'Buscar versiones',
    introEyebrow: 'PROGRAMACIÓN DE RADIO, SIMPLIFICADA',
    introTitle: 'Haz que tu próximo cambio de canal cuente.',
    introText: 'Trabaja con una imagen de radio, organiza tu lista de canales y transfiérela cuando estés listo.',
    chooseFile: 'Elegir un archivo',
    fileTypes: 'IMG, CSV, ICF y formatos compatibles · hasta 20 MB',
    mergeFile: 'Combinar canales desde archivo',
    compareFile: 'Comparar / copiar desde imagen',
    connectionProfiles: 'Perfiles de conexión',
    chooseProfile: 'Elige un perfil…',
    useProfile: 'Usar',
    delete: 'Eliminar',
    profileNamePlaceholder: 'Nombre del perfil',
    profileNotes: 'Notas',
    profileNotesPlaceholder: 'Notas (guardadas solo en este navegador)',
    saveProfile: 'Guardar perfil',
    exportProfiles: 'Exportar perfiles',
    importProfiles: 'Importar perfiles',
    sourceHistoryEyebrow: 'ACTIVIDAD DE FUENTES',
    sourceHistory: 'Trabajos recientes de fuentes',
    refresh: 'Actualizar',
    retry: 'Reintentar',
    sourceJobRestarted: 'Trabajo de fuente reiniciado.',
    sourceHistoryEmpty: 'No hay trabajos recientes de fuentes.',
    footer: 'CHIRP Web · Los datos de tu radio permanecen en este equipo.',
    profileSaved: 'Perfil de conexión guardado.',
    profileDeleted: 'Perfil de conexión eliminado.',
    profileLoaded: 'Perfil de conexión cargado.',
    profilesImported: 'Perfiles de conexión importados.',
    profilesExported: 'Perfiles de conexión exportados.',
    profileNameRequired: 'Introduce un nombre de perfil.',
    droppedOpen: 'Abriendo imagen soltada…',
    droppedImport: 'Combinando canales soltados…',
    droppedCompare: 'Comparando imagen soltada…',
    invalidImageFile: 'Elige un archivo de imagen compatible (IMG, CSV, ICF o DAT).',
    imageTooLarge: 'Elige una imagen de menos de 20 MB.',
    importTooLarge: 'Elige un archivo de canales de menos de 20 MB.',
    openDestinationFirst: 'Abre una imagen de destino antes de combinar canales.',
    shortcutOpen: 'Selector de imagen abierto.',
    shortcutSave: 'Guardando imagen.',
    shortcutSearch: 'Búsqueda de canales enfocada.',
    shortcutUndo: 'Deshaciendo el último cambio.',
    shortcutRedo: 'Rehaciendo el último cambio.',
    shortcutSelect: 'Canales visibles seleccionados.',
    shortcutCopy: 'Copiando canales seleccionados.',
    shortcutCut: 'Cortando canales seleccionados.',
    shortcutPaste: 'Destino de pegado enfocado.',
    manualPort: 'O introduzca un puerto serie',
    manualPortPlaceholder: '/dev/ttyUSB0 o COM3',
    scanUsb: 'Buscar radios USB',
    scanningUsb: 'Buscando puertos USB…',
    scanComplete: 'Búsqueda USB terminada.',
    languageChanged: 'Idioma actualizado.',
    supportReport: 'Informe de soporte',
    recoveryExport: 'Exportar recuperación',
    recoveryRestore: 'Restaurar recuperación',
    cancel: 'Cancelar',
    downloadReport: 'Descargar informe',
    reportReady: 'Informe de soporte descargado.',
    recoveryExported: 'Archivo de recuperación descargado.',
    recoveryRestored: 'Recuperación restaurada.',
    sourceSearching: 'Buscando en la fuente de red…',
    sourceCancelled: 'Búsqueda de fuente cancelada.',
    cancelSearch: 'Cancelar búsqueda',
    readRadio: 'Leer radio',
    writeRadio: 'Escribir en radio',
    searchSource: 'Buscar fuente',
  },
};

function t(key) {
  return translations[state.language]?.[key] || translations.en[key] || key;
}

function applyTranslations() {
  document.documentElement.lang = state.language;
  document.querySelectorAll('[data-i18n]').forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach((element) => {
    element.placeholder = t(element.dataset.i18nPlaceholder);
  });
  $('#downloadButton').textContent = t('readRadio');
  $('#uploadButton').textContent = t('writeRadio');
  $('#querySource').textContent = t('searchSource');
  $('#cancelSourceQuery').textContent = t('cancelSearch');
  $('#languageSelect').value = state.language;
}

function loadPreferences() {
  const saved = loadPreferenceData();
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
  if (translations[saved.language]) state.language = saved.language;
}

function loadPreferenceData() {
  try {
    return JSON.parse(localStorage.getItem(PREFERENCES_KEY) || '{}');
  } catch {
    return {};
  }
}

function loadColumnsForSession() {
  if (!state.session || state.columnRadioId === state.session.name) return;
  const saved = loadPreferenceData();
  const columns = saved.columnsByRadio?.[state.session.name] || saved.columns;
  if (columns) {
    for (const column of Object.keys(state.columns)) {
      if (typeof columns[column] === 'boolean') state.columns[column] = columns[column];
    }
  }
  state.columnRadioId = state.session.name;
}

function savePreferences() {
  try {
    localStorage.setItem(PREFERENCES_KEY, JSON.stringify({
      hideEmpty: state.hideEmpty,
      txFrequencyWorkflow: state.txFrequencyWorkflow,
      autoBandplanEdits: state.autoBandplanEdits,
      columns: state.columns,
      columnsByRadio: {
        ...(loadPreferenceData().columnsByRadio || {}),
        ...(state.session ? { [state.session.name]: state.columns } : {}),
      },
      language: state.language,
    }));
  } catch (error) {
    showNotice(`Could not save view preferences: ${error.message}`, true);
  }
}

function loadConnectionPreferences() {
    try {
      return JSON.parse(localStorage.getItem(CONNECTION_PREFERENCES_KEY) || '{}');
    } catch {
      return {};
    }
  }

function saveConnectionPreferences() {
    try {
      const saved = loadConnectionPreferences();
      saved.radioId = $('#radioModel').value;
      saved.port = selectedPort();
      saved.recentRadioIds = [saved.radioId, ...(saved.recentRadioIds || [])]
        .filter((value, index, values) => value && values.indexOf(value) === index)
        .slice(0, 5);
      saved.recentPorts = [saved.port, ...(saved.recentPorts || [])]
        .filter((value, index, values) => value && values.indexOf(value) === index)
        .slice(0, 5);
      localStorage.setItem(CONNECTION_PREFERENCES_KEY, JSON.stringify(saved));
      renderRecentPorts(saved.recentPorts);
    } catch (error) {
      showNotice(`Could not save connection preferences: ${error.message}`, true);
    }
  }

function selectedPort() {
    return $('#manualSerialPort').value.trim() || $('#serialPort').value;
  }

function renderRecentPorts(ports = loadConnectionPreferences().recentPorts || []) {
    const list = $('#recentSerialPorts');
    list.replaceChildren(...ports.map((port) => new Option(port)));
}

function isFilteredView() {
  return Boolean(state.search || state.sort !== 'number' ||
    state.direction !== 'asc' || state.hideEmpty || state.filters.length);
}

async function api(path, options = {}) {
  const route = path.split('?', 1)[0];
  const stateful = route !== '/api/session/tabs' && (
    route.startsWith('/api/session') ||
    route.startsWith('/api/memories') ||
    route.startsWith('/api/banks') ||
    route.startsWith('/api/settings') ||
    route.startsWith('/api/bandplans') ||
    route.startsWith('/api/transfers') ||
    route === '/api/sources/import'
  );
  const liveMutation = state.session?.is_live &&
    ['POST', 'PATCH'].includes((options.method || 'GET').toUpperCase()) &&
    (route !== '/api/memories/query' && (route.startsWith('/api/memories/') ||
      ['/api/settings', '/api/banks', '/api/sources/import',
        '/api/session/import'].includes(route)));
  if (liveMutation && !window.confirm(
    'Apply this change immediately to the connected live radio?')) {
    throw new Error('Live radio edit cancelled.');
  }
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(stateful && state.activeTabId
        ? { 'X-Chirp-Tab': state.activeTabId } : {}),
      ...(liveMutation ? { 'X-Chirp-Confirm-Live': 'true' } : {}),
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
  notice.setAttribute('role', isError ? 'alert' : 'status');
  notice.classList.toggle('error', isError);
  notice.hidden = !message;
}

document.querySelectorAll('.file-trigger').forEach((trigger) => {
  trigger.addEventListener('keydown', (event) => {
    if (!['Enter', ' '].includes(event.key)) return;
    event.preventDefault();
    document.getElementById(trigger.htmlFor)?.click();
  });
});

function setBusy(busy) {
  state.busy = busy;
  $('#downloadButton').disabled = busy;
  $('#uploadButton').disabled = busy || !state.session;
  $('#saveButton').disabled = busy || !state.session || state.session.is_live;
  $('#imageFile').disabled = busy;
  $('#newConfiguration').disabled = busy;
  $('#configurationTemplate').disabled = busy;
  $('#importFile').disabled = busy;
  $('#exportCsv').disabled = busy || !state.session;
  $('#showRadioInfo').disabled = busy || !state.session;
  $('#downloadDiagnostics').disabled = busy || !state.session;
  $('#downloadBackup').disabled = busy || !state.session;
  $('#manageBackups').disabled = busy || !state.session;
  $('#supportReport').disabled = busy;
  $('#exportRecovery').disabled = busy;
  $('#restoreRecovery').disabled = busy;
  $('#compareFile').disabled = busy || !state.session;
  $('#printChannels').disabled = busy || !state.session;
  $('#outputScope').disabled = busy || !state.session;
  $('#importPlacement').disabled = busy;
  $('#importDestination').disabled = busy || $('#importPlacement').value !== 'range';
  $('#openRecent').disabled = busy || !$('#recentImages').value;
  $('#undoChange').disabled = busy || !state.history.can_undo;
  $('#redoChange').disabled = busy || !state.history.can_redo;
  $('#bandplanSelect').disabled = busy || !state.session;
  $('#radioModel').disabled = busy;
  $('#serialPort').disabled = busy;
  $('#manualSerialPort').disabled = busy;
  $('#refreshPorts').disabled = busy;
  $('#scanUsb').disabled = busy;
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
  ['filterField', 'filterOperator', 'filterValue', 'filterMatch',
    'addFilter'].forEach((id) => {
    $(`#${id}`).disabled = busy || !state.session;
  });
  $('#imageTabs').querySelectorAll('button').forEach((button) => {
    button.disabled = busy;
  });
  $('#hideEmpty').disabled = busy || !state.session;
  $('#txFrequencyWorkflow').disabled = busy || !state.session;
  $('#autoBandplanEdits').disabled = busy || !state.session;
  ['showNameColumn', 'showFrequencyColumn', 'showModeColumn',
    'showShiftColumn', 'showToneColumn', 'showPowerColumn',
    'showCommentColumn', 'showExtraColumn'].forEach((id) => {
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
    option.textContent = radio.mode === 'live'
      ? `${radio.name} (live mode)` : radio.name;
    select.append(option);
  });
  if (!radios.length) {
    select.add(new Option('No serial radios available', ''));
  }
  const saved = loadConnectionPreferences();
  const preferred = saved.radioId || saved.recentRadioIds?.[0];
  if ([...select.options].some((option) => option.value === preferred)) {
    select.value = preferred;
  }
}

function portsFromResponse(response) {
  return Array.isArray(response) ? response : response.ports || [];
}

async function loadPorts() {
  renderPorts(await api('/api/ports'));
}

function renderPorts(response) {
  const ports = portsFromResponse(response);
  const select = $('#serialPort');
  const saved = loadConnectionPreferences();
  const current = selectedPort() || saved.port;
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
  if ([...select.options].some((option) => option.value === current)) {
    select.value = current;
    $('#manualSerialPort').value = '';
  } else if (saved.port) {
    $('#manualSerialPort').value = saved.port;
  }
  renderRecentPorts(saved.recentPorts);
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
    checkbox.setAttribute('aria-label', `Select repeater ${memory.name || index + 1}`);
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
    power: ['showPowerColumn', 'power-column'],
    comment: ['showCommentColumn', 'comment-column'],
    extra: ['showExtraColumn', 'extra-column'],
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
  $('#compareSelectedTab').disabled = state.busy || !canAct ||
    !$('#compareOpenTab').value;
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
    $('#subdeviceControls').hidden = true;
    $('#loadSettings').disabled = true;
    $('#applySettings').disabled = true;
    renderBanks();
    updateImportButton();
    setBusy(false);
    return;
  }
  details.hidden = false;
  details.textContent = `${state.session.name} · ${state.session.filename}${state.session.is_live ? ' · Live edits apply immediately' : ''}${state.session.dirty ? ' · Unsaved changes' : ''}`;
  saveButton.disabled = state.busy || state.session.is_live;
  $('#exportCsv').disabled = state.busy;
  const subdeviceControls = $('#subdeviceControls');
  const subdevices = state.session.subdevices || [];
  subdeviceControls.hidden = subdevices.length < 2;
  if (!subdeviceControls.hidden) {
    const select = $('#subdeviceSelect');
    select.replaceChildren(...subdevices.map((device) =>
      new Option(device.name, String(device.index))));
    select.value = String(state.session.selected_subdevice || 0);
    select.disabled = state.busy;
  }
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

$('#subdeviceSelect').addEventListener('change', async () => {
  try {
    setBusy(true);
    const session = await api(
      `/api/session/subdevices/${encodeURIComponent($('#subdeviceSelect').value)}`,
      { method: 'POST' });
    await refreshSession(session);
    showNotice(`Switched to ${state.session.name}.`);
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
    renderSession();
  }
});

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

function extraColumnValue(nodes = []) {
  return nodes.flatMap((node) => node.type === 'group'
    ? extraColumnValue(node.children)
    : [`${node.label}: ${node.value ?? ''}`]).join('; ');
}

function renderMemories(memories) {
  const rows = $('#memoryRows');
  rows.replaceChildren();
  memories.forEach((memory) => {
    const row = document.createElement('tr');
    row.dataset.memoryNumber = String(memory.number);
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
      [memory.power_label || '—', 'power-column'],
      [memory.comment || '—', 'comment-column'],
      [extraColumnValue(memory.extra), 'extra-column'],
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
    edit.setAttribute('aria-label', `Edit channel ${memory.number}`);
    edit.addEventListener('click', () => openEditor(memory));
    actionCell.append(edit);
    row.append(actionCell);
    row.addEventListener('keydown', (event) => {
      if (!['ArrowUp', 'ArrowDown'].includes(event.key)) return;
      event.preventDefault();
      const rows = [...$('#memoryRows').querySelectorAll('tr[data-memory-number]')];
      const target = rows[rows.indexOf(row) + (event.key === 'ArrowUp' ? -1 : 1)];
      target?.querySelector('.edit-button')?.focus();
    });
    rows.append(row);
  });
  if (!memories.length) {
    rows.innerHTML = '<tr class="empty-state"><td colspan="9">No channels match this view.</td></tr>';
  }
  updateBulkControls();
  if (state.focusedMemory !== null) {
    $(`#memoryRows tr[data-memory-number="${state.focusedMemory}"] .edit-button`)?.focus();
    state.focusedMemory = null;
  }
}

async function loadMemories() {
  if (!state.session) return;
  const activeRow = document.activeElement?.closest?.(
    '#memoryRows tr[data-memory-number]');
  if (activeRow) state.focusedMemory = activeRow.dataset.memoryNumber;
  const request = ++state.memoryRequest;
  const params = new URLSearchParams({
    start: String(state.start),
    limit: String(state.limit),
    search: state.search,
    sort: state.sort,
    direction: state.direction,
    hide_empty: String(state.hideEmpty),
  });
  const result = state.filters.length
    ? await api('/api/memories/query', {
      method: 'POST',
      body: JSON.stringify({
        filters: state.filters,
        match: state.filterMatch,
        start: state.start,
        limit: state.limit,
        sort: state.sort,
        direction: state.direction,
        hide_empty: state.hideEmpty,
      }),
    })
    : await api(`/api/memories?${params}`);
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
  $('#channelCount').textContent = (state.search || state.filters.length)
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

async function refreshSession(session = null) {
  state.session = session || await api('/api/session');
  loadColumnsForSession();
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
  await refreshTabs();
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
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function renderTabs() {
  const container = $('#imageTabs');
  container.replaceChildren();
  state.tabs.forEach((tab) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'image-tab';
    button.setAttribute('aria-current', tab.id === state.activeTabId
      ? 'page' : 'false');
    button.draggable = true;
    button.textContent = `${tab.name || tab.filename}${tab.dirty ? ' •' : ''}`;
    button.title = 'Switch to image tab';
    button.addEventListener('click', () => switchTab(tab.id));
    button.addEventListener('keydown', (event) => {
      const tabs = [...container.querySelectorAll('.image-tab')];
      const index = tabs.indexOf(button);
      if (event.key === 'Home') {
        event.preventDefault();
        tabs[0]?.focus();
      } else if (event.key === 'End') {
        event.preventDefault();
        tabs.at(-1)?.focus();
      } else if (['ArrowLeft', 'ArrowRight'].includes(event.key)) {
        event.preventDefault();
        tabs[(index + (event.key === 'ArrowLeft' ? -1 : 1) + tabs.length) %
          tabs.length]?.focus();
      }
    });
    button.addEventListener('dragstart', (event) => {
      event.dataTransfer.setData('text/plain', tab.id);
      event.dataTransfer.effectAllowed = 'move';
    });
    button.addEventListener('dragover', (event) => event.preventDefault());
    button.addEventListener('drop', async (event) => {
      event.preventDefault();
      const source = event.dataTransfer.getData('text/plain');
      if (!source || source === tab.id) return;
      try {
        await reorderTab(source, tab.id);
      } catch (error) { showNotice(error.message, true); }
    });
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
    const detach = document.createElement('button');
    detach.type = 'button';
    detach.className = 'image-tab-close';
    detach.disabled = state.busy;
    detach.textContent = '↗';
    detach.setAttribute('aria-label', `Open ${tab.filename} in a new window`);
    detach.addEventListener('click', () => {
      const url = new URL(window.location.href);
      url.searchParams.set('tab', tab.id);
      window.open(url, '_blank', 'noopener');
    });
    container.append(detach);
    for (const [direction, label] of [['previous', 'Move left'], ['next', 'Move right']]) {
      const move = document.createElement('button');
      move.type = 'button';
      move.className = 'image-tab-close';
      move.disabled = state.busy ||
        (direction === 'previous' ? state.tabs[0] === tab : state.tabs.at(-1) === tab);
      move.textContent = direction === 'previous' ? '←' : '→';
      move.setAttribute('aria-label', `${label}: ${tab.filename}`);
      move.addEventListener('click', async () => {
        const index = state.tabs.indexOf(tab);
        const target = state.tabs[index + (direction === 'previous' ? -1 : 1)];
        try {
          await reorderTab(tab.id, target.id);
          $(`#imageTabs .image-tab[aria-current="page"]`)?.focus();
        } catch (error) { showNotice(error.message, true); }
      });
      container.append(move);
    }
  });
  const compare = $('#compareOpenTab');
  const selected = compare.value;
  compare.replaceChildren(new Option('Choose another open image…', ''));
  state.tabs.filter((tab) => tab.id !== state.activeTabId && tab.filename)
    .forEach((tab) => compare.add(new Option(tab.filename, tab.id)));
  compare.value = [...compare.options].some((option) => option.value === selected)
    ? selected : '';
  compare.disabled = state.busy || compare.options.length < 2;
  updateBulkControls();
}

async function reorderTab(sourceId, beforeId) {
  const order = state.tabs.map((item) => item.id);
  order.splice(order.indexOf(sourceId), 1);
  order.splice(order.indexOf(beforeId), 0, sourceId);
  await api('/api/session/tabs', {
    method: 'PUT', body: JSON.stringify({ tab_ids: order }),
  });
  await refreshTabs();
  showNotice('Image tab reordered.');
}

async function refreshTabs() {
  const result = await api('/api/session/tabs');
  state.tabs = result.tabs;
  state.activeTabId = result.active_tab_id;
  renderTabs();
}

async function switchTab(id) {
  const target = state.tabs.find((tab) => tab.id === id);
  if (!target || id === state.activeTabId || state.busy) return;
  try {
    setBusy(true);
    const session = await api(`/api/session/tabs/${encodeURIComponent(id)}/activate`, {
      method: 'POST',
    });
    state.activeTabId = id;
    await refreshSession(session);
    $(`#imageTabs .image-tab[aria-current="page"]`)?.focus();
    showNotice(`Switched to ${target.name || target.filename}.`);
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
    if (tab.dirty &&
        !window.confirm(`Close ${tab.filename} and discard its unsaved changes?`)) {
      return;
    }

    if (id !== state.activeTabId) await switchTab(id);
    if (state.activeTabId !== id) return;
    setBusy(true);
    await api('/api/session/close', { method: 'POST' });
    await refreshTabs();
    if (state.activeTabId) await refreshSession();
    else {
      state.session = null;
      renderSession();
    }
  } catch (error) { showNotice(error.message, true); }
  finally {
    setBusy(false);
    renderSession();
  }
}

$('#compareOpenTab').addEventListener('change', updateBulkControls);
$('#closeTabCompare').addEventListener('click', () => $('#tabCompareDialog').close());
$('#compareSelectedTab').addEventListener('click', async () => {
  const numbers = [...state.selected];
  const tabId = $('#compareOpenTab').value;
  if (!numbers.length || !tabId) return;
  try {
    const result = await api('/api/session/compare-tab', {
      method: 'POST', body: JSON.stringify({ tab_id: tabId, numbers }),
    });
    const container = $('#tabCompareResults');
    container.replaceChildren();
    result.comparisons.forEach((comparison) => {
      const item = document.createElement('article');
      item.className = 'comparison-item';
      const heading = document.createElement('strong');
      heading.textContent = `Channel ${comparison.number}`;
      item.append(heading);
      if (comparison.equal) {
        item.append(document.createTextNode(' — identical'));
      } else {
        Object.entries(comparison.changes).forEach(([field, value]) => {
          const line = document.createElement('p');
          line.textContent = `${field}: ${value.current ?? '—'} → ${value.other ?? '—'}`;
          item.append(line);
        });
      }
      container.append(item);
    });
    $('#tabCompareDialog').showModal();
  } catch (error) { showNotice(error.message, true); }
});

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
    const result = await api('/api/session/new', {
      method: 'POST',
      body: JSON.stringify({
        template_id: $('#configurationTemplate').value,
        confirm_replace: Boolean(state.session),
      }),
    });
    state.activeTabId = result.tab_id;
    await refreshSession();
    showNotice(`Created ${state.session.filename}.`);
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
    renderSession();
  }
});

function validateImageFile(file, message = t('imageTooLarge')) {
  if (!file || !IMAGE_EXTENSIONS.test(file.name)) {
    throw new Error(t('invalidImageFile'));
  }
  if (file.size > 20 * 1024 * 1024) throw new Error(message);
}

async function openImageFile(file) {
  try {
    validateImageFile(file);
    setBusy(true);
    showNotice(t('droppedOpen'));
    const result = await api('/api/session/open', {
      method: 'POST',
      body: JSON.stringify({
        filename: file.name, data_base64: await readFileAsBase64(file),
        confirm_replace: Boolean(state.session),
      }),
    });
    state.activeTabId = result.tab_id;
    try {
      await saveRecentImage(file);
    } catch (error) {
      showNotice(`Image opened, but the browser could not save it to recents: ${error.message}`, true);
    }
    await refreshSession();
    showNotice('Radio image opened. Your edits remain on this computer.');
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
    renderSession();
  }
}

$('#imageFile').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  event.target.value = '';
  if (!file) return;
  await openImageFile(file);
});

$('#openRecent').addEventListener('click', async () => {
  try {
    const file = await getRecentImage($('#recentImages').value);
    setBusy(true);
    const result = await api('/api/session/open', {
      method: 'POST',
      body: JSON.stringify({
        filename: file.name,
        data_base64: await readFileAsBase64(file),
        confirm_replace: Boolean(state.session),
      }),
    });
    state.activeTabId = result.tab_id;
    await refreshSession();
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

async function compareImageFile(file) {
  try {
    validateImageFile(file);
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
      checkbox.setAttribute('aria-label', `Select channel ${memory.number} to copy`);
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
}

$('#compareFile').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  event.target.value = '';
  if (!file) return;
  await compareImageFile(file);
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

function updateImportPlacement() {
  const range = $('#importPlacement').value === 'range';
  $('#importDestinationLabel').hidden = !range;
  $('#importDestination').hidden = !range;
  $('#importDestination').disabled = state.busy || !range;
}

$('#importPlacement').addEventListener('change', updateImportPlacement);

async function importChannelsFile(file) {
  try {
    validateImageFile(file, t('importTooLarge'));
    if (!state.session) throw new Error(t('openDestinationFirst'));
    const placement = $('#importPlacement').value;
    const destination = Number.parseInt($('#importDestination').value, 10);
    if (placement === 'range' && !Number.isInteger(destination)) {
      throw new Error('Enter the first destination channel for range import.');
    }
    setBusy(true);
    const result = await api('/api/session/import', {
      method: 'POST',
      body: JSON.stringify({
        filename: file.name,
        data_base64: await readFileAsBase64(file),
        placement,
        ...(placement === 'range' ? { destination_start: destination } : {}),
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
    const placementText = {
      empty: 'merged into empty slots',
      matching: 'written to matching channel numbers',
      append: 'appended after the last used channel',
      range: 'written to the destination range',
    }[placement];
    showNotice(`${result.imported} of ${result.source_count} channel${result.source_count === 1 ? '' : 's'} ${placementText}.${rejected}${warnings}`);
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    setBusy(false);
    renderSession();
  }
}

$('#importFile').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  event.target.value = '';
  if (!file) return;
  await importChannelsFile(file);
});

function outputScopePayload() {
  let scope = $('#outputScope').value;
  if (scope === 'auto') {
    scope = state.selected.size ? 'selected' :
      isFilteredView() ? 'filtered' : 'all';
  }
  if (scope === 'selected' && !state.selected.size) {
    throw new Error('Select one or more channels, or choose another print/export scope.');
  }
  return {
    scope,
    numbers: [...state.selected],
    filters: state.filters,
    match: state.filterMatch,
    search: state.search,
    sort: state.sort,
    direction: state.direction,
    hide_empty: state.hideEmpty,
  };
}

async function scopedDownload(path, payload, filename) {
  const response = await fetch(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(state.activeTabId ? { 'X-Chirp-Tab': state.activeTabId } : {}),
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || response.statusText);
  }
  downloadBlob(filename, await response.blob());
}

$('#exportCsv').addEventListener('click', async () => {
  try {
    await scopedDownload(
      '/api/session/export.csv', outputScopePayload(), 'channels.csv');
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

function downloadBlob(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

async function downloadResponse(path, filename) {
  const response = await fetch(path, {
    headers: state.activeTabId ? { 'X-Chirp-Tab': state.activeTabId } : {},
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || response.statusText);
  }
  downloadBlob(filename, await response.blob());
}

$('#showRadioInfo').addEventListener('click', async () => {
  try {
    const info = await api('/api/session/info');
    $('#radioInfoContent').textContent = JSON.stringify(info, null, 2);
    $('#radioInfoDialog').showModal();
  } catch (error) { showNotice(error.message, true); }
});
$('#closeRadioInfo').addEventListener('click', () => $('#radioInfoDialog').close());
$('#downloadDiagnostics').addEventListener('click', async () => {
  try {
    await downloadResponse('/api/session/diagnostics', 'chirp-web-diagnostics.zip');
    showNotice('Diagnostics downloaded. It contains no image or channel data.');
  } catch (error) { showNotice(error.message, true); }
});
$('#downloadBackup').addEventListener('click', async () => {
  try {
    const { backups } = await api('/api/session/backups');
    const backup = backups.at(-1);
    if (!backup) throw new Error('No transfer backup is available for this tab.');
    await downloadResponse(
      `/api/session/backups/${encodeURIComponent(backup.id)}`,
      backup.filename || 'chirp-web-backup.img');
  } catch (error) { showNotice(error.message, true); }
});

async function renderBackupManager() {
  const [settings, result] = await Promise.all([
    api('/api/session/backups/settings'),
    api('/api/session/backups'),
  ]);
  $('#backupDirectory').value = settings.directory || '';
  $('#backupRetention').value = String(settings.retention);
  const list = $('#backupList');
  list.replaceChildren();
  if (!result.backups.length) {
    list.textContent = 'No backups are available for this session.';
    return;
  }
  result.backups.slice().reverse().forEach((backup) => {
    const item = document.createElement('article');
    item.className = 'backup-item';
    const detail = document.createElement('span');
    const time = new Date(backup.created_at * 1000).toLocaleString();
    detail.textContent = `${backup.filename} · ${time} · ${
      backup.persistent ? 'retained' : 'temporary'}`;
    const download = document.createElement('button');
    download.className = 'button button-quiet';
    download.type = 'button';
    download.textContent = 'Download';
    download.addEventListener('click', () => downloadResponse(
      `/api/session/backups/${encodeURIComponent(backup.id)}`,
      backup.filename));
    item.append(detail, download);
    if (backup.persistent) {
      const restore = document.createElement('button');
      restore.className = 'button button-quiet';
      restore.type = 'button';
      restore.textContent = 'Restore as new tab';
      restore.addEventListener('click', async () => {
        try {
          const opened = await api(
            `/api/session/backups/${encodeURIComponent(backup.id)}/restore`,
            { method: 'POST' });
          state.activeTabId = opened.tab_id;
          await refreshSession(opened);
          await renderBackupManager();
          showNotice('Backup restored in a new tab.');
        } catch (error) { showNotice(error.message, true); }
      });
      const remove = document.createElement('button');
      remove.className = 'button button-quiet';
      remove.type = 'button';
      remove.textContent = 'Delete';
      remove.addEventListener('click', async () => {
        if (!window.confirm(`Delete retained backup ${backup.filename}?`)) return;
        try {
          await api(`/api/session/backups/${encodeURIComponent(backup.id)}`, {
            method: 'DELETE',
          });
          await renderBackupManager();
          showNotice('Retained backup deleted.');
        } catch (error) { showNotice(error.message, true); }
      });
      item.append(restore, remove);
    }
    list.append(item);
  });
}

$('#manageBackups').addEventListener('click', async () => {
  try {
    await renderBackupManager();
    $('#backupDialog').showModal();
  } catch (error) { showNotice(error.message, true); }
});
$('#closeBackups').addEventListener('click', () => $('#backupDialog').close());
$('#saveBackupSettings').addEventListener('click', async () => {
  const directory = $('#backupDirectory').value.trim();
  const retention = Number.parseInt($('#backupRetention').value, 10);
  if (!directory || !Number.isInteger(retention) || retention < 1 ||
      retention > 100) {
    showNotice('Enter an existing backup directory and a retention from 1 to 100.', true);
    return;
  }
  try {
    await api('/api/session/backups/settings', {
      method: 'PUT', body: JSON.stringify({ directory, retention }),
    });
    await renderBackupManager();
    showNotice('Retained backup storage configured.');
  } catch (error) { showNotice(error.message, true); }
});
$('#disableBackupStorage').addEventListener('click', async () => {
  try {
    await api('/api/session/backups/settings', {
      method: 'PUT', body: JSON.stringify({ directory: null, retention: 10 }),
    });
    await renderBackupManager();
    showNotice('New backups will be temporary only.');
  } catch (error) { showNotice(error.message, true); }
});

$('#supportReport').addEventListener('click', async () => {
  try {
    const manifest = await api('/api/session/report-manifest');
    const files = $('#supportReportFiles');
    files.replaceChildren();
    manifest.files.forEach((file) => {
      const label = document.createElement('label');
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.name = 'report-file';
      checkbox.value = file.id;
      checkbox.checked = Boolean(file.default);
      const name = document.createElement('strong');
      name.textContent = file.name;
      const description = document.createElement('small');
      description.textContent = file.description;
      label.append(checkbox, name, description);
      files.append(label);
    });
    $('#supportReportDialog').showModal();
  } catch (error) { showNotice(error.message, true); }
});
['closeSupportReport', 'cancelSupportReport'].forEach((id) => {
  $(`#${id}`).addEventListener('click', () => $('#supportReportDialog').close());
});
$('#supportReportForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const include = [...$('#supportReportFiles').querySelectorAll(':checked')]
      .map((checkbox) => checkbox.value);
    const response = await fetch('/api/session/report', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(state.activeTabId ? { 'X-Chirp-Tab': state.activeTabId } : {}),
      },
      body: JSON.stringify({ include }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || response.statusText);
    }
    downloadBlob('chirp-web-support-report.zip', await response.blob());
    $('#supportReportDialog').close();
    showNotice(t('reportReady'));
  } catch (error) { showNotice(error.message, true); }
});

$('#exportRecovery').addEventListener('click', async () => {
  try {
    const recovery = await api('/api/session/recovery/export', { method: 'POST' });
    const data = JSON.stringify(recovery, null, 2);
    downloadBlob('chirp-web-recovery.json',
      new Blob([data], { type: 'application/json' }));
    showNotice(t('recoveryExported'));
  } catch (error) { showNotice(error.message, true); }
});
$('#restoreRecovery').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  event.target.value = '';
  if (!file) return;
  try {
    const recovery = JSON.parse(await file.text());
    if (!Array.isArray(recovery.tabs)) {
      throw new Error('This is not a valid CHIRP Web recovery file.');
    }
    if (!window.confirm('Restore this recovery file? Current open tabs may be replaced.')) {
      return;
    }
    setBusy(true);
    const result = await api('/api/session/recovery/import', {
      method: 'POST', body: JSON.stringify({ tabs: recovery.tabs }),
    });
    state.activeTabId = result.active_tab_id || null;
    await refreshTabs();
    if (state.activeTabId) await refreshSession();
    else { state.session = null; renderSession(); }
    showNotice(t('recoveryRestored'));
  } catch (error) { showNotice(error.message, true); }
  finally { setBusy(false); renderSession(); }
});

$('#saveButton').addEventListener('click', async () => {
  try {
    const result = await api('/api/session/save', { method: 'POST' });
    downloadData(result.filename, result.data_base64);
    state.session.dirty = false;
    await refreshTabs();
    renderSession();
    showNotice('Image saved to your computer.');
  } catch (error) {
    showNotice(error.message, true);
  }
});

function showProgress(job) {
  $('#transferProgress').hidden = false;
  $('#progressBar').style.width = `${job.progress}%`;
  $('#progressBar').setAttribute('aria-valuenow', String(job.progress));
  $('#progressMessage').textContent = job.message;
  $('#progressPercent').textContent = `${job.progress}%`;
}

async function watchTransfer(job) {
  state.transferJob = job.id;
  $('#cancelTransfer').hidden = false;
  showProgress(job);
  while (['running', 'cancelling'].includes(job.state)) {
    await new Promise((resolve) => setTimeout(resolve, 650));
    job = await api(`/api/transfers/${job.id}`);
    showProgress(job);
  }
  state.transferJob = null;
  $('#cancelTransfer').hidden = true;
  if (job.state === 'cancelled') throw new Error('Transfer cancelled.');
  if (job.state === 'failed') throw new Error(job.error || 'Radio transfer failed.');
  await refreshSession();
  return job;
}

async function confirmTransferPrompts(operation) {
  const prompts = operation === 'upload'
    ? await api('/api/transfers/prompts/upload')
    : (await api(`/api/radios/${encodeURIComponent($('#radioModel').value)}/prompts`)).download || {};
  const messages = Object.values(prompts).filter(Boolean);
  return !messages.length || window.confirm(
    `Review these ${operation} instructions before continuing:\n\n${messages.join('\n\n')}`);
}

$('#cancelTransfer').addEventListener('click', async () => {
  if (!state.transferJob) return;
  try {
    $('#cancelTransfer').disabled = true;
    await api(`/api/transfers/${encodeURIComponent(state.transferJob)}`, {
      method: 'DELETE',
    });
    showNotice('Cancelling transfer…');
  } catch (error) {
    showNotice(error.message, true);
  }
});

$('#downloadButton').addEventListener('click', async () => {
  if (!$('#radioModel').value || !selectedPort()) {
    showNotice('Select a radio model and serial port first.', true);
    return;
  }
  const confirmReplace = Boolean(state.session?.dirty);
  if (confirmReplace && !window.confirm(
      'Reading from the radio will open a new tab. Keep this unsaved image open too?')) {
    return;
  }
  try {
    if (!await confirmTransferPrompts('download')) return;
    setBusy(true);
    $('#transferProgress').hidden = false;
    const job = await api('/api/transfers/download', {
      method: 'POST',
      body: JSON.stringify({
        radio_id: $('#radioModel').value,
        port: selectedPort(),
        confirm_replace: confirmReplace,
        confirm_prompts: true,
      }),
    });
    state.activeTabId = job.tab_id;
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
  if (!state.session || !selectedPort()) {
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
    if (!await confirmTransferPrompts('upload')) return;
    setBusy(true);
    $('#transferProgress').hidden = false;
    const job = await api('/api/transfers/upload', {
      method: 'POST',
      body: JSON.stringify({
        port: selectedPort(), confirm: true, confirm_prompts: true,
      }),
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
    const result = await api('/api/session/print', {
      method: 'POST', body: JSON.stringify(outputScopePayload()),
    });
    const memories = result.memories;
    const content = $('#printContent');
    content.replaceChildren();
    const heading = document.createElement('h1');
    heading.textContent = `${state.session.name} — ${state.session.filename}`;
    content.append(heading);
    const table = document.createElement('table');
    const columns = [
      ['CH', (memory) => memory.number],
      ...(state.columns.name ? [['NAME', (memory) => memory.name]] : []),
      ...(state.columns.frequency ? [['FREQUENCY', (memory) => formatFrequency(memory.freq)]] : []),
      ...(state.columns.mode ? [['MODE', (memory) => memory.mode]] : []),
      ...(state.columns.shift ? [['DUPLEX', (memory) => memory.duplex
        ? `${memory.duplex} ${formatFrequency(memory.offset)}` : '']] : []),
      ...(state.columns.tone ? [['TONE', (memory) => memory.tmode]] : []),
      ...(state.columns.power ? [['POWER', (memory) => memory.power_label]] : []),
      ...(state.columns.comment ? [['COMMENT', (memory) => memory.comment]] : []),
      ...(state.columns.extra ? [['DRIVER FIELDS', (memory) => extraColumnValue(memory.extra)]] : []),
    ];
    const head = document.createElement('thead');
    const header = document.createElement('tr');
    columns.forEach(([label]) => {
      const cell = document.createElement('th');
      cell.textContent = label;
      header.append(cell);
    });
    head.append(header);
    table.append(head);
    const body = document.createElement('tbody');
    memories.forEach((memory) => {
      const row = document.createElement('tr');
      columns.forEach(([, render]) => {
        const cell = document.createElement('td');
        cell.textContent = render(memory) ?? '';
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

$('#scanUsb').addEventListener('click', async () => {
  try {
    $('#portScanStatus').textContent = t('scanningUsb');
    const baseline = await api('/api/ports/baseline');
    const baselinePorts = (Array.isArray(baseline) ? baseline :
      baseline.baseline || portsFromResponse(baseline)).map((port) =>
      typeof port === 'string' ? port : port.port);
    const query = new URLSearchParams({ baseline: JSON.stringify(baselinePorts) });
    const detected = await api(`/api/ports/detect?${query}`);
    renderPorts(detected);
    $('#portScanStatus').textContent = t('scanComplete');
    showNotice(t('scanComplete'));
  } catch (error) {
    $('#portScanStatus').textContent = error.message;
    showNotice(error.message, true);
  }
});

$('#radioModel').addEventListener('change', saveConnectionPreferences);
$('#serialPort').addEventListener('change', () => {
  $('#manualSerialPort').value = '';
  saveConnectionPreferences();
});
$('#manualSerialPort').addEventListener('change', saveConnectionPreferences);

$('#sourceName').addEventListener('change', updateSourceExample);
function setSourceQueryRunning(running) {
  $('#querySource').disabled = running || state.busy;
  $('#cancelSourceQuery').hidden = !running;
}

async function watchSourceQuery(job) {
  state.sourceJob = job.id;
  setSourceQueryRunning(true);
  job = await api(`/api/sources/jobs/${encodeURIComponent(job.id)}`);
  while (state.sourceJob === job.id && ['queued', 'running', 'pending'].includes(job.state)) {
    const progress = Number.isFinite(job.progress) ? ` (${job.progress}%)` : '';
    $('#sourceStatus').textContent = `${job.message || t('sourceSearching')}${progress}`;
    await new Promise((resolve) => setTimeout(resolve, 650));
    job = await api(`/api/sources/jobs/${encodeURIComponent(job.id)}`);
  }
  if (state.sourceJob !== job.id) return null;
  state.sourceJob = null;
  setSourceQueryRunning(false);
  if (job.state === 'cancelled') {
    $('#sourceStatus').textContent = t('sourceCancelled');
    return null;
  }
  if (job.state === 'failed' || job.error) {
    throw new Error(job.error || job.message || 'Source search failed.');
  }
  return job.result;
}

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
    $('#sourceStatus').textContent = t('sourceSearching');
    const job = await api(`/api/sources/${encodeURIComponent($('#sourceName').value)}/query`, {
      method: 'POST',
      body: JSON.stringify({ params }),
    });
    const result = await watchSourceQuery(job);
    if (!result) return;
    state.sourceResults = result;
    renderSourceResults(result);
    showNotice(`${result.count.toLocaleString()} repeaters found.`);
  } catch (error) {
    $('#sourceStatus').textContent = error.message;
    showNotice(error.message, true);
  } finally {
    setSourceQueryRunning(false);
    updateImportButton();
  }
});

$('#cancelSourceQuery').addEventListener('click', async () => {
  if (!state.sourceJob) return;
  const jobId = state.sourceJob;
  try {
    await api(`/api/sources/jobs/${encodeURIComponent(jobId)}`, { method: 'DELETE' });
    state.sourceJob = null;
    setSourceQueryRunning(false);
    $('#sourceStatus').textContent = t('sourceCancelled');
  } catch (error) { showNotice(error.message, true); }
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
          await refreshTabs();
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
    await refreshTabs();
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
    await refreshTabs();
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
function renderFilters() {
  $('#activeFilters').textContent = state.filters.length
    ? state.filters.map((item) =>
      `${item.field} ${item.operator} ${Array.isArray(item.value)
        ? item.value.join(',') : item.value}`).join(` ${state.filterMatch.toUpperCase()} `)
    : '';
}

$('#addFilter').addEventListener('click', async () => {
  const field = $('#filterField').value;
  const operator = $('#filterOperator').value;
  const raw = $('#filterValue').value.trim();
  if (!field || !raw) {
    showNotice('Choose a field and enter a filter value.', true);
    return;
  }
  let value = raw;
  if (operator === 'range') {
    value = raw.split(',').map((item) => Number(item.trim()));
    if (value.length !== 2 || value.some((item) => !Number.isFinite(item))) {
      showNotice('Range filters need two numbers separated by a comma.', true);
      return;
    }
  } else if (operator === 'in') {
    value = raw.split(',').map((item) => item.trim()).filter(Boolean);
    if (!value.length) return;
  }
  state.filters.push({ field, operator, value });
  state.filterMatch = $('#filterMatch').value;
  state.start = 0;
  state.selected.clear();
  renderFilters();
  try { await loadMemories(); } catch (error) { showNotice(error.message, true); }
});
$('#activeFilters').addEventListener('click', async () => {
  if (!state.filters.length) return;
  state.filters = [];
  state.start = state.session.memory_bounds[0];
  renderFilters();
  try { await loadMemories(); } catch (error) { showNotice(error.message, true); }
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
  ['power', 'showPowerColumn'],
  ['comment', 'showCommentColumn'],
  ['extra', 'showExtraColumn'],
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

function loadConnectionProfiles() {
  try {
    const profiles = JSON.parse(localStorage.getItem(CONNECTION_PROFILES_KEY) || '[]');
    return Array.isArray(profiles) ? profiles.filter((profile) =>
      profile && typeof profile.name === 'string' && typeof profile.radioId === 'string' &&
      typeof profile.port === 'string').slice(0, 50) : [];
  } catch {
    return [];
  }
}

function saveConnectionProfiles(profiles) {
  localStorage.setItem(CONNECTION_PROFILES_KEY, JSON.stringify(profiles.slice(0, 50)));
}

function renderConnectionProfiles() {
  const select = $('#connectionProfile');
  const selected = select.value;
  select.replaceChildren(new Option(t('chooseProfile'), ''));
  loadConnectionProfiles().forEach((profile) => {
    select.add(new Option(profile.name, profile.name));
  });
  select.value = [...select.options].some((option) => option.value === selected)
    ? selected : '';
  $('#loadConnectionProfile').disabled = !select.value;
  $('#deleteConnectionProfile').disabled = !select.value;
}

function applyConnectionProfile(profile) {
  if ([...$('#radioModel').options].some((option) => option.value === profile.radioId)) {
    $('#radioModel').value = profile.radioId;
  }
  $('#manualSerialPort').value = profile.port;
  $('#serialPort').value = [...$('#serialPort').options]
    .some((option) => option.value === profile.port) ? profile.port : '';
  $('#connectionProfileNotes').value = profile.notes || '';
  saveConnectionPreferences();
}

$('#connectionProfile').addEventListener('change', () => {
  const profile = loadConnectionProfiles().find(
    (item) => item.name === $('#connectionProfile').value);
  $('#connectionProfileNotes').value = profile?.notes || '';
  $('#loadConnectionProfile').disabled = !profile;
  $('#deleteConnectionProfile').disabled = !profile;
});
$('#saveConnectionProfile').addEventListener('click', () => {
  const name = $('#connectionProfileName').value.trim();
  if (!name) return showNotice(t('profileNameRequired'), true);
  const profile = {
    name, radioId: $('#radioModel').value, port: selectedPort(),
    notes: $('#connectionProfileNotes').value.trim(),
  };
  const profiles = loadConnectionProfiles().filter((item) => item.name !== name);
  profiles.push(profile);
  try {
    saveConnectionProfiles(profiles);
    renderConnectionProfiles();
    $('#connectionProfile').value = name;
    showNotice(t('profileSaved'));
  } catch (error) { showNotice(error.message, true); }
});
$('#loadConnectionProfile').addEventListener('click', () => {
  const profile = loadConnectionProfiles().find(
    (item) => item.name === $('#connectionProfile').value);
  if (!profile) return;
  applyConnectionProfile(profile);
  showNotice(t('profileLoaded'));
});
$('#deleteConnectionProfile').addEventListener('click', () => {
  const name = $('#connectionProfile').value;
  if (!name) return;
  saveConnectionProfiles(loadConnectionProfiles().filter((item) => item.name !== name));
  renderConnectionProfiles();
  showNotice(t('profileDeleted'));
});
$('#exportConnectionProfiles').addEventListener('click', () => {
  downloadBlob('chirp-web-connection-profiles.json', new Blob([
    JSON.stringify({ profiles: loadConnectionProfiles() }, null, 2),
  ], { type: 'application/json' }));
  showNotice(t('profilesExported'));
});
$('#importConnectionProfiles').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  event.target.value = '';
  if (!file || file.size > 1024 * 1024) return;
  try {
    const value = JSON.parse(await file.text());
    const imported = Array.isArray(value) ? value : value.profiles;
    if (!Array.isArray(imported)) throw new Error('This is not a connection profile export.');
    const profiles = [...loadConnectionProfiles(), ...imported]
      .filter((item) => item && typeof item.name === 'string' &&
        typeof item.radioId === 'string' && typeof item.port === 'string')
      .map(({ name, radioId, port, notes }) => ({
        name: name.slice(0, 80), radioId, port, notes: typeof notes === 'string'
          ? notes.slice(0, 500) : '',
      }));
    saveConnectionProfiles([...new Map(profiles.map((item) => [item.name, item])).values()]);
    renderConnectionProfiles();
    showNotice(t('profilesImported'));
  } catch (error) { showNotice(error.message, true); }
});

async function loadSourceHistory() {
  const container = $('#sourceHistoryRows');
  try {
    const response = await api('/api/sources/history');
    const records = Array.isArray(response) ? response : response.records || [];
    container.replaceChildren();
    records.slice(0, 20).forEach((record) => {
      const item = document.createElement('article');
      item.className = 'history-item';
      const title = document.createElement('strong');
      title.textContent = record.source || record.source_id || 'Source job';
      const detail = document.createElement('span');
      const duration = Number.isFinite(record.duration_ms) ? ` · ${record.duration_ms} ms` : '';
      detail.textContent = `${record.state || 'unknown'} · ${record.count ?? 0} results${duration}${record.error ? ` · ${record.error}` : ''}`;
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.className = 'button button-quiet';
      retry.textContent = t('retry');
      retry.disabled = !record.id;
      retry.addEventListener('click', async () => {
        try {
          retry.disabled = true;
          await api(`/api/sources/history/${encodeURIComponent(record.id)}/retry`, {
            method: 'POST',
          });
          showNotice(t('sourceJobRestarted'));
          await loadSourceHistory();
        } catch (error) { showNotice(error.message, true); }
      });
      item.append(title, detail, retry);
      container.append(item);
    });
    $('#sourceHistoryStatus').textContent = records.length
      ? `${records.length} recent source job${records.length === 1 ? '' : 's'}.`
      : t('sourceHistoryEmpty');
  } catch (error) {
    $('#sourceHistoryStatus').textContent = error.message;
  }
}

$('#refreshSourceHistory').addEventListener('click', loadSourceHistory);
$('#showAbout').addEventListener('click', async () => {
  try {
    const about = await api('/api/about');
    const details = $('#aboutDetails');
    details.replaceChildren();
    [['Version', about.version], ['Python', about.python], ['Platform', about.platform]]
      .forEach(([label, value]) => {
        const term = document.createElement('dt');
        const description = document.createElement('dd');
        term.textContent = label;
        description.textContent = value || '—';
        details.append(term, description);
      });
    const releases = $('#checkReleases');
    releases.href = about.release_url || '#';
    releases.hidden = !about.release_url;
    $('#aboutDialog').showModal();
  } catch (error) { showNotice(error.message, true); }
});
$('#closeAbout').addEventListener('click', () => $('#aboutDialog').close());

function textInputIsFocused() {
  const focused = document.activeElement;
  return focused instanceof HTMLInputElement || focused instanceof HTMLTextAreaElement ||
    focused instanceof HTMLSelectElement || focused?.isContentEditable;
}

document.addEventListener('keydown', (event) => {
  const modifier = event.ctrlKey || event.metaKey;
  if (!modifier || event.altKey) return;
  const key = event.key.toLowerCase();
  const actions = {
    o: ['imageFile', 'shortcutOpen'],
    s: ['saveButton', 'shortcutSave'],
    f: ['channelSearch', 'shortcutSearch'],
    z: [event.shiftKey ? 'redoChange' : 'undoChange',
      event.shiftKey ? 'shortcutRedo' : 'shortcutUndo'],
  };
  if (actions[key]) {
    const [id, message] = actions[key];
    const control = $(`#${id}`);
    event.preventDefault();
    if (!control.disabled) {
      if (id === 'imageFile') control.click();
      else if (id === 'channelSearch') control.focus();
      else control.click();
      showNotice(t(message));
    }
    return;
  }
  if (textInputIsFocused()) return;
  const channelActions = { a: 'selectChannels', c: 'copySelected', x: 'cutSelected' };
  if (key === 'v') {
    event.preventDefault();
    if (!$('#pasteSelected').disabled) {
      $('#pasteSelected').click();
      showNotice(t('shortcutPaste'));
    } else if (!$('#pasteChannel').disabled) {
      $('#pasteChannel').focus();
      showNotice(t('shortcutPaste'));
    }
  } else if (channelActions[key]) {
    event.preventDefault();
    const control = $(`#${channelActions[key]}`);
    if (!control.disabled) {
      if (key === 'a') {
        control.checked = true;
        control.dispatchEvent(new Event('change', { bubbles: true }));
      } else {
        control.click();
      }
      showNotice(t(`shortcut${key === 'a' ? 'Select' : key === 'c' ? 'Copy' : 'Cut'}`));
    }
  }
});

document.addEventListener('dragover', (event) => {
  if ([...event.dataTransfer?.types || []].includes('Files')) event.preventDefault();
});
document.addEventListener('dragenter', (event) => {
  if (![...event.dataTransfer?.types || []].includes('Files')) return;
  event.preventDefault();
  event.target.closest('[data-drop-operation]')?.classList.add('drag-over');
});
document.addEventListener('dragleave', (event) => {
  event.target.closest('[data-drop-operation]')?.classList.remove('drag-over');
});
document.addEventListener('drop', async (event) => {
  const files = [...(event.dataTransfer?.files || [])];
  if (!files.length) return;
  event.preventDefault();
  const target = event.target.closest('[data-drop-operation]');
  document.querySelectorAll('.drag-over').forEach((element) =>
    element.classList.remove('drag-over'));
  const operation = target?.dataset.dropOperation || 'open';
  const file = files[0];
  showNotice(t(`dropped${operation[0].toUpperCase()}${operation.slice(1)}`));
  if (operation === 'import') await importChannelsFile(file);
  else if (operation === 'compare') await compareImageFile(file);
  else await openImageFile(file);
});

async function initialize() {
  try {
    try {
      loadPreferences();
    } catch (error) {
      showNotice(`Saved view preferences could not be loaded: ${error.message}`,
        true);
    }
    applyTranslations();
    updateImportPlacement();
    $('#languageSelect').addEventListener('change', () => {
      state.language = $('#languageSelect').value;
      savePreferences();
      applyTranslations();
      showNotice(t('scanComplete'));
    });
    await Promise.all([
      loadRadios(), loadPorts(), loadSources(), loadConfigurations(), loadSourceHistory(),
    ]);
    try {
      await loadRecentImages();
    } catch (error) {
      showNotice(`Browser recents are unavailable: ${error.message}`, true);
    }
    renderConnectionProfiles();
    try {
      const requestedTab = new URLSearchParams(window.location.search).get('tab');
      if (requestedTab) {
        state.activeTabId = requestedTab;
        const session = await api(
          `/api/session/tabs/${encodeURIComponent(requestedTab)}/activate`,
          { method: 'POST' });
        await refreshSession(session);
      } else {
        await refreshSession();
      }
      renderSession();
    } catch {
      state.session = null;
      renderSession();
    }
  } catch (error) {
    showNotice(error.message, true);
  }
}

initialize();
