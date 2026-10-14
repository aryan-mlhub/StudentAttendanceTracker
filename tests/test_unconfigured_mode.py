import os
import unittest

from app import create_app


class UnconfiguredDatabaseTestCase(unittest.TestCase):
    def test_unconfigured_database_dashboard_render(self):
        """
        Verify that when DATABASE_URL is not set, the app gracefully renders
        the dashboard with a clear notice and instructions, without crashing
        or silently creating a local SQLite database.
        """
        original_env = os.environ.get('DATABASE_URL')
        if 'DATABASE_URL' in os.environ:
            del os.environ['DATABASE_URL']

        try:
            app = create_app()
            client = app.test_client()

            response = client.get('/')
            self.assertEqual(response.status_code, 200)

            html = response.data.decode('utf-8')
            # Check for PostgreSQL database requirement banner
            self.assertIn('PostgreSQL Database Connection Pending', html)
            self.assertIn('DATABASE_URL', html)
            self.assertIn('Academic Attendance Dashboard', html)
        finally:
            if original_env is not None:
                os.environ['DATABASE_URL'] = original_env


if __name__ == '__main__':
    unittest.main()
