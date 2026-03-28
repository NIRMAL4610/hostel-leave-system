from flask import Flask, render_template, request, redirect, url_for, jsonify, session, send_from_directory
from datetime import datetime
import os
import qrcode
import uuid
import psycopg2
import psycopg2.extras

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_secret")

# ================== DATABASE CONFIG ==================

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    return psycopg2.connect(DATABASE_URL)

def get_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# ================== INIT DB ==================

def init_db():
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        RegNo TEXT PRIMARY KEY,
        Name TEXT,
        Password TEXT,
        Block INTEGER,
        Room TEXT,
        Photo TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leave_records (
        id SERIAL PRIMARY KEY,
        LeaveType TEXT,
        Name TEXT,
        RegNo TEXT,
        Room TEXT,
        Place TEXT,
        FromDate TEXT,
        ToDate TEXT,
        Reason TEXT,
        Status TEXT,
        QRID TEXT,
        QRFile TEXT,
        ExitTime TEXT,
        EntryTime TEXT,
        CurrentStatus TEXT,
        Photo TEXT
    )
    """)

    conn.commit()
    conn.close()

# ================== SEED DATA ==================

def seed_students():
    conn = get_db()
    cursor = get_cursor(conn)

    students = [
        ("24MEI10149", "R Nirmal Rajan", "pass123", 5, "B311", "photos/24MEI10149.jpeg"),
        ("24MEI10050", "Prasanna Verma", "pass456", 5, "A102", "photos/24MEI10050.jpeg"),
        ("24BCE10739", "Devansh Patel", "pass789", 5, "B311", "photos/24BCE10739.jpeg")
    ]

    for s in students:
        cursor.execute("""
        INSERT INTO students (RegNo, Name, Password, Block, Room, Photo)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (RegNo) DO NOTHING
        """, s)

    conn.commit()
    conn.close()

# ================== HOME ==================

@app.route('/')
def home():
    if 'user' not in session:
        return redirect('/login')

    regno = session['user']

    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute("SELECT * FROM students WHERE RegNo=%s", (regno,))
    student = cursor.fetchone()

    conn.close()

    return render_template("apply.html", student=student)

# ================== LOGIN ==================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        regno = request.form['regno']
        password = request.form['password']

        conn = get_db()
        cursor = get_cursor(conn)

        cursor.execute(
            "SELECT * FROM students WHERE RegNo=%s AND Password=%s",
            (regno, password)
        )
        student = cursor.fetchone()
        conn.close()

        if student:
            session['user'] = regno
            return redirect('/')

        return "<h3>Invalid Login ❌</h3>"

    return render_template("login.html", error="Invalid Login")

# ================== LOGOUT ==================

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')

# ================== SUBMIT ==================

@app.route('/submit', methods=['POST'])
def submit():
    if 'user' not in session:
        return redirect('/login')

    regno = session['user']

    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute("SELECT * FROM students WHERE RegNo=%s", (regno,))
    student = cursor.fetchone()

    leave_type = request.form['leave_type']
    from_date = request.form['from_date']
    to_date = request.form.get('to_date') or "-"

    cursor.execute("""
    INSERT INTO leave_records
    (LeaveType, Name, RegNo, Room, Place, FromDate, ToDate, Reason,
     Status, QRID, QRFile, ExitTime, EntryTime, CurrentStatus, Photo)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        leave_type,
        student["Name"],
        regno,
        student["Room"],
        request.form['place'],
        from_date,
        to_date,
        request.form['reason'],
        "Pending",
        "",
        "",
        "",
        "",
        "Inside",
        student["Photo"]
    ))

    conn.commit()
    conn.close()

    return "<h3>Request Submitted Successfully ✅</h3>"

# ================== STATUS ==================

@app.route('/status')
def status():
    if 'user' not in session:
        return redirect('/login')

    regno = session['user']

    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute("SELECT * FROM leave_records WHERE RegNo=%s", (regno,))
    records = cursor.fetchall()

    conn.close()

    return render_template("status.html", records=records)

# ================== APPROVAL ==================

@app.route('/approval')
def approval():
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute("SELECT * FROM leave_records")
    records = cursor.fetchall()

    conn.close()

    return render_template("approval.html", records=records)

# ================== SCANNERS ==================

@app.route('/scanner_in')
def scanner_in_page():
    return render_template("scanner_in.html")

@app.route('/scanner_out')
def scanner_out_page():
    return render_template("scanner_out.html")

# ================== SCAN OUT ==================

