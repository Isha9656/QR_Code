import io
import zipfile
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.auth import get_current_user
from app.models import User, QRCode
from app.services.qr_printer import generate_qr_png_bytes, generate_print_pdf
from app.services.qr_generator import get_qr_redirect_url
from app.schemas import PrintRequest

router = APIRouter(prefix="/api/qr/export", tags=["Printing"])


@router.post("/pdf")
async def export_pdf(
    request: PrintRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a printable PDF with selected QR codes."""
    qr_codes = db.query(QRCode).filter(QRCode.id.in_(request.qr_ids)).all()
    
    if not qr_codes:
        raise HTTPException(status_code=404, detail="No QR codes found")
    
    qr_data_list = []
    for qr in qr_codes:
        qr_data_list.append({
            "url": get_qr_redirect_url(qr.token),
            "label": qr.qr_id if request.show_labels else None,
        })
    
    pdf_bytes = generate_print_pdf(
        qr_data_list=qr_data_list,
        qr_size_mm=request.qr_size_mm,
        page_margin_mm=request.page_margin_mm,
        spacing_mm=request.spacing_mm,
        show_labels=request.show_labels,
    )
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=qr_codes.pdf"},
    )


@router.get("/png/{qr_id}")
async def export_png(
    qr_id: int,
    size: int = Query(300, ge=100, le=1000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download a single QR code as PNG."""
    qr = db.query(QRCode).filter(QRCode.id == qr_id).first()
    if not qr:
        raise HTTPException(status_code=404, detail="QR code not found")
    
    url = get_qr_redirect_url(qr.token)
    png_bytes = generate_qr_png_bytes(url, size=size, label=qr.qr_id)
    
    return StreamingResponse(
        io.BytesIO(png_bytes),
        media_type="image/png",
        headers={"Content-Disposition": f"attachment; filename={qr.qr_id}.png"},
    )


@router.post("/zip")
async def export_zip(
    request: PrintRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download multiple QR codes as a ZIP file."""
    qr_codes = db.query(QRCode).filter(QRCode.id.in_(request.qr_ids)).all()
    
    if not qr_codes:
        raise HTTPException(status_code=404, detail="No QR codes found")
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for qr in qr_codes:
            url = get_qr_redirect_url(qr.token)
            png_bytes = generate_qr_png_bytes(url, size=request.qr_size_mm * 10, label=qr.qr_id)
            zip_file.writestr(f"{qr.qr_id}.png", png_bytes)
    
    zip_buffer.seek(0)
    
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=qr_codes.zip"},
    )
