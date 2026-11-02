#!/usr/bin/env python3
"""
Offline Database Recovery & Restore CLI
Internal QR Management System

This tool safely restores the SQLite database from a validated backup.
Requirements:
1. Stop the backend server before restoring.
2. An automatic safety snapshot of the current active database is created first.
3. WAL and SHM files are cleaned up to prevent lock or transaction log mismatch.
4. The restored database is verified with PRAGMA integrity_check before completing.
"""

import os
import sys
import shutil
import sqlite3
from datetime import datetime

# Path references
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BACKEND_DIR, "qr_system.db")
DEFAULT_BACKUP_DIR = os.path.join(BACKEND_DIR, "backups")


def validate_file(filepath: str) -> bool:
    if not os.path.exists(filepath):
        print(f"[!] Error: Backup file not found at: {filepath}")
        return False
    
    if os.path.getsize(filepath) < 100:
        print("[!] Error: File size too small to be a valid SQLite database.")
        return False

    with open(filepath, "rb") as f:
        if f.read(16) != b"SQLite format 3\x00":
            print("[!] Error: File is not a valid SQLite database (magic header mismatch).")
            return False
            
    try:
        conn = sqlite3.connect(filepath)
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        res = cur.fetchone()
        conn.close()
        if res and res[0] == "ok":
            return True
        print(f"[!] Integrity check failed: {res}")
        return False
    except Exception as e:
        print(f"[!] SQLite verification error: {e}")
        return False


def restore_database(backup_file: str, target_db: str = DEFAULT_DB_PATH):
    print("=" * 60)
    print("      INTERNAL QR SYSTEM - DATABASE RESTORE UTILITY")
    print("=" * 60)
    print(f"Target Database : {target_db}")
    print(f"Backup Source   : {backup_file}")
    print()

    # 1. Validate source backup
    print("[1/5] Validating backup integrity...")
    if not validate_file(backup_file):
        print("[ERROR] Backup validation failed. Aborting restoration.")
        sys.exit(1)
    print("      [+] Backup file is valid and intact.")

    # 2. Check if current database exists and create pre-restore safety snapshot
    print("[2/5] Creating pre-restore safety snapshot...")
    if os.path.exists(target_db):
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safety_path = f"{target_db}.pre_restore_{timestamp}.bak"
        try:
            shutil.copy2(target_db, safety_path)
            print(f"      [+] Safety snapshot saved: {os.path.basename(safety_path)}")
        except Exception as e:
            print(f"[ERROR] Failed to create safety snapshot: {e}")
            sys.exit(1)
    else:
        print("      [i] No existing database found at target; proceeding with fresh restore.")

    # 3. Clean up existing WAL and SHM journal files
    print("[3/5] Cleaning up WAL and SHM journal files...")
    for ext in ["-wal", "-shm", "-journal"]:
        sidecar = target_db + ext
        if os.path.exists(sidecar):
            try:
                os.remove(sidecar)
                print(f"      [+] Removed stale journal: {os.path.basename(sidecar)}")
            except Exception as e:
                print(f"[WARNING] Could not remove journal file {sidecar}: {e}")

    # 4. Atomically copy the backup file to destination
    print("[4/5] Restoring database file...")
    temp_target = target_db + ".restoring_tmp"
    try:
        shutil.copy2(backup_file, temp_target)
        os.replace(temp_target, target_db)
        print("      [+] Database file replaced atomically.")
    except Exception as e:
        if os.path.exists(temp_target):
            os.remove(temp_target)
        print(f"[ERROR] Failed to restore database: {e}")
        sys.exit(1)

    # 5. Final integrity verification on target
    print("[5/5] Performing post-restore integrity check...")
    if not validate_file(target_db):
        print("[ERROR] Post-restore integrity check failed!")
        sys.exit(1)
    print("      [+] Restored database integrity verified successfully (PRAGMA integrity_check: ok).")

    print()
    print("=" * 60)
    print("[SUCCESS] Database restoration completed successfully!")
    print("You may now restart the application services.")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        backup_arg = sys.argv[1]
    else:
        # Check backups directory for latest backup
        if os.path.exists(DEFAULT_BACKUP_DIR):
            files = [os.path.join(DEFAULT_BACKUP_DIR, f) for f in os.listdir(DEFAULT_BACKUP_DIR) if f.endswith(".db")]
            if files:
                files.sort(key=os.path.getmtime, reverse=True)
                backup_arg = files[0]
                print(f"[i] Using most recent backup: {os.path.basename(backup_arg)}")
            else:
                print(f"[ERROR] No .db backup files found in {DEFAULT_BACKUP_DIR}")
                print("Usage: python restore_database.py <path_to_backup_file.db>")
                sys.exit(1)
        else:
            print("Usage: python restore_database.py <path_to_backup_file.db>")
            sys.exit(1)

    restore_database(backup_arg)
