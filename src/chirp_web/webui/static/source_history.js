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

import { $ } from './state.js';


export function setupSourceHistory({ api, t, showNotice }) {
  const load = async () => {
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
        const duration = Number.isFinite(record.duration_ms)
          ? ` · ${record.duration_ms} ms` : '';
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
            await load();
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
  };

  $('#refreshSourceHistory').addEventListener('click', load);
  return load;
}
