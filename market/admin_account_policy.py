"""Require an explicit, command-scoped choice for new privileged accounts.

This protects normal ORM saves (including create_superuser), not raw SQL or a
host administrator deliberately bypassing application code.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from django.core.exceptions import PermissionDenied


_creation_allowed = ContextVar('shophot_privileged_account_creation', default=False)


@contextmanager
def privileged_account_creation():
    token = _creation_allowed.set(True)
    try:
        yield
    finally:
        _creation_allowed.reset(token)


def protect_new_privileged_account(sender, instance, using, **kwargs):
    if not (instance.is_staff or instance.is_superuser) or _creation_allowed.get():
        return
    # Loaded objects can insert too: clearing/changing their PK does not reset
    # _state.adding. Check the target database rather than trusting that flag.
    if (instance._state.adding or instance.pk is None
            or not sender._base_manager.using(using).filter(pk=instance.pk).exists()):
        raise PermissionDenied(
            '新增特权账号须使用 create_privileged_account --allow-new-privileged-account；'
            '先核对当前任务、目标环境及既有账号，不自动改名重试。'
        )
