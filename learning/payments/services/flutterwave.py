import logging
import requests
from decimal import Decimal
from django.conf import settings
from typing import Dict, Any, Optional

logger = logging.getLogger('payments.flutterwave')

BASE_URL = 'https://api.flutterwave.com/v3'


class FlutterwaveService:
    """
    Secure client wrapper for Flutterwave API.
    Used for multi-currency international collections (USD, GBP, EUR, CAD, etc.).
    """

    def __init__(self):
        self.secret_key = getattr(settings, 'FLUTTERWAVE_SECRET_KEY', '')
        self.timeout = 15

    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json',
        }

    def initialize_payment(
        self,
        email: str,
        amount: Decimal,
        reference: str,
        callback_url: str,
        currency: str = 'USD',
        customer_name: str = '',
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Initialize a multi-currency payment link on Flutterwave.
        """
        url = f"{BASE_URL}/payments"
        payload = {
            'tx_ref': reference,
            'amount': str(amount),
            'currency': currency.upper(),
            'redirect_url': callback_url,
            'customer': {
                'email': email,
                'name': customer_name or email,
            },
            'customizations': {
                'title': 'Edukom Learning Group',
                'description': 'Tuition & Lesson Fees',
            },
            'meta': metadata or {},
        }

        try:
            response = requests.post(
                url, 
                json=payload, 
                headers=self._get_headers(), 
                timeout=self.timeout
            )
            data = response.json()
            if response.status_code == 200 and data.get('status') == 'success':
                return {
                    'success': True,
                    'authorization_url': data['data']['link'],
                    'reference': reference,
                }
            return {
                'success': False,
                'error': data.get('message', 'Failed to initialize payment')
            }
        except requests.RequestException as e:
            logger.error(f"Flutterwave request exception: {str(e)}")
            return {'success': False, 'error': 'Network error connecting to payment gateway'}

    def verify_transaction(self, transaction_id: str) -> Dict[str, Any]:
        """
        Server-side direct verification of Flutterwave transaction status.
        """
        url = f"{BASE_URL}/transactions/{transaction_id}/verify"
        try:
            response = requests.get(
                url, 
                headers=self._get_headers(), 
                timeout=self.timeout
            )
            data = response.json()
            if response.status_code == 200 and data.get('status') == 'success':
                tx_data = data.get('data', {})
                return {
                    'success': True,
                    'is_paid': tx_data.get('status') == 'successful',
                    'amount_paid': Decimal(str(tx_data.get('amount', 0))),
                    'currency': tx_data.get('currency'),
                    'tx_ref': tx_data.get('tx_ref'),
                    'raw': tx_data
                }
            return {
                'success': False,
                'is_paid': False,
                'error': data.get('message', 'Verification failed')
            }
        except requests.RequestException as e:
            logger.error(f"Flutterwave verify error: {str(e)}")
            return {'success': False, 'is_paid': False, 'error': str(e)}
