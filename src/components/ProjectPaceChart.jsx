import { useState } from 'react';

const DAY = 86400000;
const BLUE = '#04BBE4';
const NAVY = '#0D2744';
const RED = '#E5352B';
const GREY = '#8497AD';
const GRID = '#E8EEF4';
const MIN_SPAN_DAYS = 14;

const W = 720;
const H = 300;
const L = 48;
const R = 28;
const T = 28;
const B = 40;
const PLOT_W = W - L - R;
const PLOT_H = H - T - B;

const parse = s => new Date(`${s}T12:00:00`);
const diffDays = (a, b) => Math.round((b.getTime() - a.getTime()) / DAY);
const fmt = d => d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
const pad = n => String(n).padStart(2, '0');
const todayDate = () => {
  const n = new Date();
  return parse(`${n.getFullYear()}-${pad(n.getMonth() + 1)}-${pad(n.getDate())}`);
};
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
const dayKey = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

function Chart({ project }) {
  const behind =
    project.status_flag === 'behind' ||
    project.status_flag === 'overdue' ||
    project.status_flag === 'at_risk';
  const color = behind ? RED : BLUE;

  const start = parse(project.created_at);
  const end = project.target_date ? parse(project.target_date) : null;
  const today = todayDate();
  const currentPct = project.current_pct ?? 0;

  // Natural domain: created → max(target, today)
  let domainStart = start;
  let domainEnd = end ? (today > end ? today : end) : today;

  const naturalSpan = Math.max(0, diffDays(domainStart, domainEnd));
  if (naturalSpan < MIN_SPAN_DAYS) {
    const mid = new Date((domainStart.getTime() + domainEnd.getTime()) / 2);
    domainStart = new Date(mid.getTime() - (MIN_SPAN_DAYS / 2) * DAY);
    domainEnd = new Date(mid.getTime() + (MIN_SPAN_DAYS / 2) * DAY);
    if (start < domainStart) domainStart = start;
    if (today > domainEnd) domainEnd = today;
    if (end && end > domainEnd) domainEnd = end;
    if (end && end < domainStart) domainStart = end;
  }

  const total = Math.max(1, diffDays(domainStart, domainEnd));
  const x = d =>
    L + (Math.max(0, Math.min(total, diffDays(domainStart, d))) / total) * PLOT_W;
  const y = v => T + (1 - Math.max(0, Math.min(100, v)) / 100) * PLOT_H;

  // Raw history → one point per calendar day (keep highest pct that day)
  const byDay = new Map();
  for (const pt of project.points || []) {
    const d = parse(pt.date);
    if (Number.isNaN(d.getTime())) continue;
    const key = dayKey(d);
    const prev = byDay.get(key);
    if (!prev || pt.pct > prev.pct) byDay.set(key, { d, pct: pt.pct });
  }

  // Always anchor start at 0% and today at current %
  const startKey = dayKey(start);
  if (!byDay.has(startKey) || byDay.get(startKey).pct > 0) {
    // Prefer explicit 0 at project start when history is sparse
    if (!byDay.has(startKey)) byDay.set(startKey, { d: start, pct: 0 });
  }
  const todayKey = dayKey(today);
  byDay.set(todayKey, { d: today, pct: currentPct });

  let pts = [...byDay.values()].sort((a, b) => a.d - b.d);

  // If everything still lands on one day, force a left→right path so the
  // chart never draws a pure vertical stack (Tableau-style rising area).
  const uniqueDays = new Set(pts.map(p => dayKey(p.d)));
  if (uniqueDays.size < 2) {
    pts = [
      { d: domainStart, pct: 0 },
      { d: today, pct: currentPct },
    ];
  } else if (pts[0].pct !== 0 && pts[0].d > domainStart) {
    pts = [{ d: domainStart, pct: 0 }, ...pts];
  }

  const coords = pts.map(pt => `${x(pt.d)},${y(pt.pct)}`);
  const first = pts[0];
  const lastPt = pts[pts.length - 1];
  const area =
    pts.length > 1
      ? `M ${x(first.d)},${y(0)} L ${coords.join(' L ')} L ${x(lastPt.d)},${y(0)} Z`
      : '';
  const gradId = `fill-${project.id}`;

  const startX = x(start);
  const todayX = x(today);
  const endX = end ? x(end) : null;
  const paceIsVertical = end && start >= end;
  const paceLine =
    end && !paceIsVertical
      ? { x1: x(start), y1: y(0), x2: x(end), y2: y(100) }
      : null;

  // X-axis labels: start, deadline, today — skip overlaps
  const labels = [];
  const pushLabel = (d, text, prefer) => {
    if (!d) return;
    const px = x(d);
    if (labels.some(l => Math.abs(l.px - px) < 48)) return;
    labels.push({ px, text, prefer });
  };
  pushLabel(start, fmt(start), 'start');
  if (end) pushLabel(end, fmt(end), 'end');
  if (dayKey(today) !== dayKey(start) && (!end || dayKey(today) !== dayKey(end))) {
    pushLabel(today, 'Today', 'today');
  }

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      style={{ width: '100%', height: 'auto', display: 'block' }}
      role="img"
      aria-label={`${project.name}: ${currentPct}% done, target pace ${project.pace_pct}%`}
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.22" />
          <stop offset="55%" stopColor={color} stopOpacity="0.08" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>

      {[0, 25, 50, 75, 100].map(v => (
        <g key={v}>
          <line
            x1={L}
            y1={y(v)}
            x2={W - R}
            y2={y(v)}
            stroke={GRID}
            strokeWidth="1"
            strokeDasharray={v === 0 || v === 100 ? '0' : '3 5'}
          />
          <text
            x={L - 10}
            y={y(v) + 4}
            fontSize="11"
            textAnchor="end"
            fill={GREY}
            fontFamily="inherit"
          >
            {v}%
          </text>
        </g>
      ))}

      <line x1={L} y1={y(0)} x2={W - R} y2={y(0)} stroke={GRID} strokeWidth="1.5" />

      {area && <path d={area} fill={`url(#${gradId})`} />}

      {paceLine && (
        <line
          x1={paceLine.x1}
          y1={paceLine.y1}
          x2={paceLine.x2}
          y2={paceLine.y2}
          stroke={GREY}
          strokeWidth="1.75"
          strokeDasharray="6 4"
          opacity="0.9"
        />
      )}
      {paceIsVertical && endX != null && (
        <line
          x1={endX}
          y1={y(0)}
          x2={endX}
          y2={y(100)}
          stroke={GREY}
          strokeWidth="1.75"
          strokeDasharray="6 4"
          opacity="0.9"
        />
      )}

      {pts.length > 1 && (
        <polyline
          points={coords.join(' ')}
          fill="none"
          stroke={color}
          strokeWidth="2.75"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      )}

      {/* Only intermediate dots when they sit on distinct days */}
      {pts.slice(0, -1).map((pt, i) => (
        <circle key={i} cx={x(pt.d)} cy={y(pt.pct)} r="3.5" fill={color} opacity="0.9">
          <title>{`${fmt(pt.d)}: ${pt.pct}% done`}</title>
        </circle>
      ))}

      {lastPt && (
        <g>
          <circle
            cx={x(lastPt.d)}
            cy={y(lastPt.pct)}
            r="6"
            fill={color}
            stroke="#fff"
            strokeWidth="2.5"
          >
            <title>{`Today: ${currentPct}% done`}</title>
          </circle>
          <text
            x={x(lastPt.d)}
            y={lastPt.pct > 82 ? y(lastPt.pct) + 22 : y(lastPt.pct) - 12}
            fontSize="13"
            fontWeight="700"
            fill={color}
            textAnchor={
              x(lastPt.d) > W - 80 ? 'end' : x(lastPt.d) < L + 40 ? 'start' : 'middle'
            }
            fontFamily="inherit"
          >
            {currentPct}%
          </text>
        </g>
      )}

      {labels.map(l => (
        <text
          key={l.text + l.px}
          x={l.px}
          y={H - 12}
          fontSize="11"
          fill={GREY}
          textAnchor={l.px < L + 30 ? 'start' : l.px > W - 70 ? 'end' : 'middle'}
          fontFamily="inherit"
        >
          {l.text}
        </text>
      ))}

      {(paceLine || paceIsVertical) && (
        <text
          x={
            paceIsVertical
              ? Math.max(L + 4, (endX ?? W - R) - 6)
              : Math.min((endX ?? W - R) - 4, W - R - 4)
          }
          y={y(100) - 8}
          fontSize="11"
          fontWeight="600"
          fill={GREY}
          textAnchor={paceIsVertical && (endX ?? 0) < L + 80 ? 'start' : 'end'}
          fontFamily="inherit"
        >
          Target pace
        </text>
      )}
    </svg>
  );
}

