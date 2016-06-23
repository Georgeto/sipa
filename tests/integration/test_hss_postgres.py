#!/usr/bin/env python
from datetime import datetime, timedelta
from operator import attrgetter

from flask_babel import gettext
from flask_login import AnonymousUserMixin

from .hss_fixtures import HSSOneAccountFixture, HSSOneTrafficAccountFixture, \
    HSSOneTrafficAccountDaysMissingFixture, HSSAccountsWithPropertiesFixture, \
    HSSOneFinanceAccountFixture
from tests.prepare import AppInitialized
from sipa.model.sqlalchemy import db
from sipa.model.hss.schema import Account, IP, Mac, TrafficLog, AccountStatementLog
from sipa.model.hss.user import User


class HssPgTestBase(AppInitialized):
    def create_app(self, *a, **kw):
        conf = {
            **kw.pop('additional_config', {}),
            'WU_CONNECTION_STRING': "sqlite:///",
            'HSS_CONNECTION_STRING': "postgresql://sipa:password@postgres:5432/",
            'DB_HELIOS_IP_MASK': "10.10.7.%",
        }
        test_app = super().create_app(*a, additional_config=conf, **kw)
        return test_app

    def setUp(self, *a, **kw):
        super().setUp(*a, **kw)
        db.drop_all(bind='hss')
        db.create_all(bind='hss')
        self.session = db.session
        # create the fixtures
        for objs in self.fixtures_pg.values():
            for obj in objs:
                self.session.add(obj)
        self.session.commit()

    fixtures_pg = {}


class HSSPgEmptyTestCase(HssPgTestBase):
    def test_no_accounts_existent(self):
        self.assertFalse(self.session.query(Account).all())


class HSSPgOneAccountTestCase(HSSOneAccountFixture, HssPgTestBase):
    def setUp(self):
        super().setUp()
        self.received_accounts = self.session.query(Account).all()
        self.received_account = self.received_accounts[0]

    def test_number_of_accounts(self):
        self.assertEqual(len(self.received_accounts),
                         len(self.fixtures_pg[Account]))

    def test_accountname(self):
        self.assertEqual(self.fixtures_pg[Account][0].account,
                         self.received_account.account)


class OneAccountTestBase(HSSOneAccountFixture, HssPgTestBase):
    def setUp(self):
        super().setUp()
        account = self.fixtures_pg[Account][0].account
        # re-receive the account in order to get the relationship
        self.account = db.session.query(Account).filter_by(account=account).one()
        self.user = User(uid=self.account.account)


class PgUserDataTestCase(OneAccountTestBase):
    def test_realname_passed(self):
        self.assertEqual(self.user.realname, self.account.name)

    def test_uid_passed(self):
        self.assertEqual(self.user.uid, self.account.account)

    def test_login_passed(self):
        self.assertEqual(self.user.login, self.account.account)

    def test_credit_passed(self):
        self.assertEqual(self.user.credit, self.account.traffic_balance / 1024)

    def test_address_passed(self):
        access = self.account.access
        for part in [access.building, access.floor, access.flat, access.room]:
            with self.subTest(part=part):
                self.assertIn(part, self.user.address)

    def test_mail_correct(self):
        acc = self.fixtures_pg[Account][0]
        user = User.get(acc.account)
        expected_mail = "{}@wh12.tu-dresden.de".format(acc.account)
        self.assertEqual(user.mail, expected_mail)


class UserFromIpTestCase(OneAccountTestBase):
    def test_from_ip_correct_user(self):
        for ip in self.fixtures_pg[IP]:
            if not ip.account:
                continue
            with self.subTest(ip=ip.ip):
                self.assertEqual(User.get(ip.account), User.from_ip(ip.ip))

    def test_from_ip_without_account_anonymous(self):
        for ip in self.fixtures_pg[IP]:
            if ip.account:
                continue

            with self.subTest(ip=ip.ip):
                self.assertIsInstance(User.from_ip(ip.ip), AnonymousUserMixin)


class UserIpsTestCase(OneAccountTestBase):
    def test_ips_passed(self):
        for account in self.fixtures_pg[Account]:
            with self.subTest(account=account):
                user = User.get(account.account)
                expected_ips = self.session.query(Account).get(account.account).ips
                for ip in expected_ips:
                    with self.subTest(ip=ip):
                        self.assertIn(ip.ip, user.ips)


