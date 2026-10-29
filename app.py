import html
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from db import PHOTO_DIR, audit, connect, hash_password, initialize, verify_password
from geo import haversine_m, valid_coordinates

st.set_page_config(page_title="GeoAttend", page_icon="📍", layout="wide")
initialize()

@st.cache_resource
def get_location_component():
    return components.declare_component("geoattend_location", path=str(Path(__file__).parent / "components" / "geolocation"))

location_component = get_location_component()

st.markdown("""
<style>
.stApp{background:#0b1220;color:#e5e7eb}.block-container{padding-top:2rem;max-width:1250px}
[data-testid="stMetric"]{background:#111c2e;border:1px solid #23324b;padding:18px;border-radius:14px}
div[data-testid="stTabs"] button{font-weight:650} .hero{padding:1.1rem 1.4rem;background:linear-gradient(110deg,#10263b,#142e39);border:1px solid #24485a;border-radius:18px;margin-bottom:1.2rem}
</style>
""", unsafe_allow_html=True)


def query(sql, params=()):
    with connect() as con:
        return con.execute(sql, params).fetchall()


def one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def login(email, password):
    user = one("SELECT * FROM employees WHERE email=? COLLATE NOCASE AND status=1", (email.strip(),))
    if user and verify_password(password, user["password_hash"]):
        return dict(user)
    return None


def register(name, email, department, password):
    with connect() as con:
        con.execute("INSERT INTO employees(employee_name,email,password_hash,department) VALUES(?,?,?,?)",
                    (name.strip(), email.strip().lower(), hash_password(password), department.strip() or "General"))


def render_auth():
    st.markdown('<div class="hero"><h1>📍 GeoAttend</h1><p>GPS verified attendance with a live camera photo.</p></div>', unsafe_allow_html=True)
    login_tab, register_tab = st.tabs(["Sign in", "Create employee account"])
    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
        if submitted:
            user = login(email, password)
            if user:
                st.session_state.user = user
                st.rerun()
            st.error("Email or password is incorrect, or this account is inactive.")
        st.caption("First run demo admin: admin@geoattend.local / Admin@123")
    with register_tab:
        with st.form("register_form"):
            name = st.text_input("Full name")
            email = st.text_input("Work email")
            dept = st.text_input("Department", value="General")
            password = st.text_input("Password", type="password")
            confirm = st.text_input("Confirm password", type="password")
            ok = st.form_submit_button("Create employee account", type="primary", use_container_width=True)
        if ok:
            if not name.strip() or not email.strip() or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()):
                st.error("Enter your name and a valid email address.")
            elif len(password) < 10:
                st.error("Use a password with at least 10 characters.")
            elif password != confirm:
                st.error("The passwords do not match.")
            else:
                try:
                    register(name, email, dept, password)
                    st.success("Account created. Sign in to continue.")
                except Exception as exc:
                    if "UNIQUE" in str(exc): st.error("An account with that email already exists.")
                    else: st.error("Account could not be created.")


def current_office():
    return one("SELECT * FROM office_locations ORDER BY location_id LIMIT 1")


