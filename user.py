# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import datetime
import logging
import random
import string
from email.mime.text import MIMEText
from email.header import Header
from trytond.cache import Cache
from trytond.config import config
from trytond.model import fields, ModelView
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.tools import get_smtp_server
from trytond.url import HOSTNAME
from trytond.wizard import Wizard, StateView, StateTransition, Button

EXPIRY_DAYS = config.getint('security', 'password_expiry_days', default=365)
PASSWORD_FACTOR = config.getfloat('security', 'password_factor', default=0.75)

__all__ = ['User', 'ExpiredPasswordStart', 'ExpiredPassword']
__metaclass__ = PoolMeta


class User:
    __name__ = "res.user"
    last_change_date = fields.DateTime('Last Change Date', required=True)
    _get_last_change_cache = Cache('res_user.last_change_date', context=False)

    @classmethod
    def __setup__(cls):
        super(User, cls).__setup__()
        cls._buttons.update({
                'reset_password': {},
                })
        cls._error_messages.update({
                'password_expired': ('Your password has expired, please '
                    'change it to a new one from user preferences.'),
                'password_strength': ('The supplied password is not strong '
                    'enough, please use a different one.'),
                'different_password': ('Please input a different password.'),
                'new_password_title': ('Your password has been changed.'),
                'new_password_body': ('Your new password of Tryton server'
                    ' %(hostname)s is %(new_password)s please login in order '
                    'to change it.'),
                })

    @staticmethod
    def default_last_change_date():
        return datetime.datetime.now()

    @classmethod
    def set_preferences(cls, values, parameters):
        if (values.get('password')
                and values.get('password') == parameters.get('password')):
            cls.raise_user_error('different_password')
        with Transaction().set_context(from_preferences=True):
            super(User, cls).set_preferences(values, parameters)

    @classmethod
    def set_password(cls, users, name, value):
        if not value:
            value = cls.generate_new_password()
        cls.check_password_strenght(value)
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
    def check_password_strenght(cls, password):
        try:
            import passwordmeter
        except ImportError:
            logger = logging.getLogger('res.user')
            logger.warn('Unable to check password strenght. Please install '
                'passwordmeter library')
            return
        strenght, suggestions = passwordmeter.test(password)
        if strenght < PASSWORD_FACTOR:
            cls.raise_user_error('password_strength')

    @staticmethod
    def generate_new_password():
        characters = []
        for number, options in [
                (8, string.ascii_letters),
                (2, string.digits),
                (2, string.punctuation),
                ]:
            characters += [random.choice(options) for x in range(number)]
        random.shuffle(characters)
        new_password = ''.join(characters)
        return new_password

    @classmethod
    @ModelView.button
    def reset_password(cls, users):
        to_write = []
        for user in users:
            to_write.extend(([user], {
                        'password': cls.generate_new_password(),
                        }))
        if to_write:
            cls.write(*to_write)
            # Force password expiration
            cls.write(users, {'last_change_date': datetime.datetime.min})
            # Don't notify in the users until all is done
            actions = iter(to_write)
            for users, values in zip(actions, actions):
                for user in users:
                    user.notify_new_password(values['password'])

    def notify_new_password(self, new_password):
        from_addr = config.get('email', 'from')
        to_addr = self.email
        subject = self.raise_user_error('new_password_title',
            raise_exception=False)
        body = self.raise_user_error('new_password_body', {
                'new_password': new_password,
                'hostname': HOSTNAME,
                }, raise_exception=False)
        if not self.email or not self.from_addr:
            return

        msg = MIMEText(body, _charset='utf-8')
        msg['To'] = to_addr
        msg['From'] = from_addr
        msg['Subject'] = Header(subject, 'utf-8')
        logger = logging.getLogger(__name__)
        if not to_addr:
            logger.error(msg.as_string())
        else:
            try:
                server = get_smtp_server()
                server.sendmail(from_addr, to_addr, msg.as_string())
                server.quit()
            except Exception, exception:
                logger.error('Unable to deliver email (%s):\n %s'
                    % (exception, msg.as_string()))

    @classmethod
    def create(cls, vlist):
        for value in vlist:
            if value.get('password'):
                # Force validation before creation
                cls.check_password_strenght(value.get('password'))
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
        User.set_preferences({'password': self.start.password},
            old_password=self.start.old_password)
        return 'end'

    def end(self):
        return 'reload menu'
