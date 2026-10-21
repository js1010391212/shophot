"""Actual PostgreSQL concurrency for catalog v2; controlled fixtures, no network."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier, Event
import time

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase, skipUnlessDBFeature

from . import test_catalog_profit_references as fixtures
from .models import CatalogPriceObservation, ProfitStudyRecord
from .profit_studies import save_study


class CatalogProfitConcurrencyTests(TransactionTestCase):
    # Reuse the controlled source fixture and form inputs, without inheriting
    # or rerunning the HTTP suite as a second collection of identical tests.
    calculated = fixtures.CatalogProfitReferenceTests.calculated
    token = fixtures.CatalogProfitReferenceTests.token

    def setUp(self):
        fixtures.CatalogProfitReferenceTests.setUp(self)

    @skipUnlessDBFeature('has_select_for_update')
    def test_same_catalog_nonce_concurrently_saves_one_immutable_record(self):
        state = self.token()
        gate = Barrier(2)

        def submit():
            close_old_connections()
            try:
                owner = get_user_model().objects.get(pk=self.owner.pk)
                gate.wait(timeout=10)
                return save_study(owner, state, 'Same catalog study', '').pk
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = pool.submit(submit), pool.submit(submit)
            self.assertEqual(first.result(timeout=20), second.result(timeout=20))
        record = ProfitStudyRecord.objects.get()
        self.assertEqual(record.snapshot['version'], 2)
        self.assertEqual(record.snapshot['scenario']['source']['id'], self.quote.pk)

    @skipUnlessDBFeature('has_select_for_update')
    def test_save_waits_for_quote_lock_then_rejects_changed_source_preserving_history(self):
        original = save_study(self.owner, self.token(), 'Original historical study', '')
        preserved = deepcopy(original.snapshot)
        pending_state = self.token()
        locked, release, saver_started = Event(), Event(), Event()
        backend = {}

        def change_quote():
            close_old_connections()
            try:
                with transaction.atomic():
                    CatalogPriceObservation.objects.select_for_update().get(pk=self.quote.pk)
                    locked.set()
                    if not release.wait(timeout=10):
                        raise TimeoutError('test did not release the controlled quote lock')
                    CatalogPriceObservation.objects.filter(pk=self.quote.pk).update(price_low='51', price_high='51')
            finally:
                connection.close()

        def submit():
            close_old_connections()
            try:
                owner = get_user_model().objects.get(pk=self.owner.pk)
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_backend_pid()')
                    backend['pid'] = cursor.fetchone()[0]
                saver_started.set()
                try:
                    save_study(owner, pending_state, 'Stale source attempt', '')
                    return 'saved'
                except ValidationError:
                    return 'rejected'
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(change_quote)
            try:
                self.assertTrue(locked.wait(timeout=5))
                saver = pool.submit(submit)
                self.assertTrue(saver_started.wait(timeout=5))
                deadline = time.monotonic() + 5
                blocked = False
                while time.monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s', [backend['pid']])
                        row = cursor.fetchone()
                    if row and row[0] == 'Lock':
                        blocked = True
                        break
                    if saver.done():
                        break
                    time.sleep(.02)
                self.assertTrue(blocked, 'save must wait for the catalog observation lock')
            finally:
                release.set()
            writer.result(timeout=10)
            self.assertEqual(saver.result(timeout=10), 'rejected')
        self.assertEqual(ProfitStudyRecord.objects.count(), 1)
        original.refresh_from_db()
        self.assertEqual(original.snapshot, preserved)
