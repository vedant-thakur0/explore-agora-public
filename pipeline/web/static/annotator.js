/* AGORA NER Annotation Workspace */

const ENTITY_TYPES = ['organizations', 'offices', 'roles', 'legislation_refs', 'named_docs'];
const NAME_FIELD = { organizations: 'name', offices: 'name', roles: 'title', legislation_refs: 'name', named_docs: 'name' };

// Extra fields per entity type.
// org_ref: true  → renders as a datalist-backed input autocompleting from tagged orgs
const EXTRA_FIELDS = {
  organizations: [{ key: 'acronym', label: 'Acronym' }],
  offices:       [{ key: 'parent_org', label: 'Parent Org', org_ref: true }],
  roles:         [{ key: 'org',        label: 'Organization', org_ref: true }],
  legislation_refs: [
    { key: 'citation', label: 'Citation' },
    { key: 'ref_type', label: 'Ref Type', options: ['cites', 'amends', 'enacts', 'repeals'] },
  ],
  named_docs: [
    { key: 'doc_type',  label: 'Doc Type', options: ['strategy', 'report', 'plan', 'initiative', 'program'] },
    { key: 'owner_org', label: 'Owner Org', org_ref: true },
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
let softAliases = [];
let fulltext = '';
let agoraId = '';
let annotationMode = 'entity'; // 'entity' or 'relationship'
let pendingSelectionOffsets = null; // { char_start, char_end } captured at mouseup
let activeEntityName = null;       // entity name whose card is selected (for related highlighting)
let pendingSoftAliasEntity = null; // { name, type } when in soft-alias capture mode

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
  softAliases = data.soft_aliases || [];
}

// ---------------------------------------------------------------------------
// Text rendering with highlights
// ---------------------------------------------------------------------------

function getRelatedNames(name) {
  const names = new Set();
  for (const rel of relationships) {
    if (rel.source_name === name) names.add(rel.target_name);
    if (rel.target_name === name) names.add(rel.source_name);
  }
  return names;
}

// ---------------------------------------------------------------------------
// Matching helpers — word-boundary and overlap guards
// ---------------------------------------------------------------------------

function findWordBoundaryMatches(text, needle) {
  // Returns [{char_start, char_end}] for every whole-word occurrence of needle in text.
  // A match is whole-word if the char before and after are non-word (\W) or string boundary.
  const lower   = text.toLowerCase();
  const lneedle = needle.toLowerCase();
  const results = [];
  let pos = 0;
  while (true) {
    const idx = lower.indexOf(lneedle, pos);
    if (idx === -1) break;
    const before = idx === 0                          ? '' : text[idx - 1];
    const after  = idx + needle.length >= text.length ? '' : text[idx + needle.length];
    if ((!before || /\W/.test(before)) && (!after || /\W/.test(after))) {
      results.push({ char_start: idx, char_end: idx + needle.length });
    }
    pos = idx + 1; // +1 not +needle.length so adjacent boundaries are checked
  }
  return results;
}

function isInsideExistingTag(charStart, charEnd) {
  // True if [charStart, charEnd) overlaps with any already-tagged entity span.
  for (const type of ENTITY_TYPES) {
    for (const ent of entities[type]) {
      if (ent.char_start == null) continue;
      if (charStart < ent.char_end && charEnd > ent.char_start) return true;
    }
  }
  return false;
}

function isInsideLongerPhrase(charStart, charEnd) {
  // True if a longer tagged entity name appears at an overlapping position in fulltext.
  // E.g. alias "Secretary" should be skipped where "Secretary of Defense" is tagged.
  const matchedLen = charEnd - charStart;
  for (const type of ENTITY_TYPES) {
    for (const ent of entities[type]) {
      const ename = (ent[NAME_FIELD[type]] || '');
      if (ename.length <= matchedLen) continue;
      // Slide a window that could contain ename and overlaps [charStart, charEnd)
      const windowStart = Math.max(0, charStart - (ename.length - matchedLen));
      const windowEnd   = charStart + ename.length;
      const window      = fulltext.slice(windowStart, windowEnd).toLowerCase();
      if (window.includes(ename.toLowerCase())) return true;
    }
  }
  return false;
}

function renderText() {
  const el = document.getElementById('text-content');
  if (!fulltext) { el.textContent = '(no text)'; return; }

  // Collect all spans to highlight
  const spans = [];
  for (const t of ENTITY_TYPES) {
    for (const ent of entities[t]) {
      const name = ent[NAME_FIELD[t]] || '';
      // Prefer exact char offsets; fall back to context indexOf
      if (ent.char_start != null && ent.char_end != null) {
        spans.push({ start: ent.char_start, end: ent.char_end, type: t, name });
        continue;
      }
      const ctx = ent.context || '';
      if (!ctx || ctx.length < 3) continue;
      let idx = fulltext.indexOf(ctx);
      if (idx === -1) {
        const short = ctx.substring(0, 60);
        idx = fulltext.indexOf(short);
      }
      if (idx >= 0) {
        const len = idx === fulltext.indexOf(ctx) ? ctx.length : 60;
        spans.push({ start: idx, end: idx + len, type: t, name });
      }
    }
  }

  // Add soft alias spans
  const relatedEntityNames = activeEntityName ? getRelatedNames(activeEntityName) : new Set();
  for (const sa of softAliases) {
    if (sa.char_start != null) {
      const isAliasActive = activeEntityName && sa.entity_name === activeEntityName;
      spans.push({ start: sa.char_start, end: sa.char_end, type: sa.entity_type,
                   isSoftAlias: true, isAliasActive, name: sa.entity_name });
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
    const safeName = escapeHtml(s.name || '');
    if (s.isSoftAlias) {
      const cls = s.isAliasActive ? 'highlight-soft-alias-active' : 'highlight-soft-alias';
      html += `<span class="highlight-${s.type} ${cls}" data-entity-name="${safeName}">${escapeHtml(fulltext.slice(s.start, s.end))}</span>`;
    } else {
      const isActive  = activeEntityName && s.name === activeEntityName;
      const isRelated = !isActive && relatedEntityNames.has(s.name);
      const extra = isActive ? ' highlight-active' : (isRelated ? ' highlight-related' : '');
      html += `<span class="highlight-${s.type}${extra}" data-entity-name="${safeName}">${escapeHtml(fulltext.slice(s.start, s.end))}</span>`;
    }
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
    const locClass = hasLoc ? ' has-location' : '';
    const isActive = activeEntityName === name;
    const activeClass = isActive ? ' card-active' : '';

    // Soft aliases for this entity
    const myAliases = softAliases.map((sa, si) => ({ sa, si })).filter(({ sa }) => sa.entity_name === name);
    const aliasCount = myAliases.length;
    const aliasBadge = aliasCount > 0 ? ` <span class="alias-count-badge">${aliasCount}~</span>` : '';
    const aliasListHtml = myAliases.map(({ sa, si }) =>
      `<span class="alias-pill" title="${escapeHtml(sa.alias_text)}">${escapeHtml(sa.alias_text)}
        <button class="alias-pill-remove" onclick="event.stopPropagation(); removeSoftAlias(${si})">×</button>
      </span>`
    ).join('');

    return `
      <div class="entity-card${locClass}${activeClass}" onclick="selectEntity('${type}', ${i})">
        <div style="flex:1;min-width:0;">
          <div class="entity-name">${escapeHtml(name)}${aliasBadge}</div>
          <div class="entity-meta">${escapeHtml(metaParts.join(' | '))}</div>
          ${aliasListHtml ? `<div class="alias-list">${aliasListHtml}</div>` : ''}
        </div>
        <div class="entity-actions">
          <button class="btn btn-sm" onclick="event.stopPropagation(); findAll('${type}', ${i})">Find</button>
          <button class="btn btn-sm" onclick="event.stopPropagation(); addToDict('${type}', ${i})">+Dict</button>
          <button class="btn btn-sm btn-alias" onclick="event.stopPropagation(); startSoftAlias('${type}', ${i})" title="Add soft alias — mark text that refers to this entity">Alias</button>
          <button class="btn btn-sm btn-danger" onclick="event.stopPropagation(); removeEntity('${type}', ${i})">x</button>
        </div>
      </div>
    `;
  }).join('');
}

function removeEntity(type, index) {
  entities[type].splice(index, 1);
  if (activeEntityName && !Object.values(entities).flat().some(e =>
      (e[NAME_FIELD[type]] || e.name || e.title) === activeEntityName)) {
    activeEntityName = null;
  }
  renderEntityList(type);
  renderText();
}

function selectEntity(type, index) {
  const ent = entities[type][index];
  const name = ent[NAME_FIELD[type]] || '';
  // Toggle: clicking the same card again deselects
  activeEntityName = (activeEntityName === name) ? null : name;
  renderAllEntityLists();
  renderText();
  if (ent.char_start != null) scrollToOffset(ent.char_start, ent.char_end);
}

function findAndAddSoftAliases(entityName, entityType, aliasText, searchFrom) {
  // Whole-word matches at or after searchFrom
  const candidates = findWordBoundaryMatches(fulltext, aliasText)
    .filter(m => m.char_start >= searchFrom);

  let added = 0, skipped = 0;
  for (const { char_start, char_end } of candidates) {
    // Skip if inside or overlapping an already-tagged entity span
    if (isInsideExistingTag(char_start, char_end)) { skipped++; continue; }
    // Skip if the match sits inside a longer tagged entity name at this position
    if (isInsideLongerPhrase(char_start, char_end)) { skipped++; continue; }
    // Skip duplicates
    if (softAliases.some(sa => sa.entity_name === entityName && sa.char_start === char_start)) continue;
    softAliases.push({
      entity_name: entityName,
      entity_type: entityType,
      alias_text:  aliasText,
      char_start,
      char_end,
      context: fulltext.slice(Math.max(0, char_start - 20), char_end + 20),
    });
    added++;
  }
  return { added, skipped };
}

function startSoftAlias(type, index) {
  const ent = entities[type][index];
  const name = ent[NAME_FIELD[type]] || '';
  pendingSoftAliasEntity = { name, type };
  const banner = document.getElementById('alias-capture-banner');
  banner.textContent = `Select text that refers to "${name}" — Esc to cancel`;
  banner.classList.remove('hidden');
}

function removeSoftAlias(index) {
  softAliases.splice(index, 1);
  renderAllEntityLists();
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

function getCharOffsetInTextContent(container, rangeNode, rangeOffset) {
  // Walk text nodes in container, accumulate char counts until we reach rangeNode
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT, null);
  let total = 0;
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node === rangeNode) return total + rangeOffset;
    total += node.textContent.length;
  }
  return total + rangeOffset;
}

