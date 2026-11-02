# Internal QR Management System

A production-ready, mobile-first Progressive Web App (PWA) built specifically for internal team operations to generate, print, scan, assign, manage, deactivate, and reuse QR codes.

---

## 🛠️ Tech Stack

- **Backend**: FastAPI (Python 3.11), SQLAlchemy ORM, SQLite / PostgreSQL ready
- **Security & Auth**: JWT Authentication, bcrypt password hashing, RBAC (Admin, Operator)
- **QR Generation**: Python `qrcode[pil]`, high-error-correction tokens
- **Printing Engine**: `reportlab` (PDF grid generator with customizable margins/sizes)
- **Scanning**: In-browser camera scanning via `html5-qrcode` + fallback direct token input
- **Frontend**: React 18, Vite, Tailwind CSS / Modern Glassmorphic Dark UI
- **PWA**: Web App Manifest, Service Worker offline caching, mobile viewport lock

---

## 🚀 Quick Start Guide

### 1. Backend Setup

```powershell
cd "d:\QR System\backend"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- API Base URL: `http://localhost:8000`
- Interactive Swagger Docs: `http://localhost:8000/api/docs`
- Default Admin Credentials:
  - **Username**: `admin`
  - **Password**: `admin123`

### 2. Frontend Setup

```powershell
cd "d:\QR System\frontend"
npm install
npm run dev
```

- Web App: `http://localhost:5173`

---

## 🧪 Running Automated Tests

Run the test suite verifying authentication, QR lifecycle, redirect resolution, exports, and RBAC:

```powershell
cd "d:\QR System\backend"
python -m pytest tests/test_api.py -v
```

---

## 📱 Core Features

1. **Batch Pre-Generation**: Admin generates batches of unassigned QR codes with unique cryptographic tokens.
2. **Print & Export**: Export QR batches to PDF sticker sheets (custom dimensions) or single PNG / ZIP archives.
3. **Scan & Instant Assignment**: Field operators scan physical codes with phone camera and instantly assign destination URL & business details.
4. **Dynamic Redirection**: Scans redirect through `/q/{token}` to current destination with real-time analytics tracking.
5. **Reassignment & History**: Change destinations on the fly without reprinting stickers, with a full audit log.
6. **PWA Installable**: Add to Android home screen for native-app feel on mobile devices.
