"""콘솔에 찍히는 로그를 파일에도 그대로 쌓기 위한 설정.

로컬에서 `uvicorn main:app --reload`나 `python main.py`로 띄우면 로그가 터미널에만
찍히고 창을 닫으면 사라진다. setup_logging()을 호출하면 같은 로그가
logs/app.log에도 append되어 나중에 다시 확인할 수 있다.

배포(systemd+gunicorn)는 accesslog/errorlog="-"(stdout)로 journald가 이미 로그를
보관하지만, 여기서도 파일 핸들러를 추가해 journalctl 없이 파일로도 바로 확인할 수
있게 한다.
"""

import logging
import logging.handlers
import os

_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")

_FORMATTER = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")

_file_handler = None


def _get_file_handler():
    global _file_handler
    if _file_handler is None:
        os.makedirs(_LOG_DIR, exist_ok=True)
        _file_handler = logging.handlers.RotatingFileHandler(
            _LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        _file_handler.setFormatter(_FORMATTER)
    return _file_handler


def setup_logging(level=logging.INFO):
    """앱 자체 로거(logging.getLogger(__name__) 쓰는 모듈들)와 print 대신 로깅을
    쓰는 코드가 남기는 로그를 파일에 쌓는다. main.py 맨 위, 다른 모듈을 import하기
    전에 호출한다."""
    file_handler = _get_file_handler()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(_FORMATTER)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    if file_handler not in root_logger.handlers:
        root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


def attach_uvicorn_file_logging():
    """uvicorn access/error 로그(요청 로그, 서버 시작/에러 메시지 등)도 같은 파일에
    쌓는다. uvicorn이 자기 로거(uvicorn/uvicorn.error/uvicorn.access)를 스스로
    dictConfig로 초기화하는 시점 *이후*에 호출해야 한다 — 그보다 먼저 붙이면
    uvicorn이 핸들러 목록을 통째로 갈아끼우면서 지워버린다. 그래서 setup_logging()과
    분리해 FastAPI startup 이벤트에서 호출한다.

    "uvicorn.error"에는 직접 붙이지 않는다 — 기본적으로 propagate=True라서 부모인
    "uvicorn" 로거로 다시 전파되는데, 거기에도 같은 핸들러를 붙이면 같은 메시지가
    파일에 두 번 찍힌다. "uvicorn"에만 붙여두면 uvicorn.error 메시지도 전파를 통해
    한 번만 기록된다.
    """
    file_handler = _get_file_handler()
    for name in ("uvicorn", "uvicorn.access"):
        logger = logging.getLogger(name)
        if file_handler not in logger.handlers:
            logger.addHandler(file_handler)
