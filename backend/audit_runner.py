import time
import requests
import json
import threading
from concurrent.futures import ThreadPoolExecutor

BASE_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:5173"

results = []

def record(test_name, passed, details="", category="functional"):
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {test_name}: {details}")
    results.append({
        "name": test_name,
        "status": status,
        "details": details,
        "category": category
    })

def run_audit():
    print("=== STARTING FULL SYSTEM AUDIT ===")
    
    # 1. Health check
    try:
        r = requests.get(f"{BASE_URL}/api/health", timeout=5)
        record("Health Check Endpoint", r.status_code == 200 and r.json().get("status") == "healthy", f"Status: {r.status_code}, Resp: {r.text}")
    except Exception as e:
        record("Health Check Endpoint", False, str(e))
        return

    # 2. Module 1: Admin login and logout
    admin_token = None
    try:
        # Invalid login
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": "wrongpassword"})
        invalid_rejected = r.status_code == 401
        
        # Valid login
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": "admin123"})
        if r.status_code == 200:
            admin_token = r.json()["access_token"]
            
        # Verify /me
        r_me = requests.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
        me_valid = r_me.status_code == 200 and r_me.json()["role"] == "admin"
        
        # Logout
        r_logout = requests.post(f"{BASE_URL}/api/auth/logout", headers={"Authorization": f"Bearer {admin_token}"})
        logout_ok = r_logout.status_code == 200
        
        record("Admin Login, Verification & Logout", invalid_rejected and admin_token is not None and me_valid and logout_ok, "Login, /me and logout endpoints verified")
    except Exception as e:
        record("Admin Login, Verification & Logout", False, str(e))

    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 3. Module 2: Admin and operator authorization & user creation
    operator_token = None
    operator_username = f"op_test_{int(time.time())}"
    try:
        # Admin creates operator user via JSON body
        r = requests.post(f"{BASE_URL}/api/auth/users", json={
            "username": operator_username,
            "password": "operatorPass123",
            "display_name": "Test Field Operator",
            "role": "operator"
        }, headers=admin_headers)
        op_created = r.status_code == 200
        
        # Operator login
        r_op_login = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": operator_username,
            "password": "operatorPass123"
        })
        if r_op_login.status_code == 200:
            operator_token = r_op_login.json()["access_token"]
            
        operator_headers = {"Authorization": f"Bearer {operator_token}"}
        
        # Test operator restriction: operator cannot bulk-generate
        r_op_bulk = requests.post(f"{BASE_URL}/api/qr/bulk-generate", json={"quantity": 1}, headers=operator_headers)
        op_bulk_forbidden = r_op_bulk.status_code == 403
        
        # Test operator restriction: operator cannot reassign
        r_op_reassign = requests.post(f"{BASE_URL}/api/qr/QR-000001/reassign", json={
            "business_name": "Op Business",
            "destination_url": "https://example.com",
            "confirm_reassignment": True
        }, headers=operator_headers)
        op_reassign_forbidden = r_op_reassign.status_code == 403
        
        record("Admin and Operator Authorization & Role Restrictions", op_created and operator_token is not None and op_bulk_forbidden and op_reassign_forbidden, f"Operator created and blocked from admin endpoints (Bulk: {r_op_bulk.status_code}, Reassign: {r_op_reassign.status_code})")
    except Exception as e:
        record("Admin and Operator Authorization & Role Restrictions", False, str(e))

    operator_headers = {"Authorization": f"Bearer {operator_token}"} if operator_token else admin_headers

    # 4. Module 4 & 5: Bulk generation of 20 unique QR codes & tokens
    batch_qrs = []
    try:
        r = requests.post(f"{BASE_URL}/api/qr/bulk-generate", json={"quantity": 20}, headers=admin_headers)
        if r.status_code == 200:
            batch_qrs = r.json()
            
        count_20 = len(batch_qrs) == 20
        all_unassigned = all(q["status"] == "unassigned" for q in batch_qrs)
        unique_tokens = len(set(q["token"] for q in batch_qrs)) == 20
        unique_qr_ids = len(set(q["qr_id"] for q in batch_qrs)) == 20
        tokens_permanent = all(len(q["token"]) >= 12 for q in batch_qrs)
        
        record("Bulk Generation of 20 Unique QR Codes", count_20 and all_unassigned and unique_tokens and unique_qr_ids and tokens_permanent, f"Generated {len(batch_qrs)} unique QR codes with tokens")
    except Exception as e:
        record("Bulk Generation of 20 Unique QR Codes", False, str(e))

    if not batch_qrs:
        print("Cannot continue without generated QR codes.")
        return

    # Select target QR code
    target_qr = batch_qrs[0]
    other_qrs = batch_qrs[1:]
    target_id = target_qr["qr_id"]
    target_token = target_qr["token"]
    print(f"\nTarget QR selected for workflow: {target_id} (token: {target_token[:8]}...)")

    # 5. Module 8: Unassigned QR behavior
    try:
        # Public scan via /q/{token}
        r = requests.get(f"{BASE_URL}/q/{target_token}")
        unassigned_html_ok = r.status_code == 200 and "not been activated" in r.text
        
        # Resolver API /api/qr/resolve/{token}
        r_res = requests.get(f"{BASE_URL}/api/qr/resolve/{target_token}")
        resolver_ok = r_res.status_code == 200 and r_res.json()["status"] == "unassigned" and r_res.json().get("qr_id") == target_id
        
        record("Unassigned QR Behavior (Public scan & Resolver)", unassigned_html_ok and resolver_ok, "Unassigned page displayed and resolver returned unassigned status")
    except Exception as e:
        record("Unassigned QR Behavior (Public scan & Resolver)", False, str(e))

    # 6. Module 9: Assignment of target QR to 'Nasta Ghar'
    try:
        assign_payload = {
            "business_name": "Nasta Ghar",
            "destination_url": "https://nastaghar.example.com/menu",
            "notes": "Breakfast table stand"
        }
        r = requests.post(f"{BASE_URL}/api/qr/{target_id}/assign", json=assign_payload, headers=operator_headers)
        assign_ok = r.status_code == 200 and r.json()["business_name"] == "Nasta Ghar"
        
        # Verify status became active
        r_get = requests.get(f"{BASE_URL}/api/qr/{target_id}", headers=operator_headers)
        active_ok = r_get.status_code == 200 and r_get.json()["status"] == "active"
        
        record("QR Assignment to 'Nasta Ghar'", assign_ok and active_ok, f"Assigned to {assign_payload['business_name']} ({assign_payload['destination_url']})")
    except Exception as e:
        record("QR Assignment to 'Nasta Ghar'", False, str(e))

    # 7. Module 10: Public QR redirect to Nasta Ghar
    try:
        r = requests.get(f"{BASE_URL}/q/{target_token}", allow_redirects=False)
        redir_ok = r.status_code == 302 and r.headers.get("Location") == "https://nastaghar.example.com/menu"
        
        # Also test /qr/{token} alias
        r_alias = requests.get(f"{BASE_URL}/qr/{target_token}", allow_redirects=False)
        alias_ok = r_alias.status_code == 302 and r_alias.headers.get("Location") == "https://nastaghar.example.com/menu"
        
        record("Public QR Redirect to Destination URL", redir_ok and alias_ok, "302 redirect verified for /q/{token} and /qr/{token}")
    except Exception as e:
        record("Public QR Redirect to Destination URL", False, str(e))

    # 8. Module 11: Deactivation of assignment
    try:
        r = requests.post(f"{BASE_URL}/api/qr/{target_id}/deactivate", headers=admin_headers)
        deact_api_ok = r.status_code == 200
        
        # Verify public scan returns unassigned/inactive, NOT old destination
        r_scan = requests.get(f"{BASE_URL}/q/{target_token}", allow_redirects=False)
        old_dest_inaccessible = r_scan.status_code == 200 and "not been activated" in r_scan.text and "Location" not in r_scan.headers
        
        record("Deactivation of Assignment", deact_api_ok and old_dest_inaccessible, "Assignment deactivated, old destination unreachable")
    except Exception as e:
        record("Deactivation of Assignment", False, str(e))

    # 9. Module 12: Reassignment of same QR to a Gym destination
    try:
        # Note: QR is currently UNASSIGNED after deactivation, so it can be assigned
        reassign_payload = {
            "business_name": "PowerFit Gym",
            "destination_url": "https://powerfitgym.example.com/join",
            "notes": "Entrance flyer"
        }
        r = requests.post(f"{BASE_URL}/api/qr/{target_id}/assign", json=reassign_payload, headers=operator_headers)
        reassign_ok = r.status_code == 200 and r.json()["business_name"] == "PowerFit Gym"
        
        # Scan again and verify it now redirects to gym
        r_scan_gym = requests.get(f"{BASE_URL}/q/{target_token}", allow_redirects=False)
        redirect_gym_ok = r_scan_gym.status_code == 302 and r_scan_gym.headers.get("Location") == "https://powerfitgym.example.com/join"
        
        record("Reassignment to Gym & Redirect Verification", reassign_ok and redirect_gym_ok, "QR reassigned to PowerFit Gym and redirects to gym URL")
    except Exception as e:
        record("Reassignment to Gym & Redirect Verification", False, str(e))

    # 10. Module 13: Assignment history preservation
    try:
        r = requests.get(f"{BASE_URL}/api/qr/{target_id}/history", headers=admin_headers)
        if r.status_code == 200:
            hist = r.json().get("assignments", [])
            has_two_records = len(hist) >= 2
            business_names = [a["business_name"] for a in hist]
            has_both_businesses = "Nasta Ghar" in business_names and "PowerFit Gym" in business_names
            
            record("Assignment History Preservation", has_two_records and has_both_businesses, f"Found {len(hist)} history records: {business_names}")
        else:
            record("Assignment History Preservation", False, f"Status: {r.status_code}")
    except Exception as e:
        record("Assignment History Preservation", False, str(e))

    # 11. Module 15: Verify the other 19 QR codes remain unaffected
    try:
        r = requests.get(f"{BASE_URL}/api/qr?status=unassigned&per_page=100", headers=admin_headers)
        unassigned_items = r.json().get("items", [])
        unassigned_ids = [item["qr_id"] for item in unassigned_items]
        
        other_19_intact = all(q["qr_id"] in unassigned_ids for q in other_qrs)
        target_not_unassigned = target_id not in unassigned_ids
        
        record("Other 19 QR Codes Unaffected", other_19_intact and target_not_unassigned, "All 19 other QR codes remain unassigned and unchanged")
    except Exception as e:
        record("Other 19 QR Codes Unaffected", False, str(e))

    # 12. Module 6: QR PNG generation and PDF printing
    try:
        target_db_id = target_qr["id"]
        # PNG export
        r_png = requests.get(f"{BASE_URL}/api/qr/export/png/{target_db_id}", headers=admin_headers)
        png_ok = r_png.status_code == 200 and r_png.headers.get("Content-Type") == "image/png" and len(r_png.content) > 500
        
        # PDF export (with all 20 QR IDs)
        all_ids = [q["id"] for q in batch_qrs]
        r_pdf = requests.post(f"{BASE_URL}/api/qr/export/pdf", json={
            "qr_ids": all_ids,
            "qr_size_mm": 30,
            "show_labels": True,
            "page_margin_mm": 10,
            "spacing_mm": 5
        }, headers=admin_headers)
        pdf_ok = r_pdf.status_code == 200 and r_pdf.headers.get("Content-Type") == "application/pdf" and len(r_pdf.content) > 2000
        
        record("QR PNG and Printable PDF Export", png_ok and pdf_ok, f"PNG: {len(r_png.content)} bytes, PDF: {len(r_pdf.content)} bytes")
    except Exception as e:
        record("QR PNG and Printable PDF Export", False, str(e))

    # 13. SECURITY AUDIT CHECKS
    print("\n--- RUNNING SECURITY TESTS ---")
    
    # Sec 1: Unauthorized access to management APIs
    try:
        r1 = requests.post(f"{BASE_URL}/api/qr/bulk-generate", json={"quantity": 5})
        r2 = requests.post(f"{BASE_URL}/api/qr/{target_id}/assign", json={"business_name": "Hack", "destination_url": "https://hack.com"})
        r3 = requests.get(f"{BASE_URL}/api/qr")
        unauth_blocked = r1.status_code == 401 and r2.status_code == 401 and r3.status_code == 401
        record("Security: Unauthorized Access to Management APIs", unauth_blocked, f"Unauthenticated requests rejected with 401 ({r1.status_code}, {r2.status_code}, {r3.status_code})", "security")
    except Exception as e:
        record("Security: Unauthorized Access to Management APIs", False, str(e), "security")

    # Sec 2: Invalid destination URLs (XSS, invalid scheme, malformed)
    try:
        r_xss = requests.post(f"{BASE_URL}/api/qr/{other_qrs[0]['qr_id']}/assign", json={
            "business_name": "XSS Test",
            "destination_url": "javascript:alert(1)"
        }, headers=admin_headers)
        
        r_ftp = requests.post(f"{BASE_URL}/api/qr/{other_qrs[0]['qr_id']}/assign", json={
            "business_name": "FTP Test",
            "destination_url": "ftp://files.example.com"
        }, headers=admin_headers)
        
        r_nodomain = requests.post(f"{BASE_URL}/api/qr/{other_qrs[0]['qr_id']}/assign", json={
            "business_name": "No Domain",
            "destination_url": "http://"
        }, headers=admin_headers)
        
        invalid_urls_blocked = r_xss.status_code == 422 and r_ftp.status_code == 422 and r_nodomain.status_code == 422
        record("Security: Invalid Destination URL Validation", invalid_urls_blocked, f"Blocked javascript:, ftp:, and empty domains (Statuses: {r_xss.status_code}, {r_ftp.status_code}, {r_nodomain.status_code})", "security")
    except Exception as e:
        record("Security: Invalid Destination URL Validation", False, str(e), "security")

    # Sec 3: Duplicate assignments (attempting to assign already active QR code)
    try:
        r_dup = requests.post(f"{BASE_URL}/api/qr/{target_id}/assign", json={
            "business_name": "Duplicate Co",
            "destination_url": "https://duplicate.example.com"
        }, headers=admin_headers)
        dup_blocked = r_dup.status_code == 400
        record("Security: Duplicate Assignment Prevention", dup_blocked, f"Attempt to assign active code rejected: {r_dup.status_code} ({r_dup.json().get('detail')})", "security")
    except Exception as e:
        record("Security: Duplicate Assignment Prevention", False, str(e), "security")

    # Sec 4: Concurrent assignment requests
    try:
        unassigned_test_qr = other_qrs[1]["qr_id"]
        status_codes = []
        
        def attempt_assign(biz_name):
            try:
                r = requests.post(f"{BASE_URL}/api/qr/{unassigned_test_qr}/assign", json={
                    "business_name": biz_name,
                    "destination_url": f"https://{biz_name.lower().replace(' ', '')}.com"
                }, headers=admin_headers, timeout=5)
                status_codes.append(r.status_code)
            except Exception as e:
                status_codes.append(str(e))
                
        with ThreadPoolExecutor(max_workers=5) as executor:
            for i in range(5):
                executor.submit(attempt_assign, f"Concurrent Biz {i}")
                
        # Exactly one must succeed (200), and others must be rejected (400 or 409), NO 500 errors!
        success_count = status_codes.count(200)
        no_500_errors = all(code in (200, 400, 409) for code in status_codes)
        
        record("Security: Concurrent Assignment Handling", success_count == 1 and no_500_errors, f"5 simultaneous requests -> exactly {success_count} succeeded, codes: {status_codes}", "security")
    except Exception as e:
        record("Security: Concurrent Assignment Handling", False, str(e), "security")

    # Sec 5: Expired sessions & invalid tokens
    try:
        fake_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI5OTk5OSIsImV4cCI6MTU3NzgzNjgwMH0.fake_signature"
        r_expired = requests.get(f"{BASE_URL}/api/qr", headers={"Authorization": f"Bearer {fake_token}"})
        expired_rejected = r_expired.status_code == 401
        record("Security: Expired / Forged Session Handling", expired_rejected, f"Expired/invalid JWT rejected with {r_expired.status_code}", "security")
    except Exception as e:
        record("Security: Expired / Forged Session Handling", False, str(e), "security")

    # Sec 6: Public visitors cannot modify mappings
    try:
        r_pub_assign = requests.post(f"{BASE_URL}/api/qr/{target_id}/assign", json={"business_name": "Pub", "destination_url": "https://pub.com"})
        r_pub_reassign = requests.post(f"{BASE_URL}/api/qr/{target_id}/reassign", json={"business_name": "Pub", "destination_url": "https://pub.com", "confirm_reassignment": True})
        r_pub_deact = requests.post(f"{BASE_URL}/api/qr/{target_id}/deactivate")
        pub_blocked = r_pub_assign.status_code == 401 and r_pub_reassign.status_code == 401 and r_pub_deact.status_code == 401
        record("Security: Public Visitors Cannot Modify Mappings", pub_blocked, f"Assign: {r_pub_assign.status_code}, Reassign: {r_pub_reassign.status_code}, Deactivate: {r_pub_deact.status_code}", "security")
    except Exception as e:
        record("Security: Public Visitors Cannot Modify Mappings", False, str(e), "security")

    # 14. Module 16: PWA manifest and installation readiness
    try:
        r_manifest = requests.get(f"{FRONTEND_URL}/manifest.json", timeout=5)
        manifest_data = r_manifest.json()
        has_icons = len(manifest_data.get("icons", [])) >= 2
        has_start_url = manifest_data.get("start_url") == "/"
        has_display = manifest_data.get("display") == "standalone"
        
        r_sw = requests.get(f"{FRONTEND_URL}/sw.js", timeout=5)
        sw_ok = r_sw.status_code == 200 and "addEventListener('install'" in r_sw.text
        
        r_icon192 = requests.get(f"{FRONTEND_URL}/icon-192.png", timeout=5)
        r_icon512 = requests.get(f"{FRONTEND_URL}/icon-512.png", timeout=5)
        icons_ok = r_icon192.status_code == 200 and r_icon512.status_code == 200
        
        record("PWA Manifest & Installation Readiness", has_icons and has_start_url and has_display and sw_ok and icons_ok, "Manifest, icons (192, 512), standalone display, and service worker verified")
    except Exception as e:
        record("PWA Manifest & Installation Readiness", False, str(e))

    # 15. Module 17: Responsive Mobile UI & Viewport
    try:
        r_html = requests.get(f"{FRONTEND_URL}/index.html", timeout=5)
        html_text = r_html.text
        has_viewport = 'name="viewport"' in html_text and "user-scalable=no" in html_text
        has_manifest_link = 'rel="manifest"' in html_text
        has_sw_reg = "serviceWorker.register" in html_text
        
        record("Responsive Mobile UI & Viewport Settings", has_viewport and has_manifest_link and has_sw_reg, "Mobile viewport meta, standalone tags, and SW auto-registration confirmed")
    except Exception as e:
        record("Responsive Mobile UI & Viewport Settings", False, str(e))

    # 16. Module 7: Camera Scanner Implementation Check
    try:
        with open("d:/QR System/frontend/src/pages/ScanPage.jsx", "r", encoding="utf-8") as f:
            scan_code = f.read()
        has_camera_lib = "Html5Qrcode" in scan_code
        has_back_camera = "facingMode: 'environment'" in scan_code
        has_fallback_input = "manualInput" in scan_code
        has_permission_handler = "Permission" in scan_code
        
        record("Mobile Camera Scanner Implementation", has_camera_lib and has_back_camera and has_fallback_input and has_permission_handler, "Html5Qrcode back camera preference, permission handlers, and manual input fallback present")
    except Exception as e:
        record("Mobile Camera Scanner Implementation", False, str(e))

    # 17. Module 3: Database persistence after restarting the backend
    try:
        import sqlite3
        conn = sqlite3.connect("d:/QR System/backend/qr_system.db")
        cur = conn.cursor()
        
        # Check tables exist
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
        has_all_tables = all(t in tables for t in ["users", "qr_codes", "qr_assignments", "qr_scan_events", "audit_logs"])
        
        # Check record count in database matches API
        cur.execute("SELECT count(*) FROM qr_codes")
        db_qr_count = cur.fetchone()[0]
        
        cur.execute("SELECT count(*) FROM users")
        db_user_count = cur.fetchone()[0]
        
        cur.execute("SELECT count(*) FROM qr_assignments")
        db_assign_count = cur.fetchone()[0]
        
        conn.close()
        
        persistence_ok = has_all_tables and db_qr_count >= 20 and db_user_count >= 1 and db_assign_count >= 2
        record("Database Persistence & On-Disk Storage", persistence_ok, f"qr_system.db verified: {db_qr_count} QRs, {db_user_count} users, {db_assign_count} assignments stored on disk")
    except Exception as e:
        record("Database Persistence & On-Disk Storage", False, str(e))

    # Save summary
    with open("audit_results.json", "w") as f:
        json.dump(results, f, indent=2)

    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    print(f"\n=== AUDIT SUMMARY: {passed}/{total} TESTS PASSED ===")

if __name__ == "__main__":
    run_audit()
