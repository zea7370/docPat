from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
import pandas as pd
from datetime import datetime, timedelta
import uuid
import os

app = Flask(__name__)
app.secret_key = "change-this-secret"  # for flash messages

# File paths (assume CSV files exist in project root)
DOCTORS_CSV = "doctors.csv"
PATIENTS_CSV = "patients.csv"
APPOINTMENTS_CSV = "appointments.csv"
QUEUE_CSV = "queue.csv"

EMERGENCY_NUMBER = "+91-1122334455"  # example emergency number

def load_dataframes():
    # Read CSVs safely and ensure date parsing for appointments
    df_doctors = pd.read_csv(DOCTORS_CSV)
    df_patients = pd.read_csv(PATIENTS_CSV)
    df_appointments = pd.read_csv(APPOINTMENTS_CSV)
    # If DateTime column exists, ensure it's datetime
    if 'DateTime' in df_appointments.columns:
        df_appointments['DateTime'] = pd.to_datetime(df_appointments['DateTime'])
    else:
        df_appointments['DateTime'] = pd.NaT
    df_queue = pd.read_csv(QUEUE_CSV) if os.path.exists(QUEUE_CSV) else pd.DataFrame(columns=['Doctor_ID','Date','Patient_ID','Queue_Position'])
    return df_doctors, df_patients, df_appointments, df_queue

def save_appointments(df_appointments):
    df_appointments.to_csv(APPOINTMENTS_CSV, index=False)

def save_queue(df_queue):
    df_queue.to_csv(QUEUE_CSV, index=False)

@app.route("/")
def index():
    df_doctors, _, df_appointments, _ = load_dataframes()
    # show next available appointment count per doctor
    now = datetime.now()
    upcoming = df_appointments[(df_appointments['Status'] == 'booked') & (df_appointments['DateTime'] >= now)]
    counts = upcoming.groupby('Doctor_ID').size().to_dict()
    doctors = df_doctors.to_dict(orient='records')
    for d in doctors:
        d['Booked_Count'] = int(counts.get(d['Doctor_ID'], 0))
    return render_template("index.html", doctors=doctors, emergency=EMERGENCY_NUMBER)

@app.route("/doctor/<doctor_id>")
def doctor_profile(doctor_id):
    df_doctors, df_patients, df_appointments, df_queue = load_dataframes()
    doc = df_doctors[df_doctors['Doctor_ID'] == doctor_id]
    if doc.empty:
        flash("Doctor not found", "danger")
        return redirect(url_for('index'))
    doc = doc.iloc[0].to_dict()
    # upcoming appointments for this doctor (next 7 days)
    now = datetime.now()
    upcoming = df_appointments[(df_appointments['Doctor_ID'] == doctor_id) & (df_appointments['DateTime'] >= now)]
    upcoming = upcoming.sort_values('DateTime').head(20)
    # join patient names
    upcoming = upcoming.merge(df_patients[['Patient_ID','Name']], on='Patient_ID', how='left')
    upcoming_list = upcoming.to_dict(orient='records')
    # today's queue for this doctor
    today = now.date()
    today_queue = df_queue[(df_queue['Doctor_ID'] == doctor_id) & (pd.to_datetime(df_queue['Date']).dt.date == today)]
    today_queue = today_queue.merge(df_patients[['Patient_ID','Name']], on='Patient_ID', how='left')
    queue_list = today_queue.sort_values('Queue_Position').to_dict(orient='records')
    return render_template("doctor.html", doctor=doc, upcoming=upcoming_list, queue=queue_list, emergency=EMERGENCY_NUMBER)

@app.route("/book/<doctor_id>", methods=['GET','POST'])
def book(doctor_id):
    df_doctors, df_patients, df_appointments, df_queue = load_dataframes()
    doc = df_doctors[df_doctors['Doctor_ID'] == doctor_id]
    if doc.empty:
        flash("Doctor not found", "danger")
        return redirect(url_for('index'))
    if request.method == 'POST':
        # read form
        patient_name = request.form.get('patient_name', '').strip()
        age = request.form.get('age')
        contact = request.form.get('contact')
        date = request.form.get('date')  # yyyy-mm-dd
        time = request.form.get('time')  # HH:MM (24h)
        if not (patient_name and date and time and contact):
            flash("Please fill all required fields", "warning")
            return redirect(request.url)
        # attempt to find existing patient by contact; otherwise create new
        existing = df_patients[df_patients['Contact'].astype(str) == str(contact)]
        if not existing.empty:
            patient_id = existing.iloc[0]['Patient_ID']
        else:
            # create new patient id
            next_idx = len(df_patients) + 1
            patient_id = f"PAT{str(next_idx).zfill(4)}"
            new_row = {'Patient_ID': patient_id, 'Name': patient_name, 'Age': int(age) if age else None, 'Contact': contact}
            df_patients = df_patients._append(new_row, ignore_index=True)
            df_patients.to_csv(PATIENTS_CSV, index=False)
        # create appointment id
        app_id = f"APP{str(uuid.uuid4().hex)[:8].upper()}"
        dt_str = f"{date} {time}"
        appt_dt = datetime.fromisoformat(dt_str)
        status = 'booked'
        new_appt = {'Appointment_ID': app_id, 'Patient_ID': patient_id, 'Doctor_ID': doctor_id, 'DateTime': appt_dt, 'Status': status}
        df_appointments = df_appointments._append(new_appt, ignore_index=True)
        # update queue for date
        date_only = appt_dt.date().isoformat()
        # compute next position for that doctor & date
        existing_positions = df_queue[(df_queue['Doctor_ID'] == doctor_id) & (df_queue['Date'] == date_only)]
        next_pos = 1 if existing_positions.empty else existing_positions['Queue_Position'].max() + 1
        df_queue = df_queue._append({'Doctor_ID': doctor_id, 'Date': date_only, 'Patient_ID': patient_id, 'Queue_Position': int(next_pos)}, ignore_index=True)
        # save
        # ensure DateTime column is serializable
        df_appointments['DateTime'] = pd.to_datetime(df_appointments['DateTime'])
        save_appointments(df_appointments)
        save_queue(df_queue)
        flash("Appointment booked successfully!", "success")
        return render_template("booked.html", appointment=new_appt, doctor=doc.iloc[0].to_dict(), emergency=EMERGENCY_NUMBER)
    else:
        doc_t = doc.iloc[0].to_dict()
        return render_template("book.html", doctor=doc_t, emergency=EMERGENCY_NUMBER)

@app.route("/api/queue/<doctor_id>")
def api_queue(doctor_id):
    # Return today's queue for doctor as JSON
    _, df_patients, _, df_queue = load_dataframes()
    now = datetime.now().date()
    dfq = df_queue[(df_queue['Doctor_ID'] == doctor_id) & (pd.to_datetime(df_queue['Date']).dt.date == now)]
    if dfq.empty:
        return jsonify({'queue': []})
    dfq = dfq.sort_values('Queue_Position').merge(df_patients[['Patient_ID','Name']], on='Patient_ID', how='left')
    result = dfq[['Patient_ID','Name','Queue_Position']].to_dict(orient='records')
    return jsonify({'queue': result})

if __name__ == "__main__":
    # create csv outputs if not present (safe-guards)
    for fname in [DOCTORS_CSV, PATIENTS_CSV, APPOINTMENTS_CSV]:
        if not os.path.exists(fname):
            pd.DataFrame().to_csv(fname, index=False)
    app.run(debug=True, port=5000)
