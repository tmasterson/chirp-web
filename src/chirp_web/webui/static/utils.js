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

export function formatFrequency(value) {
  if (value === null || value === undefined || Number(value) === 0) return '—';
  return (Number(value) / 1_000_000).toFixed(6);
}

export function txFrequency(memory) {
  if (memory.empty || !memory.freq) return null;
  if (memory.duplex === 'split') return memory.offset;
  if (memory.duplex === 'off') return null;
  return (memory.freq || 0) +
    (memory.offset || 0) * (memory.duplex === '-' ? -1 : 1);
}

export function extraColumnValue(nodes = []) {
  return nodes.flatMap((node) => node.type === 'group'
    ? extraColumnValue(node.children)
    : [`${node.label}: ${node.value ?? ''}`]).join('; ');
}

export function tsvToCsv(text) {
  const firstLine = text.split(/\r?\n/, 1)[0];
  if (!firstLine.includes('\t')) return text;
  return text.split(/\r?\n/).map((line) => line.split('\t').map((value) =>
    `"${value.replaceAll('"', '""')}"`).join(',')).join('\n');
}
