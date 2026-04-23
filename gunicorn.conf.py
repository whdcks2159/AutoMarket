"""Gunicorn 설정 — 스케줄러를 워커 fork 이후에 실행."""
import logging

workers = 1  # 스케줄러 중복 실행 방지를 위해 워커 1개
bind = "0.0.0.0:5000"
timeout = 120
loglevel = "info"

_scheduler = None


def post_fork(server, worker):
    # on_starting 대신 post_fork 사용: fork 이전에 스케줄러(백그라운드 스레드)를
    # 시작하면 fork된 워커가 잠긴 mutex를 상속받아 데드락이 발생한다.
    global _scheduler
    from scheduler import create_scheduler
    _scheduler = create_scheduler()
    _scheduler.start()
    logging.getLogger(__name__).info("APScheduler 시작됨")


def worker_exit(server, worker):
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logging.getLogger(__name__).info("APScheduler 종료됨")
