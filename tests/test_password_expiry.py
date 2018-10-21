# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import datetime
import unittest
import trytond.tests.test_tryton
from trytond.error import UserError
from trytond.pool import Pool
from trytond.tests.test_tryton import ModuleTestCase, with_transaction
from trytond.transaction import Transaction


class TestCase(ModuleTestCase):
    'Test module'
    module = 'password_expiry'

    def create_user(self, login, password):
        pool = Pool()
        User = pool.get('res.user')
        user, = User.create([{
                    'name': login,
                    'login': login,
                    'password': password,
                    }])
        return user

    @with_transaction()
    def test0010_expired_login(self):
        pool = Pool()
        User = pool.get('res.user')
        ModelData = pool.get('ir.model.data')

        with self.assertRaises(UserError) as cm:
            self.create_user('user', '12345')
        self.assertEqual(cm.exception.message, 'The supplied password is '
            'not strong enough, please use a different one.')

        complex_password = 'Tryton.45321908*'

        self.create_user('user', complex_password)

        user, = User.search([('login', '=', 'user')])
        user_id = User.get_login('user', {
                'password': complex_password,
                })
        self.assertEqual(user_id, user.id)

        # Expire the password
        user.last_change_date = datetime.datetime.min
        user.save()

        user_id = User.get_login('user', {
                'password': complex_password,
                })
        self.assertEqual(user_id, user.id)
        with Transaction().set_user(user_id):
            actions = User.get_preferences()['actions']
        expired_password_action = ModelData.get_id('password_expiry',
            'wizard_expired_password')
        self.assertEqual(actions[0], expired_password_action)

        new_complex_password = 'Tryton.45321908!'
        with Transaction().set_user(user.id):
            User.set_preferences({
                    'password': new_complex_password,
                    })
        user_id = User.get_login('user', {
                'password': complex_password,
                })
        self.assertEqual(user_id, None)
        user_id = User.get_login('user', {
                'password': new_complex_password,
                })
        self.assertEqual(user_id, user.id)

        User.reset_password([user])

        with Transaction().set_user(user_id):
            actions = User.get_preferences()['actions']
        self.assertEqual(actions[0], expired_password_action)

        # Nothing is raised if user does not exist
        user_id = User.get_login('login', {
                'password': complex_password,
                })
        self.assertEqual(user_id, None)


def suite():
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestCase))
    return suite