function statusText(project) {
  const flag = project.status_flag;
  if (flag === 'done') return { text: 'Done', color: '#159947' };
  if (flag === 'overdue') {
    const d = project.days_left != null ? -project.days_left : null;
    return {
      text: d != null ? `Overdue by ${plural(d, 'day')}` : 'Overdue',
      color: RED,
    };
  }
  if (flag === 'behind') {
    return {
      text: project.gap != null ? `Behind by ${project.gap} pts` : 'Behind',
      color: RED,
    };
  }
  if (flag === 'at_risk') {
    return {
      text: project.gap != null ? `At risk (−${project.gap} pts)` : 'At risk',
      color: '#D97706',
    };
  }
  if (flag === 'no_deadline') return { text: 'No deadline', color: GREY };
  return { text: 'On track', color: BLUE };
}

function ProjectPaceChart({ projects }) {
  const all = projects || [];
  const tracked = all
    .filter(p => p.created_at)
    .sort((a, b) => (b.gap ?? -999) - (a.gap ?? -999));
  const untracked = all.filter(p => !p.created_at);

  const [selectedId, setSelectedId] = useState(null);
  const selected = tracked.find(p => p.id === selectedId) || tracked[0] || null;

  const status = selected ? statusText(selected) : null;
  let daysNote = '';
  if (selected?.target_date) {
    const dl = diffDays(todayDate(), parse(selected.target_date));
    if (selected.status_flag !== 'done' && selected.status_flag !== 'overdue') {
      daysNote =
        dl > 0
          ? ` · ${plural(dl, 'day')} left`
          : dl === 0
            ? ' · Due today'
            : ` · ${plural(-dl, 'day')} overdue`;
    }
  }

  return (
    <div className="insight-card">
      <h3>Project pace</h3>

      {!selected ? (
        <p className="insight-note" style={{ marginTop: 8 }}>
          No active projects to chart yet.
        </p>
      ) : (
        <>
          {tracked.length > 1 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, margin: '12px 0 2px' }}>
              {tracked.map(p => {
                const active = p.id === selected.id;
                const isBehind =
                  p.status_flag === 'behind' ||
                  p.status_flag === 'overdue' ||
                  p.status_flag === 'at_risk';
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setSelectedId(p.id)}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 7,
                      cursor: 'pointer',
                      font: 'inherit',
                      fontSize: 13,
                      fontWeight: 600,
                      padding: '6px 14px',
                      borderRadius: 999,
                      color: active ? '#fff' : NAVY,
                      background: active ? NAVY : 'transparent',
                      border: `1.5px solid ${active ? NAVY : 'var(--light-blue-border, #c5d4e8)'}`,
                    }}
                  >
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: isBehind ? RED : BLUE,
                      }}
                    />
                    {p.name}
                  </button>
                );
              })}
            </div>
          )}

          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              flexWrap: 'wrap',
              gap: 8,
              margin: '12px 0 4px',
            }}
          >
            <div style={{ fontSize: 17, fontWeight: 700, color: NAVY }}>{selected.name}</div>
            <div style={{ fontSize: 13, color: 'var(--body-text-muted, #5a6b7d)' }}>
              <strong style={{ color: status.color }}>{status.text}</strong>
              {daysNote}
            </div>
          </div>

          <Chart project={selected} />
        </>
      )}

      {untracked.length > 0 && (
        <p className="insight-note" style={{ marginTop: 10 }}>
          Not shown (no start date): {untracked.map(p => p.name).join(', ')}.
        </p>
      )}
    </div>
  );
}

export default ProjectPaceChart;