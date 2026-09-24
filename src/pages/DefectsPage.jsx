import { useState, useEffect, useMemo } from 'react';
import { authFetch } from '../utils/auth';

const SEVERITIES = ['critical', 'high', 'medium', 'low'];
const STATUSES = ['open', 'in_progress', 'retest', 'reopened', 'closed'];

const STATUS_LABEL = {
  open: 'Open',
  in_progress: 'In Progress',
  retest: 'Retest',
  reopened: 'Re-Opened',
  closed: 'Closed',
};

const SEVERITY_LABEL = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

function daysBetween(isoDate) {
  if (!isoDate) return null;
  const start = new Date(isoDate + 'T00:00:00');
  if (Number.isNaN(start.getTime())) return null;
  const now = new Date();
  const diff = Math.floor((now - start) / (1000 * 60 * 60 * 24));
  return diff < 0 ? 0 : diff;
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

const emptyForm = {
  description: '',
  severity: 'high',
  status: 'open',
  owner: '',
  raised_date: todayISO(),
  eta: '',
  impacted_tc_count: 0,
  module: '',
};

function DefectsPage({ username }) {
  const [defects, setDefects] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');
  const [filterSeverity, setFilterSeverity] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');

  async function load() {
    setError('');
    try {
      const res = await authFetch('/api/defects');
      if (!res.ok) throw new Error('Failed to load defects');
      const data = await res.json();
      setDefects(Array.isArray(data) ? data : []);
    } catch (e) {
      setError(e.message || 'Failed to load defects');
    } finally {
      setLoaded(true);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    return defects.filter(d => {
      if (filterSeverity !== 'all' && d.severity !== filterSeverity) return false;
      if (filterStatus !== 'all' && d.status !== filterStatus) return false;
      return true;
    });
  }, [defects, filterSeverity, filterStatus]);

  const openCount = defects.filter(d => d.status !== 'closed').length;
  const bySeverity = SEVERITIES.reduce((acc, s) => {
    acc[s] = defects.filter(d => d.status !== 'closed' && d.severity === s).length;
    return acc;
  }, {});

  function openCreate() {
    setEditingId(null);
    setForm({ ...emptyForm, raised_date: todayISO() });
    setFormError('');
    setShowForm(true);
  }

  function openEdit(d) {
    setEditingId(d.id);
    setForm({
      description: d.description || '',
      severity: d.severity || 'high',
      status: d.status || 'open',
      owner: d.owner || '',
      raised_date: d.raised_date || todayISO(),
      eta: d.eta || '',
      impacted_tc_count: d.impacted_tc_count ?? 0,
      module: d.module || '',
    });
    setFormError('');
    setShowForm(true);
  }

  function closeForm() {
    setShowForm(false);
    setEditingId(null);
    setFormError('');
  }

  async function handleSave() {
    if (!form.description.trim()) {
      setFormError('Description is required');
      return;
    }
    if (!SEVERITIES.includes(form.severity)) {
      setFormError('Invalid severity');
      return;
    }
    if (!STATUSES.includes(form.status)) {
      setFormError('Invalid status');
      return;
    }
    if (form.status === 'closed' && editingId) {
      const existing = defects.find(d => d.id === editingId);
      if (existing && existing.status !== 'retest' && existing.status !== 'closed') {
        setFormError('Status can only be Closed after Retest is completed and validated.');
        return;
      }
    }

    setSaving(true);
    setFormError('');
    try {
      const payload = {
        description: form.description.trim(),
        severity: form.severity,
        status: form.status,
        owner: form.owner.trim() || null,
        raised_date: form.raised_date || null,
        eta: form.eta || null,
        impacted_tc_count: Number(form.impacted_tc_count) || 0,
        module: form.module.trim() || null,
      };

      const url = editingId ? `/api/defects/${editingId}` : '/api/defects';
      const method = editingId ? 'PATCH' : 'POST';
      const res = await authFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Save failed');
      }
      closeForm();
      await load();
    } catch (e) {
      setFormError(e.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id) {
    if (!window.confirm('Delete this defect permanently?')) return;
    try {
      const res = await authFetch(`/api/defects/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Delete failed');
      await load();
    } catch (e) {
      setError(e.message || 'Delete failed');
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <div className="brand welcome-brand">Welcome, {username || 'User'}</div>
          <h1>Defects</h1>
        </div>
        <button type="button" className="module-meta-save" onClick={openCreate}>
          + Add Defect
        </button>
      </div>

      <div className="defects-summary-row">
        <div className="severity-card">
          <h3>Open Defects</h3>
          <div className="insight-big">{openCount}</div>
          <p className="insight-note">of {defects.length} total</p>
        </div>
        <div className="severity-card">
          <h3>By Severity (Open)</h3>
          <div className="severity-badges">
            {SEVERITIES.map(s => (
              <div key={s} className={`severity-badge severity-${s}`}>
                <span className="severity-count">{bySeverity[s]}</span>
                <span className="severity-label">{SEVERITY_LABEL[s]}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="defects-filters">
        <label>
          Severity
          <select value={filterSeverity} onChange={e => setFilterSeverity(e.target.value)}>
            <option value="all">All</option>
            {SEVERITIES.map(s => (
              <option key={s} value={s}>{SEVERITY_LABEL[s]}</option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}>
            <option value="all">All</option>
            {STATUSES.map(s => (
              <option key={s} value={s}>{STATUS_LABEL[s]}</option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="modal-status" style={{ color: '#C5221F' }}>{error}</p>}

      {!loaded && <p className="modal-status">Loading…</p>}

      {loaded && filtered.length === 0 && (
        <div className="placeholder">
          <p>No defects match the current filters.</p>
        </div>
      )}

      {filtered.length > 0 && (
        <div className="defects-table-wrap">
          <table className="defects-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Description</th>
                <th>Module</th>
                <th># TCs</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Owner</th>
                <th>Raised</th>
                <th>ETA</th>
                <th>Aging</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(d => {
                const aging = d.status === 'closed' ? null : daysBetween(d.raised_date);
                return (
                  <tr key={d.id} className={d.status === 'closed' ? 'defect-row-closed' : ''}>
                    <td className="defect-id">{d.defect_code || `DEF-${d.id}`}</td>
                    <td className="defect-desc">{d.description}</td>
                    <td>{d.module || '—'}</td>
                    <td>{d.impacted_tc_count ?? 0}</td>
                    <td>
                      <span className={`defect-sev severity-${d.severity}`}>
                        {SEVERITY_LABEL[d.severity] || d.severity}
                      </span>
                    </td>
                    <td>
                      <span className={`defect-status status-${d.status}`}>
                        {STATUS_LABEL[d.status] || d.status}
                      </span>
                    </td>
                    <td>{d.owner || '—'}</td>
                    <td>{d.raised_date || '—'}</td>
                    <td>{d.eta || '—'}</td>
                    <td>{aging === null ? '—' : `${aging}d`}</td>
                    <td className="defect-actions">
                      <button type="button" className="archive" onClick={() => openEdit(d)}>Edit</button>
                      <button type="button" className="project-delete" onClick={() => handleDelete(d.id)}>Delete</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="insight-note" style={{ marginTop: 16 }}>
        Defect status can only be set to Closed after Retest is completed and the result is validated by the business user.
      </p>

      {showForm && (
        <div className="modal-overlay" onClick={closeForm}>
          <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 520 }}>
            <div className="modal-header">
              <h2>{editingId ? 'Edit Defect' : 'Add Defect'}</h2>
              <button type="button" className="modal-close" onClick={closeForm}>×</button>
            </div>
            <div className="modal-body">
              <div className="module-meta-form" style={{ marginTop: 0, background: 'none', border: 'none', padding: 0 }}>
                <label className="module-meta-field">
                  <span>Description</span>
                  <textarea
                    value={form.description}
                    onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                    rows={3}
                    placeholder="Error description"
                  />
                </label>
                <label className="module-meta-field">
                  <span>Module (optional)</span>
                  <input
                    value={form.module}
                    onChange={e => setForm(f => ({ ...f, module: e.target.value }))}
                    placeholder="e.g. User Authentication"
                  />
                </label>
                <div style={{ display: 'flex', gap: 12 }}>
                  <label className="module-meta-field" style={{ flex: 1 }}>
                    <span>Severity</span>
                    <select
                      value={form.severity}
                      onChange={e => setForm(f => ({ ...f, severity: e.target.value }))}
                    >
                      {SEVERITIES.map(s => (
                        <option key={s} value={s}>{SEVERITY_LABEL[s]}</option>
                      ))}
                    </select>
                  </label>
                  <label className="module-meta-field" style={{ flex: 1 }}>
                    <span>Status</span>
                    <select
                      value={form.status}
                      onChange={e => setForm(f => ({ ...f, status: e.target.value }))}
                    >
                      {STATUSES.map(s => (
                        <option key={s} value={s}>{STATUS_LABEL[s]}</option>
                      ))}
                    </select>
                  </label>
                </div>
                <label className="module-meta-field">
                  <span>Current Owner</span>
                  <input
                    value={form.owner}
                    onChange={e => setForm(f => ({ ...f, owner: e.target.value }))}
                    placeholder="Assignee"
                  />
                </label>
                <div style={{ display: 'flex', gap: 12 }}>
                  <label className="module-meta-field" style={{ flex: 1 }}>
                    <span>Raised Date</span>
                    <input
                      type="date"
                      value={form.raised_date}
                      onChange={e => setForm(f => ({ ...f, raised_date: e.target.value }))}
                    />
                  </label>
                  <label className="module-meta-field" style={{ flex: 1 }}>
                    <span>ETA</span>
                    <input
                      type="date"
                      value={form.eta}
                      onChange={e => setForm(f => ({ ...f, eta: e.target.value }))}
                    />
                  </label>
                </div>
                <label className="module-meta-field">
                  <span># Impacted TCs</span>
                  <input
                    type="number"
                    min={0}
                    value={form.impacted_tc_count}
                    onChange={e => setForm(f => ({ ...f, impacted_tc_count: e.target.value }))}
                  />
                </label>
                {formError && <div className="module-meta-error">{formError}</div>}
                <div className="module-meta-actions">
                  <button
                    type="button"
                    className="module-meta-save"
                    onClick={handleSave}
                    disabled={saving}
                  >
                    {saving ? 'Saving…' : 'Save'}
                  </button>
                  <button
                    type="button"
                    className="module-meta-cancel"
                    onClick={closeForm}
                    disabled={saving}
                  >
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