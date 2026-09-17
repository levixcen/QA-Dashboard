import { useState, useEffect } from 'react';
import { authFetch } from '../utils/auth';
import { formatDate } from "../utils/formatDate";

function ProjectsPage() {
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    authFetch('/api/projects')
      .then(res => res.json())
      .then(data => {
        setProjects(data);
        setLoading(false);
      })
      .catch(() => {
        setError('Could not load projects.');
        setLoading(false);
      });
  }, []);

  return (
    <>
      <div className="page-header">
        <div>
          <div className="brand">SEDAYU ONE</div>
          <h1>Projects</h1>
        </div>
      </div>

      {loading && <div className="placeholder"><p>Loading projects.</p></div>}
      {error && <div className="placeholder"><p>{error}</p></div>}

      {!loading && !error && (
        <div className="modules">
          {projects.map(p => (
            <div key={p.id} className="module-card">
              <div className="module-header">
                <div className="module-name">
                  <span className={`icon ${p.color}`}>
                    {p.color === 'green' ? '✓' : p.color === 'orange' ? '!' : '×'}
                  </span>
                  {p.name}
                </div>
                <div className="module-pct">{p.pct}%</div>
              </div>

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
                  <span>Test cases</span>
                  <span style={{ color: '#5a7a9a', fontWeight: 400 }}>{p.tc_done} of {p.tc_total}</span>
                </div>
                <div className="detail-row">
                  <span>Target</span>
                  <span style={{ color: '#5a7a9a', fontWeight: 400 }}>{formatDate(p.target_date)}</span>
                </div>
              </div>

              <div className="status-row" style={{ marginTop: -4 }}>
                <span>{p.note}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

export default ProjectsPage;