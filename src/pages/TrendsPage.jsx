import { useState, useEffect } from 'react';
import { authFetch } from '../utils/auth';
import YearlyChart from '../components/YearlyChart';

function TrendsPage({ username }) {
  const [year, setYear] = useState(new Date().getFullYear());
  const [months, setMonths] = useState([]);
  const [penetration, setPenetration] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    setError('');
    authFetch(`/api/reports/monthly?year=${year}`)
      .then(res => (res.ok ? res.json() : Promise.reject()))
      .then(data => setMonths(data.months || []))
      .catch(() => setError('Could not load monthly trends.'));

    authFetch('/api/defects/penetration')
      .then(res => (res.ok ? res.json() : null))
      .then(data => setPenetration(data))
      .catch(() => setPenetration(null));
  }, [year]);

  const totals = months.reduce(
    (acc, m) => {
      acc.total += m.total || 0;
      acc.passed += m.passed || 0;
      acc.failed += m.failed || 0;
      return acc;
    },
    { total: 0, passed: 0, failed: 0 }
  );
  const passRate = totals.total ? Math.round((totals.passed / totals.total) * 100) : 0;

  return (
    <>
      <div className="page-header">
        <div>
          <div className="brand welcome-brand">Welcome, {username || 'User'}</div>
          <h1>Trends</h1>
        </div>
        <div className="yearly-chart-nav">
          <button type="button" onClick={() => setYear(y => y - 1)} aria-label="Previous year">‹</button>
          <button type="button" onClick={() => setYear(y => y + 1)} aria-label="Next year">›</button>
        </div>
      </div>

      {error && <p className="modal-status">{error}</p>}

      <div className="defects-summary-row">
        <div className="severity-card">
          <h3>Executions in {year}</h3>
          <div className="insight-big">{totals.total}</div>
          <p className="insight-note">{totals.passed} passed · {totals.failed} failed</p>
        </div>
        <div className="severity-card">
          <h3>Pass rate ({year})</h3>
          <div className="insight-big">{passRate}%</div>
          <p className="insight-note">Across all months with data</p>
        </div>
        <div className="severity-card">
          <h3>Defect penetration</h3>
          <div className="insight-big">
            {penetration ? `${penetration.penetration_pct}%` : '—'}
          </div>
          <p className="insight-note">
            {penetration
              ? `${penetration.total_open} open / ${penetration.executed_tcs} executed TCs`
              : 'Add defects API to enable'}
          </p>
        </div>
      </div>

      <div className="insight-card" style={{ marginTop: 8 }}>
        <YearlyChart />
      </div>

      <div className="insight-card" style={{ marginTop: 16 }}>
        <h3>Monthly breakdown — {year}</h3>
        {months.length === 0 ? (
          <p className="insight-note">No monthly data yet.</p>
        ) : (
          <div className="defects-table-wrap" style={{ marginTop: 12 }}>
            <table className="defects-table">
              <thead>
                <tr>
                  <th>Month</th>
                  <th>Total</th>
                  <th>Passed</th>
                  <th>Failed</th>
                  <th>Pass %</th>
                </tr>
              </thead>
              <tbody>
                {months.map(m => (
                  <tr key={m.month}>
                    <td>{m.month}</td>
                    <td>{m.total}</td>
                    <td>{m.passed}</td>
                    <td>{m.failed}</td>
                    <td>{m.pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

export default TrendsPage;