"""
WhatsApp Business API Gateway Service for Edukom LMS.
Supports:
- Twilio WhatsApp API
- Termii Messaging API
- Secure local/test Sandbox simulation
"""

import json
import logging
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional
from django.conf import settings
from .phone_formatter import normalize_to_e164

logger = logging.getLogger('automations')


class WhatsAppService:
    def __init__(self):
        self.twilio_account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
        self.twilio_auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
        self.twilio_sender = getattr(settings, 'TWILIO_WHATSAPP_NUMBER', '+14155238886')
        self.termii_api_key = getattr(settings, 'TERMII_API_KEY', '')

        # Mock mode if no live credentials supplied
        self.is_mock_mode = not (self.twilio_account_sid and self.twilio_auth_token) and not self.termii_api_key

    def send_whatsapp_message(self, to_phone: str, message_body: str) -> Dict[str, Any]:
        """
        Sends an automated WhatsApp message to an international phone number.
        Returns dict with keys: 'success', 'sid', 'error', 'channel'
        """
        e164_phone = normalize_to_e164(to_phone)
        if not e164_phone:
            return {'success': False, 'error': 'Invalid recipient phone number.', 'sid': ''}

        if self.is_mock_mode:
            mock_sid = f"WA_MOCK_{abs(hash(e164_phone + message_body[:20]))}"
            logger.info(f"[WHATSAPP SANDBOX MOCK] -> {e164_phone}:\n{message_body}\n(Mock SID: {mock_sid})")
            return {
                'success': True,
                'sid': mock_sid,
                'is_mock': True,
                'recipient': e164_phone
            }

        # Live Twilio WhatsApp API
        if self.twilio_account_sid and self.twilio_auth_token:
            return self._send_twilio_whatsapp(e164_phone, message_body)

        # Fallback to Termii
        if self.termii_api_key:
            return self._send_termii_whatsapp(e164_phone, message_body)

        return {'success': False, 'error': 'No WhatsApp provider configured.', 'sid': ''}

    def _send_twilio_whatsapp(self, to_phone: str, body: str) -> Dict[str, Any]:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_account_sid}/Messages.json"
        
        # Twilio requires 'whatsapp:' prefix
        from_num = f"whatsapp:{self.twilio_sender}"
        to_num = f"whatsapp:{to_phone}"

        payload = urllib.parse.urlencode({
            'From': from_num,
            'To': to_num,
            'Body': body,
        }).encode('utf-8')

        req = urllib.request.Request(url, data=payload, method='POST')
        
        # Basic auth
        import base64
        auth_str = f"{self.twilio_account_sid}:{self.twilio_auth_token}"
        b64_auth = base64.b64encode(auth_str.encode('utf-8')).decode('utf-8')
        req.add_header('Authorization', f'Basic {b64_auth}')
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_data = json.loads(resp.read().decode('utf-8'))
                return {
                    'success': True,
                    'sid': resp_data.get('sid', ''),
                    'provider': 'twilio'
                }
        except Exception as exc:
            logger.error(f"Twilio WhatsApp dispatch failed to {to_phone}: {str(exc)}", exc_info=True)
            return {'success': False, 'error': str(exc), 'sid': ''}

    def _send_termii_whatsapp(self, to_phone: str, body: str) -> Dict[str, Any]:
        url = "https://api.ng.termii.com/api/sms/send"
        payload = json.dumps({
            'to': to_phone.lstrip('+'),
            'from': getattr(settings, 'TERMII_SENDER_ID', 'Edukom'),
            'sms': body,
            'type': 'plain',
            'channel': 'generic',
            'api_key': self.termii_api_key
        }).encode('utf-8')

        req = urllib.request.Request(url, data=payload, method='POST')
        req.add_header('Content-Type', 'application/json')

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp_data = json.loads(resp.read().decode('utf-8'))
                return {
                    'success': True,
                    'sid': resp_data.get('message_id', ''),
                    'provider': 'termii'
                }
        except Exception as exc:
            logger.error(f"Termii message dispatch failed to {to_phone}: {str(exc)}", exc_info=True)
            return {'success': False, 'error': str(exc), 'sid': ''}
