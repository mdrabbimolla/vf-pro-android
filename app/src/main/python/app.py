
import os, sqlite3, secrets, re
from datetime import date, datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.environ.get("APP_DATA_DIR", os.path.dirname(__file__)))
os.makedirs(BASE_DIR, exist_ok=True)
DB_PATH = os.path.join(BASE_DIR, "visit_followup.db")
SECRET_FILE = os.path.join(BASE_DIR, ".secret_key")

def load_secret():
    env_secret = os.environ.get("APP_SECRET_KEY")
    if env_secret:
        return env_secret
    if os.path.exists(SECRET_FILE):
        return open(SECRET_FILE, "r", encoding="utf-8").read().strip()
    value = secrets.token_urlsafe(48)
    with open(SECRET_FILE, "w", encoding="utf-8") as f:
        f.write(value)
    try:
        os.chmod(SECRET_FILE, 0o600)
    except OSError:
        pass
    return value

app = Flask(__name__)
app.config.update(SECRET_KEY=load_secret(), SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE","0")=="1", PERMANENT_SESSION_LIFETIME=timedelta(days=14))

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT NOT NULL UNIQUE,
      full_name TEXT NOT NULL,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL CHECK(role IN ('admin','staff')),
      active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS visits (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      client_name TEXT NOT NULL,
      phone TEXT NOT NULL,
      project TEXT DEFAULT '',
      visit_date TEXT NOT NULL,
      visit_time TEXT NOT NULL DEFAULT '09:00',
      purpose TEXT DEFAULT '',
      notes TEXT DEFAULT '',
      created_by INTEGER NOT NULL REFERENCES users(id),
      created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS followups (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      client_name TEXT NOT NULL,
      phone TEXT NOT NULL,
      project TEXT DEFAULT '',
      due_date TEXT NOT NULL,
      due_time TEXT NOT NULL DEFAULT '09:00',
      details TEXT DEFAULT '',
      status TEXT NOT NULL DEFAULT 'Pending'
        CHECK(status IN ('Pending','Completed','Cancelled')),
      created_by INTEGER NOT NULL REFERENCES users(id),
      created_at TEXT NOT NULL,
      completed_at TEXT
    );
    CREATE TABLE IF NOT EXISTS projects (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL UNIQUE,
      active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_visits_date ON visits(visit_date);
    CREATE INDEX IF NOT EXISTS idx_followups_due ON followups(due_date, status);
    """)
    # Safe schema migrations for scheduled reminder times.
    visit_columns = [row[1] for row in conn.execute("PRAGMA table_info(visits)").fetchall()]
    if "visit_time" not in visit_columns:
        conn.execute("ALTER TABLE visits ADD COLUMN visit_time TEXT NOT NULL DEFAULT '09:00'")
    followup_columns = [row[1] for row in conn.execute("PRAGMA table_info(followups)").fetchall()]
    if "due_time" not in followup_columns:
        conn.execute("ALTER TABLE followups ADD COLUMN due_time TEXT NOT NULL DEFAULT '09:00'")

    # Safe schema migration: remember the Visit created from each Follow-up.
    columns = [row[1] for row in conn.execute("PRAGMA table_info(followups)").fetchall()]
    if "converted_visit_id" not in columns:
        conn.execute("ALTER TABLE followups ADD COLUMN converted_visit_id INTEGER")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_followups_converted_visit ON followups(converted_visit_id) WHERE converted_visit_id IS NOT NULL")

    # Preserve project names already used in older records.
    existing = conn.execute("SELECT DISTINCT project FROM visits UNION SELECT DISTINCT project FROM followups").fetchall()
    for row in existing:
        name = (row[0] or "").strip()
        if name:
            conn.execute("INSERT OR IGNORE INTO projects(name, created_at) VALUES(?,?)", (name, datetime.now().isoformat(timespec="seconds")))
    conn.commit()
    conn.close()

def login_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapped

def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            flash("এই কাজটি শুধু Admin করতে পারবেন।", "error")
            return redirect(url_for("dashboard"))
        return fn(*args, **kwargs)
    return wrapped

@app.template_filter("wa_number")
def wa_number(value):
    return re.sub(r"\D", "", value or "")

@app.context_processor
def inject_globals():
    return {"today": date.today().isoformat()}

@app.route("/healthz")
def healthz():
    return {"status": "ok", "app": "V&F Pro"}, 200

@app.route("/sw.js")
def service_worker():
    response = app.send_static_file("sw.js")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response

@app.route("/")
def home():
    return redirect(url_for("dashboard") if session.get("user_id") else url_for("login"))

@app.route("/setup", methods=["GET", "POST"])
def setup():
    count = db().execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count:
        return redirect(url_for("login"))
    if request.method == "POST":
        full_name = request.form.get("full_name","").strip()
        username = request.form.get("username","").strip().lower()
        password = request.form.get("password","")
        if not full_name or not username or len(password) < 8:
            flash("সব তথ্য দিন। পাসওয়ার্ড কমপক্ষে ৮ অক্ষরের হতে হবে।", "error")
        else:
            db().execute("INSERT INTO users(username,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                         (username, full_name, generate_password_hash(password), "admin", datetime.now().isoformat(timespec="seconds")))
            db().commit()
            flash("Admin account তৈরি হয়েছে। এখন লগইন করুন।", "success")
            return redirect(url_for("login"))
    return render_template("setup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if db().execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        return redirect(url_for("setup"))
    if request.method == "POST":
        username = request.form.get("username","").strip().lower()
        password = request.form.get("password","")
        user = db().execute("SELECT * FROM users WHERE username=? AND active=1", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["full_name"] = user["full_name"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        flash("ইউজারনেম অথবা পাসওয়ার্ড সঠিক নয়।", "error")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    conn = db()
    uid, role = session["user_id"], session["role"]
    scope = "" if role == "admin" else " WHERE created_by=?"
    params = () if role == "admin" else (uid,)
    visits = conn.execute("SELECT COUNT(*) FROM visits"+scope, params).fetchone()[0]
    today_visits = conn.execute("SELECT COUNT(*) FROM visits"+(" WHERE " if role=="admin" else " WHERE created_by=? AND ")+"visit_date=?",
                                ((date.today().isoformat(),) if role=="admin" else (uid,date.today().isoformat()))).fetchone()[0]
    fscope = "" if role=="admin" else " AND created_by=?"
    fp = () if role=="admin" else (uid,)
    pending = conn.execute("SELECT COUNT(*) FROM followups WHERE status='Pending'"+fscope, fp).fetchone()[0]
    due = conn.execute("SELECT COUNT(*) FROM followups WHERE status='Pending' AND due_date<=?"+fscope,
                       (date.today().isoformat(),)+fp).fetchone()[0]
    recent = conn.execute("SELECT v.*,u.full_name FROM visits v JOIN users u ON u.id=v.created_by"+
                          ("" if role=="admin" else " WHERE v.created_by=?")+" ORDER BY v.visit_date DESC,v.id DESC LIMIT 5", params).fetchall()
    due_items = conn.execute("SELECT * FROM followups WHERE status='Pending' AND due_date<=?"+fscope+
                             " ORDER BY due_date LIMIT 5", (date.today().isoformat(),)+fp).fetchall()
    return render_template("dashboard.html", visits=visits, today_visits=today_visits,
                           pending=pending, due=due, recent=recent, due_items=due_items, active="dashboard")

@app.route("/visits", methods=["GET","POST"])
@login_required
def visits():
    conn = db()
    if request.method == "POST":
        name=request.form.get("client_name","").strip()
        phone=request.form.get("phone","").strip()
        visit_date=request.form.get("visit_date","").strip()
        visit_time=request.form.get("visit_time","").strip()
        if not name or not phone or not visit_date or not visit_time:
            flash("ক্লায়েন্টের নাম, ফোন, ভিজিটের তারিখ ও সময় প্রয়োজন।","error")
        else:
            try:
                datetime.strptime(visit_date + " " + visit_time, "%Y-%m-%d %H:%M")
                conn.execute("""INSERT INTO visits(client_name,phone,project,visit_date,visit_time,purpose,notes,created_by,created_at)
                  VALUES(?,?,?,?,?,?,?,?,?)""",
                  (name,phone,request.form.get("project","").strip(),visit_date,visit_time,
                   request.form.get("purpose","").strip(),request.form.get("notes","").strip(),
                   session["user_id"],datetime.now().isoformat(timespec="seconds")))
            except ValueError:
                flash("সঠিক Visit তারিখ ও সময় নির্বাচন করুন।","error")
                return redirect(url_for("visits"))
            conn.commit()
            flash("Visit সংরক্ষণ হয়েছে।","success")
            return redirect(url_for("visits"))
    if session["role"]=="admin":
        rows=conn.execute("SELECT v.*,u.full_name FROM visits v JOIN users u ON u.id=v.created_by ORDER BY visit_date DESC,id DESC").fetchall()
    else:
        rows=conn.execute("SELECT v.*,u.full_name FROM visits v JOIN users u ON u.id=v.created_by WHERE created_by=? ORDER BY visit_date DESC,id DESC",(session["user_id"],)).fetchall()
    projects=conn.execute("SELECT name FROM projects WHERE active=1 ORDER BY name").fetchall()
    return render_template("visits.html", rows=rows, projects=projects, active="visits")

@app.route("/followups", methods=["GET","POST"])
@login_required
def followups():
    conn=db()
    if request.method=="POST":
        name=request.form.get("client_name","").strip()
        phone=request.form.get("phone","").strip()
        due_date=request.form.get("due_date","").strip()
        due_time=request.form.get("due_time","").strip()
        if not name or not phone or not due_date or not due_time:
            flash("ক্লায়েন্টের নাম, ফোন, Follow-up তারিখ ও সময় প্রয়োজন।","error")
        else:
            try:
                datetime.strptime(due_date + " " + due_time, "%Y-%m-%d %H:%M")
                conn.execute("""INSERT INTO followups(client_name,phone,project,due_date,due_time,details,status,created_by,created_at)
                  VALUES(?,?,?,?,?,?,'Pending',?,?)""",
                  (name,phone,request.form.get("project","").strip(),due_date,due_time,
                   request.form.get("details","").strip(),session["user_id"],datetime.now().isoformat(timespec="seconds")))
            except ValueError:
                flash("সঠিক Follow-up তারিখ ও সময় নির্বাচন করুন।","error")
                return redirect(url_for("followups"))
            conn.commit()
            flash("Follow-up সংরক্ষণ হয়েছে।","success")
            return redirect(url_for("followups"))
    if session["role"]=="admin":
        rows=conn.execute("SELECT f.*,u.full_name FROM followups f JOIN users u ON u.id=f.created_by ORDER BY CASE status WHEN 'Pending' THEN 0 ELSE 1 END,due_date").fetchall()
    else:
        rows=conn.execute("SELECT f.*,u.full_name FROM followups f JOIN users u ON u.id=f.created_by WHERE created_by=? ORDER BY CASE status WHEN 'Pending' THEN 0 ELSE 1 END,due_date",(session["user_id"],)).fetchall()
    projects=conn.execute("SELECT name FROM projects WHERE active=1 ORDER BY name").fetchall()
    return render_template("followups.html", rows=rows, projects=projects, active="followups")

@app.route("/followups/<int:item_id>/status", methods=["POST"])
@login_required
def update_followup(item_id):
    conn=db()
    item=conn.execute("SELECT * FROM followups WHERE id=?",(item_id,)).fetchone()
    if not item or (session["role"]!="admin" and item["created_by"]!=session["user_id"]):
        flash("রেকর্ড পাওয়া যায়নি বা অনুমতি নেই।","error")
    else:
        status=request.form.get("status")
        if status in ("Pending","Completed","Cancelled"):
            completed_at=datetime.now().isoformat(timespec="seconds") if status=="Completed" else None
            conn.execute("UPDATE followups SET status=?,completed_at=? WHERE id=?",(status,completed_at,item_id))
            conn.commit()
            flash("Follow-up status আপডেট হয়েছে।","success")
    return redirect(url_for("followups"))

@app.route("/followups/<int:item_id>/convert", methods=["POST"])
@login_required
def convert_followup(item_id):
    conn=db()
    item=conn.execute("SELECT * FROM followups WHERE id=?",(item_id,)).fetchone()
    if not item or (session["role"]!="admin" and item["created_by"]!=session["user_id"]):
        flash("রেকর্ড পাওয়া যায়নি বা অনুমতি নেই।", "error")
    elif item["converted_visit_id"]:
        flash("এই Follow-up থেকে Visit আগেই তৈরি হয়েছে।", "error")
    else:
        visit_date=request.form.get("visit_date","").strip() or date.today().isoformat()
        visit_time=request.form.get("visit_time","").strip() or item["due_time"]
        try:
            datetime.strptime(visit_date + " " + visit_time, "%Y-%m-%d %H:%M")
        except ValueError:
            flash("সঠিক Visit তারিখ ও সময় নির্বাচন করুন।", "error")
            return redirect(url_for("followups"))
        now=datetime.now().isoformat(timespec="seconds")
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur=conn.execute("""INSERT INTO visits(client_name,phone,project,visit_date,visit_time,purpose,notes,created_by,created_at)
                VALUES(?,?,?,?,?,?,?,?,?)""", (item["client_name"],item["phone"],item["project"],visit_date,visit_time,
                request.form.get("purpose","Follow-up থেকে Visit").strip(),
                request.form.get("notes",item["details"] or "").strip(),item["created_by"],now))
            visit_id=cur.lastrowid
            updated=conn.execute("UPDATE followups SET status='Completed', completed_at=COALESCE(completed_at,?), converted_visit_id=? WHERE id=? AND converted_visit_id IS NULL",
                                 (now,visit_id,item_id))
            if updated.rowcount != 1:
                conn.rollback()
                flash("এই Follow-up থেকে Visit তৈরি করা যায়নি। আবার চেষ্টা করুন।", "error")
            else:
                conn.commit()
                flash("Visit তৈরি হয়েছে। Follow-up রেকর্ড সংরক্ষিত আছে।", "success")
        except sqlite3.IntegrityError:
            conn.rollback()
            flash("এই Follow-up থেকে Visit আগেই তৈরি হয়েছে।", "error")
    return redirect(url_for("followups"))

@app.route("/visits/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_visit(item_id):
    conn=db(); item=conn.execute("SELECT * FROM visits WHERE id=?",(item_id,)).fetchone()
    if not item or (session["role"]!="admin" and item["created_by"]!=session["user_id"]):
        flash("রেকর্ড পাওয়া যায়নি বা অনুমতি নেই।", "error")
    else:
        conn.execute("UPDATE followups SET converted_visit_id=NULL WHERE converted_visit_id=?",(item_id,))
        conn.execute("DELETE FROM visits WHERE id=?",(item_id,)); conn.commit(); flash("Visit মুছে ফেলা হয়েছে।", "success")
    return redirect(url_for("visits"))

@app.route("/followups/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_followup(item_id):
    conn=db(); item=conn.execute("SELECT * FROM followups WHERE id=?",(item_id,)).fetchone()
    if not item or (session["role"]!="admin" and item["created_by"]!=session["user_id"]):
        flash("রেকর্ড পাওয়া যায়নি বা অনুমতি নেই।", "error")
    else:
        conn.execute("DELETE FROM followups WHERE id=?",(item_id,)); conn.commit(); flash("Follow-up মুছে ফেলা হয়েছে।", "success")
    return redirect(url_for("followups"))



@app.route("/api/phone-exists")
@login_required
def api_phone_exists():
    phone = re.sub(r"\D", "", request.args.get("phone", ""))
    if not phone:
        return {"exists": False}
    conn = db()
    if session["role"] == "admin":
        found = conn.execute("SELECT 1 FROM visits WHERE phone=? UNION SELECT 1 FROM followups WHERE phone=? LIMIT 1", (phone, phone)).fetchone()
    else:
        found = conn.execute("SELECT 1 FROM visits WHERE phone=? AND created_by=? UNION SELECT 1 FROM followups WHERE phone=? AND created_by=? LIMIT 1", (phone, session["user_id"], phone, session["user_id"])).fetchone()
    return {"exists": bool(found)}

@app.route("/api/reminders")
@login_required
def api_reminders():
    conn = db()
    if session["role"] == "admin":
        visits_rows = conn.execute("SELECT id,client_name,project,visit_date,visit_time FROM visits").fetchall()
        followup_rows = conn.execute("SELECT id,client_name,project,due_date,due_time FROM followups WHERE status='Pending'").fetchall()
    else:
        visits_rows = conn.execute("SELECT id,client_name,project,visit_date,visit_time FROM visits WHERE created_by=?", (session["user_id"],)).fetchall()
        followup_rows = conn.execute("SELECT id,client_name,project,due_date,due_time FROM followups WHERE status='Pending' AND created_by=?", (session["user_id"],)).fetchall()
    items = []
    for row in visits_rows:
        items.append({"key":"visit-" + str(row["id"]), "type":"Visit", "id":row["id"],
                      "client":row["client_name"], "project":row["project"] or "",
                      "at":row["visit_date"] + "T" + row["visit_time"]})
    for row in followup_rows:
        items.append({"key":"followup-" + str(row["id"]), "type":"Follow-up", "id":row["id"],
                      "client":row["client_name"], "project":row["project"] or "",
                      "at":row["due_date"] + "T" + row["due_time"]})
    return {"items":items}

@app.route("/projects", methods=["GET","POST"])
@admin_required
def projects():
    conn=db()
    if request.method=="POST":
        name=request.form.get("name","").strip()
        if not name:
            flash("Project-এর নাম লিখুন।", "error")
        else:
            try:
                conn.execute("INSERT INTO projects(name,created_at) VALUES(?,?)",(name,datetime.now().isoformat(timespec="seconds")))
                conn.commit(); flash("Project যোগ হয়েছে।", "success")
            except sqlite3.IntegrityError:
                flash("এই Project আগে থেকেই আছে।", "error")
        return redirect(url_for("projects"))
    rows=conn.execute("SELECT p.*, (SELECT COUNT(*) FROM visits v WHERE v.project=p.name) + (SELECT COUNT(*) FROM followups f WHERE f.project=p.name) AS linked_count FROM projects p ORDER BY p.name").fetchall()
    return render_template("projects.html", rows=rows, active="projects")

@app.route("/projects/<int:project_id>/edit", methods=["POST"])
@admin_required
def edit_project(project_id):
    name=request.form.get("name","").strip()
    if not name:
        flash("Project-এর নাম খালি রাখা যাবে না।", "error")
        return redirect(url_for("projects"))
    conn=db(); old=conn.execute("SELECT name FROM projects WHERE id=?",(project_id,)).fetchone()
    if not old:
        flash("Project পাওয়া যায়নি।", "error")
    else:
        try:
            conn.execute("UPDATE projects SET name=? WHERE id=?",(name,project_id))
            conn.execute("UPDATE visits SET project=? WHERE project=?",(name,old["name"]))
            conn.execute("UPDATE followups SET project=? WHERE project=?",(name,old["name"]))
            conn.commit(); flash("Project-এর নাম ও সংশ্লিষ্ট রেকর্ড আপডেট হয়েছে।", "success")
        except sqlite3.IntegrityError:
            flash("এই নামে অন্য Project আছে।", "error")
    return redirect(url_for("projects"))

@app.route("/projects/<int:project_id>/toggle", methods=["POST"])
@admin_required
def toggle_project(project_id):
    conn=db(); conn.execute("UPDATE projects SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?",(project_id,)); conn.commit()
    flash("Project status পরিবর্তন হয়েছে।", "success")
    return redirect(url_for("projects"))

@app.route("/users", methods=["GET","POST"])
@admin_required
def users():
    conn=db()
    if request.method=="POST":
        full_name=request.form.get("full_name","").strip()
        username=request.form.get("username","").strip().lower()
        password=request.form.get("password","")
        role=request.form.get("role","staff")
        if not full_name or not username or len(password)<8 or role not in ("admin","staff"):
            flash("সঠিক তথ্য দিন। পাসওয়ার্ড কমপক্ষে ৮ অক্ষরের হতে হবে।","error")
        else:
            try:
                conn.execute("INSERT INTO users(username,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?)",
                    (username,full_name,generate_password_hash(password),role,datetime.now().isoformat(timespec="seconds")))
                conn.commit()
                flash("নতুন ইউজার তৈরি হয়েছে।","success")
                return redirect(url_for("users"))
            except sqlite3.IntegrityError:
                flash("এই username আগে থেকেই আছে।","error")
    rows=conn.execute("SELECT id,username,full_name,role,active,created_at FROM users ORDER BY id").fetchall()
    return render_template("users.html", rows=rows, active="users")

@app.route("/users/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle_user(user_id):
    if user_id==session["user_id"]:
        flash("নিজের account নিষ্ক্রিয় করা যাবে না।","error")
    else:
        db().execute("UPDATE users SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?",(user_id,))
        db().commit()
        flash("ইউজার status পরিবর্তন হয়েছে।","success")
    return redirect(url_for("users"))

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="পেজটি পাওয়া যায়নি।"),404

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT","5000")), debug=False)
