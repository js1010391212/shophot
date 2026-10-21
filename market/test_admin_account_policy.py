"""Regression for replaying a stale admin request during a read-only audit."""
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import PermissionDenied
from django.core.management import call_command, get_commands
from django.core.management.base import CommandError
from django.test import TestCase

from .admin_account_policy import privileged_account_creation


class AdminAccountPolicyTests(TestCase):
    def test_incident_create_superuser_script_rejected_without_writes(self):
        User = get_user_model()
        original = User.objects.create_user(username='existing', password='test-only-password')
        before = list(User.objects.values())
        with self.assertRaises(PermissionDenied):
            User.objects.create_superuser(username='extra', password='test-only-password')
        self.assertEqual(list(User.objects.values()), before)
        self.assertTrue(authenticate(username=original.username, password='test-only-password'))

    def test_new_staff_or_superuser_via_save_also_rejected(self):
        for flags in ({'is_staff': True}, {'is_superuser': True}):
            with self.subTest(flags=flags), self.assertRaises(PermissionDenied):
                get_user_model().objects.create_user(username='extra', **flags)
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_ordinary_account_creation_preserved(self):
        user = get_user_model().objects.create_user(username='ordinary')
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_loaded_admin_cannot_be_copied_by_clearing_or_changing_pk(self):
        with privileged_account_creation():
            admin = get_user_model().objects.create_superuser(username='original')
        original_pk = admin.pk
        before = list(get_user_model().objects.values())
        for target_pk in (None, original_pk + 100):
            admin.pk = target_pk
            admin.username = 'copied'
            self.assertFalse(admin._state.adding)
            with self.subTest(pk=target_pk), self.assertRaises(PermissionDenied):
                admin.save()
            self.assertEqual(list(get_user_model().objects.values()), before)

    def test_command_requires_explicit_flag(self):
        self.assertEqual(get_commands()['create_privileged_account'], 'market')
        with self.assertRaises(CommandError):
            call_command('create_privileged_account', username='extra', interactive=False, stdout=StringIO())
        self.assertEqual(get_user_model().objects.count(), 0)

    def test_explicit_command_creates_only_requested_account_and_scope_resets(self):
        with patch.dict('os.environ', {'DJANGO_SUPERUSER_PASSWORD': 'test-only-password'}):
            call_command('create_privileged_account', username='requested', email='', interactive=False,
                         allow_new_privileged_account=True, stdout=StringIO())
        user = get_user_model().objects.get()
        self.assertTrue(user.is_active and user.is_staff and user.is_superuser)
        with self.assertRaises(PermissionDenied):
            get_user_model().objects.create_superuser(username='replayed')

    def test_exception_does_not_leave_scope_enabled(self):
        with self.assertRaises(RuntimeError):
            with privileged_account_creation():
                raise RuntimeError('controlled')
        with self.assertRaises(PermissionDenied):
            get_user_model().objects.create_superuser(username='extra')

    def test_existing_accounts_permissions_and_sessions_preserved(self):
        with privileged_account_creation():
            admin = get_user_model().objects.create_superuser(username='original', password='test-only-password')
        self.client.force_login(admin)
        session_before = dict(self.client.session)
        admin.first_name = 'updated'
        admin.save(update_fields=['first_name'])
        self.assertEqual(dict(self.client.session), session_before)
        admin.refresh_from_db()
        self.assertTrue(admin.is_active and admin.is_staff and admin.is_superuser)

    def test_contained_account_cannot_authenticate_or_use_existing_session(self):
        with privileged_account_creation():
            user = get_user_model().objects.create_superuser(username='contained', password='test-only-password')
        self.client.force_login(user)
        get_user_model().objects.filter(pk=user.pk).update(is_active=False, is_staff=False, is_superuser=False)
        self.assertIsNone(authenticate(username='contained', password='test-only-password'))
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)