@app.route('/scan_out/<qr_id>')
def scan_out(qr_id):
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute("SELECT * FROM leave_records WHERE QRID=%s", (qr_id,))
    record = cursor.fetchone()

    if not record:
        return jsonify({"status": "error", "message": "Invalid QR Code"})

    today = datetime.now().date()
    from_date = datetime.strptime(record["FromDate"], "%Y-%m-%d").date()

    if today != from_date:
        return jsonify({"status": "denied", "message": "Not allowed today"})

    if record["CurrentStatus"] == "Out":
        return jsonify({"status": "warning", "message": "Already Exited"})

    cursor.execute("""
    UPDATE leave_records
    SET ExitTime=%s, CurrentStatus=%s
    WHERE QRID=%s
    """, (datetime.now().strftime("%Y-%m-%d %H:%M"), "Out", qr_id))

    conn.commit()
    conn.close()

    return jsonify({
        "status": "allowed",
        "message": "Exit Allowed",
        "name": record["Name"],
        "regno": record["RegNo"],
        "photo": record["Photo"]
    })

# ================== SCAN IN ==================

@app.route('/scan_in/<qr_id>')
def scan_in(qr_id):
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute("SELECT * FROM leave_records WHERE QRID=%s", (qr_id,))
    record = cursor.fetchone()

    if not record:
        return jsonify({"status": "denied", "message": "Invalid QR Code"})

    if record["CurrentStatus"] != "Out":
        return jsonify({"status": "denied", "message": "Exit not recorded"})

    cursor.execute("""
    UPDATE leave_records
    SET EntryTime=%s, CurrentStatus=%s
    WHERE QRID=%s
    """, (datetime.now().strftime("%Y-%m-%d %H:%M"), "Returned", qr_id))

    conn.commit()
    conn.close()

    return jsonify({
        "status": "allowed",
        "message": "Entry Recorded",
        "name": record["Name"],
        "regno": record["RegNo"],
        "photo": record["Photo"]
    })

# ================== APPROVE ==================

@app.route('/approve/<int:id>')
def approve(id):
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute("SELECT * FROM leave_records WHERE id=%s", (id,))
    record = cursor.fetchone()

    if not record:
        return "Invalid ID"

    if record["Status"] != "Approved":
        qr_id = str(uuid.uuid4())
        verify_url = request.host_url.rstrip('/') + "/scan_out/" + qr_id

        qr = qrcode.make(verify_url)

        qr_folder = os.path.join("static", "qr_codes")
        os.makedirs(qr_folder, exist_ok=True)

        qr_filename = f"qr_{qr_id}.png"
        qr_path = os.path.join(qr_folder, qr_filename)

        qr.save(qr_path)

        cursor.execute("""
        UPDATE leave_records
        SET Status=%s, QRID=%s, QRFile=%s
        WHERE id=%s
        """, ("Approved", qr_id, f"qr_codes/{qr_filename}", id))

    conn.commit()
    conn.close()

    return redirect('/approval')

# ================== REJECT ==================

@app.route('/reject/<int:id>')
def reject(id):
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute("""
    UPDATE leave_records
    SET Status='Rejected'
    WHERE id=%s AND Status='Pending'
    """, (id,))

    conn.commit()
    conn.close()

    return redirect('/approval')

# ================== DOWNLOAD QR ==================

@app.route('/download_qr/<path:filename>')
def download_qr(filename):
    custom_name = request.args.get("name")
    return send_from_directory(
        'static',
        filename,
        as_attachment=True,
        download_name=custom_name
    )

# ================== DASHBOARD ==================

@app.route('/dashboard')
def dashboard():
    conn = get_db()
    cursor = get_cursor(conn)

    cursor.execute("SELECT * FROM leave_records")
    rows = cursor.fetchall()

    overstay_list = []

    for row in rows:
        if row["CurrentStatus"] == "Out":
            if row["ToDate"] and row["ToDate"] != "-":
                end_date = datetime.strptime(row["ToDate"], "%Y-%m-%d")

                if datetime.now().date() > end_date.date():
                    overstay_list.append(row["Name"])

    total_out = len([r for r in rows if r["CurrentStatus"] == "Out"])
    returned = len([r for r in rows if r["CurrentStatus"] == "Returned"])
    pending = len([r for r in rows if r["Status"] == "Pending"])

    conn.close()

    return f"""
    <h2>📊 Dashboard</h2>
    <p>🟢 Students Outside: {total_out}</p>
    <p>🔵 Returned Students: {returned}</p>
    <p>⏳ Pending Requests: {pending}</p>

    <h3>🚨 Overstay Students:</h3>
    <ul>
    {''.join(f"<li>{name}</li>" for name in overstay_list) if overstay_list else "<li>None</li>"}
    </ul>
    """

# ================== INIT ==================

init_db()
seed_students()

# ================== RUN ==================

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
