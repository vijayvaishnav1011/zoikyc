import io
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from app.models.setting import get_platform_fee_config

def generate_recharge_pdf_invoice(company_name, client_id, gstin, address, user_name, amount, platform_fee, total_paid, reference_id, txn_date, fee_name=None, fee_percent=None):
    """
    Generates a professional PDF Tax Invoice / Recharge Receipt in memory using ReportLab.
    Returns bytes of the generated PDF document.
    """
    if fee_percent is None or fee_name is None:
        cfg_percent, cfg_name = get_platform_fee_config()
        if fee_percent is None:
            fee_percent = cfg_percent
        if fee_name is None:
            fee_name = cfg_name
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom typography styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#3b0764')
    )
    
    badge_style = ParagraphStyle(
        'Badge',
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#059669'),
        alignment=TA_RIGHT
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#64748b')
    )

    section_header = ParagraphStyle(
        'SecHeader',
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#1e293b')
    )

    body_text = ParagraphStyle(
        'BodyDark',
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#334155')
    )

    bold_text = ParagraphStyle(
        'BoldDark',
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#0f172a')
    )

    table_header = ParagraphStyle(
        'TableHeader',
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.white
    )

    total_style = ParagraphStyle(
        'TotalStyle',
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#059669'),
        alignment=TA_RIGHT
    )

    story = []

    # 1. Header Banner: Brand Logo on Left, Invoice Details on Right
    logo_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'images', 'zoikyc_logo.png')
    if os.path.exists(logo_path):
        logo_flowable = RLImage(logo_path, width=1.6*inch, height=0.5*inch)
    else:
        logo_flowable = Paragraph("<b>ZoiKYC</b>", title_style)

    header_data = [
        [
            logo_flowable,
            Paragraph("<b>PAYMENT CONFIRMED</b><br/><font color='#64748b'>TAX INVOICE / RECEIPT</font>", badge_style)
        ],
        [
            Paragraph("Digital Identity & Verification Gateway", subtitle_style),
            Paragraph(f"<b>Invoice #:</b> INV-{reference_id[-10:].upper()}<br/><b>Date:</b> {txn_date}", subtitle_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[280, 260])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('TOPPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#e2e8f0'), spaceAfter=14))

    # 2. Issuer and Customer Info Grid
    clean_gstin = gstin if gstin else "Not Provided"
    clean_addr = (address[:90] + '...') if len(address or '') > 90 else (address or "Registered Address on file")
    
    issuer_info = (
        "<b>Issuer / Service Provider:</b><br/>"
        "<b>ZoiKYC Technologies Pvt. Ltd.</b><br/>"
        "Email: info@zoikyc.com<br/>"
        "Portal: https://zoikyc.com<br/>"
        "GSTIN: 07AAAAA0000A1Z0<br/>"
        "New Delhi, India"
    )
    
    billed_info = (
        "<b>Billed To (Organisation):</b><br/>"
        f"<b>{company_name}</b><br/>"
        f"Client ID: {client_id or 'N/A'}<br/>"
        f"Signatory: {user_name}<br/>"
        f"GSTIN: {clean_gstin}<br/>"
        f"Address: {clean_addr}"
    )

    party_data = [
        [Paragraph(issuer_info, body_text), Paragraph(billed_info, body_text)]
    ]
    party_table = Table(party_data, colWidths=[270, 270])
    party_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#e2e8f0')),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
        ('TOPPADDING', (0,0), (-1,-1), 10),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(party_table)
    story.append(Spacer(1, 18))

    # 3. Itemized Line Items Table
    items_header = [
        Paragraph("#", table_header),
        Paragraph("Description", table_header),
        Paragraph("HSN/SAC", table_header),
        Paragraph("Rate", table_header),
        Paragraph("Amount (INR)", table_header)
    ]

    items_row_1 = [
        Paragraph("1", body_text),
        Paragraph(f"<b>Wallet Recharge Float</b><br/><font color='#64748b' size='8'>Prepaid balance for KYC/KRA/E-Sign verification APIs (Ref: {reference_id})</font>", body_text),
        Paragraph("998313", body_text),
        Paragraph(f"Rs. {amount:,.2f}", body_text),
        Paragraph(f"Rs. {amount:,.2f}", bold_text)
    ]

    items_row_2 = [
        Paragraph("2", body_text),
        Paragraph(f"<b>{fee_name} ({fee_percent:g}%)</b><br/><font color='#64748b' size='8'>Payment processing and platform facilitation fee</font>", body_text),
        Paragraph("998314", body_text),
        Paragraph(f"{fee_percent:.2f}%", body_text),
        Paragraph(f"Rs. {platform_fee:,.2f}", bold_text)
    ]

    items_data = [items_header, items_row_1, items_row_2]
    items_table = Table(items_data, colWidths=[24, 256, 70, 80, 110])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#3b0764')),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 12))

    # 4. Totals Summary Table
    totals_data = [
        [Paragraph("", body_text), Paragraph("Subtotal (Recharge):", bold_text), Paragraph(f"Rs. {amount:,.2f}", bold_text)],
        [Paragraph("", body_text), Paragraph(f"{fee_name} ({fee_percent:g}%):", body_text), Paragraph(f"Rs. {platform_fee:,.2f}", body_text)],
        [Paragraph("", body_text), Paragraph("<b>Total Paid via Razorpay:</b>", section_header), Paragraph(f"<b>Rs. {total_paid:,.2f}</b>", total_style)],
    ]
    totals_table = Table(totals_data, colWidths=[250, 150, 140])
    totals_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('LINEABOVE', (1,2), (-1,2), 1, colors.HexColor('#3b0764')),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 24))

    # 5. Payment Details Banner
    pay_details = (
        f"<b>Payment Gateway:</b> Razorpay Online Checkout &bull; <b>Transaction ID:</b> {reference_id}<br/>"
        "<b>Payment Status:</b> <font color='#059669'><b>COMPLETED & VERIFIED</b></font> &bull; "
        "<b>Currency:</b> INR (Indian Rupee)"
    )
    pay_table = Table([[Paragraph(pay_details, body_text)]], colWidths=[540])
    pay_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f0fdf4')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#bbf7d0')),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
    ]))
    story.append(pay_table)
    story.append(Spacer(1, 24))

    # 6. Legal Footer Note
    footer_text = (
        "<i>This is a system-generated electronic tax invoice and receipt. No physical signature is required. "
        "For any queries regarding this invoice, please reach out to accounts at info@zoikyc.com.</i><br/>"
        "&copy; 2026 ZoiKYC Technologies. All Rights Reserved."
    )
    story.append(Paragraph(footer_text, subtitle_style))

    # Build PDF into in-memory buffer
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
