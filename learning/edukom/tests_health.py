import shutil
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.urls import reverse
from django.db.utils import OperationalError


class HealthCheckTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_health_check_endpoint_healthy(self):
        """
        Tests /healthz returns 200 OK when database, cache, and disk are healthy.
        """
        url = reverse('health_check')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'healthy')
        self.assertIn('database', data['components'])
        self.assertIn('cache', data['components'])
        self.assertIn('storage', data['components'])
        self.assertEqual(data['components']['database']['status'], 'healthy')
        self.assertEqual(data['components']['cache']['status'], 'healthy')
        self.assertEqual(data['components']['storage']['status'], 'healthy')

    def test_readiness_check_endpoint(self):
        """
        Tests /readyz probe responds with 200 OK.
        """
        url = reverse('readiness_check')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'healthy')

    @patch('edukom.health.connection.cursor')
    def test_health_check_database_failure_returns_503(self, mock_cursor):
        """
        Tests /healthz returns HTTP 503 Service Unavailable when the database is unreachable.
        """
        mock_cursor.side_effect = OperationalError("Database connection timed out")
        url = reverse('health_check')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual(data['status'], 'unhealthy')
        self.assertEqual(data['components']['database']['status'], 'unhealthy')

    @patch('edukom.health.shutil.disk_usage')
    def test_health_check_low_disk_space_returns_503(self, mock_disk):
        """
        Tests /healthz returns HTTP 503 when disk space falls below 10% headroom.
        """
        # 2 GB free out of 100 GB = 2% free (< 10% headroom)
        mock_disk.return_value = shutil._ntuple_diskusage(100 * (1024**3), 98 * (1024**3), 2 * (1024**3))
        url = reverse('health_check')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 503)
        data = response.json()
        self.assertEqual(data['status'], 'unhealthy')
        self.assertEqual(data['components']['storage']['status'], 'critical_low_space')
