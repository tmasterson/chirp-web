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

import { state } from './state.js';

export async function api(path, options = {}) {
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
