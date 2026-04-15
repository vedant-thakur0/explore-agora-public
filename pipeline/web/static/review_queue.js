/* AGORA Review Queue Triage */

let allEntries = [];
let selectedKeys = new Set(); // "agora_id|entity_name|entity_type"

function entryKey(e) {
  return `${e.agora_id}|${e.entity_name}|${e.entity_type}`;
}

async function loadQueue() {
  const search = document.getElementById('rq-search').value;
  const type = document.getElementById('rq-type-filter').value;
  const source = document.getElementById('rq-source-filter').value;

  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (type) params.set('type', type);
  if (source) params.set('source', source);

  const res = await fetch('/api/review?' + params);
  allEntries = await res.json();
  selectedKeys.clear();
  renderTable();
}

function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function sourceLabel(source) {
  const map = {
    community: '<span class="status-badge status-auto">community</span>',
    doc: '<span class="status-badge status-reviewed">doc</span>',
    registry: '<span class="status-badge" style="background:#f3e8ff;color:#7c3aed;">registry</span>',
    unresolved: '<span class="status-badge status-none">unresolved</span>',
  };
  return map[source] || `<span class="status-badge status-none">${esc(source)}</span>`;
}

function renderTable() {
  const tbody = document.getElementById('rq-tbody');
  const countEl = document.getElementById('rq-count');
  countEl.textContent = `${allEntries.length} entries`;

  if (allEntries.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#888;padding:2rem;">Queue is empty.</td></tr>';
    updateBulkButtons();
    return;
  }

  tbody.innerHTML = allEntries.map(e => {
    const key = entryKey(e);
    const hasSuggestion = e.suggested_canonical && e.suggestion_source !== 'unresolved';
    const rowId = `row-${CSS.escape(key)}`;
    const detailId = `detail-${CSS.escape(key)}`;

    return `
    <tr id="${rowId}" class="rq-row" data-key="${esc(key)}" style="cursor:pointer">
      <td><input type="checkbox" class="row-select" data-key="${esc(key)}" /></td>
      <td>
        <strong>${esc(e.entity_name)}</strong>
        <span style="font-size:0.7rem;color:#888;margin-left:4px;">&#9660;</span>
      </td>
      <td><span class="color-dot dot-${esc(e.entity_type)}" title="${esc(e.entity_type)}"></span> <span style="font-size:0.8rem">${esc(e.entity_type)}</span></td>
      <td><span class="community-tag">${esc(e.community_id || '—')}</span></td>
      <td>${e.suggested_canonical ? `<em>${esc(e.suggested_canonical)}</em>` : '<span style="color:#aaa">—</span>'}</td>
      <td>${sourceLabel(e.suggestion_source)}</td>
      <td style="white-space:nowrap">
        ${hasSuggestion ? `<button class="btn btn-success btn-sm" onclick="acceptEntry(event, '${esc(key)}')">Accept</button> ` : ''}
        <button class="btn btn-sm" onclick="editEntry(event, '${esc(key)}')">Edit</button>
        <button class="btn btn-danger btn-sm" onclick="dismissEntry(event, '${esc(key)}')">Dismiss</button>
      </td>
    </tr>
    <tr id="${detailId}" class="rq-detail hidden">
      <td></td>
      <td colspan="6">
        <div style="font-size:0.8rem;padding:0.4rem 0;color:#444;">
          ${e.entity_context ? `<div style="margin-bottom:0.3rem;padding:0.3rem 0.5rem;background:#f8f9fa;border-left:3px solid #3b82f6;border-radius:2px;font-style:italic;">${esc(e.entity_context)}</div>` : ''}
          ${e.doc_disambiguation_rule ? `<div style="margin-bottom:0.3rem"><strong>Doc rule:</strong> ${esc(e.doc_disambiguation_rule)}</div>` : ''}
          ${e.community_disambiguation_rule ? `<div><strong>Community rule:</strong> ${esc(e.community_disambiguation_rule)}</div>` : ''}
          <div style="margin-top:0.3rem;color:#888;font-size:0.75rem;">Doc: ${esc(e.agora_id)} &nbsp;|&nbsp; Flagged: ${esc(e.ts || '')}</div>
        </div>
      </td>
    </tr>
    `;
  }).join('');

  // Bind expand/collapse on all rows
  document.querySelectorAll('.rq-row').forEach(row => {
    const key = row.dataset.key;
    const detailRow = document.getElementById(`detail-${CSS.escape(key)}`);
    if (!detailRow) return;
    row.addEventListener('click', (evt) => {
      if (evt.target.closest('button') || evt.target.closest('input')) return;
      detailRow.classList.toggle('hidden');
    });
  });

  // Bind checkboxes
  document.querySelectorAll('.row-select').forEach(cb => {
    cb.addEventListener('change', () => {
      if (cb.checked) selectedKeys.add(cb.dataset.key);
      else selectedKeys.delete(cb.dataset.key);
      updateBulkButtons();
    });
  });

  updateBulkButtons();
}

function updateBulkButtons() {
  const n = selectedKeys.size;
  document.getElementById('btn-bulk-accept').disabled = n === 0;
  document.getElementById('btn-bulk-dismiss').disabled = n === 0;
  if (n > 0) {
    document.getElementById('btn-bulk-accept').textContent = `Bulk Accept (${n})`;
    document.getElementById('btn-bulk-dismiss').textContent = `Bulk Dismiss (${n})`;
  } else {
    document.getElementById('btn-bulk-accept').textContent = 'Bulk Accept';
    document.getElementById('btn-bulk-dismiss').textContent = 'Bulk Dismiss';
  }
}

