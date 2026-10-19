import time
import logging
import requests
from django.conf import settings
from typing import Dict, Any, Optional

logger = logging.getLogger('classroom.daily')

DAILY_API_URL = "https://api.daily.co/v1"


class DailyVideoService:
    """
    Secure client wrapper for Daily.co Video API.
    Replaces external Zoom/Google Meet links with embedded, token-authenticated WebRTC classrooms.
    """

    def __init__(self):
        self.api_key = getattr(settings, 'DAILY_API_KEY', '')
        self.domain = getattr(settings, 'DAILY_DOMAIN', 'edukom')
        self.timeout = 15

    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

    def is_configured(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith('placeholder'))

    def create_or_get_room(self, session) -> Dict[str, Any]:
        """
        Creates an encrypted, private Daily.co video room with automated expiration.
        """
        room_name = f"edukom-{session.id.hex[:12]}"

        if not self.is_configured():
            # Return development fallback room URL
            return {
                'success': True,
                'room_name': room_name,
                'room_url': f"https://{self.domain}.daily.co/{room_name}",
                'is_mock': True
            }

        # Calculate expiration: end_time + 2 hours (in seconds since epoch)
        exp_timestamp = int(session.end_time.timestamp()) + (2 * 3600)

        url = f"{DAILY_API_URL}/rooms"
        payload = {
            'name': room_name,
            'privacy': 'private',  # Requires cryptographically signed JWT token
            'properties': {
                'exp': exp_timestamp,
                'enable_chat': True,
                'enable_screenshare': True,
                'enable_knocking': True,
                'eject_at_room_exp': True,
            }
        }

        try:
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=self.timeout)
            data = response.json()
            if response.status_code in (200, 201):
                return {
                    'success': True,
                    'room_name': data['name'],
                    'room_url': data['url'],
                    'is_mock': False
                }
            elif response.status_code == 400 and 'already exists' in str(data):
                # Room already created
                return {
                    'success': True,
                    'room_name': room_name,
                    'room_url': f"https://{self.domain}.daily.co/{room_name}",
                    'is_mock': False
                }
            else:
                logger.error(f"Daily room creation error: {data}")
                return {'success': False, 'error': data.get('info', 'Failed to create room')}
        except requests.RequestException as e:
            logger.error(f"Daily API request exception: {str(e)}")
            return {'success': False, 'error': 'Network timeout reaching video service'}

    def generate_meeting_token(
        self, 
        room_name: str, 
        user_name: str, 
        user_id: str, 
        is_owner: bool = False
    ) -> Dict[str, Any]:
        """
        Generates a short-lived, signed Daily.co Meeting Token.
        is_owner=True gives tutors host controls (kick, mute-all, admit knocking).
        """
        if not self.is_configured():
            return {'success': True, 'token': f"mock-token-{user_id}", 'is_mock': True}

        url = f"{DAILY_API_URL}/meeting-tokens"
        # Token expires in 3 hours
        exp_timestamp = int(time.time()) + (3 * 3600)

        payload = {
            'properties': {
                'room_name': room_name,
                'user_name': user_name,
                'user_id': str(user_id),
                'is_owner': is_owner,
                'exp': exp_timestamp,
                'enable_screenshare': True,
            }
        }

        try:
            response = requests.post(url, json=payload, headers=self._get_headers(), timeout=self.timeout)
            data = response.json()
            if response.status_code == 200 and 'token' in data:
                return {
                    'success': True,
                    'token': data['token'],
                    'is_mock': False
                }
            return {'success': False, 'error': data.get('info', 'Failed to generate meeting token')}
        except requests.RequestException as e:
            logger.error(f"Daily token generation error: {str(e)}")
            return {'success': False, 'error': 'Network error generating access token'}
