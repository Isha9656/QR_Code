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


def generate_print_pdf(
    qr_data_list: List[dict],
    qr_size_mm: int = 30,
    page_margin_mm: int = 10,
    spacing_mm: int = 5,
    show_labels: bool = True,
) -> bytes:
    """
    Generate a printable PDF with multiple QR codes arranged on A4 pages.
    
    qr_data_list: List of dicts with 'url' and 'label' keys
    """
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    
    margin = page_margin_mm * mm
    qr_size = qr_size_mm * mm
    spacing = spacing_mm * mm
    
    label_height = 4 * mm if show_labels else 0
    cell_width = qr_size + spacing
    cell_height = qr_size + label_height + spacing
    
    usable_width = page_width - 2 * margin
    usable_height = page_height - 2 * margin
    
    cols = max(1, int(usable_width / cell_width))
    rows = max(1, int(usable_height / cell_height))
    
    # Center the grid
    grid_width = cols * cell_width - spacing
    grid_height = rows * cell_height - spacing
    start_x = margin + (usable_width - grid_width) / 2
    start_y = page_height - margin
    
    qr_pixel_size = max(300, int(qr_size_mm * 10))  # High res
    
    for idx, qr_data in enumerate(qr_data_list):
        page_idx = idx // (cols * rows)
        pos_on_page = idx % (cols * rows)
        col = pos_on_page % cols
        row = pos_on_page // cols
        
        if pos_on_page == 0 and idx > 0:
            c.showPage()
        
        x = start_x + col * cell_width
        y = start_y - (row + 1) * cell_height + spacing
        
        # Generate QR image
        qr_img = generate_qr_image(
            qr_data["url"],
            size=qr_pixel_size,
            border=2,
        )
        img_reader = ImageReader(qr_img)
        
        c.drawImage(img_reader, x, y + label_height, qr_size, qr_size)
        
        if show_labels and qr_data.get("label"):
            c.setFont("Helvetica", 7)
            label_text = qr_data["label"]
            text_width = c.stringWidth(label_text, "Helvetica", 7)
            text_x = x + (qr_size - text_width) / 2
            c.drawString(text_x, y, label_text)
    
    c.save()
    buffer.seek(0)
    return buffer.getvalue()