class UserMacsTestCase(OneAccountTestBase):
    def test_macs_passed(self):
        for mac in self.fixtures_pg.get(Mac, []):
            if mac.account is None:
                continue

            with self.subTest(mac=mac.mac):
                user = User.get(mac.account)
                self.assertIn(mac.mac.lower(), user.mac)


# Dependency injection of new fixture
class UserTrafficLogTestCaseMixin:
    def setUp(self):
        super().setUp()
        self.user = User.get(self.account.account)
        self.history = self.user.traffic_history

    def test_traffic_log_correct_length(self):
        self.assertEqual(len(self.history), 7)

    def test_traffic_data_passed(self):
        # Pick the latest 7 entries
        expected_logs = sorted(self.fixtures_pg[TrafficLog], key=attrgetter('date'))[-7:]
        expected_entries = []

        for date_delta in range(-6, 1):
            expected_date = (datetime.today() + timedelta(date_delta)).date()
            possible_logs = [log for log in expected_logs
                             if (log.date == expected_date and
                                 log.account == self.account.account)]
            try:
                expected_entries.append(possible_logs.pop())
            except IndexError:
                expected_entries.append(None)

        for entry, expected_log in zip(self.history, expected_entries):
            with self.subTest(entry=entry, expected_log=expected_log):

                if expected_log is None:
                    self.assertFalse(entry['input'])
                    self.assertFalse(entry['output'])
                else:
                    self.assertEqual(entry['day'], expected_log.date.weekday())
                    self.assertEqual(entry['input'], expected_log.bytes_in / 1024)
                    self.assertEqual(entry['output'], expected_log.bytes_out / 1024)

    def test_correct_credit_difference(self):
        for i, entry in enumerate(self.history):
            with self.subTest(i=i, entry=entry):
                try:
                    credit_difference = self.history[i+1]['credit'] - entry['credit']
                except IndexError:
                    pass
                else:
                    self.assertEqual(credit_difference, 3 * 1024**2 - entry['throughput'])


class UserTrafficLogTestCase(
        HSSOneTrafficAccountFixture,
        UserTrafficLogTestCaseMixin,
        OneAccountTestBase,
):
    pass


class UserMissingTrafficLogTestCase(
        HSSOneTrafficAccountDaysMissingFixture,
        UserTrafficLogTestCaseMixin,
        OneAccountTestBase,
):
    pass


class UsersActiveTestCase(
        HSSAccountsWithPropertiesFixture,
        HssPgTestBase,
):

    def setUp(self):
        super().setUp()
        self.accounts = self.session.query(Account).all()

    def test_user_is_active_or_not(self):
        for account in self.accounts:
            with self.subTest(account=account):
                user = User.get(account.account)
                self.assertEqual(user.has_connection, account.properties.active)

    def test_active_user_status_correct(self):
        for account in self.accounts:
            if not account.properties.active:
                continue

            with self.subTest(account=account):
                user = User.get(account.account)
                self.assertEqual(user.status, gettext("Aktiv"))

    def test_passive_user_status_correct(self):
        for account in self.accounts:
            if account.properties.active:
                continue

            with self.subTest(account=account):
                user = User.get(account.account)
                self.assertEqual(user.status, gettext("Passiv"))


class UserFinanceTestCase(HSSOneFinanceAccountFixture, OneAccountTestBase):
    def test_finance_balance_correct(self):
        self.assertEqual(self.user.finance_balance, 3.5)

    def test_last_update_date_exists(self):
        expected_date = max(l.timestamp for l in self.fixtures_pg[AccountStatementLog])
        self.assertEqual(self.user.last_finance_update, expected_date)


class UserNoFinanceTestCase(OneAccountTestBase):
    def test_finance_balance_zero(self):
        """Test that an account with nothing set has a zero finance balance"""
        self.assertEqual(self.user.finance_balance, 0)


class UserFinanceLogTestCase(HSSOneFinanceAccountFixture, OneAccountTestBase):
    def setUp(self):
        super().setUp()
        self.transactions = self.account.combined_transactions

    def test_user_transaction_length_correct(self):
        expected_length = len(self.account.transactions) + len(self.account.fees)
        self.assertEqual(len(self.transactions), expected_length)

    def test_user_transaction_sorted(self):
        last_log = None
        for log in self.transactions:
            if last_log is not None:
                self.assertLessEqual(last_log[2], log[2])
            last_log = log
