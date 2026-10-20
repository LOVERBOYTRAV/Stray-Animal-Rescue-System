import os
from datetime import date
from functools import wraps

import psycopg
from psycopg.rows import dict_row
from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-development-secret")
DATABASE_URL = os.environ.get("DATABASE_URL", "")


def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured. Add a PostgreSQL database in Render.")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                admin_id SERIAL PRIMARY KEY,
                username VARCHAR(80) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS animals (
                animal_id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                species VARCHAR(30) NOT NULL CHECK (species IN ('Dog','Cat','Other')),
                breed VARCHAR(100),
                sex VARCHAR(20) NOT NULL DEFAULT 'Unknown' CHECK (sex IN ('Male','Female','Unknown')),
                estimated_age VARCHAR(60),
                rescue_date DATE,
                rescue_location VARCHAR(200),
                health_status VARCHAR(40) NOT NULL DEFAULT 'Needs assessment'
                    CHECK (health_status IN ('Healthy','Under treatment','Needs assessment','Recovered')),
                description TEXT,
                image_url TEXT,
                adoption_status VARCHAR(30) NOT NULL DEFAULT 'Available'
                    CHECK (adoption_status IN ('Available','Pending','Adopted','Under care')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS adopters (
                adopter_id SERIAL PRIMARY KEY,
                full_name VARCHAR(120) NOT NULL,
                email VARCHAR(254) NOT NULL,
                phone VARCHAR(40) NOT NULL,
                address TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS adoption_applications (
                application_id SERIAL PRIMARY KEY,
                animal_id INTEGER NOT NULL REFERENCES animals(animal_id) ON DELETE RESTRICT,
                adopter_id INTEGER NOT NULL REFERENCES adopters(adopter_id) ON DELETE RESTRICT,
                reason TEXT NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'Pending'
                    CHECK (status IN ('Pending','Approved','Rejected','Completed')),
                application_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (animal_id, adopter_id, status)
            );
            CREATE TABLE IF NOT EXISTS rescue_reports (
                report_id SERIAL PRIMARY KEY,
                animal_id INTEGER REFERENCES animals(animal_id) ON DELETE SET NULL,
                reporter_name VARCHAR(120) NOT NULL,
                reporter_contact VARCHAR(100) NOT NULL,
                location TEXT NOT NULL,
                description TEXT NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'New'
                    CHECK (status IN ('New','In progress','Resolved')),
                report_date TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS medical_records (
                medical_id SERIAL PRIMARY KEY,
                animal_id INTEGER NOT NULL REFERENCES animals(animal_id) ON DELETE CASCADE,
                record_date DATE NOT NULL DEFAULT CURRENT_DATE,
                diagnosis TEXT NOT NULL,
                treatment TEXT,
                vaccination_status VARCHAR(80) NOT NULL DEFAULT 'Unknown',
                notes TEXT
            );
        """)
        conn.commit()


def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("admin_id"):
            flash("Please sign in to access the admin dashboard.", "warning")
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_globals():
    return {"current_year": date.today().year}


@app.route("/")
def index():
    with get_db() as conn:
        animals = conn.execute("""
            SELECT * FROM animals WHERE adoption_status = 'Available'
            ORDER BY created_at DESC LIMIT 6
        """).fetchall()
        stats = conn.execute("""
            SELECT COUNT(*) FILTER (WHERE adoption_status <> 'Adopted') AS in_care,
                   COUNT(*) FILTER (WHERE adoption_status = 'Available') AS available,
                   COUNT(*) FILTER (WHERE adoption_status = 'Adopted') AS adopted
            FROM animals
        """).fetchone()
    return render_template("index.html", animals=animals, stats=stats)


@app.route("/animals")
def animals():
    q = request.args.get("q", "").strip()[:100]
    species = request.args.get("species", "").strip()
    allowed_species = {"Dog", "Cat", "Other"}
    with get_db() as conn:
        sql = "SELECT * FROM animals WHERE adoption_status = 'Available'"
        params = []
        if species in allowed_species:
            sql += " AND species = %s"
            params.append(species)
        if q:
            sql += " AND (name ILIKE %s OR breed ILIKE %s OR rescue_location ILIKE %s)"
            params.extend([f"%{q}%"] * 3)
        sql += " ORDER BY created_at DESC"
        rows = conn.execute(sql, params).fetchall()
    return render_template("animals.html", animals=rows, q=q, species=species)


@app.route("/animal/<int:animal_id>")
def animal_detail(animal_id):
    with get_db() as conn:
        animal = conn.execute("SELECT * FROM animals WHERE animal_id=%s", (animal_id,)).fetchone()
    if not animal:
        flash("That animal profile could not be found.", "warning")
        return redirect(url_for("animals"))
    return render_template("animal_detail.html", animal=animal)


@app.route("/adopt/<int:animal_id>", methods=["GET", "POST"])
def adopt(animal_id):
    with get_db() as conn:
        animal = conn.execute("SELECT * FROM animals WHERE animal_id=%s", (animal_id,)).fetchone()
    if not animal or animal["adoption_status"] != "Available":
        flash("This animal is not currently available for adoption.", "warning")
        return redirect(url_for("animals"))
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        reason = request.form.get("reason", "").strip()
        if not all([name, email, phone, address, reason]) or "@" not in email:
            flash("Please complete all fields with a valid email address.", "error")
            return render_template("adopt.html", animal=animal)
        if len(name) > 120 or len(email) > 254 or len(phone) > 40 or len(address) > 2000 or len(reason) > 3000:
            flash("One or more fields are too long. Please shorten your response.", "error")
            return render_template("adopt.html", animal=animal)
        with get_db() as conn:
            adopter = conn.execute(
                "INSERT INTO adopters (full_name,email,phone,address) VALUES (%s,%s,%s,%s) RETURNING adopter_id",
                (name, email, phone, address)
            ).fetchone()
            conn.execute(
                "INSERT INTO adoption_applications (animal_id,adopter_id,reason) VALUES (%s,%s,%s)",
                (animal_id, adopter["adopter_id"], reason)
            )
            conn.execute("UPDATE animals SET adoption_status='Pending' WHERE animal_id=%s", (animal_id,))
        flash("Application received! Our team will review it and contact you.", "success")
        return redirect(url_for("animals"))
    return render_template("adopt.html", animal=animal)


@app.route("/report", methods=["GET", "POST"])
def report_rescue():
    if request.method == "POST":
        name = request.form.get("reporter_name", "").strip()
        contact = request.form.get("reporter_contact", "").strip()
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()
        if not all([name, contact, location, description]):
            flash("Please complete every field before submitting.", "error")
        elif max(map(len, [name, contact, location, description])) > 3000:
            flash("One or more fields are too long.", "error")
        else:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO rescue_reports (reporter_name,reporter_contact,location,description) VALUES (%s,%s,%s,%s)",
                    (name, contact, location, description)
                )
            flash("Thank you for reporting an animal in need. The rescue team has received your report.", "success")
            return redirect(url_for("report_rescue"))
    return render_template("report.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_id"):
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with get_db() as conn:
            admin = conn.execute("SELECT * FROM admins WHERE username=%s", (username,)).fetchone()
        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = admin["admin_id"]
            session["admin_username"] = admin["username"]
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect username or password.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout", methods=["POST"])
@login_required
def admin_logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("index"))


@app.route("/admin")
@login_required
def admin_dashboard():
    with get_db() as conn:
        stats = conn.execute("""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE adoption_status='Available') AS available,
                   COUNT(*) FILTER (WHERE adoption_status='Pending') AS pending,
                   COUNT(*) FILTER (WHERE adoption_status='Adopted') AS adopted
            FROM animals
        """).fetchone()
        applications = conn.execute("""
            SELECT aa.*, a.name AS animal_name, ad.full_name, ad.email, ad.phone
            FROM adoption_applications aa
            JOIN animals a ON a.animal_id=aa.animal_id
            JOIN adopters ad ON ad.adopter_id=aa.adopter_id
            ORDER BY aa.application_date DESC LIMIT 10
        """).fetchall()
        reports = conn.execute("SELECT * FROM rescue_reports ORDER BY report_date DESC LIMIT 8").fetchall()
    return render_template("admin_dashboard.html", stats=stats, applications=applications, reports=reports)


@app.route("/admin/animals")
@login_required
def admin_animals():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM animals ORDER BY created_at DESC").fetchall()
    return render_template("admin_animals.html", animals=rows)


@app.route("/admin/animals/new", methods=["GET", "POST"])
@app.route("/admin/animals/<int:animal_id>/edit", methods=["GET", "POST"])
@login_required
def animal_form(animal_id=None):
    with get_db() as conn:
        animal = conn.execute("SELECT * FROM animals WHERE animal_id=%s", (animal_id,)).fetchone() if animal_id else None
    if animal_id and not animal:
        flash("Animal record not found.", "warning")
        return redirect(url_for("admin_animals"))
    if request.method == "POST":
        fields = {
            "name": request.form.get("name", "").strip(),
            "species": request.form.get("species", ""),
            "breed": request.form.get("breed", "").strip(),
            "sex": request.form.get("sex", "Unknown"),
            "estimated_age": request.form.get("estimated_age", "").strip(),
            "rescue_date": request.form.get("rescue_date") or None,
            "rescue_location": request.form.get("rescue_location", "").strip(),
            "health_status": request.form.get("health_status", "Needs assessment"),
            "description": request.form.get("description", "").strip(),
            "image_url": request.form.get("image_url", "").strip(),
            "adoption_status": request.form.get("adoption_status", "Available")
        }
        valid = (
            fields["name"] and len(fields["name"]) <= 100
            and fields["species"] in {"Dog", "Cat", "Other"}
            and fields["sex"] in {"Male", "Female", "Unknown"}
            and fields["health_status"] in {"Healthy", "Under treatment", "Needs assessment", "Recovered"}
            and fields["adoption_status"] in {"Available", "Pending", "Adopted", "Under care"}
            and all(len(str(fields[k] or "")) <= limit for k, limit in [
                ("breed",100),("estimated_age",60),("rescue_location",200),
                ("description",5000),("image_url",2000)])
        )
        if not valid:
            flash("Please check required fields and allowed values.", "error")
            return render_template("animal_form.html", animal=fields, editing=bool(animal_id))
        with get_db() as conn:
            if animal_id:
                conn.execute("""
                    UPDATE animals SET name=%s,species=%s,breed=%s,sex=%s,estimated_age=%s,
                    rescue_date=%s,rescue_location=%s,health_status=%s,description=%s,image_url=%s,
                    adoption_status=%s WHERE animal_id=%s
                """, (*fields.values(), animal_id))
            else:
                conn.execute("""
                    INSERT INTO animals (name,species,breed,sex,estimated_age,rescue_date,rescue_location,
                    health_status,description,image_url,adoption_status)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, tuple(fields.values()))
        flash("Animal record saved successfully.", "success")
        return redirect(url_for("admin_animals"))
    return render_template("animal_form.html", animal=animal, editing=bool(animal_id))


@app.route("/admin/animals/<int:animal_id>/delete", methods=["POST"])
@login_required
def delete_animal(animal_id):
    with get_db() as conn:
        exists = conn.execute("SELECT animal_id FROM animals WHERE animal_id=%s", (animal_id,)).fetchone()
        if not exists:
            flash("Animal record not found.", "warning")
        else:
            linked = conn.execute("SELECT 1 FROM adoption_applications WHERE animal_id=%s LIMIT 1", (animal_id,)).fetchone()
            if linked:
                flash("This animal has application history and cannot be deleted. Change its status instead.", "warning")
            else:
                conn.execute("DELETE FROM animals WHERE animal_id=%s", (animal_id,))
                flash("Animal record deleted.", "success")
    return redirect(url_for("admin_animals"))


@app.route("/admin/applications/<int:application_id>/status", methods=["POST"])
@login_required
def update_application(application_id):
    status = request.form.get("status")
    if status not in {"Pending", "Approved", "Rejected", "Completed"}:
        flash("Invalid application status.", "error")
        return redirect(url_for("admin_dashboard"))
    with get_db() as conn:
        app_row = conn.execute("SELECT animal_id FROM adoption_applications WHERE application_id=%s", (application_id,)).fetchone()
        if not app_row:
            flash("Application not found.", "warning")
        else:
            conn.execute("UPDATE adoption_applications SET status=%s WHERE application_id=%s", (status, application_id))
            if status == "Completed":
                conn.execute("UPDATE animals SET adoption_status='Adopted' WHERE animal_id=%s", (app_row["animal_id"],))
            elif status == "Rejected":
                other_pending = conn.execute("""
                    SELECT 1 FROM adoption_applications
                    WHERE animal_id=%s AND status IN ('Pending','Approved') AND application_id<>%s LIMIT 1
                """, (app_row["animal_id"], application_id)).fetchone()
                if not other_pending:
                    conn.execute("UPDATE animals SET adoption_status='Available' WHERE animal_id=%s AND adoption_status='Pending'", (app_row["animal_id"],))
            elif status in {"Pending", "Approved"}:
                conn.execute("UPDATE animals SET adoption_status='Pending' WHERE animal_id=%s AND adoption_status<>'Adopted'", (app_row["animal_id"],))
            flash("Application status updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/reports/<int:report_id>/status", methods=["POST"])
@login_required
def update_report(report_id):
    status = request.form.get("status")
    if status not in {"New", "In progress", "Resolved"}:
        flash("Invalid report status.", "error")
    else:
        with get_db() as conn:
            conn.execute("UPDATE rescue_reports SET status=%s WHERE report_id=%s", (status, report_id))
        flash("Rescue report updated.", "success")
    return redirect(url_for("admin_dashboard"))


@app.cli.command("create-admin")
def create_admin():
    """Create an admin using ADMIN_USERNAME and ADMIN_PASSWORD environment variables."""
    username = os.environ.get("ADMIN_USERNAME", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not username or len(password) < 12:
        raise SystemExit("Set ADMIN_USERNAME and ADMIN_PASSWORD (at least 12 characters) before running this command.")
    with get_db() as conn:
        existing = conn.execute("SELECT admin_id FROM admins WHERE username=%s", (username,)).fetchone()
        if existing:
            conn.execute("UPDATE admins SET password_hash=%s WHERE username=%s", (generate_password_hash(password), username))
            print("Admin password updated.")
        else:
            conn.execute("INSERT INTO admins (username,password_hash) VALUES (%s,%s)", (username, generate_password_hash(password)))
            print("Admin account created.")


@app.cli.command("init-db")
def init_db_command():
    init_db()
    print("Database tables are ready.")


@app.route("/health")
def health():
    try:
        with get_db() as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "database": "connected"}, 200
    except Exception:
        return {"status": "error", "database": "unavailable"}, 503


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
