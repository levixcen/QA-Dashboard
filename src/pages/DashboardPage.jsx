import { useState } from 'react';
import ModuleMetaEditor from '../components/ModuleMetaEditor';
import YearlyChart from '../components/YearlyChart';
import { usePeriod } from '../context/PeriodContext';

const SEVERITY_LABELS = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function formatPeriod(p) {
  const [y, m] = p.split('-');
  return `${MONTH_NAMES[Number(m) - 1]} ${y}`;
}

function DashboardPage({ modules, loaded, generatedAt, overallStats, onUpdateModuleMeta, username }) {
  const { period } = usePeriod();
  const [editingModule, setEditingModule] = useState(null);
  const [hoverLabel, setHoverLabel] = useState(null);

  const totalFailing = modules.reduce((sum, m) => sum + m.failing, 0);
  const totalOpenDefects = overallStats?.open_defects
    ?? modules.reduce((sum, m) => sum + (m.open_defects || 0), 0);
  const totalUncovered = overallStats?.uncovered_failures
    ?? modules.reduce((sum, m) => sum + (m.uncovered_failures || 0), 0);
  const notStarted = modules.filter(m => m.color === 'gray').length;
  const active = modules.filter(m => m.color !== 'gray');
  const fallbackOverall = active.length
    ? Math.round(active.reduce((s, m) => s + m.pct, 0) / active.length)
    : 0;

  const hasData = overallStats
    ? (overallStats.total > 0 || totalOpenDefects > 0)
    : (active.length > 0 || totalOpenDefects > 0);
  const periodLabel = period ? formatPeriod(period) : 'all time';

  // Ring stays execution pass rate — defects surface as separate health signals.
  const ringPct = overallStats ? overallStats.pct : fallbackOverall;

  const automatedCount = modules.length - notStarted;
  const automationPct = modules.length ? Math.round((automatedCount / modules.length) * 100) : 0;

  const totalPlanned = modules.reduce((sum, m) => sum + (m.meta?.planned_tc_count || 0), 0);
  const totalActual = modules.reduce((sum, m) => sum + (m.total || 0), 0);
  const planVsActualPct = totalPlanned > 0 ? Math.round((totalActual / totalPlanned) * 100) : null;

  // Needs Attention: red/orange modules, sorted by open defects then failing tests
  const needsAttention = modules
    .filter(m => m.color === 'red' || m.color === 'orange')
    .sort((a, b) => {
      const d = (b.open_defects || 0) - (a.open_defects || 0);
      if (d !== 0) return d;
      return b.failing - a.failing;
    })
    .slice(0, 5);

  const topFailingTests = modules
    .flatMap(m => (m.details || []).map(d => ({ module: m.name, name: d.name, count: d.count })))
    .sort((a, b) => b.count - a.count)
    .slice(0, 4);

  // Prefer open *defects* severity for the severity card; fall back to failing-test severity
  const defectSev = overallStats?.defects_by_severity || null;
  const failureSev = overallStats?.severity || null;
  const severity = defectSev && (defectSev.critical + defectSev.high + defectSev.medium + defectSev.low) > 0
    ? defectSev
    : failureSev;
  const severityHasData = severity
    && (severity.critical + severity.high + severity.medium + severity.low) > 0;
  const severityIsDefects = severity === defectSev;

  let status = 'GREEN';
  let statusClass = 'green';
  let summaryText = 'Overall status is GREEN. All active modules are healthy.';

  if (!hasData) {
    status = 'NO DATA';
    statusClass = '';
    summaryText = `No test results or open defects recorded for ${periodLabel}.`;
  } else if (totalOpenDefects > 0 || totalFailing >= 5 || ringPct < 80) {
    status = 'RED';
    statusClass = 'red';
    const parts = [];
    if (totalOpenDefects > 0) parts.push(`${totalOpenDefects} open defect(s)`);
    if (totalFailing > 0) parts.push(`${totalFailing} failing test case(s)`);
    if (totalUncovered > 0) parts.push(`${totalUncovered} failure(s) without a defect`);
    summaryText = `Overall status is RED. ${parts.join(', ')}. Immediate attention is required.`;
  } else if (totalFailing >= 1 || ringPct < 95) {
    status = 'AMBER';
    statusClass = 'amber';
    summaryText = `Overall status is AMBER. ${totalFailing} test case(s) still failing. Most other modules are healthy.`;
  }

  // --- Nested ring geometry ---
  const CX = 140;
  const CY = 140;
  const OUTER_R = 124;
  const OUTER_STROKE = 10;
  const OUTER_CIRC = 2 * Math.PI * OUTER_R;
  const outerProgress = (ringPct / 100) * OUTER_CIRC;

  const INNER_R = 92;
  const INNER_STROKE = 22;
  const INNER_CIRC = 2 * Math.PI * INNER_R;

  const pfPassed = overallStats?.passed || 0;
  const pfFailed = overallStats?.failed || 0;
  const pfActual = overallStats?.total || 0;

  const pfTotal = Math.max(totalPlanned, pfActual);
  const pfNotRun = Math.max(pfTotal - pfPassed - pfFailed, 0);

  const passedLen = pfTotal > 0 ? (pfPassed / pfTotal) * INNER_CIRC : 0;
  const failedLen = pfTotal > 0 ? (pfFailed / pfTotal) * INNER_CIRC : 0;
  const notRunLen = pfTotal > 0 ? (pfNotRun / pfTotal) * INNER_CIRC : 0;

  const passPct = overallStats?.pass_pct;
  const centerPrimary = hoverLabel
    ? hoverLabel.count
    : `${ringPct}%`;
  const centerSecondary = hoverLabel
    ? hoverLabel.label
    : 'Health Score';

  const penetration = overallStats?.penetration_pct;

  return (
    <>
      <div className="page-header">
        <div>
          <div className="brand welcome-brand">Welcome, {username || 'User'}</div>
          <h1>QA Dashboard</h1>
        </div>
        <div>
          <div className="last-synced">Showing {periodLabel}</div>
          {generatedAt && (
            <div className="last-synced">Latest run {new Date(generatedAt).toLocaleString()}</div>
          )}
        </div>
      </div>

      {loaded && !hasData && (
        <div className="placeholder" style={{ marginBottom: 20 }}>
          <p>
            {period
              ? `No test runs or open defects for ${periodLabel}. Pick another month or show all time.`
              : "No data yet. Run parse_allure.py on Mario's latest results, or raise defects from the Features page."}
          </p>
        </div>
      )}

      <div className="dashboard-ring-block">
        <div className="merged-ring">
          <svg className="merged-ring-svg" viewBox="0 0 280 280" role="img" aria-label="Overall score and pass/fail breakdown">
            <defs>
              <linearGradient id="overallGradient" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#04BBE4" />
                <stop offset="60%" stopColor="#0c4a8a" />
                <stop offset="100%" stopColor="#02013C" />
              </linearGradient>
            </defs>

            <circle className="merged-outer-bg" cx={CX} cy={CY} r={OUTER_R} />
            <circle
              className="merged-outer-progress"
              cx={CX} cy={CY} r={OUTER_R}
              strokeDasharray={`${outerProgress} ${OUTER_CIRC}`}
              strokeDashoffset="0"
              onMouseEnter={() => setHoverLabel({ label: 'Health Score', count: `${ringPct}%` })}
              onMouseLeave={() => setHoverLabel(null)}
            />

            <circle className="merged-inner-bg" cx={CX} cy={CY} r={INNER_R} />
            {pfTotal > 0 && (
              <>
                <circle
                  className="merged-inner-passed"
                  cx={CX} cy={CY} r={INNER_R}
                  strokeDasharray={`${passedLen} ${INNER_CIRC}`}
                  strokeDashoffset="0"
                  onMouseEnter={() => setHoverLabel({ label: 'Passed', count: pfPassed })}
                  onMouseLeave={() => setHoverLabel(null)}
                />
                <circle
                  className="merged-inner-failed"
                  cx={CX} cy={CY} r={INNER_R}
                  strokeDasharray={`${failedLen} ${INNER_CIRC}`}
                  strokeDashoffset={-passedLen}
                  onMouseEnter={() => setHoverLabel({ label: 'Failed', count: pfFailed })}
                  onMouseLeave={() => setHoverLabel(null)}
                />
                {pfNotRun > 0 && (
                  <circle
                    className="merged-inner-notrun"
                    cx={CX} cy={CY} r={INNER_R}
                    strokeDasharray={`${notRunLen} ${INNER_CIRC}`}
                    strokeDashoffset={-(passedLen + failedLen)}
                    onMouseEnter={() => setHoverLabel({ label: 'Not Run', count: pfNotRun })}
                    onMouseLeave={() => setHoverLabel(null)}
                  />
                )}
              </>
            )}
          </svg>

          <div className="merged-ring-content">
            <div className="merged-rate">{centerPrimary}</div>
            <div className="merged-label">{centerSecondary}</div>
            {!hoverLabel && (pfTotal > 0 || totalOpenDefects > 0) && (
              <div className="merged-meta">
                {pfTotal > 0 && (
                  <div className="merged-meta-line">
                    {pfPassed} passed · {pfFailed} failed
                    {pfNotRun > 0 ? ` · ${pfNotRun} not run` : ''} · {pfTotal} total
                  </div>
                )}
                {(passPct != null || totalOpenDefects > 0) && (
                  <div className="merged-meta-line">
                    {passPct != null ? `Pass ${passPct}%` : ''}
                    {passPct != null && totalOpenDefects > 0 ? ' · ' : ''}
                    {totalOpenDefects > 0
                      ? `${totalOpenDefects} open defect${totalOpenDefects === 1 ? '' : 's'}`
                      : ''}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <div className="summary-card summary-below-ring">
          <h3>Executive Summary</h3>
          <div className={`summary-status ${statusClass}`}>{status}</div>
          <p className="summary-text">{summaryText}</p>
        </div>
      </div>

      <div className="dashboard-secondary-row">
        <div className="severity-card">
          <h3>{severityIsDefects ? 'Open Defect Severity' : 'Failure Severity'}</h3>
          {severityHasData ? (
            <div className="severity-badges">
              {Object.entries(SEVERITY_LABELS).map(([key, label]) => (
                <div key={key} className={`severity-badge severity-${key}`}>
                  <span className="severity-count">{severity[key] || 0}</span>
                  <span className="severity-label">{label}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="insight-note">
              No open defects yet. Raise one from a failing test on Features, or add one on the Defects page.
            </p>
          )}
          {totalOpenDefects > 0 && (
            <p className="insight-note" style={{ marginTop: 10 }}>
              {totalOpenDefects} open defect{totalOpenDefects === 1 ? '' : 's'}
              {penetration != null ? ` · ${penetration}% penetration` : ''}
              {totalUncovered > 0 ? ` · ${totalUncovered} uncovered failure(s)` : ''}
            </p>
          )}
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
          {planVsActualPct !== null && (
            <p className="insight-note">
              Plan vs Actual: {totalActual} of {totalPlanned} planned test cases ({planVsActualPct}%)
            </p>
          )}
        </div>

        <div className="insight-card">
          <h3>Needs Attention</h3>
          {needsAttention.length === 0 && (
            <p className="insight-note">Nothing urgent right now.</p>
          )}
          {needsAttention.map(m => (
            <div key={m.id} className="needs-attention-item">
              <div className="insight-row">
                <span className={`icon ${m.color}`}>{m.color === 'red' ? '\u00d7' : '!'}</span>
                <span className="insight-row-name">{m.name}</span>
                <span className="insight-row-meta">
                  {(m.open_defects || 0) > 0
                    ? `${m.open_defects} defect${m.open_defects === 1 ? '' : 's'}`
                    : `${m.failing} failing`}
                </span>
                <button
                  type="button"
                  className="module-meta-edit-trigger"
                  onClick={() => setEditingModule(editingModule === m.name ? null : m.name)}
                  title="Edit owner, mitigation plan, or planned test count"
                >
                  &#9998;
                </button>
              </div>
              {(m.open_defects || 0) > 0 && m.failing > 0 && (
                <div className="module-meta-display">
                  {m.failing} failing · {m.uncovered_failures || 0} uncovered
                </div>
              )}
              {m.meta?.pic && (
                <div className="module-meta-display">Owner: {m.meta.pic}</div>
              )}
              {m.meta?.mitigation_plan && (
                <div className="module-meta-display mitigation">
                  Mitigation: {m.meta.mitigation_plan}
                </div>
              )}
              {editingModule === m.name && (
                <ModuleMetaEditor
                  module={m}
                  onSave={onUpdateModuleMeta}
                  onClose={() => setEditingModule(null)}
                />
              )}
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

      <div className="insight-card" style={{ marginTop: 20 }}>
        <YearlyChart />
      </div>
    </>
  );
}

export default DashboardPage;