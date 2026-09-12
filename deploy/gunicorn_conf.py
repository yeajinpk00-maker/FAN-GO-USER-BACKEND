"""Gunicorn 설정. FANGO_USER (이 프로젝트, adminProject 서버의 "프로젝트 B") 전용.

adminProject 는 8001 포트를 쓴다. 이 프로젝트(user용)는 8000.
워커는 반드시 1개로 고정한다 — main.py의 startup 이벤트가 APScheduler
배치를 띄우는데, 워커가 여러 개면 워커마다 스케줄러가 따로 돌아
같은 배치가 중복 실행된다.
"""

bind = "0.0.0.0:8000"

workers = 1
worker_class = "uvicorn.workers.UvicornWorker"

timeout = 60
graceful_timeout = 30
keepalive = 5

accesslog = "-"   # stdout -> journald
errorlog = "-"
loglevel = "info"
