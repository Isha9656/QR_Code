from datetime import datetime
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import QRCode, QRScanEvent, QRStatus
from app.schemas import QRResolveResponse

router = APIRouter(tags=["Scanning"])


UNASSIGNED_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QR Code Not Active</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: #e2e8f0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            text-align: center;
            max-width: 400px;
        }
        .icon {
            font-size: 64px;
            margin-bottom: 24px;
        }
        h1 {
            font-size: 24px;
            margin-bottom: 12px;
            color: #f8fafc;
        }
        p {
            font-size: 16px;
            color: #94a3b8;
            line-height: 1.6;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">🔲</div>
        <h1>This QR code has not been activated yet.</h1>
        <p>Please contact the administrator if you believe this is an error.</p>
    </div>
</body>
</html>"""


DISABLED_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QR Code Disabled</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: #e2e8f0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container { text-align: center; max-width: 400px; }
        .icon { font-size: 64px; margin-bottom: 24px; }
        h1 { font-size: 24px; margin-bottom: 12px; color: #f8fafc; }
        p { font-size: 16px; color: #94a3b8; line-height: 1.6; }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">⚠️</div>
        <h1>This QR code is currently disabled.</h1>
        <p>Please contact the administrator for assistance.</p>
    </div>
</body>
</html>"""


RETIRED_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QR Code Retired</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: #e2e8f0;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container { text-align: center; max-width: 400px; }
        .icon { font-size: 64px; margin-bottom: 24px; }
        h1 { font-size: 24px; margin-bottom: 12px; color: #f8fafc; }
        p { font-size: 16px; color: #94a3b8; line-height: 1.6; }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">🚫</div>
        <h1>This QR code has been retired.</h1>
        <p>This code is no longer in service.</p>
    </div>
</body>
</html>"""


import ipaddress
from app.config import get_settings


def is_ip_in_networks(ip_str: str, networks: list, hosts: set) -> bool:
    """Check if an IP string is in the trusted network/host list."""
    if not ip_str:
        return False
    cleaned = ip_str.strip().lower()
    if cleaned in hosts:
        return True
    try:
        addr = ipaddress.ip_address(cleaned)
        return any(addr in net for net in networks)
    except ValueError:
        return False


def extract_client_ip(request: Request) -> str | None:
    """
    Safely extract the client IP address according to reverse proxy trust boundaries:
    - Never blindly trust forwarded headers from arbitrary clients.
    - Only accept forwarded IP information from explicitly configured trusted proxies.
    - Use direct request client address when no trusted proxy is configured.
    - Safely handle multiple forwarded IP entries (walk from rightmost trusted proxy).
    """
    direct_peer = request.client.host if request.client else None
    if not direct_peer:
        return None

    settings = get_settings()
    trusted_networks = settings.trusted_proxy_networks
    trusted_hosts = settings.trusted_proxy_hosts

    # 1. If no trusted proxies configured, NEVER trust forwarded headers
    if not trusted_networks and not trusted_hosts:
        return direct_peer

    # 2. If direct peer is NOT a trusted proxy, ignore all forwarded headers
    if not is_ip_in_networks(direct_peer, trusted_networks, trusted_hosts):
        return direct_peer

    # 3. Direct peer IS trusted: parse X-Forwarded-For safely from right to left
    xff = request.headers.get("x-forwarded-for")
    if xff:
        # e.g., "forged_client, real_client, proxy1"
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        # Walk from right to left: skip trusted proxies; the first untrusted is the client
        for candidate in reversed(parts):
            if not is_ip_in_networks(candidate, trusted_networks, trusted_hosts):
                try:
                    ipaddress.ip_address(candidate)
                    return candidate
                except ValueError:
                    continue
        # If all candidates were in trusted network, return the leftmost valid IP
        for candidate in parts:
            try:
                ipaddress.ip_address(candidate)
                return candidate
            except ValueError:
                continue

    # 4. Fallback to X-Real-IP if provided, valid, and from trusted proxy
    x_real_ip = request.headers.get("x-real-ip")
    if x_real_ip:
        candidate = x_real_ip.strip()
        try:
            ipaddress.ip_address(candidate)
            return candidate
        except ValueError:
            pass

    return direct_peer


def _anonymize_ip(ip: str | None) -> str | None:
    """
    Anonymize IP address for privacy-safe analytics.
    - IPv4: Zeroes host octet (/24 subnet mask, e.g., 198.51.100.45 -> 198.51.100.0).
    - IPv6: Zeroes host interface (/48 subnet mask, e.g., 2001:db8:85a3:8d3:: -> 2001:db8:85a3::).
    - Non-IP strings / local identifiers -> 'anonymized'.
    - Raw client IP addresses are NEVER stored.
    """
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip.strip())
        if addr.version == 4:
            net = ipaddress.IPv4Network(f"{addr}/24", strict=False)
            return str(net.network_address)
        elif addr.version == 6:
            net = ipaddress.IPv6Network(f"{addr}/48", strict=False)
            return str(net.network_address)
    except ValueError:
        pass
    return "anonymized"


@router.get("/q/{token}")
@router.get("/qr/{token}")
async def public_redirect(token: str, request: Request, db: Session = Depends(get_db)):
    """Public QR redirect endpoint. This is what the printed QR code points to."""
    qr = db.query(QRCode).filter(QRCode.token == token).first()
    
    if not qr:
        return HTMLResponse(content=UNASSIGNED_HTML, status_code=404)
    
    # Log scan event with safely extracted and anonymized client IP
    client_ip = extract_client_ip(request)
    anonymized_ip = _anonymize_ip(client_ip)

    scan_event = QRScanEvent(
        qr_code_id=qr.id,
        result_type=qr.status.value if qr.status != QRStatus.ACTIVE else "redirect",
        user_agent=request.headers.get("user-agent"),
        ip_address=anonymized_ip,
    )
    db.add(scan_event)
    db.commit()
    
    if qr.status == QRStatus.UNASSIGNED:
        return HTMLResponse(content=UNASSIGNED_HTML, status_code=200)
    
    if qr.status == QRStatus.DISABLED:
        return HTMLResponse(content=DISABLED_HTML, status_code=200)
    
    if qr.status == QRStatus.RETIRED:
        return HTMLResponse(content=RETIRED_HTML, status_code=200)
    
    if qr.status == QRStatus.ACTIVE and qr.current_destination:
        return RedirectResponse(url=qr.current_destination, status_code=302)
    
    return HTMLResponse(content=UNASSIGNED_HTML, status_code=200)


@router.get("/api/qr/resolve/{token}", response_model=QRResolveResponse)
async def resolve_qr_api(token: str, db: Session = Depends(get_db)):
    """API endpoint to resolve a QR token (used by the scanner UI)."""
    qr = db.query(QRCode).filter(QRCode.token == token).first()
    
    if not qr:
        return QRResolveResponse(
            status="not_found",
            message="QR code not found in the system",
        )
    
    if qr.status == QRStatus.UNASSIGNED:
        return QRResolveResponse(
            status="unassigned",
            qr_id=qr.qr_id,
            message="This QR code has not been activated yet.",
        )
    
    if qr.status == QRStatus.ACTIVE:
        return QRResolveResponse(
            status="active",
            qr_id=qr.qr_id,
            destination_url=qr.current_destination,
            business_name=qr.current_business_name,
        )
    
    if qr.status == QRStatus.DISABLED:
        return QRResolveResponse(
            status="disabled",
            qr_id=qr.qr_id,
            message="This QR code is currently disabled.",
        )
    
    if qr.status == QRStatus.RETIRED:
        return QRResolveResponse(
            status="retired",
            qr_id=qr.qr_id,
            message="This QR code has been retired.",
        )
    
    return QRResolveResponse(status=qr.status.value, qr_id=qr.qr_id, message="Unknown status")
