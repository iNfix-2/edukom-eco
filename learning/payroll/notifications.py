import logging
from django.conf import settings
from django.core.mail import send_mail
from django.utils.html import strip_tags

logger = logging.getLogger('payroll.notifications')


def send_tutor_payslip_email(payroll_item) -> bool:
    """
    Sends an automated, itemized monthly payslip HTML email to the tutor.
    Includes session breakdown, hours, rate, and masked bank details.
    """
    subject = f"Your Payslip: {payroll_item.payroll_run.title} - Edukom Learning"
    recipient = [payroll_item.tutor_email]
    from_email = getattr(settings, 'EMAIL_HOST_USER', 'support@edukom.ng')

    # Build session rows
    sessions_html = ""
    for s in payroll_item.session_breakdown:
        sessions_html += f"""
        <tr>
          <td style="padding: 8px; border-bottom: 1px solid #f1f5f9; font-size: 13px;">{s.get('date', 'N/A')}</td>
          <td style="padding: 8px; border-bottom: 1px solid #f1f5f9; font-size: 13px;">{s.get('student_name', 'Student')}</td>
          <td style="padding: 8px; border-bottom: 1px solid #f1f5f9; font-size: 13px;">{s.get('class_level', 'N/A')}</td>
          <td style="padding: 8px; border-bottom: 1px solid #f1f5f9; font-size: 13px; text-align: right;">{s.get('duration_hours', 0)} hrs</td>
          <td style="padding: 8px; border-bottom: 1px solid #f1f5f9; font-size: 13px; text-align: right;">₦{s.get('hourly_rate', 0):,.2f}</td>
          <td style="padding: 8px; border-bottom: 1px solid #f1f5f9; font-size: 13px; text-align: right; font-weight: 600;">₦{s.get('amount', 0):,.2f}</td>
        </tr>
        """

    bank_info = "N/A"
    if payroll_item.tutor and hasattr(payroll_item.tutor, 'bank_account'):
        bank_acct = payroll_item.tutor.bank_account
        bank_info = f"{bank_acct.bank_name} - {bank_acct.masked_account_number}"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; }}
        .card {{ max-width: 650px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; }}
        .header {{ background: #002769; color: #ffffff; padding: 24px; text-align: center; }}
        .content {{ padding: 24px; }}
        .summary-box {{ background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 16px; margin: 20px 0; text-align: center; }}
        .table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
        .table th {{ background: #f8fafc; padding: 8px; text-align: left; font-size: 11px; text-transform: uppercase; color: #64748b; border-bottom: 2px solid #e2e8f0; }}
        .totals-table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        .totals-table td {{ padding: 6px 0; font-size: 14px; }}
        .footer {{ padding: 20px; text-align: center; font-size: 12px; color: #94a3b8; background: #f8fafc; border-top: 1px solid #e2e8f0; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="header">
          <h2 style="margin: 0; font-size: 20px;">Edukom Learning Group</h2>
          <p style="margin: 4px 0 0 0; font-size: 13px; opacity: 0.85;">Tutor Compensation Statement</p>
        </div>
        <div class="content">
          <p>Dear <strong>{payroll_item.tutor_name}</strong>,</p>
          <p>Your compensation for <strong>{payroll_item.payroll_run.title}</strong> has been calculated and authorized.</p>

          <div class="summary-box">
            <span style="font-size: 12px; color: #1e40af; font-weight: 700; text-transform: uppercase;">Net Payable</span>
            <div style="font-size: 30px; font-weight: 800; color: #1d4ed8; margin-top: 4px;">
              ₦{payroll_item.net_pay:,.2f}
            </div>
            <p style="margin: 4px 0 0 0; font-size: 12px; color: #475569;">
              Disbursement Account: <strong>{bank_info}</strong>
            </p>
          </div>

          <h4 style="margin: 24px 0 8px 0; color: #0f172a; font-size: 14px;">Itemized Lesson Breakdown ({payroll_item.total_hours} Total Hours)</h4>
          <table class="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Student</th>
                <th>Level</th>
                <th style="text-align: right;">Hours</th>
                <th style="text-align: right;">Rate</th>
                <th style="text-align: right;">Subtotal</th>
              </tr>
            </thead>
            <tbody>
              {sessions_html if sessions_html else '<tr><td colspan="6" style="padding: 12px; text-align: center; color: #94a3b8;">Detailed breakdown logged in portal.</td></tr>'}
            </tbody>
          </table>

          <table class="totals-table">
            <tr>
              <td style="color: #64748b;">Gross Earnings:</td>
              <td style="text-align: right; font-weight: 600;">₦{payroll_item.calculated_gross_pay:,.2f}</td>
            </tr>
            {f'<tr><td style="color: #dc2626;">Deductions:</td><td style="text-align: right; color: #dc2626; font-weight: 600;">-₦{payroll_item.deductions:,.2f}</td></tr>' if payroll_item.deductions > 0 else ''}
            {f'<tr><td style="color: #16a34a;">Bonuses:</td><td style="text-align: right; color: #16a34a; font-weight: 600;">+₦{payroll_item.bonuses:,.2f}</td></tr>' if payroll_item.bonuses > 0 else ''}
            <tr style="border-top: 2px solid #e2e8f0; font-weight: 800; font-size: 16px;">
              <td style="padding-top: 8px; color: #0f172a;">Net Payout:</td>
              <td style="padding-top: 8px; text-align: right; color: #1d4ed8;">₦{payroll_item.net_pay:,.2f}</td>
            </tr>
          </table>

          <p style="margin-top: 24px; font-size: 12px; color: #64748b;">
            For payroll inquiries or bank updates, contact the Edukom Operations Desk at <a href="mailto:support@edukom.ng" style="color: #2563eb;">support@edukom.ng</a>.
          </p>
        </div>
        <div class="footer">
          &copy; Edukom Learning Group. Strictly Confidential.
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
        logger.info(f"Payslip email sent to {payroll_item.tutor_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send payslip email to {payroll_item.tutor_email}: {str(e)}")
        return False


def send_payout_failure_alert_email(payroll_item, reason: str = "Unknown") -> bool:
    """
    Alerts Edukom Management whenever an automated bank transfer fails or reverses.
    """
    subject = f"[URGENT] Tutor Payout Failed: {payroll_item.tutor_name}"
    recipients = getattr(settings, 'OFFICIAL_NOTIFICATION_EMAILS', ['support@edukom.ng'])
    from_email = getattr(settings, 'EMAIL_HOST_USER', 'support@edukom.ng')

    body = f"""
    ATTENTION: An automated tutor disbursement has failed on Paystack.

    Tutor Name: {payroll_item.tutor_name}
    Tutor Email: {payroll_item.tutor_email}
    Payroll Run: {payroll_item.payroll_run.title}
    Amount: ₦{payroll_item.net_pay:,.2f}
    Failure Reason: {reason}

    Action Required:
    Please verify the tutor's bank account details in the Edukom Admin Dashboard.
    """

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=recipients,
            fail_silently=True
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send payout failure alert: {str(e)}")
        return False