// ---------------------------------------------------------------------------
// Single actions
// ---------------------------------------------------------------------------

function entryFromKey(key) {
  return allEntries.find(e => entryKey(e) === key);
}

async function acceptEntry(evt, key) {
  evt.stopPropagation();
  const e = entryFromKey(key);
  if (!e) return;
  if (!e.suggested_canonical) { alert('No suggestion to accept. Use Edit to set a canonical name.'); return; }

  await postAction('/api/review/accept', {
    agora_id: e.agora_id,
    entity_name: e.entity_name,
    entity_type: e.entity_type,
    canonical_name: e.suggested_canonical,
  });
  removeRowOptimistic(key);
}

function editEntry(evt, key) {
  evt.stopPropagation();
  const e = entryFromKey(key);
  if (!e) return;

  document.getElementById('edit-agora-id').value = e.agora_id;
  document.getElementById('edit-entity-name').value = e.entity_name;
  document.getElementById('edit-entity-type').value = e.entity_type;
  document.getElementById('edit-canonical').value = e.suggested_canonical || '';
  document.getElementById('edit-modal').classList.remove('hidden');
  document.getElementById('edit-canonical').focus();
  document.getElementById('edit-canonical').select();
}

async function dismissEntry(evt, key) {
  evt.stopPropagation();
  const e = entryFromKey(key);
  if (!e) return;

  await postAction('/api/review/dismiss', {
    agora_id: e.agora_id,
    entity_name: e.entity_name,
    entity_type: e.entity_type,
  });
  removeRowOptimistic(key);
}

// ---------------------------------------------------------------------------
// Edit modal
// ---------------------------------------------------------------------------

document.getElementById('edit-cancel').addEventListener('click', () => {
  document.getElementById('edit-modal').classList.add('hidden');
});

document.getElementById('edit-save').addEventListener('click', async () => {
  const agora_id = document.getElementById('edit-agora-id').value;
  const entity_name = document.getElementById('edit-entity-name').value;
  const entity_type = document.getElementById('edit-entity-type').value;
  const canonical_name = document.getElementById('edit-canonical').value.trim();

  if (!canonical_name) { alert('Canonical name cannot be empty.'); return; }

  const res = await postAction('/api/review/accept', { agora_id, entity_name, entity_type, canonical_name });
  if (res && res.ok) {
    document.getElementById('edit-modal').classList.add('hidden');
    const key = `${agora_id}|${entity_name}|${entity_type}`;
    removeRowOptimistic(key);
  }
});

// ---------------------------------------------------------------------------
// Bulk actions
// ---------------------------------------------------------------------------

document.getElementById('btn-bulk-accept').addEventListener('click', async () => {
  if (selectedKeys.size === 0) return;

  const entries = [];
  for (const key of selectedKeys) {
    const e = entryFromKey(key);
    if (!e || !e.suggested_canonical || e.suggestion_source === 'unresolved') continue;
    entries.push({
      agora_id: e.agora_id,
      entity_name: e.entity_name,
      entity_type: e.entity_type,
      canonical_name: e.suggested_canonical,
    });
  }

  if (entries.length === 0) {
    alert('No selected entries have a suggested canonical. Use Bulk Dismiss or Edit each one individually.');
    return;
  }

  const res = await fetch('/api/review/bulk-accept', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entries }),
  });
  if (res.ok) {
    for (const item of entries) {
      removeRowOptimistic(`${item.agora_id}|${item.entity_name}|${item.entity_type}`);
    }
  }
});

document.getElementById('btn-bulk-dismiss').addEventListener('click', async () => {
  if (selectedKeys.size === 0) return;

  const entries = [];
  for (const key of selectedKeys) {
    const e = entryFromKey(key);
    if (!e) continue;
    entries.push({ agora_id: e.agora_id, entity_name: e.entity_name, entity_type: e.entity_type });
  }

  const res = await fetch('/api/review/bulk-dismiss', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entries }),
  });
  if (res.ok) {
    for (const item of entries) {
      removeRowOptimistic(`${item.agora_id}|${item.entity_name}|${item.entity_type}`);
    }
  }
});

// ---------------------------------------------------------------------------
// Select all
// ---------------------------------------------------------------------------

document.getElementById('select-all').addEventListener('change', (e) => {
  const checked = e.target.checked;
  document.querySelectorAll('.row-select').forEach(cb => {
    cb.checked = checked;
    if (checked) selectedKeys.add(cb.dataset.key);
    else selectedKeys.delete(cb.dataset.key);
  });
  updateBulkButtons();
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function postAction(url, payload) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return res;
}

function removeRowOptimistic(key) {
  allEntries = allEntries.filter(e => entryKey(e) !== key);
  selectedKeys.delete(key);
  renderTable();
}

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------

document.getElementById('rq-search').addEventListener('input', loadQueue);
document.getElementById('rq-type-filter').addEventListener('change', loadQueue);
document.getElementById('rq-source-filter').addEventListener('change', loadQueue);

// Boot
loadQueue();
