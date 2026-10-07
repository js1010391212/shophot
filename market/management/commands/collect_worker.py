import time
from django.core.management.base import BaseCommand
from market.jobs import run_next


class Command(BaseCommand):
    help = "执行采集队列；--once 处理当前队列后退出（可由定时任务调用）"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write("ShopHot 采集进程启动，按 Ctrl+C 停止。")
        try:
            while True:
                if not run_next():
                    if options["once"]:
                        break
                    time.sleep(2)
        except KeyboardInterrupt:
            self.stdout.write("采集进程已停止；中断任务会在下次运行时回收。")