function setupTextSelection() {
  const textContent = document.getElementById('text-content');
  textContent.addEventListener('mouseup', (e) => {
    const sel = window.getSelection();
    const text = (sel.toString() || '').trim();
    if (text.length < 1) return;

    // Capture real char offsets from the live selection range
    if (sel.rangeCount > 0) {
      const range = sel.getRangeAt(0);
      const container = document.getElementById('text-content');
      const start = getCharOffsetInTextContent(container, range.startContainer, range.startOffset);
      const end   = getCharOffsetInTextContent(container, range.endContainer,   range.endOffset);
      pendingSelectionOffsets = { char_start: start, char_end: end };
    }

    // Soft-alias capture mode: consume the selection as an alias
    if (pendingSoftAliasEntity && text.length >= 1) {
      softAliases.push({
        entity_name: pendingSoftAliasEntity.name,
        entity_type: pendingSoftAliasEntity.type,
        alias_text: text,
        char_start: pendingSelectionOffsets ? pendingSelectionOffsets.char_start : null,
        char_end:   pendingSelectionOffsets ? pendingSelectionOffsets.char_end   : null,
        context: text.substring(0, 150),
      });
      pendingSoftAliasEntity = null;
      pendingSelectionOffsets = null;
      document.getElementById('alias-capture-banner').classList.add('hidden');
      renderText();
      return;
    }

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

let popNameDebounce = null;
let _popDictCache = {}; // entity_id → entry, for field auto-fill

function setupPopover() {
  const popType = document.getElementById('pop-type');
  popType.addEventListener('change', () => {
    renderExtraFields(popType.value);
    // Re-run autocomplete with current name for new type
    const q = document.getElementById('pop-name').value.trim();
    if (q.length >= 2) fetchPopSuggestions(q, popType.value);
    else hidePopSuggestions();
  });

  const popName = document.getElementById('pop-name');
  popName.addEventListener('input', () => {
    clearTimeout(popNameDebounce);
    const q = popName.value.trim();
    if (q.length < 2) { hidePopSuggestions(); return; }
    popNameDebounce = setTimeout(() => fetchPopSuggestions(q, document.getElementById('pop-type').value), 200);
  });
  popName.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { hidePopSuggestions(); e.stopPropagation(); }
  });

  document.getElementById('pop-cancel').addEventListener('click', hidePopover);
  document.getElementById('pop-add').addEventListener('click', addEntityFromPopover);
  document.getElementById('pop-prefix').addEventListener('input', renderSplitPreview);

  // Close popover on Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') hidePopover();
  });
}

