/* AGORA NER Annotation Workspace */

const ENTITY_TYPES = ['organizations', 'offices', 'roles', 'legislation_refs', 'named_docs'];
const NAME_FIELD = { organizations: 'name', offices: 'name', roles: 'title', legislation_refs: 'name', named_docs: 'name' };

// Extra fields per entity type
const EXTRA_FIELDS = {
  organizations: [{ key: 'acronym', label: 'Acronym' }],
  offices: [{ key: 'parent_org', label: 'Parent Org' }],
  roles: [{ key: 'org', label: 'Organization' }],
  legislation_refs: [
    { key: 'citation', label: 'Citation' },
    { key: 'ref_type', label: 'Ref Type', options: ['cites', 'amends', 'enacts', 'repeals'] },
  ],
  named_docs: [
    { key: 'doc_type', label: 'Doc Type', options: ['strategy', 'report', 'plan', 'initiative', 'program'] },
    { key: 'owner_org', label: 'Owner Org' },
  ],
};

const RELATION_TYPES = [
  'PART_OF', 'OVERSEES', 'FUNDS', 'CREATED_BY', 'AMENDS',
  'IMPLEMENTS', 'AUTHORED_BY', 'MANDATES', 'REPORTS_TO',
  'COLLABORATES_WITH', 'REFERENCES', 'SUCCEEDS',
];

// State
let entities = { organizations: [], offices: [], roles: [], legislation_refs: [], named_docs: [] };
let relationships = [];
let customRelationTypes = [];
let fulltext = '';
let agoraId = '';
let annotationMode = 'entity'; // 'entity' or 'relationship'

// Extract agora_id from URL
agoraId = window.location.pathname.split('/').pop();

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function init() {
  // Load document
  const docRes = await fetch(`/api/documents/${agoraId}`);
  if (!docRes.ok) { document.getElementById('doc-title').textContent = 'Document not found'; return; }
  const doc = await docRes.json();
  fulltext = doc.fulltext;

  // Set title
  const title = doc.title || doc.casual_name || `Doc ${agoraId}`;
  document.getElementById('doc-title').textContent = title;

  // Populate metadata bar
  const metaBar = document.getElementById('doc-meta-bar');
  if (doc.title) {
    metaBar.style.display = '';
    document.getElementById('meta-title').textContent = doc.title;
    if (doc.congress_url) {
      const link = document.getElementById('meta-link');
      link.href = doc.congress_url;
      link.style.display = '';
    }
    if (doc.short_summary) {
      document.getElementById('meta-summary-row').style.display = '';
      document.getElementById('meta-summary').textContent = doc.short_summary;
    }
    if (doc.activity) {
      document.getElementById('meta-activity').textContent = doc.activity + (doc.activity_date ? ` (${doc.activity_date})` : '');
    }
    if (doc.proposed_date) {
      document.getElementById('meta-proposed').textContent = `Proposed: ${doc.proposed_date}`;
    }
    if (doc.community_label) {
      document.getElementById('meta-community').textContent = doc.community_label;
    }
  }

  // Load existing annotations (manual first, then auto)
  const annRes = await fetch(`/api/annotations/${agoraId}`);
  const annData = await annRes.json();
  if (annData) {
    loadEntities(annData);
  } else {
    const entRes = await fetch(`/api/documents/${agoraId}/entities`);
    const entData = await entRes.json();
    if (entData) loadEntities(entData);
  }

  renderText();
  renderAllEntityLists();
  setupTextSelection();
  setupPopover();
}

function loadEntities(data) {
  for (const t of ENTITY_TYPES) {
    entities[t] = data[t] || [];
  }
  relationships = data.relationships || [];
  customRelationTypes = data.custom_relation_types || [];
}

// ---------------------------------------------------------------------------
// Text rendering with highlights
// ---------------------------------------------------------------------------

