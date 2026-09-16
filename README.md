# InsiteFuel V3

**InsiteFuel V3** is a web-based fuel management and operational tracking system built around a **Project → Site → Vessel** hierarchy.

It provides a centralized interface for managing sites and vessels, recording fuel activity, handling fuel transfers, collecting soundings, tracking shift-level operational data, and maintaining an auditable workflow around fuel operations.

The application is designed for deployment on an internal Windows server and uses **FastAPI**, **PostgreSQL**, **SQLAlchemy**, **Alembic**, **Uvicorn**, and **PM2**.

---

## Table of Contents

- [Overview](#overview)
- [Key Concepts](#key-concepts)
- [Core Features](#core-features)
- [Application Architecture](#application-architecture)
- [Project Structure](#project-structure)
- [Technology Stack](#technology-stack)
- [Database](#database)
- [Shift Management](#shift-management)
- [Fuel Management](#fuel-management)
- [Fuel Transfers](#fuel-transfers)
- [Transfer Notes](#transfer-notes)
- [Soundings](#soundings)
- [Advancement and Dredging Hours](#advancement-and-dredging-hours)
- [Attachments](#attachments)
- [Audit Trail](#audit-trail)
- [Frontend](#frontend)
- [Backend](#backend)
- [Authentication and Users](#authentication-and-users)
- [Migrations](#migrations)
- [Configuration](#configuration)
- [Running Locally](#running-locally)
- [Windows Server Deployment](#windows-server-deployment)
- [PM2](#pm2)
- [Application URL](#application-url)
- [Updating the Server](#updating-the-server)
- [Database Backups](#database-backups)
- [Troubleshooting](#troubleshooting)
- [Development Guidelines](#development-guidelines)
- [Important Design Rules](#important-design-rules)
- [Future Development](#future-development)

---

# Overview

InsiteFuel V3 is intended to provide a structured system for managing fuel operations across marine projects.

The central hierarchy is:

```text
Project
   │
   └── Site
        │
        └── Vessel
             │
             └── Shifts
                  │
                  ├── Fuel Activity
                  ├── Soundings
                  ├── Attachments
                  ├── Advancement
                  └── Dredging Hours
```

The system separates operational entities from workflow and audit information.

The application is designed so that fuel-related operations can be recorded against the correct project, site, vessel, shift, and transfer.

---

# Key Concepts

## Project

A project represents the top-level operational grouping.

Projects contain one or more sites.

```text
Project
├── Site A
├── Site B
└── Site C
```

---

## Site

A site belongs to a project and represents a specific operational location.

Sites can contain multiple vessels.

```text
Project A
│
├── Site 1
│   ├── Vessel A
│   └── Vessel B
│
└── Site 2
    ├── Vessel C
    └── Vessel D
```

---

## Vessel

A vessel belongs to a site.

Vessels have a vessel type, which is important for certain operational rules.

One important vessel type is:

```text
Dredger
```

Dredgers have additional shift-level requirements such as:

- Advancement
- Dredging hours

These values are required when closing a Dredger shift.

---

## Shift

A shift represents an operational period for a vessel.

A shift can contain operational records such as:

- Fuel transactions
- Soundings
- Transfer relationships
- Transfer-related notes
- Attachments
- Advancement
- Dredging hours

Shifts have a lifecycle and must satisfy required validation before they can be closed.

---

# Core Features

The current system includes the following major areas:

### Site and Vessel Management

- Project → Site → Vessel hierarchy
- Site master management
- Vessel-to-site relationships
- Vessel type information

### Shift Management

- Shift creation
- Shift status management
- Shift-level operational data
- Shift close validation

### Fuel Management

- Fuel recording
- Fuel balances
- Fuel transfers
- Approval workflow
- Balance updates

### Soundings

- Shift-specific soundings
- Image attachment support
- Minimum and maximum sounding limits
- Deadline/status tracking
- Shift-close enforcement

### Transfer Notes

- Notes attached to completed fuel transfers
- Minimum and maximum note limits
- Transfer-specific attachment storage
- Shift-close enforcement

### Operational Data

- Advancement in meters
- Dredging hours
- Dredger-specific validation

### Attachments

- Generic attachment handling
- Shift attachments
- Transfer attachments
- Image-based operational records

### Audit

- User/action tracking
- Entity-level audit records
- Old/new values for supported updates

---

# Application Architecture

The application follows a conventional FastAPI backend + browser frontend architecture.

```text
                        Client Browser
                              │
                              │ HTTP
                              ▼
                     FastAPI / Uvicorn
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
           Routes          Services         Schemas
              │               │
              │               ▼
              │             Models
              │               │
              └───────────────┤
                              ▼
                         SQLAlchemy
                              │
                              ▼
                         PostgreSQL
```

The frontend communicates with the backend through API routes.

---

# Technology Stack

## Backend

- Python
- FastAPI
- Uvicorn
- SQLAlchemy
- Pydantic
- Pydantic Settings
- Alembic
- psycopg

## Database

- PostgreSQL

## Frontend

- HTML
- CSS
- JavaScript

## Server Process Management

- PM2
- Windows
- `start.bat`

---

# Project Structure

The main project structure is:

```text
InsiteFuel/
│
├── backend/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── dependencies.py
│   │
│   ├── models/
│   │
│   ├── routes/
│   │
│   ├── schemas/
│   │
│   ├── services/
│   │
│   ├── migrations/
│   │
│   ├── seed/
│   │
│   ├── tests/
│   │
│   └── utils/
│
├── frontend/
│   ├── index.html
│   └── js/
│       └── app.js
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

# Backend

The backend entry point is:

```text
backend/main.py
```

The FastAPI application object is:

```text
backend.main:app
```

This is important when starting Uvicorn.

Correct:

```powershell
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8010
```

Incorrect:

```powershell
python -m uvicorn main:app
```

The latter assumes that `main.py` exists in the project root.

---

# Backend Organization

The backend is separated into several logical areas.

## `backend/routes/`

Contains API route definitions.

Routes are responsible for:

- Receiving HTTP requests
- Validating request dependencies
- Calling services
- Returning responses
- Translating expected application errors into HTTP responses

Business logic should generally remain in services rather than being duplicated inside routes.

---

## `backend/services/`

Contains application/business logic.

Examples of service responsibilities include:

- Shift operations
- Fuel operations
- Transfer workflows
- Sounding operations
- Attachment handling
- Audit logging

Services are the preferred location for validation that is part of the application's business rules.

---

## `backend/models/`

Contains SQLAlchemy database models.

Models represent persistent database entities and relationships.

---

## `backend/schemas/`

Contains Pydantic request and response schemas.

Schemas define the structure of API input/output data.

---

## `backend/database.py`

Contains database connection/session configuration.

The application uses SQLAlchemy with PostgreSQL.

---

## `backend/config.py`

Contains application settings loaded using Pydantic Settings.

InsiteFuel intentionally uses the `INSITEFUEL_` environment variable prefix.

For example:

```env
INSITEFUEL_DATABASE_URL=postgresql+psycopg://postgres:password@localhost:5432/insitefuel_v3
```

This avoids conflicts with global environment variables used by other applications on the same Windows server.

---

# Database

The application uses PostgreSQL.

The expected application database is:

```text
insitefuel_v3
```

A typical connection string is:

```text
postgresql+psycopg://postgres:PASSWORD@localhost:5432/insitefuel_v3
```

The actual password should be stored in `.env`, not in source control.

---

# Shift Management

Shifts are central to the operational workflow.

A shift has a status, with `OPEN` being the state in which operational information can be entered or modified.

Certain records and validations are tied directly to the shift.

The system validates shift requirements before allowing a shift to close.

---

# Fuel Management

Fuel operations are associated with the appropriate operational entities and shifts.

The system supports fuel transfers between operational parties/shifts.

Fuel-related workflows should be handled through the existing service and route layers rather than directly modifying database state from the frontend.

---

# Fuel Transfers

Fuel transfers have a defined workflow.

The transfer lifecycle includes:

```text
INITIATED
    ↓
RECEIVING_CONFIRMED
    ↓
MANAGER_REVIEW
    ↓
APPROVED
    ↓
BALANCES_UPDATED
```

The exact workflow rules are implemented in the backend services.

A transfer reaching:

```text
BALANCES_UPDATED
```

means that the transfer has completed the balance-update stage.

---

# Transfer Notes

Transfer notes are used to document completed fuel transfers.

A completed transfer can have:

- Minimum: 1 transfer note
- Maximum: 5 transfer notes

Transfer notes are linked to the transfer through the transfer attachment relationship.

The transfer note system does **not** block:

- Manager Review
- Transfer Approval

The requirement is enforced when the related shift is closed.

## Shift-close rule

If an `OPEN` shift is associated with a completed transfer:

```text
status = BALANCES_UPDATED
```

then the shift cannot close until that transfer has at least one transfer note.

The system checks completed transfers where the shift is either:

```text
from_shift_id
```

or:

```text
to_shift_id
```

and verifies the number of associated transfer notes.

---

# Soundings

Soundings are shift-specific operational records.

Each shift must have:

```text
Minimum: 1 sounding
Maximum: 5 soundings
```

A shift cannot be closed without at least one sounding.

The backend enforces these rules.

Soundings can include image attachments.

---

## Sounding Deadline

Sounding status is associated with a configured deadline.

The application uses the project's timezone-aware time utilities when creating and comparing timestamps.

The configured deadline is represented by:

```text
SOUNDING_DEADLINE_HOUR
SOUNDING_DEADLINE_MINUTE
```

The application currently uses:

```text
Asia/Kolkata
```

for its IST time utility.

Timezone-aware datetimes should be used consistently when working with sounding timestamps and deadlines.

---

# Advancement and Dredging Hours

Shift records support two operational values:

```text
advancement_m
dredging_hours
```

Both are nullable at the database level.

## Advancement

Represents operational advancement in meters.

Example:

```text
12.50
```

Negative advancement is not permitted.

---

## Dredging Hours

Represents dredging operating time in decimal hours.

Example:

```text
8.50
```

Negative dredging hours are not permitted.

---

## Dredger Validation

For vessels whose exact vessel type is:

```text
Dredger
```

both values are required before the shift can be closed:

```text
advancement_m
dredging_hours
```

For non-Dredger vessels, these fields remain optional.

The current requirement is based on the exact vessel type:

```text
Dredger
```

These fields are currently operational records only.

They should **not** be used to modify existing Production calculations unless that is explicitly implemented as a future feature.

---

# Attachments

The application has a generic attachment system used by operational records.

Attachments can be associated with relevant entities such as shifts and transfers.

The system also supports transfer-specific attachments for transfer notes.

---

## Transfer Attachments

Transfer attachments are associated with:

```text
FuelTransfer
```

through the transfer attachment relationship.

The transfer note implementation supports a maximum of five notes per transfer.

Duplicate note/attachment restrictions and other validation are handled by the backend service.

---

# Audit Trail

Important operational updates are recorded through the audit system.

Audited operations can include:

- Shift updates
- Shift operational data updates
- Sounding operations
- Transfer note operations
- Other business-critical changes

Audit records can include:

```text
user
action
entity
entity_id
old_values
new_values
details
```

The audit trail should be preserved when implementing new business-critical mutations.

---

# Frontend

The frontend is a browser-based interface.

The main frontend files include:

```text
frontend/index.html
frontend/js/app.js
```

The frontend communicates with FastAPI API endpoints.

---

# Application URL

The FastAPI application listens on port:

```text
8010
```

The frontend is served under:

```text
/ui
```

Therefore, the normal application URL is:

```text
http://SERVER_IP:8010/ui
```

For example:

```text
http://192.168.1.110:8010/ui
```

## Important

The `/ui` path is required to open the InsiteFuel frontend.

This:

```text
http://SERVER_IP:8010
```

is not the normal frontend URL.

Use:

```text
http://SERVER_IP:8010/ui
```

---

# Authentication and Users

The backend includes authentication/dependency handling and user-related functionality.

The application supports role-based operational access.

Current role identifiers used by the application include:

```text
site_accounts
general_manager
project_director
senior_accountant
accounts_manager
admin
```

Access to particular operations should be enforced through the existing authentication and authorization mechanisms.

Do not bypass backend authorization simply because a frontend control is hidden.

---

# Configuration

The application uses environment-based configuration.

A typical `.env` contains:

```env
APP_NAME=InsiteFuel V3
DEBUG=true
INSITEFUEL_DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/insitefuel_v3
```

Other application settings may also be configured through environment variables.

---

## `.env` vs `.env.example`

`.env.example` is a template intended for source control.

`.env` contains server-specific configuration.

Do not commit the real `.env` file if it contains passwords or secrets.

---

## Environment Variable Isolation

Do not modify a Windows-wide environment variable named:

```text
DATABASE_URL
```

just to configure InsiteFuel.

Other applications on the same server may depend on it.

Use:

```text
INSITEFUEL_DATABASE_URL
```

for InsiteFuel.

---

# Migrations

Database schema changes are managed using Alembic.

After obtaining the source code and configuring the database:

```powershell
alembic upgrade head
```

To see the current migration:

```powershell
alembic current
```

To view migration history:

```powershell
alembic history
```

---

## Creating a Migration

When a model/database change is intentionally introduced, create an Alembic migration.

Typical workflow:

```powershell
alembic revision --autogenerate -m "describe the change"
```

Then inspect the generated migration before applying it.

Apply it with:

```powershell
alembic upgrade head
```

Never assume that changing a SQLAlchemy model automatically changes the existing production database.

The migration must be created and applied.

---

# Running Locally

From the project root:

```powershell
cd D:\InsiteFuel
```

Activate the virtual environment:

```powershell
.venv\Scripts\activate
```

Start FastAPI:

```powershell
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8010
```

Open:

```text
http://127.0.0.1:8010/ui
```

---

# Using start.bat

The repository contains:

```text
start.bat
```

It changes to the project directory, activates the virtual environment, and starts the FastAPI application.

It can be run with:

```powershell
.\start.bat
```

The startup command uses:

```text
backend.main:app
```

as the FastAPI application.

---

# Windows Server Deployment

The recommended server environment is:

```text
Windows Server PC
    │
    ├── PostgreSQL
    │      └── insitefuel_v3
    │
    └── PM2
           │
           └── InsiteFuel
                  │
                  └── start.bat
                         │
                         └── Uvicorn
                                │
                                └── backend.main:app
```

The application listens on:

```text
0.0.0.0:8010
```

and is accessed through:

```text
http://SERVER_IP:8010/ui
```

For detailed installation instructions, see:

```text
SETUP.md
```

---

# PM2

PM2 is used to keep InsiteFuel running as a background server process.

The current deployment starts the repository's `start.bat` through Windows `cmd.exe`.

Example:

```powershell
pm2 start C:\Windows\System32\cmd.exe --name InsiteFuel --cwd D:\InsiteFuel -- /c D:\InsiteFuel\start.bat
```

---

## Check PM2

```powershell
pm2 status
```

Expected:

```text
InsiteFuel    online
```

---

## View InsiteFuel Logs

```powershell
pm2 logs InsiteFuel
```

Or:

```powershell
pm2 logs InsiteFuel --lines 50
```

---

## Monitor PM2

```powershell
pm2 monit
```

---

## Save PM2 Processes

After confirming that InsiteFuel is running:

```powershell
pm2 save
```

This saves the current PM2 process list.

---

# Updating the Server

The server installation is based on the GitHub repository.

Typical update process:

```powershell
cd D:\InsiteFuel
```

Check the working tree:

```powershell
git status
```

Pull the latest version:

```powershell
git pull origin main
```

If dependencies changed:

```powershell
.venv\Scripts\activate
pip install -r requirements.txt
```

Apply database migrations:

```powershell
alembic upgrade head
```

Restart the application:

```powershell
pm2 restart InsiteFuel
```

Check:

```powershell
pm2 status
```

Then inspect:

```powershell
pm2 logs InsiteFuel --lines 50
```

---

# Updating Safely

Before updating a server installation:

1. Check `git status`.
2. Make sure server-specific `.env` is not being overwritten.
3. Review migration changes.
4. Back up the database before significant schema changes.
5. Pull the new source.
6. Install changed dependencies.
7. Run migrations.
8. Restart PM2.
9. Check logs.
10. Test the frontend through `/ui`.

---

# Database Backups

The PostgreSQL database contains operational data and should be backed up regularly.

Example backup:

```powershell
pg_dump -U postgres -d insitefuel_v3 -F c -f insitefuel_backup.dump
```

Example restore:

```powershell
pg_restore -U postgres -d insitefuel_v3 insitefuel_backup.dump
```

For real deployments, backups should use an appropriate storage location and retention policy.

---

# Windows Firewall

The application uses TCP port:

```text
8010
```

If the application works on the server but cannot be accessed from another computer on the LAN, check Windows Firewall.

Run CMD/PowerShell as Administrator:

```cmd
netsh advfirewall firewall add rule name="InsiteFuel V3" dir=in action=allow protocol=TCP localport=8010
```

Then access:

```text
http://SERVER_IP:8010/ui
```

---

# Troubleshooting

## PM2 shows `errored`

Check:

```powershell
pm2 logs InsiteFuel --lines 50
```

Do not immediately recreate the process without checking the actual error.

---

## `Could not import module "main"`

If you see:

```text
ERROR: Error loading ASGI app.
Could not import module "main".
```

the application entry point is:

```text
backend.main:app
```

not:

```text
main:app
```

Use the repository's `start.bat` or start Uvicorn with:

```powershell
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8010
```

---

## `ERR_CONNECTION_REFUSED`

Check:

```powershell
pm2 status
```

If InsiteFuel is not online:

```powershell
pm2 logs InsiteFuel --lines 50
```

Also check whether port `8010` is listening:

```powershell
netstat -ano | findstr :8010
```

---

## Application works locally but not from another PC

Check:

```powershell
ipconfig
```

Confirm the server IP.

Confirm Uvicorn is listening on:

```text
0.0.0.0:8010
```

Check Windows Firewall.

Then access:

```text
http://SERVER_IP:8010/ui
```

---

## Database connection problems

Check the application configuration:

```powershell
python -c "from backend.config import settings; print(settings.database_url)"
```

It should point to:

```text
insitefuel_v3
```

Also verify that PostgreSQL is running.

---

## Migration problems

Check the current migration:

```powershell
alembic current
```

View migration history:

```powershell
alembic history
```

Do not manually modify production tables to work around a migration problem without understanding the migration state.

---

# Development Guidelines

## Keep Business Logic in Services

Routes should generally coordinate requests and responses.

Business rules should be implemented in the appropriate service layer.

This helps keep the application consistent when the same operation is triggered from different API endpoints.

---

## Validate on the Backend

Frontend validation is useful for user experience but should not be treated as security or business-rule enforcement.

Important rules must be enforced by the backend.

Examples include:

- Shift close requirements
- Sounding limits
- Transfer note limits
- Transfer workflow transitions
- Dredger shift requirements
- Negative value validation
- Authorization

---

## Preserve Audit Logging

When adding important state-changing operations, use the existing audit service where appropriate.

Audit information should make it possible to understand:

- Who changed something
- What was changed
- Which entity was affected
- Previous values
- New values
- Why/what operation occurred when appropriate

---

## Use Database Migrations

Never rely on SQLAlchemy model changes alone for schema changes.

If a database model changes:

```text
Model change
    ↓
Alembic migration
    ↓
Review migration
    ↓
alembic upgrade head
```

---

# Important Design Rules

These rules are particularly important when modifying InsiteFuel.

## 1. Project → Site → Vessel hierarchy

Maintain the established hierarchy:

```text
Project
    ↓
Site
    ↓
Vessel
```

Do not introduce alternate ownership paths without a specific design requirement.

---

## 2. Do not modify Production calculations casually

Advancement and dredging hours are currently operational shift data.

They should not automatically be incorporated into existing Production calculations.

Any future change to Production calculations should be treated as a separate feature.

---

## 3. Dredger requirement is exact

The Dredger-specific shift-close requirement is based on the exact vessel type:

```text
Dredger
```

Do not silently broaden this rule to unrelated vessel types.

---

## 4. Soundings are shift-specific

Soundings belong to shifts.

The current requirements are:

```text
Minimum 1
Maximum 5
```

A shift cannot close without at least one sounding.

---

## 5. Transfer notes are transfer-specific

Transfer notes belong to completed transfers.

The current limits are:

```text
Minimum 1
Maximum 5
```

They are required for shift closure after a transfer reaches:

```text
BALANCES_UPDATED
```

They do not block Manager Review or Approval.

---

## 6. Do not remove existing attachment functionality unnecessarily

The existing generic/shift attachment functionality may support other workflows.

Adding transfer attachments should not require removing unrelated attachment types.

---

## 7. Do not modify global server configuration unnecessarily

Other applications may run on the same Windows server.

Avoid changing global environment variables when an application-specific setting can be used.

InsiteFuel uses:

```text
INSITEFUEL_
```

environment variable names for this reason.

---

# Future Development

The application can be extended as new operational requirements are identified.

Areas that may be developed further include:

- Dashboard enhancements
- Fuel consumption analytics
- Additional operational reporting
- Improved document/export functionality
- Additional approval workflows
- More comprehensive server deployment automation
- Automated database backup procedures
- Deployment bundles

---

# Dashboard Considerations

Planned dashboard functionality includes fuel-related operational information such as:

- Transfer In
- Average Fuel Consumption (L/hr)
- Date-range weighted fuel consumption calculations

These calculations should be implemented without unintentionally changing the underlying Production workflow.

---

# Deployment Documentation

For complete server installation instructions, use:

```text
SETUP.md
```

The setup document covers:

- Installing prerequisites
- Cloning from GitHub
- Creating the virtual environment
- Installing dependencies
- Creating PostgreSQL database
- Configuring `.env`
- Running Alembic migrations
- Testing the application
- Windows Firewall
- PM2 deployment
- PM2 persistence
- Server troubleshooting

---

# Quick Reference

## Clone

```powershell
git clone <GITHUB_REPOSITORY_URL> InsiteFuel
cd InsiteFuel
```

## Virtual environment

```powershell
python -m venv .venv
.venv\Scripts\activate
```

## Dependencies

```powershell
pip install -r requirements.txt
```

## Database migration

```powershell
alembic upgrade head
```

## Manual start

```powershell
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8010
```

## Start script

```powershell
.\start.bat
```

## PM2 start

```powershell
pm2 start C:\Windows\System32\cmd.exe --name InsiteFuel --cwd D:\InsiteFuel -- /c D:\InsiteFuel\start.bat
```

## PM2 status

```powershell
pm2 status
```

## PM2 logs

```powershell
pm2 logs InsiteFuel --lines 50
```

## Save PM2

```powershell
pm2 save
```

## Frontend

```text
http://SERVER_IP:8010/ui
```

Example:

```text
http://192.168.1.110:8010/ui
```

---

# Current Production Deployment

The current Windows server deployment follows this pattern:

```text
Windows Server PC
│
├── PostgreSQL
│   └── insitefuel_v3
│
└── PM2
    │
    └── InsiteFuel
        │
        └── start.bat
            │
            └── Python virtual environment
                │
                └── Uvicorn
                    │
                    └── backend.main:app
                        │
                        └── Port 8010
                            │
                            └── /ui
```

The frontend is therefore accessed through:

```text
http://SERVER_IP:8010/ui
```

---

# Repository Documentation

The repository should contain at least:

```text
README.md
SETUP.md
```

`README.md` provides the project overview, architecture, features, design rules, and developer reference.

`SETUP.md` provides the step-by-step instructions for installing and deploying the application from GitHub.

---

# End of README
