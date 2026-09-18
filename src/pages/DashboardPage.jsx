function DashboardPage({ modules, loaded, generatedAt }) {
  const totalFailing = modules.reduce((sum, m) => sum + m.failing, 0);
  const notStarted = modules.filter(m => m.color === 'gray').length;
  const active = modules.filter(m => m.color !== 'gray');
  const overall = active.length ? Math.round(active.reduce((s, m) => s + m.pct, 0) / active.length) : 0;

  const automatedCount = modules.length - notStarted;
  const automationPct = modules.length ? Math.round((automatedCount / modules.length) * 100) : 0;

  const needsAttention = modules
    .filter(m => m.color === 'red' || m.color === 'orange')
    .sort((a, b) => b.failing - a.failing)
    .slice(0, 3);

  const topFailingTests = modules
    .flatMap(m => (m.details || []).map(d => ({ module: m.name, name: d.name, count: d.count })))
    .sort((a, b) => b.count - a.count)
    .slice(0, 4);

  let status = 'GREEN';
  let statusClass = 'green';
  let summaryText = 'Overall status is GREEN. All active modules are healthy.';

  if (totalFailing >= 5 || overall < 80) {
    status = 'RED';
    statusClass = 'red';
    summaryText = `Overall status is RED. ${totalFailing} test cases are currently failing across modules. Immediate attention is required on high-impact failures.`;
  } else if (totalFailing >= 1 || overall < 95) {
    status = 'AMBER';
    statusClass = 'amber';
    summaryText = `Overall status is AMBER. ${totalFailing} test case(s) still failing. Main open issue is in Support (Warranty Claim category missing). Most other modules are healthy.`;
  }

  return (
    <>
      <div className="page-header">
        <div>
          <div className="brand">SEDAYU ONE</div>
          <h1>QA Dashboard</h1>
        </div>
        {generatedAt && (
          <div className="last-synced">Last synced {new Date(generatedAt).toLocaleString()}</div>
        )}
      </div>

      {loaded && modules.length === 0 && (
        <div className="placeholder" style={{ marginBottom: 20 }}>
          <p>No data yet. Run parse_allure.py on Mario's latest results.</p>
        </div>
      )}

      <div className="dashboard-layout">
        <div className="overall">
  <svg className="overall-svg" viewBox="0 0 220 220">
    <defs>
      <linearGradient id="sidebarGradient" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stopColor="#04BBE4" />
        <stop offset="60%" stopColor="#0c4a8a" />
        <stop offset="100%" stopColor="#02013C" />
      </linearGradient>
    </defs>
    <circle className="overall-bg-circle" cx="110" cy="110" r="100" />
    <circle className="overall-progress-circle" cx="110" cy="110" r="100" />
  </svg>
  <div className="overall-content">
    <div className="rate">100%</div>
    <div className="label">Overall Score</div>
    <div className="meta">
      <span>Completed</span>
    </div>
  </div>
</div>

        <div className="summary-card">
          <h3>Executive Summary</h3>
          <div className={`summary-status ${statusClass}`}>{status}</div>
          <p className="summary-text">{summaryText}</p>
        </div>
      </div>

      <div className="insights-grid">
        <div className="insight-card">
          <h3>Automation Coverage</h3>
          <div className="insight-big">{automatedCount} of {modules.length}</div>
          <div className="progress">
            <div className="progress-bar green" style={{ width: `${automationPct}%` }} />
          </div>
          <p className="insight-note">
            features have automated results. {notStarted} still test case only.
          </p>
        </div>

        <div className="insight-card">
          <h3>Needs Attention</h3>
          {needsAttention.length === 0 && (
            <p className="insight-note">Nothing urgent right now.</p>
          )}
          {needsAttention.map(m => (
            <div key={m.id} className="insight-row">
              <span className={`icon ${m.color}`}>{m.color === 'red' ? '\u00d7' : '!'}</span>
              <span className="insight-row-name">{m.name}</span>
              <span className="insight-row-meta">{m.failing} failing</span>
            </div>
          ))}
        </div>

        <div className="insight-card">
          <h3>Top Failing Tests</h3>
          {topFailingTests.length === 0 && (
            <p className="insight-note">No failing tests recorded.</p>
          )}
          {topFailingTests.map((t, i) => (
            <div key={i} className="insight-row">
              <span className="insight-row-name">{t.name}</span>
              <span className="insight-row-meta">{t.module}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

export default DashboardPage;