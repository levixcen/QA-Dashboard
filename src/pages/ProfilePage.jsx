function ProfilePage({ username, onLogout }) {
  return (
    <>
      <div className="page-header">
        <div>
          <div className="brand">SEDAYU ONE</div>
          <h1>Profile</h1>
        </div>
      </div>

      <div className="module-card" style={{ maxWidth: 360 }}>
        <div className="status-row">
          <span>Signed in as</span>
          <span style={{ color: '#1a2a3a', fontWeight: 700 }}>{username}</span>
        </div>

        <button className="btn btn-dark" onClick={onLogout} style={{ marginTop: 8 }}>
          Log out
        </button>
      </div>
    </>
  );
}

export default ProfilePage;