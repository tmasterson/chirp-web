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

import {
  $, CONNECTION_PREFERENCES_KEY, PREFERENCES_KEY, state, translations,
} from './state.js';


export function loadPreferences() {
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

export function loadPreferenceData() {
  try {
    return JSON.parse(localStorage.getItem(PREFERENCES_KEY) || '{}');
  } catch {
    return {};
  }
}

export function loadColumnsForSession() {
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

export function savePreferences(showNotice) {
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

export function loadConnectionPreferences() {
  try {
    return JSON.parse(
      localStorage.getItem(CONNECTION_PREFERENCES_KEY) || '{}');
  } catch {
    return {};
  }
}

export function selectedPort() {
  return $('#manualSerialPort').value.trim() || $('#serialPort').value;
}

export function renderRecentPorts(
    ports = loadConnectionPreferences().recentPorts || []) {
  const list = $('#recentSerialPorts');
  list.replaceChildren(...ports.map((port) => new Option(port)));
}

export function saveConnectionPreferences(showNotice) {
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
