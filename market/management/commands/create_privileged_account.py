"""Reuse Django's creation flow with an explicit per-command switch."""
from django.contrib.auth.management.commands.createsuperuser import Command as DjangoCommand
from django.core.management.base import CommandError

from market.admin_account_policy import privileged_account_creation


class Command(DjangoCommand):
    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument('--allow-new-privileged-account', action='store_true',
                            help='已核对当前建号任务、目标环境及既有账号；仅本次命令允许新增特权账号。')

    def handle(self, *args, **options):
        if not options.pop('allow_new_privileged_account', False):
            raise CommandError('默认禁止新增特权账号；核对当前任务后显式指定 --allow-new-privileged-account。')
        with privileged_account_creation():
            return super().handle(*args, **options)
