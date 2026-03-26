from flask import Flask, render_template, request, redirect, url_for
from flask import redirect, url_for
from datetime import datetime
import pandas as pd
import os
import qrcode
import uuid
from flask import jsonify
from flask import session



app = Flask(__name__)

EXCEL_FILE = "leave_records.xlsx"

# Create Excel file if it doesn't exist
if not os.path.exists(EXCEL_FILE):
    df = pd.DataFrame(columns=[
        "Leave Type", "Name", "RegNo", "Room",
        "Place", "From Date", "From Time",
        "To Date", "To Time", "Reason",
        "Status", "QR ID", "QR File",
        "Exit Time", "Entry Time", "Current Status",
    ])
    df.to_excel(EXCEL_FILE, index=False)

import pandas as pd
import os

data = [
    {"RegNo": "24MEI10149", "Name": "R Nirmal Rajan", "Password": "pass123", "Block": 5,"Room": "B311", "Photo": "photos/24MEI10149.jpeg"},
    {"RegNo": "24MEI10050", "Name": "Prasanna Verma",  "Password": "pass456", "Block": 5,"Room": "A102", "Photo": "photos/24MEI10050.jpeg"},
    {"RegNo": "24BCE10739", "Name": "Devansh Patel", "Password": "pass789", "Block": 5, "Room": "B311", "Photo": "photos/24BCE10739.jpeg"}

]

df = pd.DataFrame(data)
df.to_excel("students.xlsx", index=False)


def ensure_columns(df):
    required_cols = ["Current Status", "Exit Time", "Entry Time", "QR ID", "QR File"]

    for col in required_cols:
        if col not in df.columns:
            df[col] = ""

    return df

@app.route('/')
def home():
    if 'user' not in session:
        return redirect('/login')   # 🔥 THIS LINE IS IMPORTANT

    regno = session['user']

    df = pd.read_excel("students.xlsx")
    student = df[df['RegNo'].astype(str) == regno].iloc[0]

    return render_template("apply.html", student=student)

app.secret_key = "secret123"

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        regno = request.form['regno']
        password = request.form['password']

        df = pd.read_excel("students.xlsx")

        student = df[(df['RegNo'].astype(str) == regno) & (df['Password'] == password)]

        if not student.empty:
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
    session['user'] = regno

    students_df = pd.read_excel("students.xlsx")
    student = students_df[students_df['RegNo'].astype(str) == regno].iloc[0]
    leave_type = request.form['leave_type']
    from_date = request.form['from_date']
    to_date = request.form.get('to_date')

    if leave_type == "Leave" and to_date:
        final_to_date = to_date
    else:
        final_to_date = "-"

    data = {
        "Leave Type": leave_type,
        "Name": student['Name'],
        "RegNo": regno,
        "Room": student['Room'],
        "Place": request.form['place'],
        "From Date": from_date,
        "From Time": "-",
        "To Date": final_to_date,
        "To Time": "-",
        "Reason": request.form['reason'],
        "Status": "Pending",
        "QR ID": "",
        "QR File": "",
        "Exit Time": "",
        "Entry Time": "",
        "Current Status": "Inside",
        "Photo": student['Photo']
    }

    df = pd.read_excel(EXCEL_FILE)
    df = pd.concat([df, pd.DataFrame([data])], ignore_index=True)
    df.to_excel(EXCEL_FILE, index=False)

    return "<h3>Request Submitted Successfully ✅</h3>"

@app.route('/status')
def status():

    if 'user' not in session:
        return redirect('/login')

    regno = session['user']

    df = pd.read_excel(EXCEL_FILE)
    student_data = df[df['RegNo'].astype(str) == regno]

    records = student_data.to_dict(orient='records')

    current_date = datetime.now().date()

    for record in records:

        record["QR Expired"] = False

        if record["Status"] == "Approved":

            if record["To Date"] != "-" and pd.notna(record["To Date"]):
                end_date = datetime.strptime(
                    record["To Date"], "%Y-%m-%d"
                ).date()
            else:
                end_date = datetime.strptime(
                    record["From Date"], "%Y-%m-%d"
                ).date()

            if current_date > end_date:
                record["QR Expired"] = True

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

    df = pd.read_excel(EXCEL_FILE)
    df.columns = df.columns.str.strip()

    record_df = df[df['QR ID'].astype(str) == str(qr_id)]

    if record_df.empty:
        return jsonify({
            "status": "error",
            "message": "Invalid QR Code",
            "name": "",
            "regno": "",
            "photo": ""
        })

    index = record_df.index[0]
    record = record_df.iloc[0]

    # ✅ Date Fix
    from_date_raw = record["From Date"]

    if pd.isna(from_date_raw):
        return jsonify({
            "status": "error",
            "message": "Invalid Date",
            "name": record["Name"],
            "regno": record["RegNo"],
            "photo": record["Photo"]
        })

    from_date = pd.to_datetime(from_date_raw).date()
    today = datetime.now().date()

    if today != from_date:
        return jsonify({
            "status": "denied",
            "message": "Not allowed today",
            "name": record["Name"],
            "regno": record["RegNo"],
            "photo": record["Photo"]
        })

    status = str(record.get("Current Status", "")).strip()

    if status == "Out":
        return jsonify({
            "status": "warning",
            "message": "Already Exited",
            "name": record["Name"],
            "regno": record["RegNo"],
            "photo": record["Photo"]
        })

    if status == "Returned":
        return jsonify({
            "status": "error",
            "message": "QR Expired",
            "name": record["Name"],
            "regno": record["RegNo"],
            "photo": record["Photo"]
        })

    # ✅ ALLOW EXIT
    current_time = datetime.now()

    df.at[index, "Exit Time"] = current_time.strftime("%Y-%m-%d %H:%M")
    df.at[index, "Current Status"] = "Out"

    df.to_excel(EXCEL_FILE, index=False)

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

if __name__ == '__main__':
    app.run()