def employee_app(user):
    st.title(f"Welcome, {user['employee_name'].split()[0]} 👋")
    office = current_office()
    if not office:
        st.error("An administrator must configure an office location first.")
        return
    today = date.today().isoformat()
    record = one("SELECT * FROM attendance WHERE employee_id=? AND work_date=?", (user["employee_id"], today))
    tab_mark, tab_history = st.tabs(["Mark attendance", "My history"])
    with tab_mark:
        st.subheader("Today's attendance")
        if record:
            st.success(f"Check-in recorded at {record['check_in_time']} · status: {record['status']}")
            if record["check_out_time"]:
                st.info(f"Check-out recorded at {record['check_out_time']}. Your day is complete.")
            else:
                st.caption("Check-out when your workday is complete.")
        else:
            st.info("No check-in recorded for today yet.")
        st.write(f"**Assigned location:** {office['location_name']} · allowed radius {office['allowed_radius']} m")
        if not record:
            st.markdown("#### 1. Verify your current location")
            location = location_component(key="geo_location", default=None)
            if location:
                lat, lon = float(location["latitude"]), float(location["longitude"])
                accuracy = float(location.get("accuracy") or 0)
                distance = haversine_m(lat, lon, office["latitude"], office["longitude"])
                st.write(f"GPS accuracy: ±{accuracy:.0f} m · distance from office: **{distance:.0f} m**")
                if accuracy > max(100, office["allowed_radius"]):
                    st.warning("GPS accuracy is weak. Move outdoors and capture location again for a better reading.")
                if distance > office["allowed_radius"]:
                    st.error("You are outside the permitted area. Attendance cannot be submitted.")
                else:
                    st.success("You are within the allowed area.")
                    st.markdown("#### 2. Capture a live photo")
                    photo = st.camera_input("Take a photo for today's attendance", key="attendance_camera")
                    if photo:
                        st.caption("Review the image, then submit your attendance below.")
                        if st.button("Submit check-in", type="primary", key="submit_checkin"):
                            if not valid_coordinates(lat, lon):
                                st.error("The captured coordinates are invalid. Capture your location again.")
                            elif distance > office["allowed_radius"]:
                                st.error("You are outside the permitted area.")
                            else:
                                stamp = datetime.now().astimezone()
                                filename = f"employee_{user['employee_id']}_{stamp.strftime('%Y%m%d_%H%M%S')}.jpg"
                                filepath = PHOTO_DIR / filename
                                filepath.write_bytes(photo.getvalue())
                                try:
                                    with connect() as con:
                                        cur = con.execute("""INSERT INTO attendance(employee_id,location_id,work_date,check_in_time,latitude,longitude,accuracy_m,photo_path,status)
                                            VALUES(?,?,?,?,?,?,?,?, 'Present')""",
                                            (user["employee_id"], office["location_id"], stamp.date().isoformat(), stamp.isoformat(timespec="seconds"), lat, lon, accuracy, str(filepath)))
                                        audit(con, cur.lastrowid, user["employee_id"], "Submitted", f"Distance {distance:.0f} m; GPS accuracy ±{accuracy:.0f} m")
                                    st.session_state.pop("geo_location", None)
                                    st.success("Check-in recorded successfully.")
                                    st.rerun()
                                except Exception as exc:
                                    filepath.unlink(missing_ok=True)
                                    if "UNIQUE" in str(exc): st.error("A check-in already exists for today.")
                                    else: st.error("Attendance could not be saved. Please try again.")
        elif not record["check_out_time"]:
            if st.button("Check out", type="primary"):
                stamp = datetime.now().astimezone().isoformat(timespec="seconds")
                with connect() as con:
                    con.execute("UPDATE attendance SET check_out_time=? WHERE attendance_id=? AND check_out_time IS NULL", (stamp, record["attendance_id"]))
                    audit(con, record["attendance_id"], user["employee_id"], "Checked out", "Employee check-out")
                st.success("Check-out recorded.")
                st.rerun()
    with tab_history:
        rows = query("""SELECT a.work_date,a.check_in_time,a.check_out_time,a.status,a.latitude,a.longitude,a.accuracy_m,o.location_name
            FROM attendance a JOIN office_locations o USING(location_id) WHERE a.employee_id=? ORDER BY a.work_date DESC LIMIT 180""", (user["employee_id"],))
        if rows:
            st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True, hide_index=True)
        else:
            st.info("Your attendance history will appear here after your first check-in.")


