# InsiteFuel V3 — Setup Guide

This document explains how to set up InsiteFuel V3 from the GitHub repository on a Windows machine.

The application uses:

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Uvicorn
- PM2 (for server deployment)
- HTML/CSS/JavaScript frontend

---

# 1. Requirements

Install the following before setting up the application.

## Required

### Python

Python 3.11+ is recommended.

Verify:

```powershell
python --version
```

or:

```powershell
py --version
```

### PostgreSQL

Install PostgreSQL and make sure the PostgreSQL service is running.

Verify:

```powershell
psql --version
```

### Git

Verify:

```powershell
git --version
```

### Node.js / PM2

PM2 is required for server deployment.

Verify:

```powershell
node --version
npm --version
pm2 --version
```

PM2 can be installed globally if it is not already installed:

```powershell
npm install -g pm2
```

---

# 2. Clone the Repository

Choose the directory where the application should be installed.

For example:

```powershell
cd D:\
```

Clone the repository:

```powershell
git clone https://github.com/ShashankSP233/InsiteFuel_V3.git InsiteFuel
```

Enter the project:

```powershell
cd D:\InsiteFuel
```

Verify the files:

```powershell
dir
```

The project should contain files/directories similar to:

```text
backend/
frontend/
storage/
alembic.ini
requirements.txt
start.bat
.env.example
README.md
```

---

# 3. Create the Python Virtual Environment

From the project root:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\activate
```

After activation, the terminal should show:

```text
(.venv)
```

---

# 4. Install Python Dependencies

With the virtual environment activated:

```powershell
python -m pip install --upgrade pip
```

Then:

```powershell
pip install -r requirements.txt
```

Verify Uvicorn:

```powershell
python -m uvicorn --version
```

---

# 5. Create the PostgreSQL Database

Open PostgreSQL:

```powershell
psql -U postgres
```

Create the application database:

```sql
CREATE DATABASE insitefuel_v3;
```

Exit PostgreSQL:

```sql
\q
```

The database name must match the database configured in the application.

---

# 6. Configure Environment Variables

Copy the example environment file:

```powershell
copy .env.example .env
```

Open `.env`:

```powershell
notepad .env
```

Configure the database connection.

Example:

```env
APP_NAME=InsiteFuel V3
DEBUG=true

