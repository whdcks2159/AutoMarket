"""Gunicorn 설정 — 스케줄러를 워커 시작 후 실행."""
import atexit
import logging

workers = 1  # 스케줄러 중복 실행 방지를 위해 워커 1개
bind = "0.0.0.0:5000"
timeout = 120
loglevel = "info"

_scheduler = None


def on_starting(server):
    global _scheduler
    from scheduler import create_scheduler
    _scheduler = create_scheduler()
    _scheduler.start()
    logging.getLogger(__name__).info("APScheduler 시작됨")


def on_exit(server):
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logging.getLogger(__name__).info("APScheduler 종료됨")
