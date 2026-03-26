from flask import Flask, render_template, request, redirect, url_for
from flask import redirect, url_for
from datetime import datetime
import pandas as pd
import os
import qrcode
import uuid
from flask import jsonify
from flask import session
import sqlite3



app = Flask(__name__)

DB_FILE = "database.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # Students Table
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

    # Leave Records Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leave_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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


def seed_students():
    conn = get_db()
    cursor = conn.cursor()

    students = [
        ("24MEI10149", "R Nirmal Rajan", "pass123", 5, "B311", "photos/24MEI10149.jpeg"),
        ("24MEI10050", "Prasanna Verma", "pass456", 5, "A102", "photos/24MEI10050.jpeg"),
        ("24BCE10739", "Devansh Patel", "pass789", 5, "B311", "photos/24BCE10739.jpeg")
    ]

    for s in students:
        cursor.execute("""
        INSERT OR IGNORE INTO students VALUES (?, ?, ?, ?, ?, ?)
        """, s)

    conn.commit()
    conn.close()

seed_students()


def ensure_columns(df):
    required_cols = ["Current Status", "Exit Time", "Entry Time", "QR ID", "QR File"]

    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    return df

@app.route('/')
def home():
    if 'user' not in session:
        return redirect('/login')

    regno = session['user']

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM students WHERE RegNo=?", (regno,))
    student = cursor.fetchone()

    conn.close()

    return render_template("apply.html", student=student)

app.secret_key = "secret123"

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        regno = request.form['regno']
        password = request.form['password']

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM students WHERE RegNo=? AND Password=?", (regno, password))
        student = cursor.fetchone()

        conn.close()

        if student:
            session['user'] = regno
            return redirect('/')

        return "<h3>Invalid Login ❌</h3>"

    return render_template("login.html")

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')

@app.route('/submit', methods=['POST'])
def submit():
    if 'user' not in session:
        return redirect('/login')

    regno = session['user']

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM students WHERE RegNo=?", (regno,))
    student = cursor.fetchone()

    leave_type = request.form['leave_type']
    from_date = request.form['from_date']
    to_date = request.form.get('to_date') or "-"

    cursor.execute("""
    INSERT INTO leave_records
    (LeaveType, Name, RegNo, Room, Place, FromDate, ToDate, Reason,
     Status, QRID, QRFile, ExitTime, EntryTime, CurrentStatus, Photo)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

@app.route('/status')
def status():
    if 'user' not in session:
        return redirect('/login')

    regno = session['user']

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM leave_records WHERE RegNo=?", (regno,))
    records = cursor.fetchall()

    conn.close()

    return render_template("status.html", records=records)

@app.route('/approval')
def approval():
    df = pd.read_excel(EXCEL_FILE)
    records = df.to_dict(orient='records')
    return render_template("approval.html", records=records)

@app.route('/scanner_in')
def scanner_in_page():
    return render_template("scanner_in.html")

@app.route('/scanner_out')
def scanner_out_page():
    return render_template("scanner_out.html")

@app.route('/scan_out/<qr_id>')
def scan_out(qr_id):

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM leave_records WHERE QRID=?", (qr_id,))
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
    SET ExitTime=?, CurrentStatus=?
    WHERE QRID=?
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

@app.route('/scan_in/<qr_id>')
def scan_in(qr_id):

    df = pd.read_excel(EXCEL_FILE)
    df.columns = df.columns.str.strip()

    record_df = df[df['QR ID'].astype(str) == str(qr_id)]

    if record_df.empty:
        return jsonify({
            "status": "denied",
            "message": "Invalid QR Code",
            "name": "",
            "regno": "",
            "photo": ""
        })

    index = record_df.index[0]
    record = record_df.iloc[0]

    status = str(record.get("Current Status", "")).strip()

    if status != "Out":
        return jsonify({
            "status": "denied",
            "message": "Exit not recorded",
            "name": record["Name"],
            "regno": record["RegNo"],
            "photo": record["Photo"]
        })

    current_time = datetime.now()

    df.at[index, "Entry Time"] = current_time.strftime("%Y-%m-%d %H:%M")
    df.at[index, "Current Status"] = "Returned"

    df.to_excel(EXCEL_FILE, index=False)

    return jsonify({
        "status": "allowed",
        "message": "Entry Recorded",
        "name": record["Name"],
        "regno": record["RegNo"],
        "photo": record["Photo"]
    })

@app.route('/approve/<int:index>')
def approve(index):

    df = pd.read_excel(EXCEL_FILE)

    if df.loc[index, "Status"] != "Approved":

        df.loc[index, "Status"] = "Approved"

        qr_id = str(uuid.uuid4())
        df.loc[index, "QR ID"] = qr_id

        verify_url = request.host_url.rstrip('/') + "/scan_out/" + qr_id
        print("QR URL:", verify_url)  # DEBUG


        qr = qrcode.QRCode(
            version=1,
            box_size=10,
            border=5
        )

        qr.add_data(verify_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        qr_folder = "static/qr_codes"
        os.makedirs(qr_folder, exist_ok=True)

        qr_filename = f"qr_{qr_id}.png"
        qr_path = os.path.join(qr_folder, qr_filename)

        img.save(qr_path)

        df.loc[index, "QR File"] = f"qr_codes/{qr_filename}"

    df.to_excel(EXCEL_FILE, index=False)

    return redirect('/approval')

@app.route('/reject/<int:index>')
def reject(index):

    df = pd.read_excel(EXCEL_FILE)

    if df.loc[index, "Status"] == "Pending":
        df.loc[index, "Status"] = "Rejected"

    df.to_excel(EXCEL_FILE, index=False)

    return redirect('/approval')

from flask import send_from_directory, request

@app.route('/download_qr/<path:filename>')
def download_qr(filename):
    custom_name = request.args.get("name")  # 👈 get filename from URL
    return send_from_directory(
        'static',
        filename,
        as_attachment=True,
        download_name=custom_name   # 🔥 FORCE filename
    )

@app.route('/dashboard')
def dashboard():

    df = pd.read_excel(EXCEL_FILE)

    overstay_list = []

    for i, row in df.iterrows():
        if row["Current Status"] == "Out":

            if row["To Date"] != "-" and pd.notna(row["To Date"]):
                end_date = datetime.strptime(row["To Date"], "%Y-%m-%d")

                if datetime.now().date() > end_date.date():
                    overstay_list.append(row["Name"])

    total_out = df[df['Current Status'] == 'Out'].shape[0]
    returned = df[df['Current Status'] == 'Returned'].shape[0]
    pending = df[df['Status'] == 'Pending'].shape[0]

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

# ================== RUN ==================
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
