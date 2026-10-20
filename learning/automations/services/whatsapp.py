"""
Unified Messaging Gateway (WhatsApp & SMS) for Edukom LMS.
Supports:
- WhatsApp Business API via Twilio & Termii
- SMS Gateway via Termii (Nigeria/Africa) & Twilio (International UK/US/Global)
- Automatic WhatsApp-to-SMS fallback delivery
- Secure local development sandbox simulation
"""

import json
import logging
import urllib.request
import urllib.parse
import base64
from typing import Dict, Any, Optional
from django.conf import settings
from .phone_formatter import normalize_to_e164

logger = logging.getLogger('automations')


class WhatsAppService:
    """
    Unified SMS & WhatsApp messaging provider for Edukom.
    """
    def __init__(self):
        self.twilio_account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
        self.twilio_auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
        self.twilio_whatsapp_sender = getattr(settings, 'TWILIO_WHATSAPP_NUMBER', '+14155238886')
        self.twilio_sms_sender = getattr(settings, 'TWILIO_SMS_NUMBER', getattr(settings, 'TWILIO_WHATSAPP_NUMBER', ''))
        self.termii_api_key = getattr(settings, 'TERMII_API_KEY', '')
        self.termii_sender_id = getattr(settings, 'TERMII_SENDER_ID', 'Edukom')

        # Mock mode if no live credentials supplied
        self.is_mock_mode = not (self.twilio_account_sid and self.twilio_auth_token) and not self.termii_api_key

    # ==========================================================================
    # WHATSAPP DISPATCH
    # ==========================================================================

    def send_whatsapp_message(self, to_phone: str, message_body: str) -> Dict[str, Any]:
        """
        Sends an automated WhatsApp message to an international phone number.
        Returns dict with keys: 'success', 'sid', 'error', 'provider', 'channel'
        """
        e164_phone = normalize_to_e164(to_phone)
        if not e164_phone:
            return {'success': False, 'error': 'Invalid recipient phone number.', 'sid': '', 'channel': 'WHATSAPP'}

        if self.is_mock_mode:
            mock_sid = f"WA_MOCK_{abs(hash(e164_phone + message_body[:20]))}"
            logger.info(f"[WHATSAPP SANDBOX MOCK] -> {e164_phone}:\n{message_body}\n(Mock SID: {mock_sid})")
            return {
                'success': True,
                'sid': mock_sid,
                'is_mock': True,
                'recipient': e164_phone,
                'channel': 'WHATSAPP',
                'provider': 'mock'
            }

        # 1. Live Twilio WhatsApp
        if self.twilio_account_sid and self.twilio_auth_token:
            return self._send_twilio_whatsapp(e164_phone, message_body)

        # 2. Live Termii WhatsApp
        if self.termii_api_key:
            return self._send_termii_whatsapp(e164_phone, message_body)

        return {'success': False, 'error': 'No WhatsApp provider configured.', 'sid': '', 'channel': 'WHATSAPP'}

    def _send_twilio_whatsapp(self, to_phone: str, body: str) -> Dict[str, Any]:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_account_sid}/Messages.json"
        from_num = f"whatsapp:{self.twilio_whatsapp_sender.replace('whatsapp:', '')}"
        to_num = f"whatsapp:{to_phone}"

        payload = urllib.parse.urlencode({
            'From': from_num,
            'To': to_num,
            'Body': body,
        }).encode('utf-8')

        req = urllib.request.Request(url, data=payload, method='POST')
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
                    'provider': 'twilio',
                    'channel': 'WHATSAPP'
                }
        except Exception as exc:
            logger.error(f"Twilio WhatsApp dispatch failed to {to_phone}: {str(exc)}", exc_info=True)
            return {'success': False, 'error': str(exc), 'sid': '', 'channel': 'WHATSAPP'}

    def _send_termii_whatsapp(self, to_phone: str, body: str) -> Dict[str, Any]:
        url = "https://api.ng.termii.com/api/sms/send"
        payload = json.dumps({
            'to': to_phone.lstrip('+'),
            'from': self.termii_sender_id,
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
                    'provider': 'termii',
                    'channel': 'WHATSAPP'
                }
        except Exception as exc:
            logger.error(f"Termii message dispatch failed to {to_phone}: {str(exc)}", exc_info=True)
            return {'success': False, 'error': str(exc), 'sid': '', 'channel': 'WHATSAPP'}

    # ==========================================================================
    # SMS DISPATCH
    # ==========================================================================

    def send_sms_message(self, to_phone: str, message_body: str) -> Dict[str, Any]:
        """
        Sends an automated SMS message to an international phone number.
        Uses Termii for Nigerian/African lines or Twilio SMS for international destinations.
        """
        e164_phone = normalize_to_e164(to_phone)
        if not e164_phone:
            return {'success': False, 'error': 'Invalid recipient phone number.', 'sid': '', 'channel': 'SMS'}

        if self.is_mock_mode:
            mock_sid = f"SMS_MOCK_{abs(hash(e164_phone + message_body[:20]))}"
            logger.info(f"[SMS SANDBOX MOCK] -> {e164_phone}:\n{message_body}\n(Mock SID: {mock_sid})")
            return {
                'success': True,
                'sid': mock_sid,
                'is_mock': True,
                'recipient': e164_phone,
                'channel': 'SMS',
                'provider': 'mock'
            }

        # Route Nigerian numbers (+234) through Termii if key present
        if e164_phone.startswith('+234') and self.termii_api_key:
            return self._send_termii_sms(e164_phone, message_body)

        # International numbers (+44, +1, etc.) or fallback via Twilio SMS
        if self.twilio_account_sid and self.twilio_auth_token:
            return self._send_twilio_sms(e164_phone, message_body)

        # Fallback to Termii for any line if configured
        if self.termii_api_key:
            return self._send_termii_sms(e164_phone, message_body)

        return {'success': False, 'error': 'No SMS provider configured.', 'sid': '', 'channel': 'SMS'}

    def _send_termii_sms(self, to_phone: str, body: str) -> Dict[str, Any]:
        url = "https://api.ng.termii.com/api/sms/send"
        clean_num = to_phone.lstrip('+')
        payload = json.dumps({
            'to': clean_num,
            'from': self.termii_sender_id,
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
                    'provider': 'termii',
                    'channel': 'SMS'
                }
        except Exception as exc:
            logger.error(f"Termii SMS dispatch failed to {to_phone}: {str(exc)}", exc_info=True)
            return {'success': False, 'error': str(exc), 'sid': '', 'channel': 'SMS'}

    def _send_twilio_sms(self, to_phone: str, body: str) -> Dict[str, Any]:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_account_sid}/Messages.json"
        from_num = self.twilio_sms_sender.replace('whatsapp:', '').strip()

        payload = urllib.parse.urlencode({
            'From': from_num,
            'To': to_phone,
            'Body': body,
        }).encode('utf-8')

        req = urllib.request.Request(url, data=payload, method='POST')
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
                    'provider': 'twilio',
                    'channel': 'SMS'
                }
        except Exception as exc:
            logger.error(f"Twilio SMS dispatch failed to {to_phone}: {str(exc)}", exc_info=True)
            return {'success': False, 'error': str(exc), 'sid': '', 'channel': 'SMS'}

    # ==========================================================================
    # SMART FALLBACK DISPATCH
    # ==========================================================================

    def send_with_fallback(self, to_phone: str, body: str, prefer_sms: bool = False) -> Dict[str, Any]:
        """
        Smart Delivery: If preferred channel is WhatsApp, attempts WhatsApp first.
        If WhatsApp fails (e.g. unregistered number or network issue), falls back to SMS.
        """
        if prefer_sms:
            res = self.send_sms_message(to_phone, body)
            if not res['success']:
                logger.info(f"SMS delivery failed to {to_phone}, attempting WhatsApp fallback...")
                return self.send_whatsapp_message(to_phone, body)
            return res
        else:
            res = self.send_whatsapp_message(to_phone, body)
            if not res['success']:
                logger.info(f"WhatsApp delivery failed to {to_phone}, attempting SMS fallback...")
                return self.send_sms_message(to_phone, body)
            return res


# Alias for backward compatibility
MessagingService = WhatsAppService