async function fetchPopSuggestions(query, type) {
  try {
    const res = await fetch(`/api/dictionary?search=${encodeURIComponent(query)}&type=${encodeURIComponent(type)}`);
    const results = await res.json();
    // Cache all returned entries for field auto-fill
    for (const e of results) _popDictCache[e.entity_id] = e;
    renderPopSuggestions(results.slice(0, 6));
  } catch { hidePopSuggestions(); }
}

function renderPopSuggestions(results) {
  const box = document.getElementById('pop-name-suggestions');
  if (!results.length) { hidePopSuggestions(); return; }
  box.classList.remove('hidden');
  box.innerHTML = results.map(e =>
    `<div class="pop-suggestion" onmousedown="applyPopSuggestion('${escapeHtml(e.entity_id)}')">
      ${escapeHtml(e.canonical_name)}
      ${e.acronym ? `<span class="meta-tag">${escapeHtml(e.acronym)}</span>` : ''}
    </div>`
  ).join('');
}

function hidePopSuggestions() {
  document.getElementById('pop-name-suggestions').classList.add('hidden');
}

function applyPopSuggestion(entityId) {
  const entry = _popDictCache[entityId];
  if (!entry) return;
  hidePopSuggestions();

  // Fill name field
  document.getElementById('pop-name').value = entry.canonical_name;

  // Auto-set type to match dictionary entry
  const typeSelect = document.getElementById('pop-type');
  if (entry.entity_type) {
    typeSelect.value = entry.entity_type;
    renderExtraFields(entry.entity_type);
  }

  // Fill known metadata fields — never touch context or offset inputs
  const meta = entry.metadata || {};
  const fieldMap = {
    acronym:    entry.acronym,
    parent_org: meta.parent_org,
    citation:   meta.citation,
    ref_type:   meta.ref_type,
    doc_type:   meta.doc_type,
    owner_org:  meta.owner_org,
  };
  for (const [key, val] of Object.entries(fieldMap)) {
    if (!val) continue;
    const el = document.getElementById(`pop-extra-${key}`);
    if (el) el.value = val;
  }

  // Show alias section since this is a known entity — user may want to mark hereafter text
  document.getElementById('pop-alias-section').classList.remove('hidden');
  document.getElementById('pop-alias-text').value = '';
  document.getElementById('pop-alias-text').focus();
}

