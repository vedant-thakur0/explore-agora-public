/* AGORA Entity Dictionary Browser */

let allEntries = [];
let selectedIds = new Set();

async function loadDictionary() {
  const search = document.getElementById('dict-search').value;
  const type = document.getElementById('dict-type-filter').value;

  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (type) params.set('type', type);

  const res = await fetch('/api/dictionary?' + params);
  allEntries = await res.json();
  selectedIds.clear();
  renderTable();
}

function renderTable() {
  const tbody = document.getElementById('dict-tbody');
  const countEl = document.getElementById('dict-count');
  countEl.textContent = `${allEntries.length} entries`;

  tbody.innerHTML = allEntries.map(e => `
    <tr>
      <td><input type="checkbox" class="row-select" data-id="${e.entity_id}" /></td>
      <td><strong>${esc(e.canonical_name)}</strong></td>
      <td><span class="status-badge">${esc(e.entity_type)}</span></td>
      <td>${esc(e.acronym || '—')}</td>
      <td>${(e.aliases || []).map(a => esc(a)).join(', ') || '—'}</td>
      <td>${(e.soft_aliases || []).map(a => esc(a)).join(', ') || '—'}</td>
      <td>${e.mention_count || 0}</td>
      <td>
        <button class="btn btn-sm" onclick="editEntry('${e.entity_id}')">Edit</button>
        <button class="btn btn-sm btn-danger" onclick="deleteEntry('${e.entity_id}')">Del</button>
      </td>
    </tr>
  `).join('');

  // Re-bind checkboxes
  document.querySelectorAll('.row-select').forEach(cb => {
    cb.addEventListener('change', () => {
      if (cb.checked) selectedIds.add(cb.dataset.id);
      else selectedIds.delete(cb.dataset.id);
      document.getElementById('btn-merge').disabled = selectedIds.size !== 2;
    });
  });
}

function esc(s) {
  if (!s) return '';
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ---------------------------------------------------------------------------
// Edit
// ---------------------------------------------------------------------------

function editEntry(entityId) {
  const entry = allEntries.find(e => e.entity_id === entityId);
  if (!entry) return;

  document.getElementById('edit-id').value = entityId;
  document.getElementById('edit-name').value = entry.canonical_name || '';
  document.getElementById('edit-acronym').value = entry.acronym || '';
  document.getElementById('edit-aliases').value = (entry.aliases || []).join(', ');
  document.getElementById('edit-soft-aliases').value = (entry.soft_aliases || []).join(', ');
  document.getElementById('edit-type').value = entry.entity_type || '';
  document.getElementById('edit-modal').classList.remove('hidden');
}

document.getElementById('edit-cancel').addEventListener('click', () => {
  document.getElementById('edit-modal').classList.add('hidden');
});

document.getElementById('edit-save').addEventListener('click', async () => {
  const entityId = document.getElementById('edit-id').value;
  const payload = {
    entity_id: entityId,
    canonical_name: document.getElementById('edit-name').value.trim(),
    acronym: document.getElementById('edit-acronym').value.trim(),
    aliases: document.getElementById('edit-aliases').value.split(',').map(s => s.trim()).filter(Boolean),
    soft_aliases: document.getElementById('edit-soft-aliases').value.split(',').map(s => s.trim()).filter(Boolean),
    entity_type: document.getElementById('edit-type').value,
  };

  const res = await fetch('/api/dictionary', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (res.ok) {
    document.getElementById('edit-modal').classList.add('hidden');
    loadDictionary();
  }
});

// ---------------------------------------------------------------------------
// Delete
// ---------------------------------------------------------------------------

async function deleteEntry(entityId) {
  if (!confirm(`Delete ${entityId}?`)) return;
  await fetch(`/api/dictionary/${entityId}`, { method: 'DELETE' });
  loadDictionary();
}

// ---------------------------------------------------------------------------
// Merge
// ---------------------------------------------------------------------------

document.getElementById('btn-merge').addEventListener('click', async () => {
  const ids = [...selectedIds];
  if (ids.length !== 2) return;
  const keepId = prompt(`Which to keep?\n1) ${ids[0]}\n2) ${ids[1]}\n\nEnter 1 or 2:`, '1');
  if (!keepId) return;

  const keep = keepId === '2' ? ids[1] : ids[0];
  const merge = keepId === '2' ? ids[0] : ids[1];

  const res = await fetch('/api/dictionary/merge', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keep_id: keep, merge_id: merge }),
  });

  if (res.ok) {
    selectedIds.clear();
    loadDictionary();
  }
});

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

document.getElementById('btn-export').addEventListener('click', async () => {
  const btn = document.getElementById('btn-export');
  btn.disabled = true;
  btn.textContent = 'Exporting...';

  const res = await fetch('/api/dictionary/export');
  const data = await res.json();

  if (res.ok) {
    btn.textContent = `Exported ${data.entries} entries`;
    setTimeout(() => { btn.textContent = 'Export for Pipeline'; btn.disabled = false; }, 2000);
  } else {
    btn.textContent = 'Export failed';
    btn.disabled = false;
  }
});

// ---------------------------------------------------------------------------
// Select all
// ---------------------------------------------------------------------------

document.getElementById('select-all').addEventListener('change', (e) => {
  const checked = e.target.checked;
  document.querySelectorAll('.row-select').forEach(cb => {
    cb.checked = checked;
    if (checked) selectedIds.add(cb.dataset.id);
    else selectedIds.delete(cb.dataset.id);
  });
  document.getElementById('btn-merge').disabled = selectedIds.size !== 2;
});

// ---------------------------------------------------------------------------
// Filters
// ---------------------------------------------------------------------------

document.getElementById('dict-search').addEventListener('input', loadDictionary);
document.getElementById('dict-type-filter').addEventListener('change', loadDictionary);

// Boot
loadDictionary();
