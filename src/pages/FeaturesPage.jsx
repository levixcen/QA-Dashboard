import { useState } from 'react';
import ModuleTestsModal from '../components/ModuleTestsModal';

function ModulesPage({ modules }) {
  const [filter, setFilter] = useState('All');
  const [openModule, setOpenModule] = useState(null);

  const filtered = modules.filter(m => {
    if (filter === 'All') return true;
    if (filter === 'Healthy') return m.color === 'green';
    if (filter === 'Needs Attention') return m.color === 'red' || m.color === 'orange';
    if (filter === 'Not Started') return m.color === 'gray';
    return true;  
  });

  return (
    <>
      <div className="page-header">
        <div>
          <div className="brand">SEDAYU ONE</div>
          <h1>Features</h1>
        </div>
      </div>

      <div className="controls">
        <div className="control-group">
          <label>Add feature</label>
          <input placeholder="e.g. Marketplace" />
        </div>
        <button className="btn btn-dark">+ Add</button>

        <div className="control-group">
          <label>Feature name</label>
          <input placeholder="Feature name" />
        </div>
        <div className="control-group">
          <label>Failing test</label>
          <input placeholder="e.g. Warranty Claim" />
        </div>
        <div className="control-group">
          <label>Pass</label>
          <input type="number" defaultValue={45} style={{ width: 70 }} />
        </div>
        <div className="control-group">
          <label>Fail</label>
          <input type="number" defaultValue={1} style={{ width: 70 }} />
        </div>
        <button className="btn btn-primary">↑ Ingest</button>
      </div>

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
              <div className="module-pct">{m.pct}%</div>
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

            <button
              className="archive"
              onClick={e => e.stopPropagation()}
            >
              Archive
            </button>
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