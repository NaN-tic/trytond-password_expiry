# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import datetime
import unittest
from trytond.error import UserError
import trytond.tests.test_tryton
from trytond.tests.test_tryton import test_view, test_depends
from trytond.tests.test_tryton import POOL, DB_NAME, USER, CONTEXT
from trytond.transaction import Transaction


class TestCase(unittest.TestCase):
    'Test module'

    def setUp(self):
        trytond.tests.test_tryton.install_module('password_expiry')
        self.user = POOL.get('res.user')
        self.model_data = POOL.get('ir.model.data')

    def test0005views(self):
        'Test views'
        test_view('password_expiry')

    def test0006depends(self):
        'Test depends'
        test_depends()

    def create_user(self, login, password):
        user, = self.user.create([{
                    'name': login,
                    'login': login,
                    'password': password,
                    }])

    def test0010_expired_login(self):
        with Transaction().start(DB_NAME, USER, CONTEXT) as transaction:
            with self.assertRaises(UserError) as cm:
                self.create_user('user', '12345')
            self.assertEqual(cm.exception.message, 'The supplied password is '
                'not strength enought, please use a diferent password.')

            complex_password = 'Tryton45.Foundation'

            self.create_user('user', complex_password)

            user, = self.user.search([('login', '=', 'user')])
            user_id = self.user.get_login('user', complex_password)
            self.assertEqual(user_id, user.id)
            # Expire the password
            user.last_change_date = datetime.datetime.min
            user.save()

            user_id = self.user.get_login('user', complex_password)
            self.assertEqual(user_id, user.id)
            with transaction.set_user(user_id):
                actions = self.user.get_preferences()['actions']
            expired_password_action = self.model_data.get_id('password_expiry',
                'wizard_expired_password')
            self.assertEqual(actions[0], expired_password_action)

            new_complex_password = 'Foundation.Tryton45'
            with Transaction().set_user(user.id):
                with self.assertRaises(UserError) as cm:
                    self.user.set_preferences({'password': complex_password},
                        old_password=complex_password)
                self.assertEqual(cm.exception.message, 'Please input a '
                    'diferent password.')
                self.user.set_preferences({'password': new_complex_password},
                    old_password=complex_password)
            user_id = self.user.get_login('user', complex_password)
            self.assertEqual(user_id, 0)
            user_id = self.user.get_login('user', new_complex_password)
            self.assertEqual(user_id, user.id)

            self.user.reset_password([user])

            with transaction.set_user(user_id):
                actions = self.user.get_preferences()['actions']
            self.assertEqual(actions[0], expired_password_action)
            # Nothing is raised if user does not exist
            user_id = self.user.get_login('login', complex_password)
            self.assertEqual(user_id, 0)


def suite():
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestCase))
    return suite
