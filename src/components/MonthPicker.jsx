import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { authFetch } from '../utils/auth';
import { usePeriod } from '../context/PeriodContext';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function MonthPicker({ expanded }) {
  const { period, setPeriod } = usePeriod();
  const [open, setOpen] = useState(false);
  const [available, setAvailable] = useState([]);
  const [pos, setPos] = useState({ left: 0, top: 0 });
  const [year, setYear] = useState(() =>
    period ? Number(period.slice(0, 4)) : new Date().getFullYear()
  );
  const triggerRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    authFetch('/api/reports/periods')
      .then(res => (res.ok ? res.json() : Promise.reject()))
      .then(data => setAvailable(data.periods || []))
      .catch(() => setAvailable([]));
  }, [open]);

  function toggle() {
    if (!open && triggerRef.current) {
      const r = triggerRef.current.getBoundingClientRect();
      setPos({ left: r.right + 8, top: r.top });
    }
    setOpen(o => !o);
  }

  function choose(value) {
    setPeriod(value);
    setOpen(false);
  }

  const label = period
    ? `${MONTHS[Number(period.slice(5, 7)) - 1]} ${period.slice(0, 4)}`
    : 'All time';

  const selectedHasData = !period || available.includes(period);

  return (
    <>
      <div
        ref={triggerRef}
        className="sidebar-icon"
        onClick={toggle}
        title={`Period: ${label}`}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="4" width="18" height="18" rx="2" />
          <path d="M16 2v4M8 2v4M3 10h18" />
        </svg>
        <span className={`sidebar-label ${expanded ? 'visible' : ''}`}>{label}</span>
      </div>

      {open && createPortal(
        <>
          <div className="month-picker-backdrop" onClick={() => setOpen(false)} />
          <div className="month-picker-popover" style={{ left: pos.left, top: pos.top }}>
            <div className="month-picker-year">
              <button onClick={() => setYear(y => y - 1)}>‹</button>
              <span>{year}</span>
              <button onClick={() => setYear(y => y + 1)}>›</button>
            </div>

            <div className="month-picker-grid">
              {MONTHS.map((name, i) => {
                const value = `${year}-${String(i + 1).padStart(2, '0')}`;
                const hasData = available.includes(value);
                return (
                  <button
                    key={value}
                    className={`month-picker-cell${period === value ? ' active' : ''}${hasData ? '' : ' empty'}`}
                    onClick={() => choose(value)}
                  >
                    {name}
                  </button>
                );
              })}
            </div>

            {!selectedHasData && (
              <div className="month-picker-notice">No activity recorded for {label}.</div>
            )}

            <button className="month-picker-all" onClick={() => choose(null)}>
              Show all time
            </button>
          </div>
        </>,
        document.body
      )}
    </>
  );
}

export default MonthPicker;