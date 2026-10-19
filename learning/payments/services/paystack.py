import logging
import requests
from decimal import Decimal
from django.conf import settings
from typing import Dict, Any, Optional, List

logger = logging.getLogger('payments.paystack')

BASE_URL = 'https://api.paystack.co'


class PaystackService:
    """
    Secure client wrapper for the Paystack API.
    Handles inbound card/bank collections and outbound automated tutor disbursements.
    """

    def __init__(self):
        self.secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', '')
        self.timeout = 15  # Avoid worker hanging

    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self.secret_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

    def initialize_transaction(
        self,
        email: str,
        amount: Decimal,
        reference: str,
        callback_url: str,
        currency: str = 'NGN',
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Initialize a checkout session.
        Converts standard currency units into minor currency units (e.g., Kobo/Cents = amount * 100).
        """
        url = f"{BASE_URL}/transaction/initialize"
        amount_in_minor_unit = int(Decimal(amount) * 100)

        payload = {
            'email': email,
            'amount': amount_in_minor_unit,
            'reference': reference,
            'callback_url': callback_url,
            'currency': currency.upper(),
            'metadata': metadata or {},
        }

        try:
            response = requests.post(
                url, 
                json=payload, 
                headers=self._get_headers(), 
                timeout=self.timeout
            )
            data = response.json()
            if response.status_code == 200 and data.get('status'):
                return {
                    'success': True,
                    'authorization_url': data['data']['authorization_url'],
                    'access_code': data['data']['access_code'],
                    'reference': reference,
                }
            else:
                logger.error(f"Paystack initialization failed: {data.get('message')}")
                return {
                    'success': False,
                    'error': data.get('message', 'Failed to initialize payment')
                }
        except requests.RequestException as e:
            logger.error(f"Paystack request exception: {str(e)}")
            return {
                'success': False,
                'error': 'Network error connecting to payment gateway'
            }

    def verify_transaction(self, reference: str) -> Dict[str, Any]:
        """
        Server-side direct verification of transaction state.
        Zero-trust architecture: Never trust client-reported success alone.
        """
        url = f"{BASE_URL}/transaction/verify/{reference}"
        try:
            response = requests.get(
                url, 
                headers=self._get_headers(), 
                timeout=self.timeout
            )
            data = response.json()
            if response.status_code == 200 and data.get('status'):
                tx_data = data.get('data', {})
                return {
                    'success': True,
                    'is_paid': tx_data.get('status') == 'success',
                    'amount_paid': Decimal(tx_data.get('amount', 0)) / Decimal(100),
                    'currency': tx_data.get('currency'),
                    'channel': tx_data.get('channel'),
                    'paid_at': tx_data.get('paid_at'),
                    'raw': tx_data
                }
            return {
                'success': False,
                'is_paid': False,
                'error': data.get('message', 'Verification failed')
            }
        except requests.RequestException as e:
            logger.error(f"Paystack verification request exception for {reference}: {str(e)}")
            return {
                'success': False,
                'is_paid': False,
                'error': 'Network timeout verifying payment'
            }

    def list_banks(self, country: str = 'nigeria') -> Dict[str, Any]:
        """
        Fetches the official list of commercial and digital banks in Nigeria.
        """
        url = f"{BASE_URL}/bank"
        params = {'country': country, 'perPage': 100}
        try:
            response = requests.get(url, headers=self._get_headers(), params=params, timeout=self.timeout)
            data = response.json()
            if response.status_code == 200 and data.get('status'):
                return {'success': True, 'banks': data.get('data', [])}
            return {'success': False, 'error': data.get('message', 'Failed to fetch banks')}
        except requests.RequestException as e:
            logger.error(f"Paystack list banks error: {str(e)}")
            return {'success': False, 'error': 'Network timeout fetching banks'}

    def resolve_account_number(self, account_number: str, bank_code: str) -> Dict[str, Any]:
        """
        NUBAN Account Verification (KYC):
        Directly queries the Nigerian Inter-Bank Settlement System (NIBSS) via Paystack
        to confirm the official registered name on the bank account before payout.
        """
        url = f"{BASE_URL}/bank/resolve"
        params = {'account_number': account_number, 'bank_code': bank_code}
        try:
            response = requests.get(url, headers=self._get_headers(), params=params, timeout=self.timeout)
            data = response.json()
            if response.status_code == 200 and data.get('status'):
                account_data = data.get('data', {})
                return {
                    'success': True,
                    'account_name': account_data.get('account_name'),
                    'account_number': account_data.get('account_number'),
                    'bank_id': account_data.get('bank_id'),
                }
            return {
                'success': False,
                'error': data.get('message', 'Unable to resolve account name. Check account number and bank.')
            }
        except requests.RequestException as e:
            logger.error(f"Paystack resolve account error: {str(e)}")
            return {'success': False, 'error': 'Network timeout resolving account'}

    def create_transfer_recipient(
        self, 
        name: str, 
        account_number: str, 
        bank_code: str, 
        currency: str = 'NGN'
    ) -> Dict[str, Any]:
        """
        Creates a transfer recipient for automated tutor bank payouts in Nigeria.
        """
        url = f"{BASE_URL}/transferrecipient"
        payload = {
            'type': 'nuban',
            'name': name,
            'account_number': account_number,
            'bank_code': bank_code,
            'currency': currency.upper(),
        }

        try:
            response = requests.post(
                url, 
                json=payload, 
                headers=self._get_headers(), 
                timeout=self.timeout
            )
            data = response.json()
            if response.status_code in (200, 201) and data.get('status'):
                return {
                    'success': True,
                    'recipient_code': data['data']['recipient_code'],
                    'details': data['data']
                }
            return {
                'success': False,
                'error': data.get('message', 'Failed to create recipient')
            }
        except requests.RequestException as e:
            logger.error(f"Error creating transfer recipient: {str(e)}")
            return {'success': False, 'error': str(e)}

    def initiate_bulk_transfer(
        self, 
        transfers: List[Dict[str, Any]], 
        currency: str = 'NGN'
    ) -> Dict[str, Any]:
        """
        Executes automated batch bank disbursements to multiple tutors in a single API call.
        transfers: [
            {"amount": 5000000, "recipient": "RCP_12345", "reference": "REF123", "reason": "Oct Tutor Pay"},
            ...
        ]
        """
        url = f"{BASE_URL}/transfer/bulk"
        payload = {
            'currency': currency.upper(),
            'source': 'balance',
            'transfers': transfers
        }

        try:
            response = requests.post(
                url, 
                json=payload, 
                headers=self._get_headers(), 
                timeout=self.timeout
            )
            data = response.json()
            if response.status_code in (200, 201) and data.get('status'):
                return {
                    'success': True,
                    'batch_code': data.get('data', {}).get('batch_code'),
                    'data': data.get('data')
                }
            return {
                'success': False,
                'error': data.get('message', 'Bulk transfer failed')
            }
        except requests.RequestException as e:
            logger.error(f"Paystack bulk transfer failed: {str(e)}")
            return {'success': False, 'error': str(e)}
