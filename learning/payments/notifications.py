import logging
from django.conf import settings
from django.core.mail import send_mail
from django.utils.html import strip_tags

logger = logging.getLogger('payments.notifications')


def send_payment_receipt_email(invoice, transaction) -> bool:
    """
    Sends an automated, branded HTML payment receipt to the client/parent.
    Fail-soft: logs errors without interrupting the transaction flow.
    """
    subject = f"Payment Receipt: {invoice.invoice_number} - Edukom Learning"
    recipient = [invoice.client_email]
    from_email = getattr(settings, 'EMAIL_HOST_USER', 'support@edukom.ng')

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; }}
        .card {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; }}
        .header {{ background: #002769; color: #ffffff; padding: 24px; text-align: center; }}
        .content {{ padding: 24px; }}
        .table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
        .table td {{ padding: 10px 0; border-bottom: 1px solid #f1f5f9; font-size: 14px; }}
        .table td.label {{ color: #64748b; }}
        .table td.value {{ text-align: right; font-weight: 600; color: #0f172a; }}
        .total-box {{ background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; padding: 16px; margin: 20px 0; text-align: center; }}
        .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #94a3b8; background: #f8fafc; border-top: 1px solid #e2e8f0; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">
          <h2 style="margin: 0; font-size: 20px;">Edukom Learning Group</h2>
          <p style="margin: 4px 0 0 0; font-size: 13px; opacity: 0.85;">Official Payment Receipt</p>
        </div>
        <div class="content">
          <p>Dear <strong>{invoice.client_name}</strong>,</p>
          <p>Thank you for your payment. Your transaction has been verified and your account is up to date.</p>

          <div class="total-box">
            <span style="font-size: 13px; color: #166534; font-weight: 600; text-transform: uppercase;">Amount Paid</span>
            <div style="font-size: 28px; font-weight: 800; color: #15803d; margin-top: 4px;">
              {invoice.currency} {invoice.amount:,.2f}
            </div>
          </div>

          <table class="table">
            <tr>
              <td class="label">Invoice Number</td>
              <td class="value">{invoice.invoice_number}</td>
            </tr>
            <tr>
              <td class="label">Transaction Reference</td>
              <td class="value" style="font-family: monospace; font-size: 12px;">{transaction.reference}</td>
            </tr>
            <tr>
              <td class="label">Payment Channel</td>
              <td class="value" style="text-transform: capitalize;">{transaction.channel or transaction.gateway}</td>
            </tr>
            <tr>
              <td class="label">Payment Date</td>
              <td class="value">{invoice.paid_at.strftime('%B %d, %Y - %H:%M') if invoice.paid_at else 'Verified'} UTC</td>
            </tr>
          </table>

          {f'<div style="margin-top: 16px; padding: 12px; background: #f8fafc; border-radius: 6px; font-size: 13px; color: #475569;"><strong>Description:</strong><br>{invoice.description}</div>' if invoice.description else ''}

          <p style="margin-top: 24px; font-size: 13px; color: #475569;">
            If you have questions regarding this receipt, reach out to <a href="mailto:support@edukom.ng" style="color: #2563eb;">support@edukom.ng</a>.
          </p>
        </div>
        <div class="footer">
          &copy; Edukom Learning Group. All rights reserved.
        </div>
      </div>
    </body>
    </html>
    """

    plain_message = strip_tags(html_content)

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=recipient,
            html_message=html_content,
            fail_silently=False,
        )
        logger.info(f"Payment receipt email sent to {invoice.client_email} for invoice {invoice.invoice_number}")
        return True
    except Exception as e:
        logger.error(f"Failed to send receipt email for invoice {invoice.invoice_number}: {str(e)}")
        return False
