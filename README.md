# Hospital Appointment Booking System

A Flask web app where patients book, reschedule and cancel appointments, doctors manage
their working hours and daily schedule, and admins manage doctor accounts. It prevents
double booking in the application **and** in the database, and ships with a GitHub Actions
pipeline (tests on MySQL, linting, security scans, deployment).

## Run it in VS Code

**One-time setup**

1. Install [Python 3.12+](https://www.python.org/downloads/) (on Windows, tick *Add Python to PATH*), [VS Code](https://code.visualstudio.com/) and [Git](https://git-scm.com/).
2. Unzip the project, then in VS Code use **File → Open Folder** and pick `hospital-booking`.
   Accept the prompt to install the recommended extensions (Python, Ruff, GitHub Actions).
3. Open a terminal in VS Code (**Terminal → New Terminal**) and create a virtual environment:

   ```bash
   python -m venv .venv
   ```

   Activate it:

   | OS | Command |
   |---|---|
   | Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |
   | Windows (cmd) | `.venv\Scripts\activate.bat` |
   | macOS / Linux | `source .venv/bin/activate` |

   If PowerShell blocks the script, run `Set-ExecutionPolicy -Scope Process RemoteSigned` first.
   Then press **Ctrl+Shift+P → Python: Select Interpreter** and choose the `.venv` one.

4. Install the dependencies:

   ```bash
   pip install -r requirements-dev.txt
   ```

5. Create your settings file and set a secret key:

   ```bash
   copy .env.example .env        # Windows
   cp .env.example .env          # macOS / Linux
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

   Paste the printed value after `SECRET_KEY=` in `.env`. The default `DATABASE_URL`
   uses a local SQLite file, so nothing else is needed to get started.

6. Create the tables and your admin account (the password is prompted, never stored in code):

   ```bash
   flask --app run init-db
   flask --app run create-admin
   ```

7. Optional, for trying it out: load sample doctors, patients and bookings. You choose one
   password (at least 8 characters) that all demo accounts share:

   ```bash
   flask --app run seed-demo
   ```

   It prints the demo accounts, for example `demo.patient@example.com` and
   `meera.iyer@example.com` (a doctor). Use it on your own computer only, never on a real
   or public deployment.

**Every time**

- Press **F5** (the "Flask: run the app" configuration), or run `flask --app run run --debug`.
- Open http://127.0.0.1:5000.
- Log in as the admin, choose **Add a doctor**, then log in as that doctor and add **Working hours**.
  Register a patient account to book appointments.

## Tests, linting and security checks

```bash
pytest                      # 93 tests; also runnable from VS Code's Testing panel
ruff format .               # auto-format
ruff check .                # lint
flake8                      # style / syntax checks
pip install pip-audit && pip-audit -r requirements.txt   # known-vulnerability scan
```

## Using MySQL instead of SQLite

```sql
CREATE DATABASE hospital CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'hospital_user'@'localhost' IDENTIFIED BY 'choose-a-strong-password';
GRANT ALL PRIVILEGES ON hospital.* TO 'hospital_user'@'localhost';
```

Then set this in `.env` and run `flask --app run init-db` again:

```
DATABASE_URL=mysql+pymysql://hospital_user:choose-a-strong-password@localhost:3306/hospital
```

The tests use the same variable: with `DATABASE_URL` set they run against that database
(and **drop its tables**, so point it at a throwaway test database), otherwise they use
in-memory SQLite. CI sets it to a MySQL service container.

## GitHub Actions pipeline

`.github/workflows/ci.yml` runs on every push and pull request to `main`:

| Job | What it does |
|---|---|
| `lint` | `ruff format --check`, `ruff check`, `flake8` |
| `security` | `pip-audit` on `requirements.txt`, gitleaks secret scan |
| `test` | `pytest` against a temporary MySQL 8 container |
| `deploy` | on pushes to `main` only, after the three jobs above pass |

To turn it on:

1. Create a GitHub repository and push the project (`git init`, `git add .`, `git commit`, `git remote add origin ...`, `git push -u origin main`).
2. Host the app (for example a Render web service with build command `pip install -r requirements.txt && flask --app run init-db` and start command `gunicorn run:app`). Set `SECRET_KEY`, `DATABASE_URL` and `SESSION_COOKIE_SECURE=1` as environment variables on the host, not in the repo.
3. Add the host's deploy hook URL as a repository secret named `RENDER_DEPLOY_HOOK_URL` (Settings → Secrets and variables → Actions). Using another host? Replace the last step of the `deploy` job.
4. Optional but recommended: Settings → Branches → add a rule for `main` that requires the `lint`, `security` and `test` checks to pass before merging.

## How double booking is prevented

- **Application check:** every booking and reschedule verifies the time is a real slot in the doctor's working hours, is in the future, and does not overlap any live appointment (`app/services.py`).
- **Database check:** `appointments` has a unique constraint on `(doctor_id, slot_start)`. `slot_start` equals the start time while an appointment holds its slot and is set to `NULL` when it is cancelled, so cancelled rows never block a slot but two live bookings for the same start time can never both be saved, even if two requests race.

## Project layout

```
app/
  __init__.py      app factory, security headers, error pages
  models.py        User, Doctor, Availability, Appointment, Notification
  services.py      all booking rules (slots, book, cancel, reschedule, complete)
  security.py      role decorator, safe redirects, email check
  cli.py           flask init-db, create-admin, seed-demo
  demo.py          sample data used by seed-demo
  formatting.py    time and name formatting used by the templates
  routes/          auth, patient, doctor, admin, main (notifications)
  templates/, static/
tests/             services (rules) and web (forms, roles, redirects) tests
.github/workflows/ci.yml
.vscode/           settings, F5 launch config, extension recommendations
```

## Known limits and next steps

- Notifications are in-app only; sending email would be a natural next feature.
- Times are stored as the clinic's local time with no time zone handling.
- There is no login rate limiting or password reset yet.
- Tables are created with `flask init-db`; add Flask-Migrate once the schema starts changing.
- Two live appointments with *different* start times can only overlap if a doctor changes slot length while bookings exist; the application check rejects new overlaps, but that path is not protected by the database constraint.
