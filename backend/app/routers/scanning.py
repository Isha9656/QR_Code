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


def _anonymize_ip(ip: str | None) -> str | None:
    """Anonymize IP address for privacy-safe analytics (masks host octets)."""
    if not ip:
        return None
    if ":" in ip:  # IPv6
        parts = ip.split(":")
        return ":".join(parts[:3]) + "::xxx" if len(parts) >= 3 else "ipv6"
    parts = ip.split(".")
    if len(parts) == 4:  # IPv4
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0"
    return "anonymized"


@router.get("/q/{token}")
@router.get("/qr/{token}")
async def public_redirect(token: str, request: Request, db: Session = Depends(get_db)):
    """Public QR redirect endpoint. This is what the printed QR code points to."""
    qr = db.query(QRCode).filter(QRCode.token == token).first()
    
    if not qr:
        return HTMLResponse(content=UNASSIGNED_HTML, status_code=404)
    
    # Log scan event (privacy-safe metadata only)
    raw_ip = request.client.host if request.client else None
    scan_event = QRScanEvent(
        qr_code_id=qr.id,
        result_type=qr.status.value if qr.status != QRStatus.ACTIVE else "redirect",
        user_agent=request.headers.get("user-agent"),
        ip_address=_anonymize_ip(raw_ip),
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
