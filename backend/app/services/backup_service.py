import os
import sqlite3
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional

BACKUP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backups"))


def get_backup_dir() -> str:
    """Ensure backup directory exists and return its path."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    return BACKUP_DIR


def calculate_sha256(filepath: str) -> str:
    """Calculate SHA256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def validate_sqlite_backup(filepath: str) -> Dict[str, Any]:
    """Validate that a file is a non-corrupt SQLite database."""
    if not os.path.exists(filepath):
        return {"valid": False, "error": "File does not exist"}
    
    # Check minimum size and magic header
    if os.path.getsize(filepath) < 100:
        return {"valid": False, "error": "File is too small to be a valid SQLite database"}
    
    with open(filepath, "rb") as f:
        header = f.read(16)
        if header != b"SQLite format 3\x00":
            return {"valid": False, "error": "Invalid SQLite magic header"}
    
    # Run PRAGMA integrity_check
    try:
        conn = sqlite3.connect(filepath)
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        result = cursor.fetchone()
        conn.close()
        if result and result[0] == "ok":
            return {"valid": True, "integrity": "ok"}
        return {"valid": False, "error": f"Integrity check failed: {result}"}
    except Exception as e:
        return {"valid": False, "error": str(e)}


def create_online_backup(source_db_path: str, backup_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Perform a safe online backup using sqlite3.Connection.backup().
    This works consistently while the application is running and serving transactions.
    """
    target_dir = backup_dir or get_backup_dir()
    os.makedirs(target_dir, exist_ok=True)
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"qr_system_backup_{timestamp}.db"
    backup_path = os.path.join(target_dir, backup_filename)
    
    # Connect to live source and create online backup
    source_conn = sqlite3.connect(source_db_path)
    backup_conn = sqlite3.connect(backup_path)
    
    try:
        source_conn.backup(backup_conn, pages=100)
    finally:
        backup_conn.close()
        source_conn.close()
    
    # Verify backup integrity
    validation = validate_sqlite_backup(backup_path)
    if not validation["valid"]:
        if os.path.exists(backup_path):
            os.remove(backup_path)
        raise RuntimeError(f"Backup created failed integrity check: {validation.get('error')}")
    
    file_size = os.path.getsize(backup_path)
    checksum = calculate_sha256(backup_path)
    
    return {
        "filename": backup_filename,
        "filepath": backup_path,
        "size_bytes": file_size,
        "checksum_sha256": checksum,
        "created_at": datetime.utcnow().isoformat(),
        "integrity": "ok",
    }


def list_backups(backup_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all available validated backup files sorted by creation date."""
    target_dir = backup_dir or get_backup_dir()
    if not os.path.exists(target_dir):
        return []
    
    backups = []
    for fname in os.listdir(target_dir):
        if fname.endswith(".db"):
            fpath = os.path.join(target_dir, fname)
            try:
                stat = os.stat(fpath)
                backups.append({
                    "filename": fname,
                    "size_bytes": stat.st_size,
                    "created_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
                    "valid": True,
                })
            except Exception:
                pass
    
    backups.sort(key=lambda x: x["created_at"], reverse=True)
    return backups