function renderText() {
  const el = document.getElementById('text-content');
  if (!fulltext) { el.textContent = '(no text)'; return; }

  // Collect all context spans to highlight
  const spans = [];
  for (const t of ENTITY_TYPES) {
    for (const ent of entities[t]) {
      const ctx = ent.context || '';
      if (!ctx || ctx.length < 3) continue;
      let idx = fulltext.indexOf(ctx);
      if (idx === -1) {
        // Try shorter match (first 60 chars)
        const short = ctx.substring(0, 60);
        idx = fulltext.indexOf(short);
      }
      if (idx >= 0) {
        const len = idx === fulltext.indexOf(ctx) ? ctx.length : 60;
        spans.push({ start: idx, end: idx + len, type: t });
      }
    }
  }

  // Sort by start position, non-overlapping (first wins)
  spans.sort((a, b) => a.start - b.start);
  const merged = [];
  for (const s of spans) {
    if (merged.length && s.start < merged[merged.length - 1].end) continue;
    merged.push(s);
  }

  // Build HTML
  let html = '';
  let cursor = 0;
  for (const s of merged) {
    if (s.start > cursor) html += escapeHtml(fulltext.slice(cursor, s.start));
    html += `<span class="highlight-${s.type}">${escapeHtml(fulltext.slice(s.start, s.end))}</span>`;
    cursor = s.end;
  }
  if (cursor < fulltext.length) html += escapeHtml(fulltext.slice(cursor));
  el.innerHTML = html;
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ---------------------------------------------------------------------------
// Scroll to offset + pulse
// ---------------------------------------------------------------------------

function scrollToOffset(charStart, charEnd) {
  const textEl = document.getElementById('text-content');
  // Find the text node and offset within the rendered HTML
  const walker = document.createTreeWalker(textEl, NodeFilter.SHOW_TEXT, null);
  let charCount = 0;
  let targetNode = null;
  let nodeOffset = 0;

  while (walker.nextNode()) {
    const node = walker.currentNode;
    const len = node.textContent.length;
    if (charCount + len > charStart) {
      targetNode = node;
      nodeOffset = charStart - charCount;
      break;
    }
    charCount += len;
  }

  if (!targetNode) return;

  // Scroll the text panel to the target
  const range = document.createRange();
  range.setStart(targetNode, nodeOffset);
  const rect = range.getBoundingClientRect();
  const panel = document.getElementById('text-panel');
  const panelRect = panel.getBoundingClientRect();
  panel.scrollTop += rect.top - panelRect.top - panel.clientHeight / 3;

  // Brief pulse highlight
  const pulseEl = document.createElement('span');
  pulseEl.className = 'pulse-highlight';
  // Find the snippet to highlight
  const snippet = fulltext.slice(charStart, Math.min(charEnd, charStart + 200));
  // Use window find + CSS animation instead of DOM manipulation
  // Simple approach: temporarily inject a marker
  const existingHTML = textEl.innerHTML;
  const escapedSnippet = escapeHtml(snippet);
  if (existingHTML.includes(escapedSnippet)) {
    textEl.innerHTML = existingHTML.replace(
      escapedSnippet,
      `<span class="pulse-highlight">${escapedSnippet}</span>`
    );
    setTimeout(() => {
      const pulse = textEl.querySelector('.pulse-highlight');
      if (pulse) {
        pulse.scrollIntoView({ behavior: 'smooth', block: 'center' });
        setTimeout(() => renderText(), 1500);
      }
    }, 50);
  }
}

// ---------------------------------------------------------------------------
// Entity list rendering
// ---------------------------------------------------------------------------

function renderAllEntityLists() {
  for (const t of ENTITY_TYPES) renderEntityList(t);
  renderRelationshipList();
}

function renderEntityList(type) {
  const list = document.getElementById(`list-${type}`);
  const count = document.getElementById(`count-${type}`);
  const items = entities[type];
  count.textContent = items.length;

  list.innerHTML = items.map((ent, i) => {
    const nf = NAME_FIELD[type];
    const name = ent[nf] || '(unnamed)';
    const metaParts = [];
    for (const ef of (EXTRA_FIELDS[type] || [])) {
      if (ent[ef.key]) metaParts.push(`${ef.label}: ${ent[ef.key]}`);
    }
    if (ent.context) metaParts.push(`"${ent.context.substring(0, 50)}..."`);

    const hasLoc = ent.char_start != null;
    const locClick = hasLoc ? `onclick="scrollToOffset(${ent.char_start}, ${ent.char_end})"` : '';
    const locClass = hasLoc ? ' has-location' : '';

    return `
      <div class="entity-card${locClass}" ${locClick}>
        <div>
          <div class="entity-name">${escapeHtml(name)}</div>
          <div class="entity-meta">${escapeHtml(metaParts.join(' | '))}</div>
        </div>
        <div class="entity-actions">
          <button class="btn btn-sm" onclick="event.stopPropagation(); findAll('${type}', ${i})">Find</button>
          <button class="btn btn-sm" onclick="event.stopPropagation(); addToDict('${type}', ${i})">+Dict</button>
          <button class="btn btn-sm btn-danger" onclick="event.stopPropagation(); removeEntity('${type}', ${i})">x</button>
        </div>
      </div>
    `;
  }).join('');
}

function removeEntity(type, index) {
  entities[type].splice(index, 1);
  renderEntityList(type);
  renderText();
}

async function addToDict(type, index) {
  const ent = entities[type][index];
  const nf = NAME_FIELD[type];
  const name = ent[nf] || '';
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/(^_|_$)/g, '');
  const PREFIX = { organizations: 'org', offices: 'office', roles: 'role', legislation_refs: 'legislation', named_docs: 'named_doc' };
  const entityId = `${PREFIX[type]}:${slug}`;

  const payload = {
    entity_id: entityId,
    entity_type: type,
    canonical_name: name,
    acronym: ent.acronym || '',
    aliases: [],
    metadata: {},
    mention_count: 1,
    seen_in: [agoraId],
    first_seen: agoraId,
  };
  for (const ef of (EXTRA_FIELDS[type] || [])) {
    payload.metadata[ef.key] = ent[ef.key] || '';
  }

  const res = await fetch('/api/dictionary', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  if (res.ok) alert(`Added "${name}" to dictionary`);
}

// ---------------------------------------------------------------------------
// Text selection → entity creation
// ---------------------------------------------------------------------------

function getSelectionCharOffset(selectedText) {
  // Find the character offset of selected text in the fulltext
  if (!selectedText || !fulltext) return null;
  const idx = fulltext.indexOf(selectedText);
  if (idx === -1) return null;
  return { char_start: idx, char_end: idx + selectedText.length };
}

function setupTextSelection() {
  const textContent = document.getElementById('text-content');
  textContent.addEventListener('mouseup', (e) => {
    const sel = window.getSelection();
    const text = (sel.toString() || '').trim();
    if (text.length < 2) return;
    if (annotationMode === 'relationship') {
      showRelPopover(e.clientX, e.clientY, text);
      return;
    }
    showPopover(e.clientX, e.clientY, text);
  });
}

// ---------------------------------------------------------------------------
// Popover
// ---------------------------------------------------------------------------

function setupPopover() {
  const popType = document.getElementById('pop-type');
  popType.addEventListener('change', () => renderExtraFields(popType.value));

  document.getElementById('pop-cancel').addEventListener('click', hidePopover);
  document.getElementById('pop-add').addEventListener('click', addEntityFromPopover);

  // Close popover on Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hidePopover();
  });
}

