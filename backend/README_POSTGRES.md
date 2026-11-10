# Moving the QA Dashboard from SQLite to PostgreSQL

Written 4 Nov 2026. Read this before copying any file.

## What is in this folder

| File | Goes to | What changed |
| --- | --- | --- |
| database.py | backend/database.py | Rewritten for PostgreSQL (connection pool, schema, the executions view, indexes) |
| parse_allure.py | parse_allure.py in the project root, same place as now | Writes to PostgreSQL, finds the backend folder by itself (no more PYTHONPATH) |
| main.py | backend/main.py | Eight small edits, listed at the bottom, so you can apply them by hand |
| migrate_sqlite_to_postgres.py | backend/migrate_sqlite_to_postgres.py | New. One time copy of your current data |

reports.py, auth.py, timeutil.py and google_auth.py do not change.

Before anything else, keep copies of your current files so you can go back:

    cp backend/database.py backend/database.sqlite.py
    cp backend/main.py backend/main.sqlite.py
    cp parse_allure.py parse_allure.sqlite.py
    cp qa_dashboard.db qa_dashboard.db.before-postgres

(Run each as one line from the qa-dashboard folder.) Your SQLite file is never changed by the new code.

## Step 1: create the database (Neon)

1. Go to neon.tech and sign up (no card needed for the free plan).
2. Create a project called qa-dashboard. Pick the region closest to Jakarta (Singapore).
3. On the project page click Connect. Copy the connection string. It looks like:
   postgresql://user:password@ep-something-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
4. It contains a password. Do not paste it in chat, in code, or in git.

Supabase works the same way: Project Settings, Database, copy the connection string (use the "Transaction pooler" one).

## Step 2: tell the app where the database is

Add one line to ~/.zshrc, with your real string between the quotes:

    export DATABASE_URL="postgresql://...your string..."

Then open a new terminal window, so it picks the line up. Check it with:

    echo $DATABASE_URL

## Step 3: install the database package (once)

From the backend folder:

    pip install "psycopg[binary,pool]"

## Step 4: copy the files

Copy the four files from the table above into place.

## Step 5: copy your data across (once)

Stop the backend first. From the backend folder, as one line:

    python migrate_sqlite_to_postgres.py

It reads ../qa_dashboard.db and prints a table of row counts per table, then compares the Executions totals per status. The last line must say "RESULT: all counts match". If it says SOME COUNTS DIFFER, do not switch over, send me the output.

It refuses to run if PostgreSQL already has data, so running it twice cannot create duplicates. If you need to start over, open the Neon SQL Editor and run:

    DROP SCHEMA public CASCADE; CREATE SCHEMA public;

then run the script again.

## Step 6: start the app

From the backend folder:

    uvicorn main:app --reload --port 8000

The first start creates the tables and the Executions view in PostgreSQL. Open the dashboard and check Features, Defects, Projects and Trends against what you saw before. Numbers should be the same.

## Step 7: importing Mario's results now

From the qa-dashboard folder:

    python parse_allure.py --input allure-results-26oct

PYTHONPATH=backend is no longer needed. The old delete step is now done in the Neon SQL Editor if you want to wipe results first:

    DELETE FROM attachments; DELETE FROM test_results;

## Screenshots and evidence files

Evidence images are still saved on your computer in backend/evidence. Only the database moved. When the backend moves to a shared server, that folder needs a persistent disk or object storage. That is a later step.

## Going back to SQLite

Stop the backend, copy the three .sqlite.py copies back over database.py, main.py and parse_allure.py, and start again. Your SQLite file still has everything up to the moment you switched. Anything entered after switching lives only in PostgreSQL.

## What changed for the many users goal

1. Connections come from a pool of 10, shared by all requests. Change it with DB_POOL_MAX.
2. Defect codes (DEF-001, ...) now come from a database sequence, so two people creating defects at the same moment can never get the same code.
3. The newest result per test (the executions view) is computed in one pass, so it stays fast with a large results table.
4. Two server processes can start at the same time without fighting over the schema.

## Two things that behave differently

1. The four sample projects (Support Feature Refinement and the others) are no longer planted when the projects table is empty. Your real projects are copied by the migration script.
2. Project cards are now always listed in the order they were created. The old code relied on SQLite's habit of doing this by accident.

## main.py edits (use these if you changed main.py after 19 Oct)

1. Replace the body of _next_defect_code with:

       cur.execute("SELECT nextval('defect_code_seq') AS n")
       n = cur.fetchone()["n"]
       return f"DEF-{n:03d}"

2. In both places that run INSERT INTO features (name, archived) VALUES (?, 0) (in _resolve_feature and in ingest_feature_entry), add ON CONFLICT (name) DO NOTHING at the end of the SQL text.
3. In list_features, change ORDER BY name COLLATE NOCASE to ORDER BY lower(name), name.
4. In list_projects, add ORDER BY id to both SELECT * FROM projects queries.
5. In list_module_tests, change both ORDER BY t.name to ORDER BY t.name, t.run_date, t.uuid.
6. Above the startup function add:

       @app.on_event("shutdown")
       def shutdown():
           from database import close_pool
           close_pool()