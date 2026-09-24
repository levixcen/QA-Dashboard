import { useState, useEffect, useCallback } from 'react';
import './index.css';
import Sidebar from './components/Sidebar';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import ModulesPage from './pages/FeaturesPage';
import ProjectsPage from './pages/ProjectsPage';
import DefectsPage from './pages/DefectsPage';
import TrendsPage from './pages/TrendsPage';
import TasksPage from './pages/TasksPage';
import ProfilePage from './pages/ProfilePage';
import { isAuthenticated, getUsername, logout, authFetch } from './utils/auth';
import { PeriodProvider, usePeriod } from './context/PeriodContext';

function mergeModuleMeta(modules, metaRows) {
  const metaByModule = {};
  for (const row of metaRows) {
    metaByModule[row.module] = row;
  }
  return modules.map(m => ({ ...m, meta: metaByModule[m.name] || null }));
}

function AppContent() {
  const { period } = usePeriod();
  const [authenticated, setAuthenticated] = useState(isAuthenticated());
  const [username, setUsername] = useState(getUsername());
  const [page, setPage] = useState('dashboard');
  const [modules, setModules] = useState([]);
  const [overallStats, setOverallStats] = useState(null);
  const [generatedAt, setGeneratedAt] = useState(null);
  const [loaded, setLoaded] = useState(false);

  const fetchSummary = useCallback(async () => {
    if (!authenticated) return;

    const query = period ? `?month=${period}` : '';

    try {
      const res = await authFetch(`/api/reports/summary${query}`);
      if (!res.ok) throw new Error('Could not load summary');
      const data = await res.json();

      let metaRows = [];
      try {
        const metaRes = await authFetch('/api/module-meta');
        if (metaRes.ok) {
          metaRows = await metaRes.json();
        }
      } catch (err) {
      }

      setModules(mergeModuleMeta(data.modules || [], metaRows));
      setOverallStats(data.overall || null);
      setGeneratedAt(data.generated_at || null);
      setLoaded(true);
    } catch (err) {
      setModules([]);
      setOverallStats(null);
      setGeneratedAt(null);
      setLoaded(true);
    }
  }, [authenticated, period]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  async function handleUpdateModuleMeta(moduleName, patch) {
    const res = await authFetch(`/api/module-meta/${encodeURIComponent(moduleName)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to save changes');
    }

    const updated = await res.json();
    setModules(prev =>
      prev.map(m => (m.name === moduleName ? { ...m, meta: updated } : m))
    );
  }

  function handleLogin(loggedInUsername) {
    setUsername(loggedInUsername);
    setAuthenticated(true);
  }

  function handleLogout() {
    logout();
    setAuthenticated(false);
    setUsername(null);
    setPage('dashboard');
  }

  if (!authenticated) {
    return <LoginPage onLogin={handleLogin} />;
  }

  return (
    <div className="app">
      <Sidebar page={page} setPage={setPage} />

      <div className="main-content">
        {page === 'dashboard' && (
          <DashboardPage
            modules={modules}
            loaded={loaded}
            generatedAt={generatedAt}
            overallStats={overallStats}
            onUpdateModuleMeta={handleUpdateModuleMeta}
            username={username}
          />
        )}
        {page === 'modules' && (
          <ModulesPage
            modules={modules}
            onFeaturesChanged={fetchSummary}
            username={username}
          />
        )}
        {page === 'projects' && <ProjectsPage username={username} />}
        {page === 'defects' && <DefectsPage username={username} />}
        {page === 'trends' && <TrendsPage username={username} />}
        {page === 'tasks' && <TasksPage username={username} />}
        {page === 'profile' && (
          <ProfilePage username={username} onLogout={handleLogout} />
        )}
      </div>
    </div>
  );
}

function App() {
  return (
    <PeriodProvider>
      <AppContent />
    </PeriodProvider>
  );
}

export default App;