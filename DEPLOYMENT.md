# Production Deployment & Security Operations Guide
## Internal QR Management System

This document outlines the operational procedures for deploying, securing, backing up, and maintaining the **Internal QR Management System** in a production environment.

---

## 1. Security Architecture & Deployment Requirements

### Critical Requirements:
1. **HTTPS is Mandatory for Mobile Camera Access**:
   Modern mobile browsers (Chrome on Android, Safari on iOS) strictly block WebRTC camera access (`navigator.mediaDevices.getUserMedia`) over plain HTTP on non-localhost addresses (e.g. `http://192.168.x.x`). A valid TLS/SSL certificate is required for field operators scanning QR codes via mobile cameras.
2. **Environment Variable Security**:
   Ensure `ENVIRONMENT=production` and generate a cryptographically strong `SECRET_KEY` using:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   The backend will refuse to start if the default development secret is detected in production mode.
3. **Mandatory Default Password Replacement**:
   On initial startup, the default administrator account (`admin`) is created with a persistent `must_change_password=True` flag. Until changed via `/api/auth/change-password`, all normal operations are rejected with `HTTP 403 Forbidden`.

---

## 2. Reverse Proxy Configuration (HTTPS)

### Option A: Caddy Server (Recommended — Automatic Let's Encrypt SSL)
Create `Caddyfile`:
```caddy
qr.internal.company.com {
    # Backend API and QR Redirection
    handle /api/* {
        reverse_proxy localhost:8000
    }
    handle /q/* {
        reverse_proxy localhost:8000
    }
    handle /qr/* {
        reverse_proxy localhost:8000
    }

    # Frontend Single Page App
    handle {
        root * /var/www/qr-system/frontend/dist
        try_files {path} /index.html
        file_server
    }
}
```

### Option B: Nginx Reverse Proxy
```nginx
server {
    listen 443 ssl http2;
    server_name qr.internal.company.com;

    ssl_certificate /etc/letsencrypt/live/qr.internal.company.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/qr.internal.company.com/privkey.pem;

    # Frontend SPA
    location / {
        root /var/www/qr-system/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # Backend API & QR Redirects
    location ~ ^/(api|q|qr)/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## 3. Database Disaster Recovery & Backup Guide

### A. Live Online Backups
* **Method**: SQLite Online Backup API (`sqlite3.Connection.backup()`).
* **Safety**: Backups can be triggered while the application is running without file locking or transaction corruption.
* **Triggering Backups**:
  - **Via UI**: Navigate to **Settings > Database Disaster Recovery** and click **Create Live Backup**.
  - **Via API**: `POST /api/admin/backups` (Admin role required).
  - **Stored Location**: `backend/backups/qr_system_backup_YYYYMMDD_HHMMSS.db`.

### B. Offline Restoration Procedure
In the event of database corruption or hardware recovery:

1. **Stop Application Services**:
   ```cmd
   stop.bat
   ```
   *(Or on Linux: `sudo systemctl stop qr-backend qr-frontend`)*

2. **Execute the Restore Utility**:
   ```cmd
   restore.bat
   ```
   *Or via command line:*
   ```bash
   python backend/restore_database.py backend/backups/qr_system_backup_YYYYMMDD_HHMMSS.db
   ```

3. **Restoration Safety Sequence**:
   - The restore tool validates the source backup file (`PRAGMA integrity_check`).
   - A safety snapshot of the active database is created automatically (`qr_system.db.pre_restore_YYYYMMDD_HHMMSS.bak`).
   - Obsolete SQLite journal/WAL/SHM files are removed.
   - The backup file is restored atomically using `os.replace`.
   - Post-restore verification is executed.

4. **Restart Services**:
   ```cmd
   run.bat
   ```

---

## 4. SQLite vs. PostgreSQL Migration Guide

The system currently uses SQLite with declarative SQLAlchemy models.

### When SQLite is Recommended:
* Single-server internal company deployment.
* Up to 50 concurrent operators and 500,000 QR codes.
* WAL mode enabled (`PRAGMA journal_mode=WAL`).

### When to Migrate to PostgreSQL:
* Multi-server deployment with load balancing.
* Concurrent high-throughput writes exceeding 100 assignments/second.
* Centralized enterprise database clustering.

### How to Migrate:
1. Update `DATABASE_URL` in `.env`:
   ```bash
   DATABASE_URL=postgresql://qr_user:PASSWORD@postgres.internal:5432/qr_system
   ```
2. Install PostgreSQL driver: `pip install psycopg2-binary`.
3. Run `init_db()` to automatically generate tables and indexes in PostgreSQL.
