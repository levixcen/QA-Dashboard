import { useState } from 'react';

// Inline edit form for the manually-maintained module fields (PIC,
// mitigation plan, planned test case count) that live in the module_meta
// table rather than the automated Allure pipeline. Visibility is controlled
// by the parent (DashboardPage holds the "which module is being edited"
// state) so the pencil trigger can sit inline in a row while this form
// renders as its own full-width block. Saves via PATCH /api/module-meta/{module}.
function ModuleMetaEditor({ module, onSave, onClose }) {
  const meta = module.meta || {};
  const [pic, setPic] = useState(meta.pic || '');
  const [mitigationPlan, setMitigationPlan] = useState(meta.mitigation_plan || '');
  const [plannedTcCount, setPlannedTcCount] = useState(
    meta.planned_tc_count != null ? String(meta.planned_tc_count) : ''
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await onSave(module.name, {
        pic: pic.trim() || null,
        mitigation_plan: mitigationPlan.trim() || null,
        planned_tc_count: plannedTcCount.trim() === '' ? null : Number(plannedTcCount),
      });
      onClose();
    } catch (err) {
      setError(err.message || 'Could not save changes');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="module-meta-form">
      <label className="module-meta-field">
        <span>Owner (PIC)</span>
        <input
          type="text"
          value={pic}
          onChange={e => setPic(e.target.value)}
          placeholder="e.g. Dara"
        />
      </label>

      <label className="module-meta-field">
        <span>Mitigation plan</span>
        <textarea
          value={mitigationPlan}
          onChange={e => setMitigationPlan(e.target.value)}
          placeholder="What's the plan to recover this module?"
          rows={2}
        />
      </label>

      <label className="module-meta-field">
        <span>Planned test cases</span>
        <input
          type="number"
          min="0"
          value={plannedTcCount}
          onChange={e => setPlannedTcCount(e.target.value)}
          placeholder="e.g. 30"
        />
      </label>

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

export default ModuleMetaEditor;