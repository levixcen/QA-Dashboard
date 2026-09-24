import { useState } from 'react';
import { authFetch } from '../utils/auth';

// Mirrors the backend's MAX_EVIDENCE_BYTES limit (main.py). Checked here
// too so the person gets instant feedback, but the backend re-checks the
// actual byte size regardless — a client-side check alone is trivial to
// bypass and isn't relied on as the real limit.
const MAX_EVIDENCE_BYTES = 2 * 1024 * 1024;

// Must match ALLOWED_SEVERITIES in main.py (no "normal" — that is only
// the fallback used by reports.normalize_severity for untagged automated tests).
const SEVERITY_OPTIONS = [
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

// One manual test-case entry per submission: description, a single
// Pass/Fail status, severity, and at most one evidence image.
// Posts to POST /api/features/ingest. Visibility is controlled by the
// parent (FeaturesPage holds "which module is being edited"), same
// pattern as ModuleMetaEditor elsewhere in this app.
function FeatureEntryEditor({ moduleName, period, onSaved, onClose }) {
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState('passed');
  const [severity, setSeverity] = useState('medium');
  const [file, setFile] = useState(null);
  const [fileError, setFileError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  function handleFileChange(e) {
    const selected = e.target.files[0] || null;
    setFileError(null);

    if (selected && selected.size > MAX_EVIDENCE_BYTES) {
      setFile(null);
      setFileError('Image must be 2MB or smaller.');
      e.target.value = '';
      return;
    }

    setFile(selected);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const form = new FormData();
      form.append('name', moduleName);
      form.append('period', period);
      form.append('status', status);
      form.append('severity', severity);
      if (description.trim()) form.append('description', description.trim());
      if (file) form.append('file', file);

      const res = await authFetch('/api/features/ingest', {
        method: 'POST',
        body: form,
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to save entry');
      }

      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="module-meta-form" onClick={e => e.stopPropagation()}>
      <label className="module-meta-field">
        <span>Description</span>
        <textarea
          value={description}
          onChange={e => setDescription(e.target.value)}
          placeholder="What did you test?"
          rows={2}
        />
      </label>

      <label className="module-meta-field">
        <span>Status</span>
        <select value={status} onChange={e => setStatus(e.target.value)}>
          <option value="passed">Pass</option>
          <option value="failed">Fail</option>
        </select>
      </label>

      <label className="module-meta-field">
        <span>Severity</span>
        <select value={severity} onChange={e => setSeverity(e.target.value)}>
          {SEVERITY_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </label>

      <label className="module-meta-field">
        <span>Evidence (1 image, max 2MB)</span>
        <input
          type="file"
          accept="image/png,image/jpeg,image/gif,image/webp"
          onChange={handleFileChange}
        />
      </label>
      {fileError && <div className="module-meta-error">{fileError}</div>}
      {error && <div className="module-meta-error">{error}</div>}

      <div className="module-meta-actions">
        <button
          type="button"
          className="module-meta-save"
          onClick={handleSave}
          disabled={saving || !!fileError}
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

export default FeatureEntryEditor;