function showPopover(x, y, selectedText) {
  const pop = document.getElementById('entity-popover');
  pop.classList.remove('hidden');
  hideSplitMode();
  hidePopSuggestions();

  // Position near click, but keep on screen
  const maxX = window.innerWidth - 320;
  const maxY = window.innerHeight - 400;
  pop.style.left = Math.min(x, maxX) + 'px';
  pop.style.top = Math.min(y + 10, maxY) + 'px';

  document.getElementById('pop-name').value = selectedText;
  document.getElementById('pop-context').value = selectedText.substring(0, 150);
  renderExtraFields(document.getElementById('pop-type').value);

  // Reset alias section
  document.getElementById('pop-alias-section').classList.add('hidden');
  document.getElementById('pop-alias-text').value = '';

  // If text contains commas, show the "Split list…" button and pre-seed split state
  const hasComma = selectedText.includes(',');
  const splitBtn = document.getElementById('pop-split-toggle');
  splitBtn.style.display = hasComma ? '' : 'none';
  if (hasComma) {
    splitSourceText = selectedText;
    splitSourceOffsets = pendingSelectionOffsets;
    document.getElementById('pop-prefix').value = guessPrefix(selectedText);
  }
}

function hidePopover() {
  document.getElementById('entity-popover').classList.add('hidden');
  hideSplitMode();
  hidePopSuggestions();
}

function toggleAliasSection() {
  const sec = document.getElementById('pop-alias-section');
  sec.classList.toggle('hidden');
  if (!sec.classList.contains('hidden')) document.getElementById('pop-alias-text').focus();
}

// ---------------------------------------------------------------------------
// Split / bulk entity mode ("Bureau of X, Y, and Z")
// ---------------------------------------------------------------------------

let splitSourceText = '';      // the full selected text for split mode
let splitSourceOffsets = null; // pendingSelectionOffsets at the time popover opened

function guessPrefix(text) {
  // Heuristic: find the longest leading word sequence before the first comma
  // e.g. "Bureau of AI, Cybersecurity" → "Bureau of"
  const firstComma = text.indexOf(',');
  if (firstComma === -1) return '';
  const before = text.substring(0, firstComma).trim();
  // Walk back from end of before to find where the last "item" starts
  // (last word that is likely a suffix, not the prefix)
  const words = before.split(/\s+/);
  if (words.length <= 1) return '';
  // Guess: prefix is everything except the last word
  return words.slice(0, -1).join(' ');
}

