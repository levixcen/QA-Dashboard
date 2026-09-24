import { useState, useEffect } from 'react';
import ModuleTestsModal from '../components/ModuleTestsModal';
import FeatureEntryEditor from '../components/FeatureEntryEditor';
import { authFetch } from '../utils/auth';
import { usePeriod } from '../context/PeriodContext';

function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function ModulesPage({ modules, onFeaturesChanged }) {
  const { period } = usePeriod();
  const [filter, setFilter] = useState('All');
  const [openModule, setOpenModule] = useState(null);
  const [editingModule, setEditingModule] = useState(null);
  const [viewArchived, setViewArchived] = useState(false);
  const [archivedModules, setArchivedModules] = useState([]);
  const [archivedLoading, setArchivedLoading] = useState(false);

  const [featureName, setFeatureName] = useState('');
  const [formError, setFormError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!viewArchived) return;
    let cancelled = false;
    setArchivedLoading(true);
    const query = period ? `?archived=true&month=${period}` : '?archived=true';
    authFetch(`/api/reports/summary${query}`)
      .then(res => (res.ok ? res.json() : Promise.reject()))
      .then(data => {
        if (cancelled) return;
        setArchivedModules(data.modules || []);
        setArchivedLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setArchivedModules([]);
        setArchivedLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [viewArchived, period]);

  async function handleAddClick() {
    const trimmed = featureName.trim();
    if (!trimmed) {
      setFormError('Enter a feature name first.');
      return;
    }
    setSubmitting(true);
    try {
      const res = await authFetch('/api/features', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: trimmed }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to add feature');
      }
      setFeatureName('');
      setFormError(null);
      onFeaturesChanged();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleArchive(name, e) {
    e.stopPropagation();
    const res = await authFetch(`/api/features/${encodeURIComponent(name)}/archive`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ archived: true }),
    });
    if (res.ok) onFeaturesChanged();
  }

  async function handleRestore(name, e) {
    e.stopPropagation();
    const res = await authFetch(`/api/features/${encodeURIComponent(name)}/archive`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ archived: false }),
    });
    if (res.ok) {
      setArchivedModules(prev => prev.filter(m => m.name !== name));
      onFeaturesChanged();
    }
  }

  async function handleDelete(name, e) {
    e.stopPropagation();
    if (!window.confirm(`Delete "${name}" permanently? This removes it and any manual entries and evidence, but not Mario's automated test history for it.`)) {
      return;
    }
    const res = await authFetch(`/api/features/${encodeURIComponent(name)}`, { method: 'DELETE' });
    if (res.ok) {
      setArchivedModules(prev => prev.filter(m => m.name !== name));
      onFeaturesChanged();
    }
  }

  const activeFiltered = modules.filter(m => {
    if (filter === 'All') return true;
    if (filter === 'Healthy') return m.color === 'green';
    if (filter === 'Needs Attention') return m.color === 'red' || m.color === 'orange';
    if (filter === 'Not Started') return m.color === 'gray';
    return true;
  });

  const filtered = viewArchived ? archivedModules : activeFiltered;

  return (
    <>
      <div className="page-header">
        <div>
          <div className="brand">SEDAYU ONE</div>
          <h1>Features</h1>
        </div>
        <button
          className={`btn ${viewArchived ? 'btn-dark' : 'btn-primary'}`}
          onClick={() => setViewArchived(v => !v)}
        >
          {viewArchived ? '← Back to Features' : 'Archived'}
        </button>
      </div>

      {!viewArchived && (
        <div className="controls">
          <div className="control-group">
            <label>Add feature</label>
            <input
              placeholder="e.g. Marketplace"
              value={featureName}
              onChange={e => {
                setFeatureName(e.target.value);
                if (formError) setFormError(null);
              }}
              onKeyDown={e => {
                if (e.key === 'Enter') handleAddClick();
              }}
            />
          </div>
          <button className="btn btn-dark" onClick={handleAddClick} disabled={submitting}>
            + Add
          </button>
          {formError && <div className="module-meta-error">{formError}</div>}
        </div>
      )}

      {!viewArchived && (
        <div className="filters">
          {['All', 'Healthy', 'Needs Attention', 'Not Started'].map(f => (
            <button
              key={f}
              className={`filter-btn ${filter === f ? 'active' : ''}`}
              onClick={() => setFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
      )}

      {viewArchived && archivedLoading && (
        <div className="placeholder"><p>Loading archived features.</p></div>
      )}
      {viewArchived && !archivedLoading && filtered.length === 0 && (
        <div className="placeholder"><p>No archived features{period ? ` for ${period}` : ''}.</p></div>
      )}

      <div className="modules">
        {filtered.map(m => (
          <div
            key={m.id}
            className="module-card"
            onClick={() => setOpenModule(m.name)}
            style={{ cursor: 'pointer' }}
          >
            <div className="module-header">
              <div className="module-name">
                <span className={`icon ${m.color}`}>
                  {m.color === 'green' ? '✓' : m.color === 'orange' ? '!' : m.color === 'red' ? '×' : '○'}
                </span>
                {m.name}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div className="module-pct">{m.pct}%</div>
                {!viewArchived && (
                  <button
                    type="button"
                    className="module-meta-edit-trigger"
                    onClick={e => {
                      e.stopPropagation();
                      setEditingModule(editingModule === m.name ? null : m.name);
                    }}
                    title="Add evidence, description, or a pass/fail entry"
                  >
                    &#9998;
                  </button>
                )}
              </div>
            </div>

            <div className="progress">
              <div className={`progress-bar ${m.color}`} style={{ width: `${m.pct}%` }} />
            </div>

            <div className="status-row">
              <span>{m.status}</span>
              {m.failing > 0 && <span className="failing">{m.failing} failing</span>}
            </div>

            {m.details && (
              <div className="details">
                {m.details.map((d, i) => (
                  <div key={i} className="detail-row">
                    <span>{d.name}</span>
                    <span>{d.count}</span>
                  </div>
                ))}
              </div>
            )}

            {editingModule === m.name && (
              <FeatureEntryEditor
                moduleName={m.name}
                period={period || currentMonth()}
                onSaved={onFeaturesChanged}
                onClose={() => setEditingModule(null)}
              />
            )}

            {viewArchived ? (
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="archive" onClick={e => handleRestore(m.name, e)}>
                  Restore
                </button>
                <button className="archive" onClick={e => handleDelete(m.name, e)}>
                  Delete permanently
                </button>
              </div>
            ) : (
              <button className="archive" onClick={e => handleArchive(m.name, e)}>
                Archive
              </button>
            )}
          </div>
        ))}
      </div>

      {openModule && (
        <ModuleTestsModal
          moduleName={openModule}
          onClose={() => setOpenModule(null)}
        />
      )}
    </>
  );
}

export default ModulesPage;