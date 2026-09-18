import { useState, useEffect } from 'react';
import './index.css';
import Sidebar from './components/sidebar';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import ModulesPage from './pages/FeaturesPage';
import ProjectsPage from './pages/ProjectsPage';
import DefectsPage from './pages/DefectsPage';
import TrendsPage from './pages/TrendsPage';
import TasksPage from './pages/TasksPage';
import ProfilePage from './pages/ProfilePage';
import { isAuthenticated, getUsername, logout } from './utils/auth';
import { withNotStarted } from './utils/mergeModules';

function App() {
  const [authenticated, setAuthenticated] = useState(isAuthenticated());
  const [username, setUsername] = useState(getUsername());
  const [page, setPage] = useState('dashboard');
  const [modules, setModules] = useState([]);
  const [generatedAt, setGeneratedAt] = useState(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!authenticated) return;

    fetch('/dashboard_data.json')
      .then(res => {
        if (!res.ok) throw new Error('No dashboard_data.json found yet');
        return res.json();
      })
      .then(data => {
        setModules(withNotStarted(data.modules || []));
        setGeneratedAt(data.generated_at || null);
        setLoaded(true);
      })
      .catch(() => {
        setModules([]);
        setGeneratedAt(null);
        setLoaded(true);
      });
  }, [authenticated]);

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
          <DashboardPage modules={modules} loaded={loaded} generatedAt={generatedAt} />
        )}
        {page === 'modules' && <ModulesPage modules={modules} />}
        {page === 'projects' && <ProjectsPage />}
        {page === 'defects' && <DefectsPage />}
        {page === 'trends' && <TrendsPage />}
        {page === 'tasks' && <TasksPage />}
        {page === 'profile' && (
          <ProfilePage username={username} onLogout={handleLogout} />
        )}
      </div>
    </div>
  );
}

export default App;

