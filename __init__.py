# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .user import *


def register():
    Pool.register(
        User,
        ExpiredPasswordStart,
        PasswordConfiguration,
        module='password_expiry', type_='model')
    Pool.register(
        ExpiredPassword,
        module='password_expiry', type_='wizard')
