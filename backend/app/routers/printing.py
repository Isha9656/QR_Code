import io
import zipfile
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.auth import get_current_user, get_admin_user
from app.models import User, QRCode, QRStatus
from app.services.qr_printer import generate_qr_png_bytes, generate_print_pdf, calculate_sheet_layout
from app.services.qr_generator import get_qr_redirect_url
from app.schemas import PrintRequest, PrintStudioRequest, PrintStudioPreviewResponse

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


@router.post("/studio-preview", response_model=PrintStudioPreviewResponse)
async def studio_sheet_preview(
    request: PrintStudioRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Calculate layout and sample preview for Bulk Printing Studio."""
    unassigned_count = db.query(QRCode).filter(QRCode.status == QRStatus.UNASSIGNED).count()
    
    # Resolve target QR count and sample codes
    if request.qr_ids and len(request.qr_ids) > 0:
        query = db.query(QRCode).filter(QRCode.id.in_(request.qr_ids))
        if request.unassigned_only:
            non_unassigned = query.filter(QRCode.status != QRStatus.UNASSIGNED).all()
            if non_unassigned:
                names = [q.qr_id for q in non_unassigned[:5]]
                raise HTTPException(
                    status_code=400,
                    detail=f"Only unassigned QR codes can be printed in Bulk Printing Studio. Selected non-unassigned: {', '.join(names)}",
                )
        selected_qrs = query.all()
        total_items = len(selected_qrs)
        sample_qrs = [{"qr_id": q.qr_id, "token": q.token, "status": q.status.value} for q in selected_qrs[:24]]
    else:
        total_items = request.quantity if request.quantity else min(50, unassigned_count)
        sample_rows = db.query(QRCode).filter(QRCode.status == QRStatus.UNASSIGNED).order_by(QRCode.id.asc()).limit(min(total_items, 24)).all()
        sample_qrs = [{"qr_id": q.qr_id, "token": q.token, "status": q.status.value} for q in sample_rows]
    
    layout = calculate_sheet_layout(
        total_items=total_items,
        qr_size_mm=request.qr_size_mm,
        page_margin_mm=request.page_margin_mm,
        spacing_mm=request.spacing_mm,
        show_labels=request.show_labels,
        has_header=bool(request.company_name or request.header_text),
        has_footer=bool(request.footer_text),
        custom_cols=request.custom_cols,
        custom_rows=request.custom_rows,
    )
    
    return PrintStudioPreviewResponse(
        total_qrs=total_items,
        unassigned_available=unassigned_count,
        qr_size_mm=request.qr_size_mm,
        cols=layout["cols"],
        rows=layout["rows"],
        qrs_per_page=layout["qrs_per_page"],
        total_pages=layout["total_pages"],
        page_margin_mm=request.page_margin_mm,
        spacing_mm=request.spacing_mm,
        company_name=request.company_name,
        header_text=request.header_text,
        footer_text=request.footer_text,
        sample_qrs=sample_qrs,
    )


@router.post("/studio-pdf")
async def export_studio_pdf(
    request: PrintStudioRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    Generate bulk printable A4 sheet PDF for unassigned QR codes with corporate branding.
    Enforces that only unassigned QR codes can be printed.
    """
    if request.qr_ids and len(request.qr_ids) > 0:
        qr_codes = db.query(QRCode).filter(QRCode.id.in_(request.qr_ids)).order_by(QRCode.id.asc()).all()
        if not qr_codes:
            raise HTTPException(status_code=404, detail="No matching QR codes found")
    elif request.quantity:
        qr_codes = (
            db.query(QRCode)
            .filter(QRCode.status == QRStatus.UNASSIGNED)
            .order_by(QRCode.id.asc())
            .limit(request.quantity)
            .all()
        )
        if not qr_codes:
            raise HTTPException(status_code=404, detail="No unassigned QR codes available to print")
    else:
        raise HTTPException(status_code=400, detail="Must provide either quantity or qr_ids")
    
    # CRITICAL CONSTRAINT: Verify only unassigned QR codes can be selected for printing
    if request.unassigned_only:
        invalid_codes = [q.qr_id for q in qr_codes if q.status != QRStatus.UNASSIGNED]
        if invalid_codes:
            raise HTTPException(
                status_code=400,
                detail=f"Only unassigned QR codes can be selected for printing in Bulk Printing Studio. Found non-unassigned codes: {', '.join(invalid_codes[:5])}",
            )
    
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
        company_name=request.company_name,
        header_text=request.header_text,
        footer_text=request.footer_text,
        custom_rows=request.custom_rows,
        custom_cols=request.custom_cols,
    )
    
    filename = f"qr_stickers_{qr_codes[0].qr_id}_to_{qr_codes[-1].qr_id}.pdf"
    
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

