import { useState } from 'react';

// Inline editor for a project's test-case counts (target, passed, failed).
// pct itself is never edited directly here or anywhere else -- the backend
// derives it from these numbers (and checklist completion) via
// recompute_project_pct, so this form only ever sends the three raw counts
// and trusts whatever pct comes back in the response.
function ProjectTestCaseEditor({ project, onSave, onClose }) {
  const [tcTotal, setTcTotal] = useState(String(project.tc_total ?? 0));
  const [tcDone, setTcDone] = useState(String(project.tc_done ?? 0));
  const [tcFailed, setTcFailed] = useState(String(project.tc_failed ?? 0));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await onSave(project.id, {
        tc_total: Number(tcTotal) || 0,
        tc_done: Number(tcDone) || 0,
        tc_failed: Number(tcFailed) || 0,
      });
      onClose();
    } catch (err) {
      setError(err.message || 'Could not save changes');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="module-meta-form project-tc-form">
      <div className="project-tc-fields">
        <label className="module-meta-field project-tc-field">
          <span>Target</span>
          <input
            type="number"
            min="0"
            value={tcTotal}
            onChange={e => setTcTotal(e.target.value)}
          />
        </label>
        <label className="module-meta-field project-tc-field">
          <span>Passed</span>
          <input
            type="number"
            min="0"
            value={tcDone}
            onChange={e => setTcDone(e.target.value)}
          />
        </label>
        <label className="module-meta-field project-tc-field">
          <span>Failed</span>
          <input
            type="number"
            min="0"
            value={tcFailed}
            onChange={e => setTcFailed(e.target.value)}
          />
        </label>
      </div>

      {error && <div className="module-meta-error">{error}</div>}

      <div className="module-meta-actions">
        <button
          type="button"
          className="module-meta-save"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? 'Saving...' : 'Save'}
        </button>
        <button
          type="button"
          className="module-meta-cancel"
          onClick={onClose}
          disabled={saving}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

export default ProjectTestCaseEditor;