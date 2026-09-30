import { useState, useEffect } from 'react';
import { authFetch } from '../utils/auth';
import { formatDate } from '../utils/formatDate';
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

function ProjectsPage({ username }) {
  const { period } = usePeriod();
  const [projects, setProjects] = useState([]);
  const [archivedProjects, setArchivedProjects] = useState([]);
  const [showArchived, setShowArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [newProject, setNewProject] = useState(emptyNewProject);
  const [addError, setAddError] = useState(null);
  const [adding, setAdding] = useState(false);

  // Which project is open in the detail overlay (checklist + edit)
  const [openProjectId, setOpenProjectId] = useState(null);
  // Inside the overlay: editing test-case counts
  const [editingTc, setEditingTc] = useState(false);
  // Draft for the "add checklist item" row inside the overlay
  const [checklistDraft, setChecklistDraft] = useState({ text: '', assignees: '' });
  // Inline edit of a checklist item's assignees: itemId or null
  const [editingAssigneesId, setEditingAssigneesId] = useState(null);
  const [assigneesDraft, setAssigneesDraft] = useState('');
  // Project-level assignees edit inside overlay
  const [editingOwner, setEditingOwner] = useState(false);
  const [ownerDraft, setOwnerDraft] = useState('');

  const openProject =
    [...projects, ...archivedProjects].find(p => p.id === openProjectId) || null;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');

    const params = new URLSearchParams();
    if (period) params.set('month', period);
    if (showArchived) params.set('archived', 'true');

    authFetch(`/api/projects?${params.toString()}`)
      .then(res => {
        if (!res.ok) throw new Error('bad response');
        return res.json();
      })
      .then(data => {
        if (cancelled) return;
        if (showArchived) {
          setArchivedProjects(data);
        } else {
          setProjects(data);
        }
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
  }, [period, showArchived]);

  function closeOverlay() {
    setOpenProjectId(null);
    setEditingTc(false);
    setChecklistDraft({ text: '', assignees: '' });
    setEditingAssigneesId(null);
    setAssigneesDraft('');
    setEditingOwner(false);
    setOwnerDraft('');
  }

  function openOverlay(projectId) {
    setOpenProjectId(projectId);
    setEditingTc(false);
    setChecklistDraft({ text: '', assignees: '' });
    setEditingAssigneesId(null);
    setAssigneesDraft('');
    setEditingOwner(false);
    setOwnerDraft('');
  }

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
          owner: null,
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
        setAddError(
          'Project added, but its target date is outside the selected month. Show all time to see it.'
        );
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

  async function handleSaveOwner(projectId) {
    try {
      const res = await authFetch(`/api/projects/${projectId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ owner: ownerDraft.trim() || null }),
      });
      if (!res.ok) throw new Error('Failed to update assignees');
      const updated = await res.json();
      setProjects(prev => prev.map(p => (p.id === projectId ? updated : p)));
      setEditingOwner(false);
      setOwnerDraft('');
    } catch (err) {
      window.alert('Could not update project assignees.');
    }
  }

  async function handleArchive(project, archived) {
    try {
      const res = await authFetch(`/api/projects/${project.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ archived }),
      });
      if (!res.ok) throw new Error('Failed to update project');
      if (archived) {
        setProjects(prev => prev.filter(p => p.id !== project.id));
      } else {
        setArchivedProjects(prev => prev.filter(p => p.id !== project.id));
      }
      if (openProjectId === project.id) closeOverlay();
    } catch (err) {
      window.alert('Could not update project.');
    }
  }

  async function handleDeleteProject(project) {
    const confirmed = window.confirm(`Delete "${project.name}"? This cannot be undone.`);
    if (!confirmed) return;

    const prevProjects = projects;
    const prevArchived = archivedProjects;
    setProjects(prev => prev.filter(p => p.id !== project.id));
    setArchivedProjects(prev => prev.filter(p => p.id !== project.id));
    if (openProjectId === project.id) closeOverlay();

    try {
      const res = await authFetch(`/api/projects/${project.id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Failed to delete project');
    } catch (err) {
      setProjects(prevProjects);
      setArchivedProjects(prevArchived);
    }
  }

  async function handleAddChecklistItem(projectId) {
    const text = (checklistDraft.text || '').trim();
    if (!text) return;
    const assignees = (checklistDraft.assignees || '').trim() || null;

    try {
      const res = await authFetch(`/api/projects/${projectId}/checklist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, assignees }),
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
      setChecklistDraft({ text: '', assignees: '' });
    } catch (err) {
      // leave draft so the user can retry
    }
  }

  async function handleSaveChecklistAssignees(projectId, itemId) {
    const assignees = assigneesDraft.trim() || null;
    try {
      const res = await authFetch(`/api/projects/checklist/${itemId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ assignees }),
      });
      if (!res.ok) throw new Error('Failed to update assignees');
      const updated = await res.json();
      setProjects(prev =>
        prev.map(p =>
          p.id === projectId
            ? {
                ...p,
                checklist: p.checklist.map(c =>
                  c.id === itemId ? { ...c, assignees: updated.assignees } : c
                ),
              }
            : p
        )
      );
      setEditingAssigneesId(null);
      setAssigneesDraft('');
    } catch (err) {
      window.alert('Could not update assignees.');
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
      if (project_pct != null) {
        setProjects(prev =>
          prev.map(p => (p.id === projectId ? { ...p, pct: project_pct } : p))
        );
      }
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
      if (project_pct != null) {
        setProjects(prev =>
          prev.map(p => (p.id === projectId ? { ...p, pct: project_pct } : p))
        );
      }
    } catch (err) {
      setProjects(prevProjects);
    }
  }

  return (
    <>
      <div className="page-header">
        <div>
          <div className="brand welcome-brand">Welcome, {username || 'User'}</div>
          <h1>Projects</h1>
        </div>
        <button
          type="button"
          className={`btn ${showArchived ? 'btn-primary' : 'btn-dark'}`}
          onClick={() => setShowArchived(v => !v)}
        >
          {showArchived ? 'Show active projects' : 'Archived'}
        </button>
      </div>

      {!showArchived && (
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
      )}
      {addError && <div className="module-meta-error">{addError}</div>}

      {loading && (
        <div className="placeholder">
          <p>Loading projects.</p>
        </div>
      )}
      {error && (
        <div className="placeholder">
          <p>{error}</p>
        </div>
      )}

      {!loading && !error && showArchived && archivedProjects.length === 0 && (
        <div className="placeholder">
          <p>No archived projects.</p>
        </div>
      )}

      {!loading && !error && !showArchived && projects.length === 0 && (
        <div className="placeholder">
          <p>
            {period
              ? 'No projects with a target date in this month.'
              : 'No projects yet.'}
          </p>
        </div>
      )}

      {!loading && !error && !showArchived && (
        <div className="modules">
          {projects.map(p => {
            const checklist = p.checklist || [];
            const doneCount = checklist.filter(c => c.done).length;

            return (
              <div key={p.id} className="module-card project-card-compact">
                <div className="module-header">
                  <div className="module-name">
                    <span className={`icon ${p.color}`}>
                      {p.color === 'green'
                        ? '✓'
                        : p.color === 'orange'
                          ? '!'
                          : p.color === 'gray'
                            ? '○'
                            : '×'}
                    </span>
                    {p.name}
                  </div>
                  <span className="module-pct">{p.pct}%</span>
                </div>

                {p.target_date && (
                  <div className="project-target-date">{formatDate(p.target_date)}</div>
                )}

                <div className="progress">
                  <div
                    className={`progress-bar ${p.color}`}
                    style={{ width: `${p.pct}%` }}
                  />
                </div>

                <div className="status-row">
                  <span>{p.status}</span>
                  <span title="Project assignees">{p.owner || 'Unassigned'}</span>
                </div>

                <div className="details">
                  <div className="detail-row">
                    <span>Feature</span>
                    <span style={{ color: '#5a7a9a', fontWeight: 400 }}>
                      {p.module || '—'}
                    </span>
                  </div>
                  <div className="detail-row">
                    <span>TCs</span>
                    <span style={{ color: '#5a7a9a', fontWeight: 400 }}>
                      {p.tc_done}/{p.tc_total}
                      {p.tc_failed ? ` · ${p.tc_failed} failed` : ''}
                    </span>
                  </div>
                  <div className="detail-row">
                    <span>Checklist</span>
                    <span style={{ color: '#5a7a9a', fontWeight: 400 }}>
                      {checklist.length === 0
                        ? 'None'
                        : `${doneCount}/${checklist.length} done`}
                    </span>
                  </div>
                </div>

                {p.note && (
                  <div className="status-row" style={{ marginTop: -4 }}>
                    <span
                      style={{
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {p.note}
                    </span>
                  </div>
                )}

                <button
                  type="button"
                  className="project-open-btn"
                  onClick={() => openOverlay(p.id)}
                >
                  Open checklist &amp; edit
                </button>
              </div>
            );
          })}
        </div>
      )}

      {!loading && !error && showArchived && archivedProjects.length > 0 && (
        <div className="modules">
          {archivedProjects.map(p => (
            <div key={p.id} className="module-card">
              <div className="module-header">
                <div className="module-name">{p.name}</div>
              </div>
              <div className="status-row">
                <span>{p.status}</span>
                <span>{p.owner || 'Unassigned'}</span>
              </div>
              <div className="details">
                <div className="detail-row">
                  <span>Feature</span>
                  <span style={{ color: '#5a7a9a', fontWeight: 400 }}>{p.module || '—'}</span>
                </div>
                <div className="detail-row">
                  <span>Target date</span>
                  <span style={{ color: '#5a7a9a', fontWeight: 400 }}>
                    {p.target_date ? formatDate(p.target_date) : '—'}
                  </span>
                </div>
                <div className="detail-row">
                  <span>Checklist</span>
                  <span style={{ color: '#5a7a9a', fontWeight: 400 }}>
                    {(p.checklist || []).length === 0
                      ? 'None'
                      : `${(p.checklist || []).filter(c => c.done).length}/${(p.checklist || []).length} done`}
                  </span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                <button type="button" className="archive" onClick={() => handleArchive(p, false)}>
                  Restore
                </button>
                <button
                  type="button"
                  className="archive"
                  style={{ color: '#C5221F' }}
                  onClick={() => handleDeleteProject(p)}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Detail overlay — checklist, assignees, TC counts, delete */}
      {openProject && (
        <div
          className="modal-overlay"
          onClick={e => {
            if (e.target === e.currentTarget) closeOverlay();
          }}
        >
          <div className="modal-content project-detail-modal">
            <div className="modal-header">
              <h2>{openProject.name}</h2>
              <button type="button" className="modal-close" onClick={closeOverlay}>
                ×
              </button>
            </div>

            <div className="modal-body">
              <div className="project-detail-meta">
                <div className="detail-row">
                  <span>Status</span>
                  <span>{openProject.status}</span>
                </div>
                <div className="detail-row">
                  <span>Assignees</span>
                  {editingOwner ? (
                    <span className="project-checklist-assignees-edit">
                      <input
                        type="text"
                        autoFocus
                        placeholder="e.g. Dara, Mario"
                        value={ownerDraft}
                        onChange={e => setOwnerDraft(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter') handleSaveOwner(openProject.id);
                          if (e.key === 'Escape') {
                            setEditingOwner(false);
                            setOwnerDraft('');
                          }
                        }}
                      />
                      <button
                        type="button"
                        className="archive"
                        onClick={() => handleSaveOwner(openProject.id)}
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        className="archive"
                        onClick={() => {
                          setEditingOwner(false);
                          setOwnerDraft('');
                        }}
                      >
                        Cancel
                      </button>
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="project-checklist-assignees"
                      title="Click to edit assignees"
                      onClick={() => {
                        setEditingOwner(true);
                        setOwnerDraft(openProject.owner || '');
                      }}
                    >
                      {openProject.owner || 'Assign'}
                    </button>
                  )}
                </div>
                <div className="detail-row">
                  <span>Feature</span>
                  <span>{openProject.module || '—'}</span>
                </div>
                <div className="detail-row">
                  <span>Target date</span>
                  <span>
                    {openProject.target_date
                      ? formatDate(openProject.target_date)
                      : '—'}
                  </span>
                </div>
                <div className="detail-row">
                  <span>Progress</span>
                  <span>{openProject.pct}%</span>
                </div>
                <div className="detail-row">
                  <span>Test cases</span>
                  <span>
                    {openProject.tc_done} passed · {openProject.tc_failed} failed ·{' '}
                    {openProject.tc_total} target
                    <button
                      type="button"
                      className="module-meta-edit-trigger"
                      style={{ marginLeft: 6 }}
                      onClick={() => setEditingTc(e => !e)}
                      title="Edit test case counts"
                    >
                      &#9998;
                    </button>
                  </span>
                </div>
                {openProject.note && (
                  <div className="detail-row">
                    <span>Note</span>
                    <span>{openProject.note}</span>
                  </div>
                )}
              </div>

              {editingTc && (
                <ProjectTestCaseEditor
                  project={openProject}
                  onSave={handleUpdateTestCases}
                  onClose={() => setEditingTc(false)}
                />
              )}

              <div className="project-checklist project-checklist-in-modal">
                <div className="project-checklist-header">
                  <span>Checklist</span>
                  {(openProject.checklist || []).length > 0 && (
                    <span className="project-checklist-count">
                      {(openProject.checklist || []).filter(c => c.done).length}/
                      {(openProject.checklist || []).length}
                    </span>
                  )}
                </div>

                {(openProject.checklist || []).map(item => {
                  const isEditingThis = editingAssigneesId === item.id;
                  return (
                    <div key={item.id} className="project-checklist-item">
                      <label className="project-checklist-label">
                        <input
                          type="checkbox"
                          checked={!!item.done}
                          onChange={() =>
                            handleToggleChecklistItem(openProject.id, item)
                          }
                        />
                        <span
                          className={
                            item.done
                              ? 'project-checklist-text done'
                              : 'project-checklist-text'
                          }
                        >
                          {item.text}
                        </span>
                      </label>
                      {isEditingThis ? (
                        <span className="project-checklist-assignees-edit">
                          <input
                            type="text"
                            autoFocus
                            placeholder="e.g. Dara, Mario"
                            value={assigneesDraft}
                            onChange={e => setAssigneesDraft(e.target.value)}
                            onKeyDown={e => {
                              if (e.key === 'Enter') {
                                handleSaveChecklistAssignees(openProject.id, item.id);
                              }
                              if (e.key === 'Escape') {
                                setEditingAssigneesId(null);
                                setAssigneesDraft('');
                              }
                            }}
                          />
                          <button
                            type="button"
                            className="archive"
                            onClick={() =>
                              handleSaveChecklistAssignees(openProject.id, item.id)
                            }
                          >
                            Save
                          </button>
                          <button
                            type="button"
                            className="archive"
                            onClick={() => {
                              setEditingAssigneesId(null);
                              setAssigneesDraft('');
                            }}
                          >
                            Cancel
                          </button>
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="project-checklist-assignees"
                          title="Click to edit assignees"
                          onClick={() => {
                            setEditingAssigneesId(item.id);
                            setAssigneesDraft(item.assignees || '');
                          }}
                        >
                          {item.assignees || 'Assign'}
                        </button>
                      )}
                      <button
                        type="button"
                        className="project-checklist-remove"
                        onClick={() =>
                          handleDeleteChecklistItem(openProject.id, item.id)
                        }
                        title="Remove item"
                      >
                        &times;
                      </button>
                    </div>
                  );
                })}

                <div className="project-checklist-add project-checklist-add-stacked">
                  <input
                    type="text"
                    placeholder="New checklist item"
                    value={checklistDraft.text}
                    onChange={e =>
                      setChecklistDraft(d => ({ ...d, text: e.target.value }))
                    }
                    onKeyDown={e => {
                      if (e.key === 'Enter') handleAddChecklistItem(openProject.id);
                    }}
                  />
                  <div className="project-checklist-add-row">
                    <input
                      type="text"
                      placeholder="Assignees (optional)"
                      value={checklistDraft.assignees}
                      onChange={e =>
                        setChecklistDraft(d => ({ ...d, assignees: e.target.value }))
                      }
                      onKeyDown={e => {
                        if (e.key === 'Enter') handleAddChecklistItem(openProject.id);
                      }}
                      title="Comma-separated names"
                    />
                    <button
                      type="button"
                      className="project-checklist-add-btn"
                      onClick={() => handleAddChecklistItem(openProject.id)}
                    >
                      +
                    </button>
                  </div>
                </div>
              </div>

              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  type="button"
                  className="archive"
                  onClick={() => handleArchive(openProject, !openProject.archived)}
                >
                  {openProject.archived ? 'Restore project' : 'Archive project'}
                </button>
                <button
                  className="project-delete"
                  onClick={() => handleDeleteProject(openProject)}
                >
                  Delete project
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default ProjectsPage;