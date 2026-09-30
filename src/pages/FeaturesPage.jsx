import { useState, useEffect } from 'react';
import { authFetch } from '../utils/auth';
import { usePeriod } from '../context/PeriodContext';
import ModuleMetaEditor from '../components/ModuleMetaEditor';
import ModuleTestsModal from '../components/ModuleTestsModal';

const FILTERS = ['All', 'Healthy', 'Needs Attention', 'Not Started'];

const SEVERITY_ORDER = ['critical', 'high', 'medium', 'low'];
const SEVERITY_LABELS = {
  critical: 'C',
  high: 'H',
  medium: 'M',
  low: 'L',
};

function FeaturesPage({ username, onUpdateModuleMeta }) {
  const { period } = usePeriod();
  const [modules, setModules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('All');
  const [showArchived, setShowArchived] = useState(false);
  const [newName, setNewName] = useState('');
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState(null);
  const [editingModule, setEditingModule] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [selectedModule, setSelectedModule] = useState(null);

  useEffect(() => {
    load();
  }, [period, showArchived]);

  async function load() {
    setLoading(true);
    setError('');
    setActionError(null);
    try {
      const q = new URLSearchParams();
      if (period) q.set('month', period);
      if (showArchived) q.set('archived', 'true');
      const res = await authFetch(`/api/reports/summary?${q.toString()}`);
      if (!res.ok) throw new Error('bad response');
      const data = await res.json();
      setModules(data.modules || []);
      setLoading(false);
    } catch (err) {
      setError('Could not load features.');
      setLoading(false);
    }
  }

  async function handleAdd() {
    const name = newName.trim();
    if (!name) {
      setAddError('Feature name is required.');
      return;
    }
    setAdding(true);
    setAddError(null);
    try {
      const res = await authFetch('/api/features', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to add feature');
      }
      setNewName('');
      await load();
    } catch (err) {
      setAddError(err.message);
    } finally {
      setAdding(false);
    }
  }

  async function handleArchive(name, archived) {
    setActionError(null);
    try {
      const res = await authFetch(`/api/features/${encodeURIComponent(name)}/archive`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ archived }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to update feature');
      }
      await load();
    } catch (err) {
      setActionError(err.message);
    }
  }

  async function handleDelete(name) {
    if (!window.confirm(`Delete feature "${name}"? Manual entries for it will be removed.`)) return;
    setActionError(null);
    try {
      const res = await authFetch(`/api/features/${encodeURIComponent(name)}`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to delete feature');
      }
      await load();
    } catch (err) {
      setActionError(err.message);
    }
  }

  async function handleMetaSave(moduleName, payload) {
    if (onUpdateModuleMeta) {
      await onUpdateModuleMeta(moduleName, payload);
    } else {
      const res = await authFetch(`/api/module-meta/${encodeURIComponent(moduleName)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error('Failed to save meta');
    }
    setEditingModule(null);
    await load();
  }

  const filtered = modules.filter(m => {
    if (filter === 'All') return true;
    if (filter === 'Healthy') return m.status === 'Healthy' || m.color === 'green';
    if (filter === 'Needs Attention') {
      return m.status === 'Needs Attention' || m.color === 'red' || m.color === 'orange';
    }
    if (filter === 'Not Started') return m.status === 'Not Started' || m.color === 'gray';
    return true;
  });

  return (
    <>
      <div className="page-header">
        <div>
          <div className="brand welcome-brand">Welcome, {username || 'User'}</div>
          <h1>Features</h1>
        </div>
        <button
          type="button"
          className={`btn ${showArchived ? 'btn-primary' : 'btn-dark'}`}
          onClick={() => setShowArchived(v => !v)}
        >
          {showArchived ? 'Active features' : 'Archived'}
        </button>
      </div>

      {!showArchived && (
        <div className="controls">
          <div className="control-group" style={{ flex: 1, minWidth: 200 }}>
            <label>Add feature</label>
            <input
              placeholder="e.g. Marketplace"
              value={newName}
              onChange={e => setNewName(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter') handleAdd();
              }}
            />
          </div>
          <button className="btn btn-dark" onClick={handleAdd} disabled={adding}>
            {adding ? 'Adding...' : '+ Add'}
          </button>
        </div>
      )}
      {addError && <div className="module-meta-error">{addError}</div>}
      {actionError && <div className="module-meta-error">{actionError}</div>}

      <div className="filters">
        {FILTERS.map(f => (
          <button
            key={f}
            type="button"
            className={`filter-btn ${filter === f ? 'active' : ''}`}
            onClick={() => setFilter(f)}
          >
            {f}
          </button>
        ))}
      </div>

      {loading && (
        <div className="placeholder">
          <p>Loading features.</p>
        </div>
      )}
      {error && (
        <div className="placeholder">
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && filtered.length === 0 && (
        <div className="placeholder">
          <p>
            {showArchived
              ? 'No archived features.'
              : 'No features match this filter.'}
          </p>
        </div>
      )}

      {!loading && !error && filtered.length > 0 && (
        <div className="modules">
          {filtered.map(m => {
            const sev = m.defects_by_severity || {};
            const hasSev =
              (sev.critical || 0) + (sev.high || 0) + (sev.medium || 0) + (sev.low || 0) > 0;
            const failSev = m.severity || {};
            const hasFailSev =
              !hasSev &&
              ((failSev.critical || 0) +
                (failSev.high || 0) +
                (failSev.medium || 0) +
                (failSev.low || 0) >
                0);

            return (
              <div
                key={m.name}
                className="module-card"
                role="button"
                tabIndex={0}
                style={{ cursor: 'pointer' }}
                onClick={() => setSelectedModule(m.name)}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setSelectedModule(m.name);
                  }
                }}
              >
                <div className="module-header">
                  <div className="module-name">
                    <span className={`icon ${m.color}`}>
                      {m.color === 'green'
                        ? '✓'
                        : m.color === 'orange'
                          ? '!'
                          : m.color === 'gray'
                            ? '○'
                            : '×'}
                    </span>
                    {m.name}
                  </div>
                  <div className="module-pct-wrap">
                    <span className="module-pct">{m.pct}%</span>
                    <button
                      type="button"
                      className="module-meta-edit-trigger"
                      onClick={e => {
                        e.stopPropagation();
                        setEditingModule(editingModule === m.name ? null : m.name);
                      }}
                      title="Edit PIC, mitigation, planned TCs"
                    >
                      &#9998;
                    </button>
                  </div>
                </div>

                <div className="progress">
                  <div
                    className={`progress-bar ${m.color}`}
                    style={{ width: `${m.pct}%` }}
                  />
                </div>

                <div className="status-row">
                  <span>{m.status}</span>
                  {m.failing > 0 ? (
                    <span className="failing">{m.failing} failing</span>
                  ) : (
                    <span style={{ color: '#5a7a9a' }}>
                      {(m.open_defects || 0) > 0
                        ? `${m.open_defects} open defect${m.open_defects === 1 ? '' : 's'}`
                        : '—'}
                    </span>
                  )}
                </div>

                {(hasSev || hasFailSev) && (
                  <div className="feature-severity-row">
                    <span className="feature-severity-label">
                      {hasSev ? 'Open defects' : 'Fail severity'}
                    </span>
                    <div className="feature-severity-chips">
                      {SEVERITY_ORDER.map(key => {
                        const n = hasSev ? sev[key] || 0 : failSev[key] || 0;
                        if (!n) return null;
                        return (
                          <span
                            key={key}
                            className={`feature-sev-chip severity-${key}`}
                            title={`${key}: ${n}`}
                          >
                            {SEVERITY_LABELS[key]} {n}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                )}

                {(m.details || []).slice(0, 3).map((d, i) => (
                  <div key={i} className="detail-row" style={{ marginTop: i === 0 ? 6 : 2 }}>
                    <span
                      style={{
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        fontWeight: 400,
                        color: 'var(--body-text)',
                      }}
                    >
                      {d.name}
                    </span>
                    <span style={{ color: '#C5221F', fontWeight: 700 }}>{d.count || 1}</span>
                  </div>
                ))}

                {m.meta?.pic && (
                  <div className="module-meta-display">PIC: {m.meta.pic}</div>
                )}
                {m.meta?.mitigation_plan && (
                  <div className="module-meta-display mitigation">
                    Mitigation: {m.meta.mitigation_plan}
                  </div>
                )}

                {editingModule === m.name && (
                  <div onClick={e => e.stopPropagation()}>
                    <ModuleMetaEditor
                      module={m}
                      onSave={handleMetaSave}
                      onClose={() => setEditingModule(null)}
                    />
                  </div>
                )}

                <div
                  style={{ display: 'flex', gap: 8, marginTop: 8, justifyContent: 'flex-end' }}
                  onClick={e => e.stopPropagation()}
                >
                  {showArchived ? (
                    <button
                      type="button"
                      className="archive"
                      onClick={() => handleArchive(m.name, false)}
                    >
                      Restore
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="archive"
                      onClick={() => handleArchive(m.name, true)}
                    >
                      Archive
                    </button>
                  )}
                  <button
                    type="button"
                    className="archive"
                    style={{ color: '#C5221F' }}
                    onClick={() => handleDelete(m.name)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {selectedModule && (
        <ModuleTestsModal
          moduleName={selectedModule}
          onClose={() => setSelectedModule(null)}
        />
      )}
    </>
  );
}

export default FeaturesPage;