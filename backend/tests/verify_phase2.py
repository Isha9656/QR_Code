import urllib.request
import json
import sys

BASE_URL = 'http://localhost:8000'

def request(endpoint, method='GET', data=None, token=None):
    url = f'{BASE_URL}{endpoint}'
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    req_data = json.dumps(data).encode('utf-8') if data else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content_type = resp.headers.get('Content-Type', '')
            if 'application/pdf' in content_type:
                return resp.status, resp.read(), content_type
            body = resp.read().decode('utf-8')
            return resp.status, json.loads(body) if body else {}, content_type
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = body
        return e.code, parsed, ''

print('=== 1. Login ===')
status, data, _ = request('/api/auth/login', 'POST', {'username': 'admin', 'password': 'admin123'})
assert status == 200, f'Login failed: {data}'
jwt_token = data['access_token']
print('Login successful. Token acquired.')

print('\n=== 2. Check QR Inventory Stats ===')
status, stats, _ = request('/api/qr/stats', token=jwt_token)
assert status == 200, f'Stats failed: {stats}'
print('Initial Inventory Stats:', stats)
assert 'total' in stats and 'unassigned' in stats and 'active' in stats

print('\n=== 3. Bulk Generate 10 QR Codes ===')
status, new_qrs, _ = request('/api/qr/bulk-generate', 'POST', {'quantity': 10}, token=jwt_token)
assert status == 200, f'Bulk generate failed: {new_qrs}'
assert len(new_qrs) == 10
new_ids = [q['id'] for q in new_qrs]
print(f'Generated 10 codes: IDs {new_ids}')

print('\n=== 4. Verify Updated Stats ===')
status, stats2, _ = request('/api/qr/stats', token=jwt_token)
assert stats2['unassigned'] >= stats['unassigned'] + 10
print('Updated Inventory Stats:', stats2)

print('\n=== 5. Bulk Printing Studio Preview ===')
preview_payload = {
    'qr_ids': new_ids[:6],
    'qr_size_mm': 35,
    'page_margin_mm': 12,
    'spacing_mm': 6,
    'show_labels': True,
    'company_name': 'INTERNAL QR MANAGEMENT',
    'header_text': 'OFFICIAL ASSET STICKERS',
    'footer_text': 'Scan with internal camera',
    'unassigned_only': True
}
status, preview, _ = request('/api/qr/export/studio-preview', 'POST', preview_payload, token=jwt_token)
assert status == 200, f'Preview failed: {preview}'
print('Preview Layout Result:')
print(f"  Columns: {preview['cols']}, Rows: {preview['rows']}")
print(f"  Codes Per Page: {preview['qrs_per_page']}, Total Pages: {preview['total_pages']}")
assert preview['qrs_per_page'] > 0
assert preview['total_pages'] >= 1

print('\n=== 6. Bulk Printing Studio PDF Generation ===')
status, pdf_bytes, ctype = request('/api/qr/export/studio-pdf', 'POST', preview_payload, token=jwt_token)
assert status == 200, f'PDF generation failed: {status}'
assert 'application/pdf' in ctype
assert pdf_bytes.startswith(b'%PDF'), 'Not a valid PDF'
print(f'Generated valid A4 PDF: {len(pdf_bytes)} bytes')

print('\n=== 7. Strict Unassigned Verification: Assign a Code & Test Reject in Studio ===')
target_qr = new_qrs[0]
target_id = target_qr['id']
status, assign_resp, _ = request(f'/api/qr/{target_id}/assign', 'POST', {
    'business_name': 'Phase 2 Test Enterprise',
    'destination_url': 'https://phase2.internal.example.com',
    'notes': 'Warehouse Bin #42'
}, token=jwt_token)
assert status == 200, f'Assignment failed: {assign_resp}'
assert assign_resp['is_active'] == True
print(f'Assigned QR {target_id} to Phase 2 Test Enterprise')

# Now attempt to print target_id in bulk studio
forbidden_payload = {
    'qr_ids': [target_id],
    'unassigned_only': True
}
status, err_resp, _ = request('/api/qr/export/studio-pdf', 'POST', forbidden_payload, token=jwt_token)
print(f'Attempting to print active QR {target_id} returned HTTP {status}: {err_resp}')
assert status == 400, f'Expected 400 Bad Request, got {status}'
assert 'non-unassigned' in str(err_resp).lower(), 'Expected unassigned error message'
print('Strict unassigned check verified: non-unassigned codes are rejected!')

print('\n=== 8. Reassignment & History Preservation ===')
status, reassign_resp, _ = request(f'/api/qr/{target_id}/reassign', 'POST', {
    'business_name': 'Phase 2 Secondary Logistics',
    'destination_url': 'https://secondary.internal.example.com',
    'notes': 'Dock B Shipping',
    'confirm_reassignment': True
}, token=jwt_token)
assert status == 200, f'Reassignment failed: {reassign_resp}'

# Check history endpoint
status, history_resp, _ = request(f'/api/qr/{target_id}/history', token=jwt_token)
assert status == 200
history = history_resp['assignments']
print(f'Preserved History Count: {len(history)}')
assert len(history) == 2, f'Expected 2 history items, got {len(history)}'
print('History (Latest first):', history[0]['business_name'], '->', history[0]['destination_url'], f'(Active: {history[0]["is_active"]})')
print('History (Previous):', history[1]['business_name'], '->', history[1]['destination_url'], f'(Active: {history[1]["is_active"]})')

print('\n=== 9. Business Autocomplete Directory ===')
status, businesses, _ = request('/api/qr/businesses', token=jwt_token)
assert status == 200
print('Businesses list:', businesses)
assert 'Phase 2 Test Enterprise' in businesses
assert 'Phase 2 Secondary Logistics' in businesses

print('\n=== 10. Public QR Resolver Test ===')
token = target_qr['token']
status, resolve_resp, _ = request(f'/api/qr/resolve/{token}')
assert status == 200
assert resolve_resp['destination_url'] == 'https://secondary.internal.example.com'
print(f'Token {token} correctly resolved to active destination: {resolve_resp["destination_url"]}')

print('\n>>> ALL 10 PHASE 2 END-TO-END VERIFICATION CHECKS PASSED SUCCESSFULLY! <<<')