INSITEFUEL_DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/insitefuel_v3
```

Replace `YOUR_PASSWORD` with the PostgreSQL password.

## Important

Do **not** commit the real `.env` file to GitHub.

The `.env` file may contain passwords and other server-specific configuration.

Only `.env.example` should normally be committed.

---

# 7. Important: Environment Variable Isolation

InsiteFuel uses the `INSITEFUEL_` prefix for its environment variables.

For example:

```env
INSITEFUEL_DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/insitefuel_v3
```

This is intentional.

Some Windows machines may already have a global:

```text
DATABASE_URL
```

environment variable used by other applications.

Do **not** change the global `DATABASE_URL` just to configure InsiteFuel.

InsiteFuel should use:

```text
INSITEFUEL_DATABASE_URL
```

instead.

---

# 8. Verify the Application Configuration

From the project root:

```powershell
python -c "from backend.config import settings; print(settings.database_url)"
```

It should print the InsiteFuel PostgreSQL connection, for example:

```text
postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/insitefuel_v3
```

If it points to another database, stop and correct the configuration before continuing.

---

# 9. Run Database Migrations

InsiteFuel uses Alembic for database migrations.

From the project root run:

```powershell
alembic upgrade head
```

A successful migration should finish without errors.

To check the current migration:

```powershell
alembic current
```

To see migration history:

```powershell
alembic history
```

---

# 10. Start InsiteFuel Manually

Before configuring PM2, verify that the application works.

From the project root:

```powershell
.venv\Scripts\activate
```

Then:

```powershell
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8010
```

The FastAPI server will start on port `8010`.

## Open the Frontend

The InsiteFuel frontend is served under the `/ui` route.

From the server itself:

```text
http://127.0.0.1:8010/ui
```

From another computer on the same LAN:

```text
http://SERVER_IP:8010/ui
```

For example:

```text
http://192.168.1.110:8010/ui
```

**Important:** Opening only:

```text
http://SERVER_IP:8010
```

does not open the InsiteFuel frontend.

Use:

```text
http://SERVER_IP:8010/ui
```

to access the application interface.

---

# 11. Using start.bat

The repository contains:

```text
start.bat
```

The startup script starts the FastAPI application.

From the project directory:

```powershell
.\start.bat
```

The application uses:

```text
backend.main:app
```

as its FastAPI application entry point.

---

# 12. Windows Firewall

If the application works locally but cannot be accessed from another computer on the LAN, Windows Firewall may be blocking port `8010`.

Run PowerShell/CMD as Administrator:

```cmd
netsh advfirewall firewall add rule name="InsiteFuel V3" dir=in action=allow protocol=TCP localport=8010
```

Then access:

```text
http://SERVER_IP:8010/ui
```

---

# 13. PM2 Deployment

For a server installation, PM2 can keep InsiteFuel running in the background and restart it if the process exits.

The recommended PM2 setup uses the repository's `start.bat`.

## Remove an old InsiteFuel PM2 process

If an InsiteFuel process already exists:

```powershell
pm2 delete InsiteFuel
```

This is only necessary if an old or broken process already exists.

## Start InsiteFuel with PM2

From any directory:

```powershell
pm2 start C:\Windows\System32\cmd.exe --name InsiteFuel --cwd D:\InsiteFuel -- /c D:\InsiteFuel\start.bat
```

If the project is installed somewhere other than `D:\InsiteFuel`, replace the paths accordingly.

---

# 14. Check PM2

Run:

```powershell
pm2 status
```

You should see:

```text
InsiteFuel    online
```

View application logs:

```powershell
pm2 logs InsiteFuel
```

View the last 50 lines:

```powershell
pm2 logs InsiteFuel --lines 50
```

---

# 15. Save the PM2 Configuration

Once InsiteFuel is confirmed to be working:

```powershell
pm2 save
```

This saves the current PM2 process list.

Check the current processes:

```powershell
pm2 list
```

---

# 16. PM2 Monitoring

To view a live PM2 monitoring dashboard:

```powershell
pm2 monit
```

To view logs from all PM2 applications:

```powershell
pm2 logs
```

PM2 applications do not require an open terminal window to keep running.

The terminal can be closed after PM2 has started the applications.

---

# 17. Testing the Server

## Local frontend test

On the server, open:

```text
http://127.0.0.1:8010/ui
```

## LAN frontend test

From another computer on the same network:

```text
http://SERVER_IP:8010/ui
```

Example:

```text
http://192.168.1.110:8010/ui
```

## PM2 test

```powershell
pm2 status
```

Expected:

```text
InsiteFuel    online
```

## Logs

```powershell
pm2 logs InsiteFuel --lines 50
```

There should be no repeated startup/import errors.

---

# 18. Updating an Existing Installation

When new code is pushed to GitHub, update the server from the project directory:

```powershell
cd D:\InsiteFuel
```

Check the current state:

```powershell
git status
```

Pull the latest code:

```powershell
git pull origin main
```

If dependencies changed:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
```

Run any new database migrations:

```powershell
alembic upgrade head
```

Restart InsiteFuel:

```powershell
pm2 restart InsiteFuel
```

Check:

```powershell
pm2 status
```

Then:

```powershell
pm2 logs InsiteFuel --lines 50
```

---

# 19. Important Server Configuration

Some configuration is specific to each server.

Do not blindly overwrite:

```text
.env
```

when updating from GitHub.

The `.env` file contains server-specific settings such as:

- Database password
- Database connection
- Other deployment-specific configuration

The Git repository should contain:

```text
.env.example
```

rather than the real server `.env`.

---

# 20. Database Backups

The PostgreSQL database contains the application's operational data.

Before significant database changes or migrations, create a PostgreSQL backup.