function showPopover(x, y, selectedText) {
  const pop = document.getElementById('entity-popover');
  pop.classList.remove('hidden');

  // Position near click, but keep on screen
  const maxX = window.innerWidth - 320;
  const maxY = window.innerHeight - 400;
  pop.style.left = Math.min(x, maxX) + 'px';
  pop.style.top = Math.min(y + 10, maxY) + 'px';

  document.getElementById('pop-name').value = selectedText;
  document.getElementById('pop-context').value = selectedText.substring(0, 150);
  renderExtraFields(document.getElementById('pop-type').value);
}

function hidePopover() {
  document.getElementById('entity-popover').classList.add('hidden');
}

function renderExtraFields(type) {
  const container = document.getElementById('pop-extra-fields');
  const fields = EXTRA_FIELDS[type] || [];
  container.innerHTML = fields.map(f => {
    if (f.options) {
      return `<label>${f.label}
        <select id="pop-extra-${f.key}">
          <option value="">—</option>
          ${f.options.map(o => `<option value="${o}">${o}</option>`).join('')}
        </select>
      </label>`;
    }
    return `<label>${f.label} <input type="text" id="pop-extra-${f.key}" /></label>`;
  }).join('');
}

function addEntityFromPopover() {
  const type = document.getElementById('pop-type').value;
  const nf = NAME_FIELD[type];
  const name = document.getElementById('pop-name').value.trim();
  if (!name) return;

  const context = document.getElementById('pop-context').value.trim();
  const ent = { [nf]: name, context };
  for (const ef of (EXTRA_FIELDS[type] || [])) {
    const el = document.getElementById(`pop-extra-${ef.key}`);
    if (el) ent[ef.key] = el.value.trim();
  }

  // Capture char offsets from context
  const offsets = getSelectionCharOffset(context);
  if (offsets) {
    ent.char_start = offsets.char_start;
    ent.char_end = offsets.char_end;
  }

  entities[type].push(ent);
  hidePopover();
  renderEntityList(type);
  renderText();
}

