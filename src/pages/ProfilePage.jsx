function ProfilePage({ username, onLogout }) {
  function handleLogout() {
    try {
      localStorage.removeItem('qa_token');
      localStorage.removeItem('token');
      localStorage.removeItem('qa_username');
    } catch {
    }
    if (typeof onLogout === 'function') onLogout();
  }

  return (
    <div className="login-screen profile-logout-screen">
      <div className="logout-content">
        <p className="logout-label">Signed in as</p>
        <h1 className="logout-username">{username || 'User'}</h1>
        <button className="btn btn-primary" type="button" onClick={handleLogout}>
          Sign out
        </button>
      </div>

      <img
        className="login-logo"
        src="/logos/main-logo-white.png"
        alt="Sedayu One"
      />
    </div>
  );
}

export default ProfilePage;