function parseSplitItems(prefix, text) {
  // Strip "and"/"or" before last item, split on commas, prepend prefix to each
  const stripped = text.replace(/\band\b|\bor\b/gi, ',').replace(/,+/g, ',');
  return stripped.split(',')
    .map(s => s.trim())
    .filter(s => s.length > 0)
    .map(suffix => prefix ? `${prefix} ${suffix}` : suffix);
}

function showSplitMode() {
  document.getElementById('pop-single-mode').style.display = 'none';
  document.getElementById('pop-split-mode').style.display = '';
  renderSplitPreview();
  document.getElementById('pop-prefix').focus();
}

function hideSplitMode() {
  document.getElementById('pop-split-mode').style.display = 'none';
  document.getElementById('pop-single-mode').style.display = '';
}

function renderSplitPreview() {
  const prefix = document.getElementById('pop-prefix').value.trim();
  const items = parseSplitItems(prefix, splitSourceText);
  const preview = document.getElementById('pop-split-preview');
  if (!items.length) { preview.innerHTML = '<em style="color:#888">No items parsed</em>'; return; }
  preview.innerHTML = items.map((name, i) =>
    `<div class="split-item">
      <input type="text" class="split-item-input" value="${escapeHtml(name)}" data-idx="${i}" />
    </div>`
  ).join('');
}

function addAllFromSplit() {
  const type = document.getElementById('pop-type').value;
  const nf = NAME_FIELD[type];
  const inputs = document.querySelectorAll('.split-item-input');
  const offsets = splitSourceOffsets; // all entities share the list's span location

  inputs.forEach(input => {
    const name = input.value.trim();
    if (!name) return;
    const ent = { [nf]: name, context: splitSourceText.substring(0, 150) };
    if (offsets) {
      ent.char_start = offsets.char_start;
      ent.char_end   = offsets.char_end;
    }
    entities[type].push(ent);
  });

  splitSourceOffsets = null;
  hidePopover();
  renderEntityList(type);
  renderText();
}

function getTaggedOrgNames() {
  // Returns org names currently tagged in this document, deduped
  return [...new Set(entities.organizations.map(e => e.name).filter(Boolean))];
}

