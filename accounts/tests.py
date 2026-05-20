from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory

from accounts.backends import EmailOrUsernameModelBackend

User = get_user_model()


class EmailOrUsernameBackendTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='securepassword123',
        )
        self.backend = EmailOrUsernameModelBackend()
        self.request = RequestFactory().post('/accounts/login/')

    def test_authenticate_with_username(self):
        user = self.backend.authenticate(self.request, username='testuser', password='securepassword123')
        self.assertEqual(user, self.user)

    def test_authenticate_with_email(self):
        user = self.backend.authenticate(self.request, username='test@example.com', password='securepassword123')
        self.assertEqual(user, self.user)

    def test_authenticate_with_email_case_insensitive(self):
        user = self.backend.authenticate(self.request, username='TEST@EXAMPLE.COM', password='securepassword123')
        self.assertEqual(user, self.user)

    def test_authenticate_with_wrong_password(self):
        user = self.backend.authenticate(self.request, username='testuser', password='wrongpassword')
        self.assertIsNone(user)

    def test_authenticate_with_nonexistent_user(self):
        user = self.backend.authenticate(self.request, username='nonexistent', password='securepassword123')
        self.assertIsNone(user)

    def test_authenticate_with_none_username(self):
        user = self.backend.authenticate(self.request, username=None, password='securepassword123')
        self.assertIsNone(user)

    def test_authenticate_with_none_password(self):
        user = self.backend.authenticate(self.request, username='testuser', password=None)
        self.assertIsNone(user)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save()
        user = self.backend.authenticate(self.request, username='testuser', password='securepassword123')
        self.assertIsNone(user)

    def test_login_with_email_via_client(self):
        response = self.client.post('/usuarios/login/', {
            'username': 'test@example.com',
            'password': 'securepassword123',
        })
        # Redirect after successful login
        self.assertEqual(response.status_code, 302)

    def test_login_with_username_via_client(self):
        response = self.client.post('/usuarios/login/', {
            'username': 'testuser',
            'password': 'securepassword123',
        })
        self.assertEqual(response.status_code, 302)
