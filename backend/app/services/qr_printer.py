import io
import math
import qrcode
from qrcode.constants import ERROR_CORRECT_H
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from typing import List, Optional
from app.config import get_settings

settings = get_settings()

# A4 dimensions in mm
A4_WIDTH_MM = 210
A4_HEIGHT_MM = 297


def generate_qr_image(
    data: str,
    size: int = 300,
    border: int = 2,
    label: Optional[str] = None,
) -> Image.Image:
    """Generate a high-resolution QR code image."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=10,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img = img.resize((size, size), Image.LANCZOS)
    
    if label:
        # Add label below QR code
        label_height = 30
        total_height = size + label_height
        labeled_img = Image.new("RGB", (size, total_height), "white")
        labeled_img.paste(img, (0, 0))
        
        draw = ImageDraw.Draw(labeled_img)
        try:
            font = ImageFont.truetype("arial.ttf", 14)
        except (IOError, OSError):
            font = ImageFont.load_default()
        
        bbox = draw.textbbox((0, 0), label, font=font)
        text_width = bbox[2] - bbox[0]
        text_x = (size - text_width) // 2
        text_y = size + 5
        draw.text((text_x, text_y), label, fill="black", font=font)
        
        return labeled_img
    
    return img


def generate_qr_png_bytes(
    data: str,
    size: int = 300,
    border: int = 2,
    label: Optional[str] = None,
) -> bytes:
    """Generate a QR code and return as PNG bytes."""
    img = generate_qr_image(data, size, border, label)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", quality=95)
    buffer.seek(0)
    return buffer.getvalue()


def calculate_sheet_layout(
    total_items: int,
    qr_size_mm: int = 30,
    page_margin_mm: int = 10,
    spacing_mm: int = 5,
    show_labels: bool = True,
    has_header: bool = True,
    has_footer: bool = True,
    custom_cols: Optional[int] = None,
    custom_rows: Optional[int] = None,
) -> dict:
    """Calculate grid layout dimensions for A4 sheet printing."""
    margin = page_margin_mm * mm
    qr_size = qr_size_mm * mm
    spacing = spacing_mm * mm
    
    label_height = 4.5 * mm if show_labels else 0
    cell_width = qr_size + spacing
    cell_height = qr_size + label_height + spacing
    
    page_width, page_height = A4
    header_space = 14 * mm if has_header else 0
    footer_space = 10 * mm if has_footer else 0
    
    usable_width = page_width - (2 * margin)
    usable_height = page_height - (2 * margin) - header_space - footer_space
    
    cols = custom_cols if (custom_cols and custom_cols > 0) else max(1, int(usable_width / cell_width))
    rows = custom_rows if (custom_rows and custom_rows > 0) else max(1, int(usable_height / cell_height))
    
    qrs_per_page = max(1, cols * rows)
    total_pages = max(1, math.ceil(total_items / qrs_per_page)) if total_items > 0 else 1
    
    return {
        "cols": cols,
        "rows": rows,
        "qrs_per_page": qrs_per_page,
        "total_pages": total_pages,
        "cell_width_mm": round(cell_width / mm, 1),
        "cell_height_mm": round(cell_height / mm, 1),
        "page_margin_mm": page_margin_mm,
        "spacing_mm": spacing_mm,
        "qr_size_mm": qr_size_mm,
    }


def generate_print_pdf(
    qr_data_list: List[dict],
    qr_size_mm: int = 30,
    page_margin_mm: int = 10,
    spacing_mm: int = 5,
    show_labels: bool = True,
    company_name: Optional[str] = "INTERNAL QR MANAGEMENT",
    header_text: Optional[str] = "OFFICIAL ASSET STICKERS • DO NOT DISCARD",
    footer_text: Optional[str] = "Scan with system camera to activate or reassign",
    custom_rows: Optional[int] = None,
    custom_cols: Optional[int] = None,
) -> bytes:
    """
    Generate a printable PDF with multiple QR codes arranged on A4 pages.
    Includes corporate branding header, footer, page numbering, and optional cut lines.
    qr_data_list: List of dicts with 'url' and 'label' keys
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    
    margin = page_margin_mm * mm
    qr_size = qr_size_mm * mm
    spacing = spacing_mm * mm
    
    has_header = bool(company_name or header_text)
    has_footer = bool(footer_text)
    
    header_space = 14 * mm if has_header else 0
    footer_space = 10 * mm if has_footer else 0
    
    label_height = 4.5 * mm if show_labels else 0
    cell_width = qr_size + spacing
    cell_height = qr_size + label_height + spacing
    
    usable_width = page_width - (2 * margin)
    usable_height = page_height - (2 * margin) - header_space - footer_space
    
    cols = custom_cols if (custom_cols and custom_cols > 0) else max(1, int(usable_width / cell_width))
    rows = custom_rows if (custom_rows and custom_rows > 0) else max(1, int(usable_height / cell_height))
    
    grid_width = cols * cell_width - spacing
    start_x = margin + max(0, (usable_width - grid_width) / 2)
    start_y = page_height - margin - header_space
    
    items_per_page = max(1, cols * rows)
    total_items = len(qr_data_list)
    total_pages = max(1, math.ceil(total_items / items_per_page))
    
    qr_pixel_size = max(300, int(qr_size_mm * 10))
    
    for idx, qr_data in enumerate(qr_data_list):
        page_idx = idx // items_per_page
        pos_on_page = idx % items_per_page
        col = pos_on_page % cols
        row = pos_on_page // cols
        
        # New page setup
        if pos_on_page == 0:
            if idx > 0:
                c.showPage()
                
            # Draw Company Branding Header
            if has_header:
                c.setFillColorRGB(0.08, 0.15, 0.35)  # Corporate deep blue
                c.setFont("Helvetica-Bold", 10)
                if company_name:
                    c.drawString(margin, page_height - margin - 3 * mm, company_name.upper())
                
                c.setFont("Helvetica", 7.5)
                c.setFillColorRGB(0.35, 0.45, 0.6)
                if header_text:
                    c.drawRightString(page_width - margin, page_height - margin - 3 * mm, header_text)
                    
                # Divider line
                c.setStrokeColorRGB(0.8, 0.85, 0.92)
                c.setLineWidth(0.75)
                c.line(margin, page_height - margin - 6 * mm, page_width - margin, page_height - margin - 6 * mm)
            
            # Draw Footer
            if has_footer:
                c.setStrokeColorRGB(0.85, 0.88, 0.92)
                c.setLineWidth(0.5)
                c.line(margin, margin + 6 * mm, page_width - margin, margin + 6 * mm)
                
                c.setFont("Helvetica", 7)
                c.setFillColorRGB(0.4, 0.45, 0.55)
                c.drawString(margin, margin + 2 * mm, footer_text)
                page_label = f"Sheet Page {page_idx + 1} of {total_pages}"
                c.drawRightString(page_width - margin, margin + 2 * mm, page_label)
        
        x = start_x + col * cell_width
        y = start_y - (row + 1) * cell_height + spacing
        
        # Dotted sticker border guide
        c.setStrokeColorRGB(0.82, 0.85, 0.9)
        c.setLineWidth(0.4)
        c.setDash(2, 2)
        c.roundRect(x - 1 * mm, y - 1 * mm, qr_size + 2 * mm, qr_size + label_height + 2 * mm, 1.5 * mm, stroke=1, fill=0)
        c.setDash()  # reset solid
        
        # Generate and draw QR image
        qr_img = generate_qr_image(
            qr_data["url"],
            size=qr_pixel_size,
            border=2,
        )
        img_reader = ImageReader(qr_img)
        c.drawImage(img_reader, x, y + label_height, qr_size, qr_size)
        
        # Label below QR
        if show_labels and qr_data.get("label"):
            c.setFont("Helvetica-Bold", 7.5)
            c.setFillColorRGB(0.1, 0.15, 0.25)
            label_text = qr_data["label"]
            text_width = c.stringWidth(label_text, "Helvetica-Bold", 7.5)
            text_x = x + (qr_size - text_width) / 2
            c.drawString(text_x, y + 0.5 * mm, label_text)
    
    c.save()
    buffer.seek(0)
    return buffer.getvalue()
