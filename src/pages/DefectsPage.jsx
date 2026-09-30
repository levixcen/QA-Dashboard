import { useState, useEffect } from 'react';
import { authFetch } from '../utils/auth';

const SEVERITY_OPTIONS = ['critical', 'high', 'medium', 'low'];
const STATUS_OPTIONS = ['open', 'in_progress', 'retest', 'reopened', 'closed'];
const SEVERITY_RANK = { critical: 4, high: 3, medium: 2, low: 1 };
const MAX_FOLDER_NAME_LENGTH = 60;

function titleCase(str) {
  return (str || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

function severityRank(sev) {
  return SEVERITY_RANK[sev] || 0;
}

function FolderIcon() {
  return (
    <svg className="defect-folder-icon-svg" width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3 7.5A1.5 1.5 0 0 1 4.5 6H9l1.5 2H19.5A1.5 1.5 0 0 1 21 9.5v8A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5v-10Z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function DefectCard({ defect, selected, onToggleSelect, onEdit, onDelete, onUncluster }) {
  return (
    <div className={`module-card defect-card severity-border-${defect.severity}`}>
      <div className="module-header">
        <label className="defect-select">
          <input type="checkbox" checked={selected} onChange={onToggleSelect} />
          <span className="defect-code">{defect.defect_code}</span>
        </label>
        <div className="defect-card-header-right">
          <span className={`severity-badge-inline severity-${defect.severity}`}>{titleCase(defect.severity)}</span>
          <button
            type="button"
            className="module-meta-edit-trigger"
            onClick={onEdit}
            title="Edit defect"
          >
            &#9998;
          </button>
        </div>
      </div>

      <div className="module-name">{defect.description}</div>

      <div className="status-row">
        <span>{defect.module}</span>
        <span>{titleCase(defect.status)}</span>
      </div>

      <div className="details">
        <div className="detail-row">
          <span>Owner</span>
          <span style={{ color: '#5a7a9a', fontWeight: 400 }}>{defect.owner || 'Unassigned'}</span>
        </div>
        <div className="detail-row">
          <span>Raised</span>
          <span style={{ color: '#5a7a9a', fontWeight: 400 }}>{defect.raised_date || '—'}</span>
        </div>
        <div className="detail-row">
          <span>Due</span>
          <span style={{ color: '#5a7a9a', fontWeight: 400 }}>{defect.eta || '—'}</span>
        </div>
        <div className="detail-row">
          <span>Impacted TCs</span>
          <span style={{ color: '#5a7a9a', fontWeight: 400 }}>{defect.impacted_tc_count}</span>
        </div>
        {defect.source_ref && (
          <div className="detail-row">
            <span>Source</span>
            <span style={{ color: '#5a7a9a', fontWeight: 400 }}>{defect.source_ref}</span>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', gap: 8, marginTop: 4, flexWrap: 'wrap' }}>
        {onUncluster && (
          <button type="button" className="archive" onClick={onUncluster}>Remove from folder</button>
        )}
        <button type="button" className="archive" onClick={onDelete} style={{ color: '#C5221F' }}>
          Delete
        </button>
      </div>
    </div>
  );
}

function ClusterFolder({
  clusterId,
  members,
  expanded,
  onToggle,
  renderCard,
  allSelected,
  onToggleSelectAll,
  isRenaming,
  renameDraft,
  renameError,
  onStartRename,
  onRenameChange,
  onSaveRename,
  onCancelRename,
  onUngroup,
}) {
  const openMembers = members.filter(m => m.status !== 'closed');
  const worst = openMembers.length
    ? openMembers.reduce((acc, m) => (severityRank(m.severity) > severityRank(acc) ? m.severity : acc), openMembers[0].severity)
    : null;

  return (
    <div className={`defect-folder ${expanded ? 'expanded' : ''}`}>
      <div
        className="defect-folder-header"
        style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', flexWrap: 'wrap' }}
        onClick={onToggle}
      >
        <input
          type="checkbox"
          checked={allSelected}
          onChange={onToggleSelectAll}
          onClick={e => e.stopPropagation()}
          title="Select all in this folder"
        />
        <span className="defect-folder-chevron">{expanded ? '▾' : '▸'}</span>
        <span className="defect-folder-icon" aria-hidden="true"><FolderIcon /></span>

        {isRenaming ? (
          <span
            onClick={e => e.stopPropagation()}
            style={{ display: 'flex', gap: 6, alignItems: 'center' }}
          >
            <input
              autoFocus
              value={renameDraft}
              maxLength={MAX_FOLDER_NAME_LENGTH}
              onChange={e => onRenameChange(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') onSaveRename();
                if (e.key === 'Escape') onCancelRename();
              }}
            />
            <button type="button" className="archive" onClick={onSaveRename}>Save</button>
            <button type="button" className="archive" onClick={onCancelRename}>Cancel</button>
          </span>
        ) : (
          <span
            className="defect-folder-title"
            onClick={e => { e.stopPropagation(); onStartRename(); }}
            title="Click to rename this folder"
            style={{ cursor: 'text' }}
          >
            {clusterId}
          </span>
        )}

        <span className="defect-folder-count">{members.length} defect{members.length === 1 ? '' : 's'}</span>
        <span className="defect-folder-count">
          {worst ? `${openMembers.length} open, worst ${titleCase(worst)}` : 'All closed'}
        </span>

        <button
          type="button"
          className="archive"
          onClick={e => { e.stopPropagation(); onUngroup(); }}
          style={{ marginLeft: 'auto' }}
        >
          Ungroup folder
        </button>
      </div>

      {isRenaming && renameError && (
        <div className="module-meta-error" style={{ marginLeft: 32 }}>{renameError}</div>
      )}

      {expanded && (
        <div className="defect-folder-body">
          {members.map(renderCard)}
        </div>
      )}
    </div>
  );
}

function DefectsPage({ username }) {
  const [defects, setDefects] = useState([]);
  const [features, setFeatures] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(new Set());
  const [statusFilter, setStatusFilter] = useState('All');
  const [expandedFolders, setExpandedFolders] = useState(new Set());
  const [moveTarget, setMoveTarget] = useState('');

  const [renamingClusterId, setRenamingClusterId] = useState(null);
  const [renameDraft, setRenameDraft] = useState('');
  const [renameError, setRenameError] = useState(null);

  const [newDefect, setNewDefect] = useState({
    description: '', severity: 'medium', module: '', owner: '', eta: '',
  });
  const [addError, setAddError] = useState(null);
  const [adding, setAdding] = useState(false);
  const [creatingFromFailures, setCreatingFromFailures] = useState(false);

  // Edit overlay (same pattern as Projects)
  const [editingId, setEditingId] = useState(null);
  const [editDraft, setEditDraft] = useState(null);
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState(null);

  const editingDefect = editingId != null
    ? defects.find(d => d.id === editingId) || null
    : null;

  function openEdit(defect) {
    setEditingId(defect.id);
    setEditDraft({
      description: defect.description || '',
      severity: defect.severity || 'medium',
      status: defect.status || 'open',
      owner: defect.owner || '',
      module: defect.module || '',
      eta: defect.eta || '',
      raised_date: defect.raised_date || '',
      impacted_tc_count: defect.impacted_tc_count ?? 0,
    });
    setEditError(null);
  }

  function closeEdit() {
    setEditingId(null);
    setEditDraft(null);
    setEditError(null);
    setEditSaving(false);
  }

  async function saveEdit() {
    if (!editingId || !editDraft) return;
    const description = (editDraft.description || '').trim();
    if (!description) {
      setEditError('Description is required.');
      return;
    }
    if (!(editDraft.module || '').trim()) {
      setEditError('Pick a feature.');
      return;
    }
    setEditSaving(true);
    setEditError(null);
    try {
      await handleUpdateDefect(editingId, {
        description,
        severity: editDraft.severity,
        status: editDraft.status,
        owner: (editDraft.owner || '').trim() || null,
        module: editDraft.module,
        eta: editDraft.eta || null,
        raised_date: editDraft.raised_date || null,
        impacted_tc_count: Number(editDraft.impacted_tc_count) || 0,
      });
      closeEdit();
    } catch (err) {
      setEditError(err.message || 'Failed to save');
    } finally {
      setEditSaving(false);
    }
  }

  useEffect(() => {
    fetchAll();
  }, []);

  async function fetchAll() {
    setLoading(true);
    setError('');
    try {
      const [defectsRes, featuresRes] = await Promise.all([
        authFetch('/api/defects'),
        authFetch('/api/features'),
      ]);
      if (!defectsRes.ok || !featuresRes.ok) throw new Error('bad response');
      setDefects(await defectsRes.json());
      setFeatures((await featuresRes.json()).filter(f => !f.archived));
      setLoading(false);
    } catch (err) {
      setError('Could not load defects.');
      setLoading(false);
    }
  }

  async function handleAddDefect() {
    const description = newDefect.description.trim();
    const module = newDefect.module.trim();
    if (!description) {
      setAddError('Description is required.');
      return;
    }
    if (!module) {
      setAddError('Pick a feature.');
      return;
    }
    setAdding(true);
    setAddError(null);
    try {
      const res = await authFetch('/api/defects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description,
          severity: newDefect.severity,
          module,
          owner: newDefect.owner.trim() || null,
          eta: newDefect.eta || null,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to add defect');
      }
      setNewDefect({ description: '', severity: 'medium', module: '', owner: '', eta: '' });
      await fetchAll();
    } catch (err) {
      setAddError(err.message);
    } finally {
      setAdding(false);
    }
  }

  async function handleCreateFromFailures() {
    setCreatingFromFailures(true);
    try {
      const res = await authFetch('/api/defects/from-failures', { method: 'POST' });
      if (!res.ok) throw new Error('Failed to create defects');
      const data = await res.json();
      window.alert(`Created ${data.created} defect(s) from current failures.${data.skipped ? ` Skipped ${data.skipped} with no valid feature.` : ''}`);
      await fetchAll();
    } catch (err) {
      window.alert('Could not create defects from failures.');
    } finally {
      setCreatingFromFailures(false);
    }
  }

  function toggleSelect(id) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function toggleSelectAllInFolder(members) {
    const ids = members.map(m => m.id);
    const allSelected = ids.length > 0 && ids.every(id => selected.has(id));
    setSelected(prev => {
      const next = new Set(prev);
      if (allSelected) {
        ids.forEach(id => next.delete(id));
      } else {
        ids.forEach(id => next.add(id));
      }
      return next;
    });
  }

  function toggleFolder(clusterId) {
    setExpandedFolders(prev => {
      const next = new Set(prev);
      if (next.has(clusterId)) next.delete(clusterId); else next.add(clusterId);
      return next;
    });
  }

  async function handleGroupSelected() {
    const groupingIntoExisting = moveTarget !== '';
    if (!groupingIntoExisting && selected.size < 2) return;
    if (groupingIntoExisting && selected.size < 1) return;

    const existingMembers = groupingIntoExisting ? (clusters[moveTarget] || []) : [];
    const mergedIds = new Set([...selected, ...existingMembers.map(m => m.id)]);

    try {
      const res = await authFetch('/api/defects/cluster', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          defect_ids: [...mergedIds],
          ...(groupingIntoExisting ? { cluster_id: moveTarget } : {}),
        }),
      });
      if (!res.ok) throw new Error('Failed to group');
      const data = await res.json();
      setSelected(new Set());
      setMoveTarget('');
      if (data.cluster_id) {
        setExpandedFolders(prev => new Set([...prev, data.cluster_id]));
      }
      await fetchAll();
    } catch (err) {
      window.alert('Could not group the selected defects.');
    }
  }

  async function handleUncluster(id) {
    try {
      const res = await authFetch(`/api/defects/${id}/uncluster`, { method: 'POST' });
      if (!res.ok) throw new Error('Failed to uncluster');
      await fetchAll();
    } catch (err) {
      window.alert('Could not remove this defect from its folder.');
    }
  }

  async function handleUngroupFolder(clusterId, members) {
    if (!window.confirm(`Ungroup this folder? Its ${members.length} defect${members.length === 1 ? '' : 's'} will become unclustered.`)) {
      return;
    }
    try {
      const results = await Promise.all(
        members.map(m => authFetch(`/api/defects/${m.id}/uncluster`, { method: 'POST' }))
      );
      if (results.some(r => !r.ok)) throw new Error('Failed to ungroup');
      await fetchAll();
    } catch (err) {
      window.alert('Could not ungroup this folder.');
    }
  }

  function startRename(clusterId) {
    setRenamingClusterId(clusterId);
    setRenameDraft(clusterId);
    setRenameError(null);
  }

  async function saveRename(clusterId, members) {
    const trimmed = renameDraft.trim();
    if (!trimmed) {
      setRenameError('Name cannot be empty.');
      return;
    }
    if (trimmed.length > MAX_FOLDER_NAME_LENGTH) {
      setRenameError(`Keep it under ${MAX_FOLDER_NAME_LENGTH} characters.`);
      return;
    }
    const collision = clusterEntries.some(([id]) => id !== clusterId && id === trimmed);
    if (collision) {
      setRenameError('A folder with that name already exists.');
      return;
    }
    if (trimmed === clusterId) {
      setRenamingClusterId(null);
      return;
    }
    try {
      const res = await authFetch('/api/defects/cluster', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ defect_ids: members.map(m => m.id), cluster_id: trimmed }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to rename folder');
      }
      setRenamingClusterId(null);
      await fetchAll();
    } catch (err) {
      setRenameError(err.message);
    }
  }

  async function handleUpdateDefect(id, patch) {
    const res = await authFetch(`/api/defects/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to update defect');
    }
    const updated = await res.json();
    setDefects(prev => prev.map(d => (d.id === id ? updated : d)));
    return updated;
  }

  async function handleDeleteDefect(id) {
    if (!window.confirm('Delete this defect? This cannot be undone.')) return;
    try {
      const res = await authFetch(`/api/defects/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed to delete defect');
      setDefects(prev => prev.filter(d => d.id !== id));
      setSelected(prev => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      if (editingId === id) closeEdit();
    } catch (err) {
      window.alert('Could not delete this defect.');
    }
  }

  const filtered = statusFilter === 'All' ? defects : defects.filter(d => d.status === statusFilter);
  const clusters = {};
  const unclustered = [];
  filtered.forEach(d => {
    if (d.cluster_id) {
      if (!clusters[d.cluster_id]) clusters[d.cluster_id] = [];
      clusters[d.cluster_id].push(d);
    } else {
      unclustered.push(d);
    }
  });
  const clusterEntries = Object.entries(clusters);

  function renderDefectCard(d) {
    return (
      <DefectCard
        key={d.id}
        defect={d}
        selected={selected.has(d.id)}
        onToggleSelect={() => toggleSelect(d.id)}
        onEdit={() => openEdit(d)}
        onDelete={() => handleDeleteDefect(d.id)}
        onUncluster={d.cluster_id ? () => handleUncluster(d.id) : null}
      />
    );
  }

  return (
    <>
      <div className="page-header">
        <div>
          <div className="brand welcome-brand">Welcome, {username || 'User'}</div>
          <h1>Defects</h1>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {selected.size >= 1 && (
            <>
              {clusterEntries.length > 0 && (
                <select
                  value={moveTarget}
                  onChange={e => setMoveTarget(e.target.value)}
                  title="Add selected defects into an existing folder"
                >
                  <option value="">Existing folder…</option>
                  {clusterEntries.map(([id]) => (
                    <option key={id} value={id}>{id}</option>
                  ))}
                </select>
              )}
              {moveTarget ? (
                <button className="btn btn-primary" onClick={handleGroupSelected}>
                  Add to folder ({selected.size})
                </button>
              ) : (
                <button
                  className="btn btn-primary"
                  onClick={handleGroupSelected}
                  disabled={selected.size < 2}
                >
                  New folder ({selected.size})
                </button>
              )}
              <button className="btn btn-dark" onClick={() => { setSelected(new Set()); setMoveTarget(''); }}>
                Clear selection
              </button>
            </>
          )}
          <button className="btn btn-dark" onClick={handleCreateFromFailures} disabled={creatingFromFailures}>
            {creatingFromFailures ? 'Creating...' : 'Create from current failures'}
          </button>
        </div>
      </div>

      <div className="controls">
        <div className="control-group">
          <label>Description</label>
          <input
            placeholder="What's broken?"
            value={newDefect.description}
            onChange={e => setNewDefect({ ...newDefect, description: e.target.value })}
          />
        </div>
        <div className="control-group">
          <label>Feature</label>
          <input
            list="defect-feature-list"
            placeholder="Select or type a feature"
            value={newDefect.module}
            onChange={e => setNewDefect({ ...newDefect, module: e.target.value })}
          />
          <datalist id="defect-feature-list">
            {features.map(f => (
              <option key={f.name} value={f.name} />
            ))}
          </datalist>
        </div>
        <div className="control-group">
          <label>Severity</label>
          <select
            value={newDefect.severity}
            onChange={e => setNewDefect({ ...newDefect, severity: e.target.value })}
          >
            {SEVERITY_OPTIONS.map(s => (
              <option key={s} value={s}>{titleCase(s)}</option>
            ))}
          </select>
        </div>
        <div className="control-group">
          <label>Owner</label>
          <input
            placeholder="e.g. Dara"
            value={newDefect.owner}
            onChange={e => setNewDefect({ ...newDefect, owner: e.target.value })}
          />
        </div>
        <div className="control-group">
          <label>Due</label>
          <input
            type="date"
            value={newDefect.eta}
            onChange={e => setNewDefect({ ...newDefect, eta: e.target.value })}
          />
        </div>
        <button className="btn btn-dark" onClick={handleAddDefect} disabled={adding}>
          {adding ? 'Adding...' : '+ Add Defect'}
        </button>
      </div>
      {addError && <div className="module-meta-error">{addError}</div>}

      <div className="filters">
        {['All', ...STATUS_OPTIONS].map(s => (
          <button
            key={s}
            className={`filter-btn ${statusFilter === s ? 'active' : ''}`}
            onClick={() => setStatusFilter(s)}
          >
            {s === 'All' ? 'All' : titleCase(s)}
          </button>
        ))}
      </div>

      {loading && <div className="placeholder"><p>Loading defects.</p></div>}
      {error && <div className="placeholder"><p>{error}</p></div>}

      {!loading && !error && filtered.length === 0 && (
        <div className="placeholder">
          <p>No defects yet. Add one above, or raise one from a failing test on the Features page.</p>
        </div>
      )}

      {!loading && !error && filtered.length > 0 && (
        <div className="defects-sections">
          {clusterEntries.length > 0 && (
            <section className="defects-section">
              <h2 className="defects-section-title">Clustered</h2>
              <div className="defects-folder-list">
                {clusterEntries.map(([clusterId, members]) => {
                  const ids = members.map(m => m.id);
                  const allSelected = ids.length > 0 && ids.every(id => selected.has(id));
                  return (
                    <ClusterFolder
                      key={clusterId}
                      clusterId={clusterId}
                      members={members}
                      expanded={expandedFolders.has(clusterId)}
                      onToggle={() => toggleFolder(clusterId)}
                      renderCard={renderDefectCard}
                      allSelected={allSelected}
                      onToggleSelectAll={() => toggleSelectAllInFolder(members)}
                      isRenaming={renamingClusterId === clusterId}
                      renameDraft={renamingClusterId === clusterId ? renameDraft : ''}
                      renameError={renamingClusterId === clusterId ? renameError : null}
                      onStartRename={() => startRename(clusterId)}
                      onRenameChange={setRenameDraft}
                      onSaveRename={() => saveRename(clusterId, members)}
                      onCancelRename={() => setRenamingClusterId(null)}
                      onUngroup={() => handleUngroupFolder(clusterId, members)}
                    />
                  );
                })}
              </div>
            </section>
          )}

          <section className="defects-section">
            <h2 className="defects-section-title">
              Unclustered
              {unclustered.length > 0 && (
                <span className="defects-section-count">{unclustered.length}</span>
              )}
            </h2>
            {unclustered.length === 0 ? (
              <p className="defects-section-empty">
                {clusterEntries.length > 0
                  ? 'All defects are in folders. Select two or more and use "New folder" to group more.'
                  : 'No unclustered defects.'}
              </p>
            ) : (
              <div className="modules">
                {unclustered.map(renderDefectCard)}
              </div>
            )}
          </section>
        </div>
      )}

      {/* Edit overlay — same pattern as Projects */}
      {editingDefect && editDraft && (
        <div
          className="modal-overlay"
          onClick={e => {
            if (e.target === e.currentTarget) closeEdit();
          }}
        >
          <div className="modal-content project-detail-modal">
            <div className="modal-header">
              <h2>{editingDefect.defect_code}</h2>
              <button type="button" className="modal-close" onClick={closeEdit}>
                ×
              </button>
            </div>
            <div className="modal-body">
              <div className="module-meta-form" style={{ marginTop: 0 }}>
                <label className="module-meta-field">
                  <span>Description</span>
                  <textarea
                    rows={3}
                    value={editDraft.description}
                    onChange={e => setEditDraft({ ...editDraft, description: e.target.value })}
                  />
                </label>
                <label className="module-meta-field">
                  <span>Feature</span>
                  <input
                    list="defect-edit-feature-list"
                    placeholder="Select or type a feature"
                    value={editDraft.module}
                    onChange={e => setEditDraft({ ...editDraft, module: e.target.value })}
                  />
                  <datalist id="defect-edit-feature-list">
                    {features.map(f => (
                      <option key={f.name} value={f.name} />
                    ))}
                  </datalist>
                </label>
                <label className="module-meta-field">
                  <span>Severity</span>
                  <select
                    value={editDraft.severity}
                    onChange={e => setEditDraft({ ...editDraft, severity: e.target.value })}
                  >
                    {SEVERITY_OPTIONS.map(s => (
                      <option key={s} value={s}>{titleCase(s)}</option>
                    ))}
                  </select>
                </label>
                <label className="module-meta-field">
                  <span>Status</span>
                  <select
                    value={editDraft.status}
                    onChange={e => setEditDraft({ ...editDraft, status: e.target.value })}
                  >
                    {STATUS_OPTIONS.map(s => (
                      <option key={s} value={s}>{titleCase(s)}</option>
                    ))}
                  </select>
                </label>
                <label className="module-meta-field">
                  <span>Owner</span>
                  <input
                    value={editDraft.owner}
                    onChange={e => setEditDraft({ ...editDraft, owner: e.target.value })}
                    placeholder="e.g. Dara"
                  />
                </label>
                <label className="module-meta-field">
                  <span>Raised</span>
                  <input
                    type="date"
                    value={editDraft.raised_date || ''}
                    onChange={e => setEditDraft({ ...editDraft, raised_date: e.target.value })}
                  />
                </label>
                <label className="module-meta-field">
                  <span>Due (expected fix-ready date)</span>
                  <input
                    type="date"
                    value={editDraft.eta || ''}
                    onChange={e => setEditDraft({ ...editDraft, eta: e.target.value })}
                  />
                </label>
                <label className="module-meta-field">
                  <span>Impacted TCs</span>
                  <input
                    type="number"
                    min="0"
                    value={editDraft.impacted_tc_count}
                    onChange={e => setEditDraft({ ...editDraft, impacted_tc_count: e.target.value })}
                  />
                </label>
                {editingDefect.source_ref && (
                  <div className="detail-row" style={{ marginTop: 4 }}>
                    <span>Source</span>
                    <span style={{ color: '#5a7a9a', fontWeight: 400 }}>{editingDefect.source_ref}</span>
                  </div>
                )}
                {editError && <div className="module-meta-error">{editError}</div>}
                <div className="module-meta-actions">
                  <button
                    type="button"
                    className="module-meta-save"
                    onClick={saveEdit}
                    disabled={editSaving}
                  >
                    {editSaving ? 'Saving...' : 'Save'}
                  </button>
                  <button type="button" className="module-meta-cancel" onClick={closeEdit}>
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default DefectsPage;
