# Stray Animal Rescue and Adoption Management System

A Flask + PostgreSQL database management project for CIS 104. It provides a public adoption catalogue and rescue-report form, plus a protected admin area for managing animal records, applications, and rescue reports.

## Features

- Public home page, searchable animal catalogue, and animal detail pages
- Adoption application workflow
- Public stray-animal rescue reporting form
- Admin login with Werkzeug password hashing and session-based access control
- Admin CRUD for animal records
- Adoption application review and rescue-report status updates
- PostgreSQL relational tables with primary keys, foreign keys, constraints, and parameterized SQL
- Render deployment blueprint and `/health` endpoint

## Database entities

- `admins`
- `animals`
- `adopters`
- `adoption_applications`
- `rescue_reports`
- `medical_records`

## Run locally

Requires Python 3.11+ and PostgreSQL.

1. Create a PostgreSQL database.
2. In a terminal, set environment variables:

   **PowerShell**
   ```powershell
   $env:DATABASE_URL="postgresql://USER:PASSWORD@localhost:5432/stray_rescue"
   $env:SECRET_KEY="replace-with-a-long-random-secret"
   $env:ADMIN_USERNAME="rescueadmin"
   $env:ADMIN_PASSWORD="use-a-unique-password-at-least-12-characters"
   ```

   **macOS/Linux**
   ```bash
   export DATABASE_URL="postgresql://USER:PASSWORD@localhost:5432/stray_rescue"
   export SECRET_KEY="replace-with-a-long-random-secret"
   export ADMIN_USERNAME="rescueadmin"
   export ADMIN_PASSWORD="use-a-unique-password-at-least-12-characters"
   ```

3. Install and initialize:
   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate
   # macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   flask --app app init-db
   flask --app app create-admin
   flask --app app run
   ```
4. Open `http://127.0.0.1:5000`.

## Deploy to Render

1. Upload this project to a GitHub repository.
2. In Render, choose **New + → Blueprint** and connect the repository containing `render.yaml`.
3. Review the blueprint before applying it. It provisions a PostgreSQL database and web service. Check current Render pricing/plan availability before deploying; database plans and free allowances can change.
4. When prompted for `ADMIN_USERNAME` and `ADMIN_PASSWORD`, enter a unique admin username and a strong password of at least 12 characters. Set a strong, unique `SECRET_KEY` if you override the generated one.
5. After deployment, open the service Shell or use a one-off command to create the admin account:
   ```bash
   flask --app app create-admin
   ```
   The command reads `ADMIN_USERNAME` and `ADMIN_PASSWORD` from the service environment and hashes the password before storing it. Run again to update the password.
6. Visit `/admin/login` on the deployed website.

## Important notes

- Never commit `.env` files, database passwords, or real personal data to GitHub.
- Set a strong unique admin password and secret key in Render environment settings.
- This starter does not include email notifications, file uploads, CSRF protection, or rate limiting. Add these before using it with real users or sensitive personal data.
- The medical-record table is included for the database design; a medical-record management UI can be added as a future enhancement.
- Use only sample/demo data for classroom testing unless you have permission to store real applicants' information.
