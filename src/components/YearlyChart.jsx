import { useState, useEffect } from 'react';
import { authFetch } from '../utils/auth';
import { usePeriod } from '../context/PeriodContext';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
// Smaller overall chart
const W = 480;
const H = 200;
const TOP = 14;
const BOTTOM = 24;
const PLOT_H = H - TOP - BOTTOM;

function YearlyChart() {
  const { period, setPeriod } = usePeriod();
  const [year, setYear] = useState(() =>
    period ? Number(period.slice(0, 4)) : new Date().getFullYear()
  );
  const [months, setMonths] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    setError('');
    authFetch(`/api/reports/monthly?year=${year}`)
      .then(res => (res.ok ? res.json() : Promise.reject()))
      .then(data => setMonths(data.months || []))
      .catch(() => setError('Could not load yearly data.'));
  }, [year]);

  const max = Math.max(1, ...months.map(m => m.total));
  const step = W / 12;
  // Thinner bars
  const barW = 16;

  return (
    <div className="yearly-chart">
      <div className="yearly-chart-header">
        <h3>Test executions in {year}</h3>
        <div className="yearly-chart-nav">
          <button type="button" onClick={() => setYear(y => y - 1)} aria-label="Previous year">‹</button>
          <button type="button" onClick={() => setYear(y => y + 1)} aria-label="Next year">›</button>
        </div>
      </div>

      {error && <p className="modal-status">{error}</p>}

      {!error && (
        <svg viewBox={`0 0 ${W} ${H}`} className="yearly-chart-svg" role="img">
          {months.map((m, i) => {
            const x = i * step + (step - barW) / 2;
            const totalH = (m.total / max) * PLOT_H;
            const passedH = (m.passed / max) * PLOT_H;
            const baseY = TOP + PLOT_H;
            const selected = period === m.month;
            return (
              <g
                key={m.month}
                style={{ cursor: m.total ? 'pointer' : 'default' }}
                onClick={() => m.total && setPeriod(m.month)}
              >
                <title>{`${MONTHS[i]}: ${m.total} run, ${m.passed} passed, ${m.failed} failed`}</title>
                {/* Failed (bottom) — softer red */}
                <rect x={x} y={baseY - totalH} width={barW} height={totalH} rx="2" fill="#C5221F" opacity={selected ? 1 : 0.8} />
                {/* Passed (top of failed) — theme pacific blue */}
                <rect x={x} y={baseY - passedH} width={barW} height={passedH} rx="2" fill="#04BBE4" opacity={selected ? 1 : 0.85} />
                {selected && (
                  <rect x={x - 2} y={baseY - totalH - 2} width={barW + 4} height={totalH + 4} rx="3" fill="none" stroke="#02013C" strokeWidth="1.5" />
                )}
                <text x={x + barW / 2} y={H - 6} textAnchor="middle" fontSize="10" fill="currentColor">
                  {MONTHS[i]}
                </text>
                {m.total > 0 && (
                  <text x={x + barW / 2} y={baseY - totalH - 3} textAnchor="middle" fontSize="9" fill="currentColor">
                    {m.total}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      )}

      <div className="yearly-chart-legend">
        <span><i style={{ background: '#04BBE4' }} /> Passed</span>
        <span><i style={{ background: '#C5221F' }} /> Failed</span>
      </div>
    </div>
  );
}

export default YearlyChart;