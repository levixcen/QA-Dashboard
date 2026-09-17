function DashboardPage({ modules, loaded }) {
  const totalFailing = modules.reduce((sum, m) => sum + m.failing, 0);
  const notStarted = modules.filter(m => m.color === 'gray').length;
  const active = modules.filter(m => m.color !== 'gray');
  const overall = active.length ? Math.round(active.reduce((s, m) => s + m.pct, 0) / active.length) : 0;

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
      </div>

      {loaded && modules.length === 0 && (
        <div className="placeholder" style={{ marginBottom: 20 }}>
          <p>No data yet. Run parse_allure.py on Mario's latest results.</p>
        </div>
      )}

      <div className="dashboard-layout">
        <div className="overall">
          <div className="rate">{overall}%</div>
          <div className="label">Overall Pass Rate</div>
          <div className="meta">
            <span>{totalFailing} cases failing</span>
            <span>{notStarted} modules not started</span>
          </div>
        </div>

        <div className="summary-card">
          <h3>Executive Summary</h3>
          <div className={`summary-status ${statusClass}`}>{status}</div>
          <p className="summary-text">{summaryText}</p>
        </div>
      </div>
    </>
  );
}

export default DashboardPage;