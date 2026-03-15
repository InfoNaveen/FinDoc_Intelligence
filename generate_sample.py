from reportlab.pdfgen.canvas import Canvas
import os

pdf_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "tests", "sample_docs", "sample_invoice.pdf"))
os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

c = Canvas(pdf_path)
c.drawString(100, 750, 'TAX INVOICE')
c.drawString(100, 730, 'Invoice No: INV-2025-00015')
c.drawString(100, 710, 'Date: 12/07/2025')
c.drawString(100, 680, 'VENDOR DETAILS')
c.drawString(100, 660, 'Name: Maruti Suzuki India Ltd')
c.drawString(100, 640, 'GSTIN: 36MOVHL9365E1ZJ')
c.drawString(100, 600, 'BILL TO: HyperAPI Technologies Pvt Ltd')
c.drawString(100, 560, 'LINE ITEMS')
c.drawString(100, 540, '1 Consulting 998412 1 Hrs 1000.00 1000.00')
c.drawString(100, 500, 'Subtotal: 1000.00')
c.drawString(100, 480, 'CGST: 90.00')
c.drawString(100, 460, 'SGST: 90.00')
c.drawString(100, 440, 'GRAND TOTAL: 1180.00')
c.save()

print(f"Created {pdf_path}")
