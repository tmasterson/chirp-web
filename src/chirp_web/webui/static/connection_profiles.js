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

import { $, CONNECTION_PROFILES_KEY } from './state.js';
import { selectedPort } from './preferences.js';


function loadProfiles() {
  try {
    const profiles = JSON.parse(
      localStorage.getItem(CONNECTION_PROFILES_KEY) || '[]');
    return Array.isArray(profiles) ? profiles.filter((profile) =>
      profile && typeof profile.name === 'string' &&
      typeof profile.radioId === 'string' &&
      typeof profile.port === 'string').slice(0, 50) : [];
  } catch {
    return [];
  }
}

function saveProfiles(profiles) {
  localStorage.setItem(
    CONNECTION_PROFILES_KEY, JSON.stringify(profiles.slice(0, 50)));
}

export function setupConnectionProfiles({
  t, showNotice, downloadBlob, saveConnectionPreferences,
}) {
  const render = () => {
    const select = $('#connectionProfile');
    const selected = select.value;
    select.replaceChildren(new Option(t('chooseProfile'), ''));
    loadProfiles().forEach((profile) => {
      select.add(new Option(profile.name, profile.name));
    });
    select.value = [...select.options].some((option) => option.value === selected)
      ? selected : '';
    $('#loadConnectionProfile').disabled = !select.value;
    $('#deleteConnectionProfile').disabled = !select.value;
  };

  const apply = (profile) => {
    if ([...$('#radioModel').options].some(
      (option) => option.value === profile.radioId)) {
      $('#radioModel').value = profile.radioId;
    }
    $('#manualSerialPort').value = profile.port;
    $('#serialPort').value = [...$('#serialPort').options]
      .some((option) => option.value === profile.port) ? profile.port : '';
    $('#connectionProfileNotes').value = profile.notes || '';
    saveConnectionPreferences(showNotice);
  };

  $('#connectionProfile').addEventListener('change', () => {
    const profile = loadProfiles().find(
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
    const profiles = loadProfiles().filter((item) => item.name !== name);
    profiles.push(profile);
    try {
      saveProfiles(profiles);
      render();
      $('#connectionProfile').value = name;
      showNotice(t('profileSaved'));
    } catch (error) { showNotice(error.message, true); }
  });
  $('#loadConnectionProfile').addEventListener('click', () => {
    const profile = loadProfiles().find(
      (item) => item.name === $('#connectionProfile').value);
    if (!profile) return;
    apply(profile);
    showNotice(t('profileLoaded'));
  });
  $('#deleteConnectionProfile').addEventListener('click', () => {
    const name = $('#connectionProfile').value;
    if (!name) return;
    saveProfiles(loadProfiles().filter((item) => item.name !== name));
    render();
    showNotice(t('profileDeleted'));
  });
  $('#exportConnectionProfiles').addEventListener('click', () => {
    downloadBlob('chirp-web-connection-profiles.json', new Blob([
      JSON.stringify({ profiles: loadProfiles() }, null, 2),
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
      if (!Array.isArray(imported)) {
        throw new Error('This is not a connection profile export.');
      }
      const profiles = [...loadProfiles(), ...imported]
        .filter((item) => item && typeof item.name === 'string' &&
          typeof item.radioId === 'string' && typeof item.port === 'string')
        .map(({ name, radioId, port, notes }) => ({
          name: name.slice(0, 80), radioId, port,
          notes: typeof notes === 'string' ? notes.slice(0, 500) : '',
        }));
      saveProfiles(
        [...new Map(profiles.map((item) => [item.name, item])).values()]);
      render();
      showNotice(t('profilesImported'));
    } catch (error) { showNotice(error.message, true); }
  });

  render();
}
