import { useState, useEffect } from 'react';
import { authFetch } from '../utils/auth';
import { formatDate } from "../utils/formatDate";

const taskColumns = ['To Do', 'In Progress', 'Done'];

function TasksPage() {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    authFetch('/api/tasks')
      .then(res => res.json())
      .then(data => {
        setTasks(data);
        setLoading(false);
      })
      .catch(() => {
        setError('Could not load tasks.');
        setLoading(false);
      });
  }, []);

  return (
    <>
      <div className="page-header">
        <div>
          <div className="brand">SEDAYU ONE</div>
          <h1>Tasks</h1>
        </div>
      </div>

      {loading && <div className="placeholder"><p>Loading tasks.</p></div>}
      {error && <div className="placeholder"><p>{error}</p></div>}

      {!loading && !error && (
        <div className="board">
          {taskColumns.map(col => (
            <div key={col} className="board-column">
              <div className="board-column-header">
                {col}
                <span className="board-count">
                  {tasks.filter(t => t.column_name === col).length}
                </span>
              </div>
              {tasks.filter(t => t.column_name === col).map(t => (
                <div key={t.id} className="task-card">
                  <div className="task-title">{t.title}</div>
                  <div className="task-tags">
                    <span className="label-tag">{t.label}</span>
                    <span className="due-date">Due {formatDate(t.due_date)}</span>
                  </div>
                  <div className="task-meta">
                    <span className={`priority priority-${t.priority.toLowerCase()}`}>{t.priority}</span>
                    <span className="assignee-tag">{t.assignee}</span>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </>
  );
}

export default TasksPage;