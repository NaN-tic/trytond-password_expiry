# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import datetime
import logging
import random
import string
import secrets
from trytond.cache import Cache
from trytond.config import config
from trytond.model import fields, ModelView
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, StateTransition, Button
from trytond.i18n import gettext
from trytond.exceptions import UserError
from trytond.res.user import _send_email

EXPIRY_DAYS = config.getint('security', 'password_expiry_days', default=365)
PASSWORD_FACTOR = config.getfloat('security', 'password_factor', default=0.75)

class WeakPassword(UserError):
    pass

def gen_password():
    choice = secrets.choice
    characters = []
    for number, options in [
            (8, string.ascii_letters),
            (2, string.digits),
            (2, string.punctuation),
            ]:
        characters += [choice(options) for x in range(number)]
    random.shuffle(characters)
    return ''.join(characters)


class User(metaclass=PoolMeta):
    __name__ = "res.user"
    last_change_date = fields.DateTime('Last Change Date', required=True)
    _get_last_change_cache = Cache('res_user.last_change_date', context=False)

    @staticmethod
    def default_last_change_date():
        return datetime.datetime.now()

    @classmethod
    def set_preferences(cls, values):
        with Transaction().set_context(from_preferences=True):
            super(User, cls).set_preferences(values)

    @classmethod
    def set_password(cls, users, name, value):
        if not value:
            # use gen_password method from password_expiry and not from res.user
            # because random password is more strong (pass check_password_strength)
            value = gen_password()
        cls.check_password_strength(value)
        super(User, cls).set_password(users, name, value)
        current, other = [], []
        user_id = Transaction().user
        for user in users:
            if user.id == user_id:
                current.append(user)
            else:
                other.append(user)
        cls.write(current, {
                'last_change_date': datetime.datetime.now(),
                },
            other, {
                'last_change_date': datetime.datetime.min,
                })

    @classmethod
    def get_preferences(cls, context_only=False):
        pool = Pool()
        ModelData = pool.get('ir.model.data')
        preferences = super(User, cls).get_preferences(context_only)
        date = cls._get_last_change_date()
        if (datetime.datetime.now() - date).days > EXPIRY_DAYS:
            actions = preferences.get('actions', [])
            actions.insert(0, ModelData.get_id('password_expiry',
                    'wizard_expired_password'))
            preferences['actions'] = actions
        return preferences.copy()

    @classmethod
    def _get_last_change_date(cls, login=None):
        if login is None:
            login = cls(Transaction().user).login
        result = cls._get_last_change_cache.get(login)
        if result:
            return result
        cursor = Transaction().connection.cursor()
        table = cls.__table__()
        cursor.execute(*table.select(table.last_change_date,
                where=(table.login == login) & table.active))
        result = cursor.fetchone()
        if result:
            result, = result
        else:
            result = datetime.datetime.max
        cls._get_last_change_cache.set(login, result)
        return result

    @classmethod
    def check_password_strength(cls, password):
        try:
            import passwordmeter
        except ImportError:
            logger = logging.getLogger('res.user')
            logger.warn('Unable to check password strength. Please install '
                'passwordmeter library')
            return
        strength, suggestions = passwordmeter.test(password)
        if strength < PASSWORD_FACTOR:
            raise WeakPassword(gettext('password_expiry.password_strength'))

    @classmethod
    @ModelView.button
    def reset_password(cls, users, length=8, from_=None):
        # Do not call super() because we must use our own gen_password method
        for user in users:
            user.password_reset = gen_password()
            user.password_reset_expire = (
                datetime.datetime.now() + datetime.timedelta(
                    seconds=config.getint('password', 'reset_timeout')))
            user.password = None
            user.last_change_date = datetime.datetime.now()
        cls.save(users)
        _send_email(from_, users, cls.get_email_reset_password)

    @classmethod
    def create(cls, vlist):
        for value in vlist:
            if value.get('password'):
                # Force validation before creation
                cls.check_password_strength(value.get('password'))
        instances = super(User, cls).create(vlist)
        # Restart the cache for _get_last_change
        cls._get_last_change_cache.clear()
        return instances

    @classmethod
    def write(cls, *args):
        super(User, cls).write(*args)
        # Restart the cache for _get_last_change
        cls._get_last_change_cache.clear()


class ExpiredPasswordStart(ModelView):
    'Expired Password Start'
    __name__ = 'res.user.expired_password.start'
    old_password = fields.Char('Old Password', required=True)
    password = fields.Char('Password', required=True)


class ExpiredPassword(Wizard):
    'Expired Password'
    __name__ = 'res.user.expired_password'

    start = StateView('res.user.expired_password.start',
        'password_expiry.expired_password_start_view_form', [
            Button('Change Password', 'set_password', 'tryton-ok',
                default=True),
            ])
    set_password = StateTransition()

    def transition_set_password(self):
        pool = Pool()
        User = pool.get('res.user')
        User.set_preferences({'password': self.start.password})
        return 'end'

    def end(self):
        return 'reload menu'
