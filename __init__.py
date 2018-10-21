# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import user


def register():
    Pool.register(
        user.User,
        user.ExpiredPasswordStart,
        module='password_expiry', type_='model')
    Pool.register(
        user.ExpiredPassword,
        module='password_expiry', type_='wizard')