Example:

```powershell
pg_dump -U postgres -d insitefuel_v3 -F c -f insitefuel_backup.dump
```

Restore example:

```powershell
pg_restore -U postgres -d insitefuel_v3 insitefuel_backup.dump
```

Use an appropriate backup location and retention policy for the server.

---

# 21. Troubleshooting

## Error: Could not import module "main"

If PM2 shows:

```text
ERROR: Error loading ASGI app.
Could not import module "main".
```

The correct application module is:

```text
backend.main:app
```

not:

```text
main:app
```

The PM2 command should use `start.bat`, which uses:

```text
backend.main:app
```

---

## Browser shows ERR_CONNECTION_REFUSED

Check whether InsiteFuel is running:

```powershell
pm2 status
```

If it is stopped or errored:

```powershell
pm2 logs InsiteFuel --lines 50
```

You can also test the application manually:

```powershell
cd D:\InsiteFuel
.venv\Scripts\activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8010
```

---

## Application works on the server but not from another PC

Check:

1. Server IP address
2. Windows Firewall
3. Port `8010`
4. Uvicorn host is `0.0.0.0`

Check the server IP:

```powershell
ipconfig
```

The application should be started with:

```text
--host 0.0.0.0 --port 8010
```

Then access the frontend using:

```text
http://SERVER_IP:8010/ui
```

---

## Database connection errors

Verify:

```powershell
python -c "from backend.config import settings; print(settings.database_url)"
```

Make sure it points to:

```text
insitefuel_v3
```

and not another PostgreSQL database.

Also verify PostgreSQL is running.

---

# 22. Project Structure

The important project structure is:

```text
InsiteFuel/
│
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── dependencies.py
│   ├── models/
│   ├── routes/
│   ├── schemas/
│   ├── services/
│   ├── migrations/
│   ├── seed/
│   ├── tests/
│   └── utils/
│
├── frontend/
│   ├── index.html
│   └── js/
│
├── storage/
│
├── .env
├── .env.example
├── .gitignore
├── alembic.ini
├── requirements.txt
├── start.bat
├── README.md
└── SETUP.md
```

---

# 23. Quick Setup Checklist

For a new Windows server:

```text
[ ] Install Python
[ ] Install PostgreSQL
[ ] Install Git
[ ] Install Node.js
[ ] Install PM2
[ ] Clone GitHub repository
[ ] Create Python virtual environment
[ ] Install requirements.txt
[ ] Create PostgreSQL database
[ ] Create/configure .env
[ ] Verify database configuration
[ ] Run alembic upgrade head
[ ] Test Uvicorn manually
[ ] Configure Windows Firewall
[ ] Start using PM2
[ ] Verify PM2 status
[ ] Run pm2 save
[ ] Test frontend at /ui from another LAN computer
```

---

# 24. Production Notes

For a production/server installation:

- Do not commit `.env`.
- Do not expose PostgreSQL unnecessarily to the network.
- Keep regular database backups.
- Run database migrations before starting code that depends on them.
- Check PM2 logs after deployments.
- Keep the server's `.env` separate from Git-managed files.
- Do not change global Windows environment variables used by other applications.
- Use `backend.main:app` as the FastAPI application entry point.
- PM2 should manage the running application process.
- Access the InsiteFuel frontend through `/ui`.

---

# 25. Current Deployment Architecture

The intended Windows server architecture is:

```text
                    Windows Server
                         │
              ┌──────────┴──────────┐
              │                     │
             PM2              PostgreSQL
              │                     │
              │              insitefuel_v3
              │
         InsiteFuel
              │
        start.bat
              │
           Uvicorn
              │
       backend.main:app
              │
          Port 8010
              │
       ┌──────┴──────┐
       │             │
    Frontend      FastAPI
       │
      /ui
```

The application frontend can be accessed from the LAN using:

```text
http://SERVER_IP:8010/ui
```

Example:

```text
http://192.168.1.110:8010/ui
```

---

# End of Setup Guide
