"""Gunicorn 설정"""
import logging

workers = 1
bind = "0.0.0.0:5000"
timeout = 300
loglevel = "info"
accesslog = "-"

_scheduler = None


def post_fork(server, worker):
    global _scheduler
    try:
        from scheduler import create_scheduler
        _scheduler = create_scheduler()
        _scheduler.start()
        logging.getLogger(__name__).info("APScheduler 시작됨")
    except Exception as e:
        logging.getLogger(__name__).error("APScheduler 시작 실패: %s", e)


def worker_exit(server, worker):
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
