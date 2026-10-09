"""开发用联盟详情响应预览；不调用网络，不写入任何业务记录。"""
import json
import os
import stat
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from market.aliexpress_affiliate import (
    AffiliateRequestContext, AffiliateResponseError, MAX_RESPONSE_BYTES,
    normalize_affiliate_response,
)


def read_fixture(path):
    """只读一个有界普通文件；不跟随符号链接或阻塞在设备/管道上。"""
    descriptor = None
    try:
        descriptor = os.open(Path(path), os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_size > MAX_RESPONSE_BYTES:
            raise CommandError('测试响应必须是大小不超过上限的普通文件。')
        with os.fdopen(descriptor, 'rb') as stream:
            descriptor = None
            raw = stream.read(MAX_RESPONSE_BYTES + 1)
        if not raw or len(raw) > MAX_RESPONSE_BYTES:
            raise CommandError('测试响应为空或大小超过上限。')
        return raw
    except (OSError, TypeError, ValueError):
        # 路径/OS 错误可能含个人资料；不用原异常文字做输出。
        raise CommandError('无法读取测试响应；请检查普通文件及读取权限。') from None
    finally:
        if descriptor is not None:
            os.close(descriptor)


class Command(BaseCommand):
    help = '仅开发验收：预览离线速卖通联盟JSON测试响应，不调用API、不保存商品。'
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--fixture-path', required=True)
        parser.add_argument('--product-id', required=True)
        parser.add_argument('--country', required=True)
        parser.add_argument('--target-currency', required=True)
        parser.add_argument('--requested-at', required=True)
        parser.add_argument('--received-at', required=True)

    def handle(self, *args, **options):
        try:
            requested_at = parse_datetime(options['requested_at'])
            received_at = parse_datetime(options['received_at'])
        except (TypeError, ValueError):
            raise CommandError('请求与接收时间须为带时区的ISO日期时间。') from None
        try:
            context = AffiliateRequestContext(
                product_id=options['product_id'], country=options['country'],
                target_currency=options['target_currency'],
                requested_at=requested_at, received_at=received_at,
            )
            preview = normalize_affiliate_response(read_fixture(options['fixture_path']), context)
        except AffiliateResponseError as exc:
            raise CommandError(f'离线测试响应未通过校验（{exc.code}）：{exc}') from None
        self.stdout.write(json.dumps({
            'mode': 'offline_fixture', 'live_api_verified': False,
            'database_written': False, 'preview': preview.as_dict(),
        }, ensure_ascii=False, indent=2, allow_nan=False))
