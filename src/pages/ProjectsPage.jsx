import { useState, useEffect } from 'react';
import { authFetch } from '../utils/auth';
import { formatDate } from "../utils/formatDate";
import { usePeriod } from '../context/PeriodContext';
import ProjectTestCaseEditor from '../components/ProjectTestCaseEditor';

const emptyNewProject = {
  name: '',
  module: '',
  owner: '',
  target_date: '',
  tc_total: '',
  note: '',
};

function ProjectsPage() {
  const { period } = usePeriod();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [newProject, setNewProject] = useState(emptyNewProject);
  const [addError, setAddError] = useState(null);
  const [adding, setAdding] = useState(false);

  const [checklistDrafts, setChecklistDrafts] = useState({});
  const [editingProjectId, setEditingProjectId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');

    authFetch(`/api/projects${period ? `?month=${period}` : ''}`)
      .then(res => {
        if (!res.ok) throw new Error('bad response');
        return res.json();
      })
      .then(data => {
        if (cancelled) return;
        setProjects(data);
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setError('Could not load projects.');
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [period]);

  async function handleAddProject() {
    const name = newProject.name.trim();
    if (!name) {
      setAddError('Project name is required.');
      return;
    }

    setAdding(true);
    setAddError(null);
    try {
      const res = await authFetch('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          module: newProject.module.trim() || null,
          owner: newProject.owner.trim() || null,
          status: 'Not Started',
          color: 'gray',
          tc_done: 0,
          tc_failed: 0,
          tc_total: Number(newProject.tc_total) || 0,
          target_date: newProject.target_date || null,
          note: newProject.note.trim() || null,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to add project');
      }

      const created = await res.json();
      const inView = !period || (created.target_date || '').startsWith(period);
      if (inView) {
        setProjects(prev => [...prev, created]);
      } else {
        setAddError('Project added, but its target date is outside the selected month. Show all time to see it.');
      }
      setNewProject(emptyNewProject);
    } catch (err) {
      setAddError(err.message);
    } finally {
      setAdding(false);
    }
  }

  async function handleUpdateTestCases(projectId, payload) {
    const res = await authFetch(`/api/projects/${projectId}/testcases`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to save test case counts');
    }

    const updated = await res.json();
    setProjects(prev => prev.map(p => (p.id === projectId ? updated : p)));
  }

  async function handleDeleteProject(project) {
    const confirmed = window.confirm(`Delete "${project.name}"? This cannot be undone.`);
    if (!confirmed) return;

    const prevProjects = projects;
    setProjects(prev => prev.filter(p => p.id !== project.id));

    try {
      const res = await authFetch(`/api/projects/${project.id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed to delete project');
    } catch (err) {
      setProjects(prevProjects);
    }
  }

  async function handleAddChecklistItem(projectId) {
    const text = (checklistDrafts[projectId] || '').trim();
    if (!text) return;

    try {
      const res = await authFetch(`/api/projects/${projectId}/checklist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) throw new Error('Failed to add checklist item');

      const { project_pct, ...item } = await res.json();
      setProjects(prev =>
        prev.map(p =>
          p.id === projectId
            ? { ...p, pct: project_pct, checklist: [...(p.checklist || []), item] }
            : p
        )
      );
      setChecklistDrafts(prev => ({ ...prev, [projectId]: '' }));
    } catch (err) {
      setChecklistDrafts(prev => ({ ...prev, [projectId]: text }));
    }
  }

    async function handleUploadChecklistEvidence(projectId, itemId, file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await authFetch(`/api/projects/checklist/${itemId}/evidence`, {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) throw new Error('Failed to upload evidence');

      const updated = await res.json();
      setProjects(prev =>
        prev.map(p =>
          p.id === projectId
            ? { ...p, checklist: p.checklist.map(c => (c.id === itemId ? updated : c)) }
            : p
        )
      );
    } catch (err) {
      window.alert('Could not upload evidence image.');
    }
  }

  async function handleViewChecklistEvidence(evidencePath) {
    try {
      const res = await authFetch(`/api/evidence/${evidencePath}`);
      if (!res.ok) throw new Error('Failed to load evidence');

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
    } catch (err) {
      window.alert('Could not load evidence image.');
    }
  }

  async function handleToggleChecklistItem(projectId, item) {
    const nextDone = !item.done;

    setProjects(prev =>
      prev.map(p =>
        p.id === projectId
          ? {
              ...p,
              checklist: p.checklist.map(c =>
                c.id === item.id ? { ...c, done: nextDone } : c
              ),
            }
          : p
      )
    );

    try {
      const res = await authFetch(`/api/projects/checklist/${item.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ done: nextDone }),
      });
      if (!res.ok) throw new Error('Failed to update item');

      const { project_pct } = await res.json();
      setProjects(prev =>
        prev.map(p => (p.id === projectId ? { ...p, pct: project_pct } : p))
      );
    } catch (err) {
      setProjects(prev =>
        prev.map(p =>
          p.id === projectId
            ? {
                ...p,
                checklist: p.checklist.map(c =>
                  c.id === item.id ? { ...c, done: item.done } : c
                ),
              }
            : p
        )
      );
    }
  }

  async function handleDeleteChecklistItem(projectId, itemId) {
    const prevProjects = projects;
    setProjects(prev =>
      prev.map(p =>
        p.id === projectId
          ? { ...p, checklist: p.checklist.filter(c => c.id !== itemId) }
          : p
      )
    );

    try {
      const res = await authFetch(`/api/projects/checklist/${itemId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed to delete item');

      const { project_pct } = await res.json();
      setProjects(prev =>
        prev.map(p => (p.id === projectId ? { ...p, pct: project_pct } : p))
      );
    } catch (err) {
      setProjects(prevProjects);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <div className="brand">SEDAYU ONE</div>
          <h1>Projects</h1>
        </div>
      </div>

      <div className="controls">
        <div className="control-group">
          <label>Project name</label>
          <input
            placeholder="e.g. Guest Access Revamp"
            value={newProject.name}
            onChange={e => setNewProject({ ...newProject, name: e.target.value })}
          />
        </div>
        <div className="control-group">
          <label>Feature</label>
          <input
            placeholder="e.g. Guest"
            value={newProject.module}
            onChange={e => setNewProject({ ...newProject, module: e.target.value })}
          />
        </div>
        <div className="control-group">
          <label>Owner</label>
          <input
            placeholder="e.g. Dara"
            value={newProject.owner}
            onChange={e => setNewProject({ ...newProject, owner: e.target.value })}
          />
        </div>
        <div className="control-group">
          <label>Target TCs</label>
          <input
            type="number"
            min="0"
            placeholder="e.g. 30"
            value={newProject.tc_total}
            onChange={e => setNewProject({ ...newProject, tc_total: e.target.value })}
          />
        </div>
        <div className="control-group">
          <label>Target date</label>
          <input
            type="date"
            value={newProject.target_date}
            onChange={e => setNewProject({ ...newProject, target_date: e.target.value })}
          />
        </div>
        <div className="control-group">
          <label>Note</label>
          <input
            placeholder="Optional note"
            value={newProject.note}
            onChange={e => setNewProject({ ...newProject, note: e.target.value })}
          />
        </div>
        <button className="btn btn-dark" onClick={handleAddProject} disabled={adding}>
          {adding ? 'Adding...' : '+ Add'}
        </button>
      </div>
      {addError && <div className="module-meta-error">{addError}</div>}

      {loading && <div className="placeholder"><p>Loading projects.</p></div>}
      {error && <div className="placeholder"><p>{error}</p></div>}

      {!loading && !error && projects.length === 0 && (
        <div className="placeholder">
          <p>{period ? 'No projects with a target date in this month.' : 'No projects yet.'}</p>
        </div>
      )}

      {!loading && !error && (
        <div className="modules">
          {projects.map(p => {
            const checklist = p.checklist || [];
            const doneCount = checklist.filter(c => c.done).length;
            const isEditingTc = editingProjectId === p.id;

            return (
              <div key={p.id} className="module-card">
                <div className="module-header">
                  <div className="module-name">
                    <span className={`icon ${p.color}`}>
                      {p.color === 'green' ? '✓' : p.color === 'orange' ? '!' : p.color === 'gray' ? '○' : '×'}
                    </span>
                    {p.name}
                  </div>
                  <div className="module-pct-wrap">
                    <span className="module-pct">{p.pct}%</span>
                    <button
                      type="button"
                      className="module-meta-edit-trigger"
                      onClick={() => setEditingProjectId(isEditingTc ? null : p.id)}
                      title="Edit test case counts"
                    >
                      &#9998;
                    </button>
                  </div>
                </div>

                {p.target_date && (
                  <div className="project-target-date">{formatDate(p.target_date)}</div>
                )}

                <div className="progress">
                  <div className={`progress-bar ${p.color}`} style={{ width: `${p.pct}%` }} />
                </div>

                <div className="status-row">
                  <span>{p.status}</span>
                  <span>{p.owner}</span>
                </div>

                <div className="details">
                  <div className="detail-row">
                    <span>Feature</span>
                    <span style={{ color: '#5a7a9a', fontWeight: 400 }}>{p.module}</span>
                  </div>
                  <div className="detail-row">
                    <span>Passed</span>
                    <span style={{ color: '#5a7a9a', fontWeight: 400 }}>{p.tc_done}</span>
                  </div>
                  <div className="detail-row">
                    <span>Failed</span>
                    <span style={{ color: '#5a7a9a', fontWeight: 400 }}>{p.tc_failed}</span>
                  </div>
                  <div className="detail-row">
                    <span>Target</span>
                    <span style={{ color: '#5a7a9a', fontWeight: 400 }}>{p.tc_total}</span>
                  </div>
                </div>

                {isEditingTc && (
                  <ProjectTestCaseEditor
                    project={p}
                    onSave={handleUpdateTestCases}
                    onClose={() => setEditingProjectId(null)}
                  />
                )}

                <div className="status-row" style={{ marginTop: -4 }}>
                  <span>{p.note}</span>
                </div>

                <div className="project-checklist">
                  <div className="project-checklist-header">
                    <span>Checklist</span>
                    {checklist.length > 0 && (
                      <span className="project-checklist-count">{doneCount}/{checklist.length}</span>
                    )}
                  </div>

                  {checklist.map(item => (
                    <div key={item.id} className="project-checklist-item">
                      <label className="project-checklist-label">
                        <input
                          type="checkbox"
                          checked={!!item.done}
                          onChange={() => handleToggleChecklistItem(p.id, item)}
                        />
                        <span className={item.done ? 'project-checklist-text done' : 'project-checklist-text'}>
                          {item.text}
                        </span>
                      </label>
                      <button
                        type="button"
                        className="project-checklist-remove"
                        onClick={() => handleDeleteChecklistItem(p.id, item.id)}
                        title="Remove item"
                      >
                        &times;
                      </button>
                    </div>
                  ))}

                  <div className="project-checklist-add">
                    <input
                      type="text"
                      placeholder="Add checklist item"
                      value={checklistDrafts[p.id] || ''}
                      onChange={e =>
                        setChecklistDrafts(prev => ({ ...prev, [p.id]: e.target.value }))
                      }
                      onKeyDown={e => {
                        if (e.key === 'Enter') handleAddChecklistItem(p.id);
                      }}
                    />
                    <button
                      type="button"
                      className="project-checklist-add-btn"
                      onClick={() => handleAddChecklistItem(p.id)}
                    >
                      +
                    </button>
                  </div>
                </div>

                <button
                  className="project-delete"
                  onClick={() => handleDeleteProject(p)}
                >
                  Delete project
                </button>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}

export default ProjectsPage;