import { useState, useEffect } from 'react';
import { authFetch } from '../utils/auth';
import { usePeriod } from '../context/PeriodContext';

const IMAGE_EXTENSIONS = /\.(png|jpe?g|gif|webp)$/i;

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

function ModuleTestsModal({ moduleName, onClose }) {
  const { period } = usePeriod();
  const [tests, setTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedUuid, setExpandedUuid] = useState(null);

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
                </div>

                {t.error_message && (
                  <p className="test-row-error">{t.error_message}</p>
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