// ---------------------------------------------------------------------------
// Auto-extract
// ---------------------------------------------------------------------------

document.getElementById('btn-auto').addEventListener('click', async () => {
  const btn = document.getElementById('btn-auto');
  const status = document.getElementById('rate-status');
  btn.disabled = true;
  btn.textContent = 'Extracting...';
  status.textContent = '';

  try {
    const res = await fetch(`/api/extract/${agoraId}`, { method: 'POST' });
    if (res.status === 429) {
      const data = await res.json();
      status.textContent = data.error || 'Rate limited';
      status.className = 'rate-indicator busy';
      return;
    }
    if (!res.ok) {
      const data = await res.json();
      alert('Extraction failed: ' + (data.error || 'unknown error'));
      return;
    }
    const data = await res.json();
    loadEntities(data);
    renderText();
    renderAllEntityLists();
    status.textContent = `Extracted (${data.chunks_processed || 0} chunks)`;
    status.className = 'rate-indicator';
  } catch (err) {
    alert('Error: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Auto-Extract';
  }
});

// ---------------------------------------------------------------------------
// Save
// ---------------------------------------------------------------------------

document.getElementById('btn-save').addEventListener('click', async () => {
  const btn = document.getElementById('btn-save');
  btn.disabled = true;
  btn.textContent = 'Saving...';

  try {
    const payload = {};
    for (const t of ENTITY_TYPES) payload[t] = entities[t];
    payload.relationships = relationships;
    if (customRelationTypes.length) payload.custom_relation_types = customRelationTypes;

    const res = await fetch(`/api/annotations/${agoraId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok) {
      btn.textContent = 'Saved!';
      setTimeout(() => { btn.textContent = 'Save'; }, 1500);
    } else {
      alert('Save failed: ' + (data.error || 'unknown'));
    }
  } finally {
    btn.disabled = false;
    if (btn.textContent === 'Saving...') btn.textContent = 'Save';
  }
});

// ---------------------------------------------------------------------------
// Section toggles
// ---------------------------------------------------------------------------

document.querySelectorAll('.section-toggle').forEach(el => {
  el.addEventListener('click', () => {
    const list = el.nextElementSibling;
    list.style.display = list.style.display === 'none' ? '' : 'none';
  });
});

// ---------------------------------------------------------------------------
// Relationships
// ---------------------------------------------------------------------------

const TYPE_LABELS = {
  organizations: 'Org', offices: 'Office', roles: 'Role',
  legislation_refs: 'Legis', named_docs: 'Doc',
};

function getAllEntityOptions() {
  const options = [];
  for (const t of ENTITY_TYPES) {
    const nf = NAME_FIELD[t];
    for (const ent of entities[t]) {
      const name = ent[nf] || '';
      if (name) options.push({ type: t, name });
    }
  }
  return options;
}

function renderRelationshipList() {
  const list = document.getElementById('list-relationships');
  const count = document.getElementById('count-relationships');
  count.textContent = relationships.length;

  list.innerHTML = relationships.map((rel, i) => {
    const srcLabel = TYPE_LABELS[rel.source_type] || rel.source_type;
    const tgtLabel = TYPE_LABELS[rel.target_type] || rel.target_type;
    const ctx = rel.context ? `"${escapeHtml(rel.context.substring(0, 60))}..."` : '';
    const hasLoc = rel.context_start != null;
    const locClick = hasLoc ? `onclick="scrollToOffset(${rel.context_start}, ${rel.context_end})"` : '';
    const locClass = hasLoc ? ' has-location' : '';

    return `
      <div class="rel-card${locClass}" ${locClick}>
        <span class="type-badge-sm">${srcLabel}</span>
        <span class="rel-entity">${escapeHtml(rel.source_name)}</span>
        <span class="rel-arrow">&rarr;</span>
        <span class="rel-type-badge">${escapeHtml(rel.relation_type)}</span>
        <span class="rel-arrow">&rarr;</span>
        <span class="type-badge-sm">${tgtLabel}</span>
        <span class="rel-entity">${escapeHtml(rel.target_name)}</span>
        <button class="btn btn-sm btn-danger" onclick="event.stopPropagation(); removeRelationship(${i})">x</button>
        ${ctx ? `<div class="rel-context">${ctx}</div>` : ''}
      </div>
    `;
  }).join('');
}

function getAllRelTypes() {
  return [...RELATION_TYPES, ...customRelationTypes];
}

function populateRelTypeSelect(selectEl) {
  const types = getAllRelTypes();
  selectEl.innerHTML = types.map(r =>
    `<option value="${r}">${r}</option>`
  ).join('') + '<option value="__other__">Other...</option>';
}

function handleRelTypeChange(selectEl, customInputId) {
  if (selectEl.value === '__other__') {
    let input = document.getElementById(customInputId);
    if (!input) {
      input = document.createElement('input');
      input.type = 'text';
      input.id = customInputId;
      input.placeholder = 'Custom relation type...';
      input.style.marginTop = '4px';
      selectEl.parentNode.appendChild(input);
    }
    input.style.display = '';
    input.focus();
  } else {
    const input = document.getElementById(customInputId);
    if (input) input.style.display = 'none';
  }
}

function resolveRelType(selectEl, customInputId) {
  if (selectEl.value === '__other__') {
    const input = document.getElementById(customInputId);
    const custom = (input ? input.value.trim() : '').toUpperCase().replace(/\s+/g, '_');
    if (!custom) return null;
    if (!customRelationTypes.includes(custom)) customRelationTypes.push(custom);
    return custom;
  }
  return selectEl.value;
}

function openRelationshipModal() {
  const options = getAllEntityOptions();
  if (options.length < 2) {
    alert('Add at least 2 entities before creating a relationship.');
    return;
  }

  const optHtml = options.map((o, i) =>
    `<option value="${i}">[${TYPE_LABELS[o.type] || o.type}] ${escapeHtml(o.name)}</option>`
  ).join('');

  document.getElementById('rel-source').innerHTML = optHtml;
  document.getElementById('rel-target').innerHTML = optHtml;
  if (options.length > 1) document.getElementById('rel-target').selectedIndex = 1;

  const relTypeSelect = document.getElementById('rel-type');
  populateRelTypeSelect(relTypeSelect);
  relTypeSelect.onchange = () => handleRelTypeChange(relTypeSelect, 'rel-custom-type');

  document.getElementById('rel-context').value = '';
  document.getElementById('rel-modal').classList.remove('hidden');
}

function closeRelationshipModal() {
  document.getElementById('rel-modal').classList.add('hidden');
}

function addRelationship() {
  const options = getAllEntityOptions();
  const srcIdx = parseInt(document.getElementById('rel-source').value);
  const tgtIdx = parseInt(document.getElementById('rel-target').value);
  const relTypeSelect = document.getElementById('rel-type');
  const relType = resolveRelType(relTypeSelect, 'rel-custom-type');
  const context = document.getElementById('rel-context').value.trim();

  if (!relType) { alert('Enter a relation type.'); return; }
  if (srcIdx === tgtIdx) { alert('Source and target must be different entities.'); return; }

  const src = options[srcIdx];
  const tgt = options[tgtIdx];
  const rel = {
    source_type: src.type,
    source_name: src.name,
    target_type: tgt.type,
    target_name: tgt.name,
    relation_type: relType,
    context: context,
  };
  // Add context offsets if available
  const offsets = getSelectionCharOffset(context);
  if (offsets) {
    rel.context_start = offsets.char_start;
    rel.context_end = offsets.char_end;
  }

  relationships.push(rel);
  closeRelationshipModal();
  renderRelationshipList();
}

function removeRelationship(index) {
  relationships.splice(index, 1);
  renderRelationshipList();
}

// ---------------------------------------------------------------------------
// Mode toggle
// ---------------------------------------------------------------------------

function setMode(mode) {
  annotationMode = mode;
  document.getElementById('mode-entity').classList.toggle('active', mode === 'entity');
  document.getElementById('mode-relationship').classList.toggle('active', mode === 'relationship');
  const textPanel = document.getElementById('text-panel');
  textPanel.classList.toggle('rel-mode', mode === 'relationship');
}

// ---------------------------------------------------------------------------
// Relationship popover (relationship mode)
// ---------------------------------------------------------------------------

function showRelPopover(x, y, selectedText) {
  const options = getAllEntityOptions();
  if (options.length < 2) {
    alert('Add at least 2 entities before creating a relationship.');
    return;
  }

  const pop = document.getElementById('rel-popover');
  pop.classList.remove('hidden');

  const maxX = window.innerWidth - 320;
  const maxY = window.innerHeight - 400;
  pop.style.left = Math.min(x, maxX) + 'px';
  pop.style.top = Math.min(y + 10, maxY) + 'px';

  document.getElementById('rpop-context').value = selectedText.substring(0, 200);

  const optHtml = options.map((o, i) =>
    `<option value="${i}">[${TYPE_LABELS[o.type] || o.type}] ${escapeHtml(o.name)}</option>`
  ).join('');
  document.getElementById('rpop-source').innerHTML = optHtml;
  document.getElementById('rpop-target').innerHTML = optHtml;
  if (options.length > 1) document.getElementById('rpop-target').selectedIndex = 1;

  const rpopType = document.getElementById('rpop-type');
  populateRelTypeSelect(rpopType);
  rpopType.onchange = () => handleRelTypeChange(rpopType, 'rpop-custom-type');
}

function hideRelPopover() {
  document.getElementById('rel-popover').classList.add('hidden');
}

function addRelFromPopover() {
  const options = getAllEntityOptions();
  const srcIdx = parseInt(document.getElementById('rpop-source').value);
  const tgtIdx = parseInt(document.getElementById('rpop-target').value);
  const rpopType = document.getElementById('rpop-type');
  const relType = resolveRelType(rpopType, 'rpop-custom-type');
  const context = document.getElementById('rpop-context').value.trim();

  if (!relType) { alert('Enter a relation type.'); return; }
  if (srcIdx === tgtIdx) { alert('Source and target must be different entities.'); return; }

  const src = options[srcIdx];
  const tgt = options[tgtIdx];
  const rel = {
    source_type: src.type,
    source_name: src.name,
    target_type: tgt.type,
    target_name: tgt.name,
    relation_type: relType,
    context: context,
  };
  const offsets = getSelectionCharOffset(context);
  if (offsets) {
    rel.context_start = offsets.char_start;
    rel.context_end = offsets.char_end;
  }

  relationships.push(rel);
  hideRelPopover();
  renderRelationshipList();
}

// ---------------------------------------------------------------------------
// Quick-add + dictionary lookup
// ---------------------------------------------------------------------------

let qaDebounce = null;

function quickAdd() {
  const type = document.getElementById('qa-type').value;
  const nf = NAME_FIELD[type];
  const name = document.getElementById('qa-name').value.trim();
  if (!name) return;

  entities[type].push({ [nf]: name });
  document.getElementById('qa-name').value = '';
  hideSuggestions();
  renderEntityList(type);
  renderText();
}

function setupQuickAddLookup() {
  const input = document.getElementById('qa-name');
  input.addEventListener('input', () => {
    clearTimeout(qaDebounce);
    const q = input.value.trim();
    if (q.length < 2) { hideSuggestions(); return; }
    qaDebounce = setTimeout(() => fetchSuggestions(q), 250);
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); quickAdd(); }
    if (e.key === 'Escape') hideSuggestions();
  });
}

async function fetchSuggestions(query) {
  try {
    const res = await fetch(`/api/dictionary?search=${encodeURIComponent(query)}`);
    const results = await res.json();
    renderSuggestions(results.slice(0, 8));
  } catch { hideSuggestions(); }
}

function renderSuggestions(results) {
  const box = document.getElementById('qa-suggestions');
  if (!results.length) { hideSuggestions(); return; }
  box.classList.remove('hidden');
  box.innerHTML = results.map(e => {
    const typeLabel = TYPE_LABELS[e.entity_type] || e.entity_type;
    return `<div class="qa-suggestion" onclick="applySuggestion('${escapeHtml(e.canonical_name)}', '${e.entity_type}')">
      <span class="type-badge-sm">${typeLabel}</span> ${escapeHtml(e.canonical_name)}
      ${e.acronym ? `<span class="meta-tag">${escapeHtml(e.acronym)}</span>` : ''}
    </div>`;
  }).join('');
}

function applySuggestion(name, type) {
  document.getElementById('qa-name').value = name;
  document.getElementById('qa-type').value = type;
  hideSuggestions();
}

function hideSuggestions() {
  document.getElementById('qa-suggestions').classList.add('hidden');
}

// ---------------------------------------------------------------------------
// Find all occurrences
// ---------------------------------------------------------------------------

function findAll(type, index) {
  const ent = entities[type][index];
  const nf = NAME_FIELD[type];
  const name = ent[nf] || '';
  if (!name || name.length < 2) return;

  const textEl = document.getElementById('text-content');
  // Re-render text then highlight all occurrences of the entity name
  renderText();

  const escapedName = escapeHtml(name);
  const html = textEl.innerHTML;
  const regex = new RegExp(escapedName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
  const matches = html.match(regex);
  if (!matches || !matches.length) {
    alert(`"${name}" not found in document text.`);
    return;
  }

  textEl.innerHTML = html.replace(regex, `<span class="find-all-highlight">$&</span>`);

  // Scroll to first match
  const first = textEl.querySelector('.find-all-highlight');
  if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });

  // Clear after 5 seconds
  setTimeout(() => renderText(), 5000);
}

// Close popovers on Escape
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeRelationshipModal();
    hideRelPopover();
  }
});

// Boot
setupQuickAddLookup();
init();
