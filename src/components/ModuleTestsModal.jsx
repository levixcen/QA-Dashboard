import { useState, useEffect } from 'react';
import { authFetch } from '../utils/auth';
import { usePeriod } from '../context/PeriodContext';

const IMAGE_EXTENSIONS = /\.(png|jpe?g|gif|webp)$/i;
const SEVERITY_OPTIONS = ['critical', 'high', 'medium', 'low'];
const FAILING_STATUSES = ['failed', 'broken'];

function EvidenceImage({ url, name }) {
  const [src, setSrc] = useState(null);

  useEffect(() => {
    let objectUrl;
    let cancelled = false;
    authFetch(url)
      .then(res => (res.ok ? res.blob() : Promise.reject()))
      .then(blob => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);

  if (!src) return <span className="evidence-thumb">Loading</span>;
  return (
    <a className="evidence-item" href={src} target="_blank" rel="noreferrer">
      <img className="evidence-thumb" src={src} alt={name} />
    </a>
  );
}

function RaiseDefectForm({ test, moduleName, onRaised, onCancel }) {
  const [severity, setSeverity] = useState(SEVERITY_OPTIONS.includes(test.severity) ? test.severity : 'medium');
  const [owner, setOwner] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  async function submit() {
    setSaving(true);
    setError(null);
    try {
      const res = await authFetch('/api/defects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_ref: test.uuid,
          severity,
          module: moduleName,
          owner: owner.trim() || null,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to raise defect');
      }
      const created = await res.json();
      onRaised(created);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="module-meta-form">
      <label className="module-meta-field">
        <span>Severity</span>
        <select value={severity} onChange={e => setSeverity(e.target.value)}>
          {SEVERITY_OPTIONS.map(s => (
            <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>
          ))}
        </select>
      </label>
      <label className="module-meta-field">
        <span>Owner</span>
        <input value={owner} onChange={e => setOwner(e.target.value)} placeholder="Optional" />
      </label>
      {error && <div className="module-meta-error">{error}</div>}
      <div className="module-meta-actions">
        <button type="button" className="module-meta-save" onClick={submit} disabled={saving}>
          {saving ? 'Raising...' : 'Raise Defect'}
        </button>
        <button type="button" className="module-meta-cancel" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </div>
  );
}

function ModuleTestsModal({ moduleName, onClose }) {
  const { period } = usePeriod();
  const [tests, setTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedUuid, setExpandedUuid] = useState(null);
  const [raisingUuid, setRaisingUuid] = useState(null);

  useEffect(() => {
    const query = period ? `?month=${period}` : '';
    authFetch(`/api/modules/${encodeURIComponent(moduleName)}/tests${query}`)
      .then(res => {
        if (!res.ok) throw new Error('bad response');
        return res.json();
      })
      .then(data => {
        setTests(data);
        setLoading(false);
      })
      .catch(() => {
        setError('Could not load test results.');
        setLoading(false);
      });
  }, [moduleName, period]);

  function toggleExpanded(uuid) {
    setExpandedUuid(current => (current === uuid ? null : uuid));
  }

  function handleDefectRaised(testUuid, defect) {
    setTests(prev =>
      prev.map(t =>
        t.uuid === testUuid ? { ...t, defect: { code: defect.defect_code } } : t
      )
    );
    setRaisingUuid(null);
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{moduleName}</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <div className="modal-body">
          {loading && <p className="modal-status">Loading test results.</p>}
          {error && <p className="modal-status">{error}</p>}

          {!loading && !error && tests.length === 0 && (
            <p className="modal-status">No test results for this module yet.</p>
          )}

          {!loading && !error && tests.map(t => {
            const images = t.attachments.filter(a => IMAGE_EXTENSIONS.test(a.url));
            const isExpanded = expandedUuid === t.uuid;
            const isFailing = FAILING_STATUSES.includes(t.status);

            return (
              <div key={t.uuid} className="test-row-thin">
                <div className="test-row-thin-line">
                  <span className="test-row-name">{t.name}</span>
                  <span className={`test-row-status test-row-status-${t.status}`}>{t.status}</span>

                  {images.length > 0 ? (
                    <button
                      className="evidence-eye-btn"
                      onClick={() => toggleExpanded(t.uuid)}
                      title={isExpanded ? 'Hide evidence' : 'View evidence'}
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    </button>
                  ) : (
                    <span className="evidence-eye-btn evidence-eye-btn-disabled" title="No evidence">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    </span>
                  )}

                  {isFailing && (
                    t.defect ? (
                      <span className="raised-defect-label">Defect {t.defect.code} raised</span>
                    ) : (
                      <button
                        type="button"
                        className="raise-defect-trigger"
                        onClick={() => setRaisingUuid(raisingUuid === t.uuid ? null : t.uuid)}
                      >
                        Raise defect
                      </button>
                    )
                  )}
                </div>

                {t.error_message && (
                  <p className="test-row-error">{t.error_message}</p>
                )}

                {raisingUuid === t.uuid && (
                  <RaiseDefectForm
                    test={t}
                    moduleName={moduleName}
                    onRaised={defect => handleDefectRaised(t.uuid, defect)}
                    onCancel={() => setRaisingUuid(null)}
                  />
                )}

                {isExpanded && images.length > 0 && (
                  <div className="test-row-evidence">
                    {images.map((a, i) => (
                      <EvidenceImage key={i} url={a.url} name={a.name} />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default ModuleTestsModal;