def admin_app(user):
    st.title("Admin dashboard")
    st.caption("Monitor attendance, manage employees, review captured photos, and export records.")
    tabs = st.tabs(["Overview & reports", "Attendance review", "Employees", "Office settings", "Audit trail"])
    with tabs[0]:
        today = date.today().isoformat()
        total = one("SELECT COUNT(*) n FROM employees WHERE role='Employee' AND status=1")["n"]
        present = one("SELECT COUNT(*) n FROM attendance WHERE work_date=? AND status!='Rejected'", (today,))["n"]
        checked_out = one("SELECT COUNT(*) n FROM attendance WHERE work_date=? AND check_out_time IS NOT NULL", (today,))["n"]
        c1,c2,c3=st.columns(3); c1.metric("Active employees",total); c2.metric("Today's check-ins",present); c3.metric("Checked out",checked_out)
        dates = query("SELECT DISTINCT work_date FROM attendance ORDER BY work_date DESC")
        if dates:
            choices=[r["work_date"] for r in dates]
            selected=st.selectbox("Report date", choices)
            df=pd.read_sql_query("""SELECT a.attendance_id,e.employee_name,e.email,e.department,o.location_name,a.work_date,a.check_in_time,a.check_out_time,a.latitude,a.longitude,a.accuracy_m,a.status,a.photo_path
                FROM attendance a JOIN employees e USING(employee_id) JOIN office_locations o USING(location_id) WHERE a.work_date=? ORDER BY e.employee_name""", connect(), params=(selected,))
            a,b=st.columns(2); a.metric("Present",int((df.status!="Rejected").sum())); b.metric("Absent",max(0,total-len(df)))
            st.dataframe(df.drop(columns=["photo_path"]),use_container_width=True,hide_index=True)
            st.download_button("Download this day's CSV",df.drop(columns=["photo_path"]).to_csv(index=False).encode("utf-8-sig"),file_name=f"geoattend_{selected}.csv",mime="text/csv")
        else: st.info("No attendance records yet.")
        monthly=pd.read_sql_query("""SELECT substr(work_date,1,7) AS month,COUNT(*) AS check_ins,COUNT(DISTINCT employee_id) AS employees_present FROM attendance WHERE status!='Rejected' GROUP BY month ORDER BY month""",connect())
        if not monthly.empty:
            st.subheader("Monthly attendance trend"); st.bar_chart(monthly.set_index("month")["check_ins"])
        pct=pd.read_sql_query("""SELECT e.employee_name,e.department,COUNT(a.attendance_id) AS days_present FROM employees e LEFT JOIN attendance a ON a.employee_id=e.employee_id AND a.status!='Rejected' WHERE e.role='Employee' AND e.status=1 GROUP BY e.employee_id""",connect())
        if not pct.empty:
            pct["attendance_percentage"]=(pct.days_present / max(1,len(dates))*100).round(1)
            st.subheader("Employee-wise attendance (%)"); st.dataframe(pct,use_container_width=True,hide_index=True)
    with tabs[1]:
        records=query("""SELECT a.*,e.employee_name,e.email,e.department,o.location_name FROM attendance a JOIN employees e USING(employee_id) JOIN office_locations o USING(location_id) ORDER BY a.work_date DESC,a.check_in_time DESC LIMIT 500""")
        if not records: st.info("No attendance to review yet.")
        else:
            options={f"#{r['attendance_id']} · {r['employee_name']} · {r['work_date']} · {r['status']}":r for r in records}
            label=st.selectbox("Select a record",list(options)); rec=options[label]
            st.write(f"**{rec['employee_name']}** · {rec['department']} · {rec['location_name']}")
            st.write(f"Check-in: {rec['check_in_time']} · Check-out: {rec['check_out_time'] or 'Not checked out'} · GPS ±{(rec['accuracy_m'] or 0):.0f} m")
            st.write(f"Captured coordinates: {rec['latitude']:.6f}, {rec['longitude']:.6f}")
            path=Path(rec["photo_path"])
            if path.exists(): st.image(str(path),caption="Attendance capture",width=420)
            else: st.warning("Photo file is missing.")
            note=st.text_input("Review note",key="review_note")
            x,y=st.columns(2)
            if x.button("Approve / keep present",type="primary"):
                with connect() as con:
                    con.execute("UPDATE attendance SET status='Present' WHERE attendance_id=?",(rec["attendance_id"],)); audit(con,rec["attendance_id"],user["employee_id"],"Approved",note)
                st.success("Record approved."); st.rerun()
            if y.button("Reject record"):
                with connect() as con:
                    con.execute("UPDATE attendance SET status='Rejected' WHERE attendance_id=?",(rec["attendance_id"],)); audit(con,rec["attendance_id"],user["employee_id"],"Rejected",note)
                st.success("Record rejected."); st.rerun()
    with tabs[2]:
        employees=query("SELECT employee_id,employee_name,email,department,role,status,created_at FROM employees ORDER BY role DESC,employee_name")
        st.dataframe(pd.DataFrame([dict(r) for r in employees]),use_container_width=True,hide_index=True)
        st.subheader("Add employee")
        with st.form("admin_add_employee"):
            name=st.text_input("Name",key="new_name"); email=st.text_input("Email",key="new_email"); dept=st.text_input("Department",key="new_dept"); password=st.text_input("Temporary password (10+ characters)",type="password",key="new_pass")
            submit=st.form_submit_button("Create employee")
        if submit:
            if not name.strip() or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",email.strip()) or len(password)<10: st.error("Enter a name, valid email, and password with at least 10 characters.")
            else:
                try: register(name,email,dept,password); st.success("Employee created."); st.rerun()
                except Exception: st.error("Could not create account; check whether the email is already registered.")
        employee_options=[dict(r) for r in employees if r["employee_id"]!=user["employee_id"]]
        if employee_options:
            selected=st.selectbox("Change employee account",employee_options,format_func=lambda r:f"{r['employee_name']} ({r['email']})")
            active=st.checkbox("Account active",value=bool(selected["status"]),key=f"active_{selected['employee_id']}")
            if st.button("Save account status"):
                with connect() as con: con.execute("UPDATE employees SET status=? WHERE employee_id=?",(int(active),selected["employee_id"]))
                st.success("Account updated."); st.rerun()
    with tabs[3]:
        office=current_office()
        with st.form("office_form"):
            name=st.text_input("Office name",office["location_name"] if office else "Main Office")
            lat=st.number_input("Latitude",value=float(office["latitude"]) if office else 0.0,min_value=-90.0,max_value=90.0,format="%.6f")
            lon=st.number_input("Longitude",value=float(office["longitude"]) if office else 0.0,min_value=-180.0,max_value=180.0,format="%.6f")
            radius=st.number_input("Allowed radius (meters)",value=int(office["allowed_radius"]) if office else 150,min_value=25,max_value=10000,step=25)
            save=st.form_submit_button("Save office location",type="primary")
        if save:
            with connect() as con:
                if office: con.execute("UPDATE office_locations SET location_name=?,latitude=?,longitude=?,allowed_radius=? WHERE location_id=?",(name,lat,lon,radius,office["location_id"]))
                else: con.execute("INSERT INTO office_locations(location_name,latitude,longitude,allowed_radius) VALUES(?,?,?,?)",(name,lat,lon,radius))
            st.success("Office location saved."); st.rerun()
        st.caption("Set these coordinates to your actual demonstration site. Use a sensible radius that accounts for GPS accuracy.")
    with tabs[4]:
        audits=query("""SELECT a.action_time,a.action,e.employee_name AS actor,at.attendance_id,at.work_date,ee.employee_name AS employee,a.remarks FROM attendance_audit a LEFT JOIN employees e ON e.employee_id=a.actor_id LEFT JOIN attendance at ON at.attendance_id=a.attendance_id LEFT JOIN employees ee ON ee.employee_id=at.employee_id ORDER BY a.action_time DESC LIMIT 500""")
        if audits: st.dataframe(pd.DataFrame([dict(r) for r in audits]),use_container_width=True,hide_index=True)
        else: st.info("No audit actions yet.")


def main():
    if "user" not in st.session_state:
        render_auth(); return
    user=st.session_state.user
    with st.sidebar:
        st.markdown("## GeoAttend")
        st.write(user["employee_name"]); st.caption(f"{user['role']} · {user['department']}")
        if st.button("Sign out",use_container_width=True):
            st.session_state.clear(); st.rerun()
        st.divider()
        st.caption("Location and camera permissions are requested by your browser only when needed.")
    if user["role"]=="Admin": admin_app(user)
    else: employee_app(user)
    st.divider()
    st.caption("Educational demo · GPS and photos have accuracy and spoofing limits. Review README before using real personal data.")

main()


