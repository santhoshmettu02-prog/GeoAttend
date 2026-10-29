# GeoAttend

A local full-stack GPS attendance demo built with Streamlit, SQLite, browser geolocation, and live camera capture.

## Requirements

- Python 3.10 or newer
- A modern browser with camera and location permissions
- VS Code (recommended)

## Run in VS Code

1. Open the `GeoAttend` folder in VS Code.
2. In the integrated terminal create and activate a virtual environment:

   **Windows PowerShell**
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   **macOS/Linux**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install packages and start the app:
   ```bash
   pip install -r requirements.txt
   streamlit run app.py
   ```
4. Open the local URL shown in the terminal. For browser GPS and camera, allow location and camera access. GPS permissions usually require localhost or HTTPS.

## First login

The database is created automatically on first run. Demo administrator:

- Email: `admin@geoattend.local`
- Password: `Admin@123`

Change this password after the first login. Use the Register tab to create employee accounts. Admins can change the office coordinates and allowed radius in Admin → Office settings. The initial office is set to the Taj Mahal as a sample location; configure it for your own demonstration site.

## Features

- PBKDF2 password hashing, role-based access, active/inactive accounts
- Browser GPS capture and server-side Haversine distance validation
- Streamlit camera capture with image preview; image files are stored locally under `data/photos/`
- One check-in per employee per local calendar day, followed by check-out
- Employee attendance history and status
- Admin employee management, attendance/photo/location review, audit trail, CSV export
- Daily/monthly summaries and employee-wise attendance percentages

## Data and privacy

SQLite data is stored in `data/geoattend.db`; captured images are stored under `data/photos/`. Back up and protect this folder. This demo does not encrypt files at rest or include a production deployment hardening process. GPS coordinates and photos can be inaccurate or spoofed and do not prove identity or physical presence by themselves. The app records server-side timestamps, limits capture to the camera widget, checks GPS accuracy when the browser provides it, and keeps an audit log. Define retention/deletion rules before using real employee data. Use HTTPS and a professional deployment platform before any public deployment.

## Project structure

```
GeoAttend/
├── app.py
├── db.py
├── geo.py
├── requirements.txt
├── README.md
├── .gitignore
├── components/geolocation/index.html
└── data/                 # created automatically; do not commit
```

This is an educational working application. Students should understand the code and explain the architecture, distance algorithm, database relations, and security limitations.