function renderExtraFields(type) {
  const container = document.getElementById('pop-extra-fields');
  const fields = EXTRA_FIELDS[type] || [];
  const taggedOrgs = getTaggedOrgNames();

  container.innerHTML = fields.map(f => {
    if (f.options) {
      return `<label>${f.label}
        <select id="pop-extra-${f.key}">
          <option value="">—</option>
          ${f.options.map(o => `<option value="${o}">${o}</option>`).join('')}
        </select>
      </label>`;
    }
    if (f.org_ref) {
      const listId = `pop-extra-${f.key}-list`;
      const opts = taggedOrgs.map(n => `<option value="${escapeHtml(n)}">`).join('');
      return `<label class="org-ref-label">${f.label}
        <div class="org-ref-wrap">
          <input type="text" id="pop-extra-${f.key}" list="${listId}" autocomplete="off"
            placeholder="Type or select…" class="org-ref-input" />
          <datalist id="${listId}">${opts}</datalist>
        </div>
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

  // Use offsets captured at mouseup time — do NOT derive from context string
  let entityOffsets = null;
  if (pendingSelectionOffsets) {
    ent.char_start = pendingSelectionOffsets.char_start;
    ent.char_end   = pendingSelectionOffsets.char_end;
    entityOffsets  = pendingSelectionOffsets;
    pendingSelectionOffsets = null;
  }

  // Hereafter alias: find all occurrences of alias text AFTER the entity's location
  const aliasText = document.getElementById('pop-alias-text').value.trim();
  if (aliasText && fulltext) {
    const searchFrom = entityOffsets ? entityOffsets.char_end : 0;
    const { added, skipped } = findAndAddSoftAliases(name, type, aliasText, searchFrom);
    const msg = `Hereafter alias "<em>${escapeHtml(aliasText)}</em>": `
      + `tagged <strong>${added}</strong> occurrence${added !== 1 ? 's' : ''}`
      + (skipped > 0 ? `, skipped <strong>${skipped}</strong> (inside longer phrases or existing tags)` : '')
      + `. <button class="btn btn-sm" onclick="dismissFindAllBanner()">Dismiss</button>`;
    showFindAllBanner(msg, 8000);
  }

  entities[type].push(ent);
  hidePopover();
  renderEntityList(type);
  renderText();
  // If an org was just added, refresh extra fields so org-ref datalists pick it up
  if (type === 'organizations') renderExtraFields(document.getElementById('pop-type').value);
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
    payload.soft_aliases = softAliases;
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
  if (pendingSelectionOffsets) {
    rel.context_start = pendingSelectionOffsets.char_start;
    rel.context_end   = pendingSelectionOffsets.char_end;
    pendingSelectionOffsets = null;
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
// Find all occurrences + auto-tag untagged
// ---------------------------------------------------------------------------

let _findAllPending = null; // { type, index, untagged: [{char_start,char_end}] }

let _findAllBannerTimer = null;

function showFindAllBanner(html, autoDismissMs = 12000) {
  clearTimeout(_findAllBannerTimer);
  const banner = document.getElementById('find-all-banner');
  banner.innerHTML = html;
  banner.classList.remove('hidden');
  if (autoDismissMs) _findAllBannerTimer = setTimeout(() => dismissFindAllBanner(), autoDismissMs);
}

function findAll(type, index) {
  const ent = entities[type][index];
  const nf = NAME_FIELD[type];
  const name = ent[nf] || '';
  if (!name || name.length < 2) return;

  // Whole-word matches only
  const allOffsets = findWordBoundaryMatches(fulltext, name);

  if (!allOffsets.length) {
    alert(`"${name}" not found in document text (whole-word match).`);
    return;
  }

  // Which are NOT already tagged for this entity?
  const needle = name.toLowerCase();
  const taggedStarts = new Set(
    entities[type]
      .filter(e => (e[nf] || '').toLowerCase() === needle && e.char_start != null)
      .map(e => e.char_start)
  );
  const untagged = allOffsets.filter(o => !taggedStarts.has(o.char_start));

  // Highlight all occurrences in the text panel
  renderText();
  const textEl = document.getElementById('text-content');
  const escapedName = escapeHtml(name);
  const regex = new RegExp(escapedName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
  textEl.innerHTML = textEl.innerHTML.replace(regex, `<span class="find-all-highlight">$&</span>`);
  const first = textEl.querySelector('.find-all-highlight');
  if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });

  // Show tag-all banner
  _findAllPending = { type, index, untagged };
  if (untagged.length > 0) {
    showFindAllBanner(
      `<strong>${allOffsets.length}</strong> occurrence${allOffsets.length !== 1 ? 's' : ''} of
       "<em>${escapeHtml(name)}</em>" &mdash;
       <strong>${untagged.length}</strong> not yet tagged.
       <button class="btn btn-sm btn-primary" onclick="tagAllUntagged()">Tag all ${untagged.length}</button>
       <button class="btn btn-sm" onclick="dismissFindAllBanner()">Dismiss</button>`
    );
  } else {
    showFindAllBanner(
      `<strong>${allOffsets.length}</strong> occurrence${allOffsets.length !== 1 ? 's' : ''} of
       "<em>${escapeHtml(name)}</em>" — all already tagged.
       <button class="btn btn-sm" onclick="dismissFindAllBanner()">Dismiss</button>`
    );
  }
}

function tagAllUntagged() {
  if (!_findAllPending) return;
  const { type, index, untagged } = _findAllPending;
  const ent = entities[type][index];

  for (const { char_start, char_end } of untagged) {
    // Clone the entity's metadata but give each instance its own location
    const newEnt = Object.assign({}, ent, {
      context:    fulltext.slice(Math.max(0, char_start - 20), char_end + 20).substring(0, 150),
      char_start,
      char_end,
    });
    entities[type].push(newEnt);
  }

  dismissFindAllBanner();
  renderEntityList(type);
  renderText();
}

function dismissFindAllBanner() {
  clearTimeout(_findAllBannerTimer);
  _findAllPending = null;
  document.getElementById('find-all-banner').classList.add('hidden');
  renderText(); // clear find-all highlights
}

// Close popovers / cancel modes on Escape
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeRelationshipModal();
    hideRelPopover();
    hidePopover();
    if (pendingSoftAliasEntity) {
      pendingSoftAliasEntity = null;
      pendingSelectionOffsets = null;
      document.getElementById('alias-capture-banner').classList.add('hidden');
    }
  }
});

// Boot
setupQuickAddLookup();
init();
