import { useState } from 'react';

function Sidebar({ page, setPage }) {
  const [expanded, setExpanded] = useState(() => {
    try {
      return localStorage.getItem('qa_sidebar_expanded') === 'true';
    } catch {
      return false;
    }
  });

  function toggleExpanded() {
    setExpanded(prev => {
      const next = !prev;
      try {
        localStorage.setItem('qa_sidebar_expanded', String(next));
      } catch {
        // ignore storage errors, expansion still works for this session
      }
      return next;
    });
  }

  return (
    <div className={`sidebar ${expanded ? 'expanded' : ''}`}>
      <button
        className="sidebar-toggle"
        onClick={toggleExpanded}
        aria-expanded={expanded}
        aria-label={expanded ? 'Collapse sidebar' : 'Expand sidebar'}
        title={expanded ? 'Collapse' : 'Expand'}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </button>

      <div className="sidebar-nav">
        <div
          className={`sidebar-icon ${page === 'dashboard' ? 'active' : ''}`}
          onClick={() => setPage('dashboard')}
          title="Dashboard"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
            <polyline points="9 22 9 12 15 12 15 22"/>
          </svg>
          <span className={`sidebar-label ${expanded ? 'visible' : ''}`}>Dashboard</span>
        </div>

        <div
          className={`sidebar-icon ${page === 'modules' ? 'active' : ''}`}
          onClick={() => setPage('modules')}
          title="Features"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
            <rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>
          </svg>
          <span className={`sidebar-label ${expanded ? 'visible' : ''}`}>Features</span>
        </div>

        <div
          className={`sidebar-icon ${page === 'projects' ? 'active' : ''}`}
          onClick={() => setPage('projects')}
          title="Projects"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
          <span className={`sidebar-label ${expanded ? 'visible' : ''}`}>Projects</span>
        </div>

        <div
          className={`sidebar-icon ${page === 'defects' ? 'active' : ''}`}
          onClick={() => setPage('defects')}
          title="Defects"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"/>
            <line x1="15" y1="9" x2="9" y2="15"/>
            <line x1="9" y1="9" x2="15" y2="15"/>
          </svg>
          <span className={`sidebar-label ${expanded ? 'visible' : ''}`}>Defects</span>
        </div>

        <div
          className={`sidebar-icon ${page === 'trends' ? 'active' : ''}`}
          onClick={() => setPage('trends')}
          title="Trends"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
          </svg>
          <span className={`sidebar-label ${expanded ? 'visible' : ''}`}>Trends</span>
        </div>

        <div
          className={`sidebar-icon ${page === 'tasks' ? 'active' : ''}`}
          onClick={() => setPage('tasks')}
          title="Tasks"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <path d="M9 12l2 2 4-4"/>
          </svg>
          <span className={`sidebar-label ${expanded ? 'visible' : ''}`}>Tasks</span>
        </div>
      </div>

      <div className="sidebar-footer">
        <div
          className={`sidebar-icon ${page === 'profile' ? 'active' : ''}`}
          onClick={() => setPage('profile')}
          title="Profile"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="8" r="4"/>
            <path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>
          </svg>
          <span className={`sidebar-label ${expanded ? 'visible' : ''}`}>Profile</span>
        </div>
      </div>
    </div>
  );
}

export default Sidebar;