import os
from datetime import datetime

from dotenv import load_dotenv

# 프로세스가 실제로 언제 기동됐는지(모듈이 처음 임포트된 시각) — 워커 1개 고정
# (deploy/gunicorn_conf.py) 구조라 이 값이 곧 "마지막 재시작 시각"과 사실상 같다.
# /health/env가 .env 파일 수정 시각과 비교해 "재시작이 .env 수정 이후인지"를
# SSH 없이 원격으로 판단할 수 있게 해준다.
_PROCESS_STARTED_AT = datetime.now().isoformat()

# load_dotenv()를 인자 없이 호출하면 python-dotenv가 "현재 작업 디렉터리(CWD)"에서 위로
# 올라가며 .env를 찾는다(find_dotenv 기본 동작) — 이 스크립트 파일 위치가 아니다.
# 배포 프로세스가 프로젝트 루트가 아닌 다른 CWD에서 기동되면(예: systemd/pm2에
# WorkingDirectory 미지정, 절대경로로 uvicorn만 실행 등) .env를 못 찾아도 예외 없이
# 조용히 무시되고, 이후 모든 os.getenv(...)가 None을 반환한다.
# → 실행 파일(main.py) 기준 절대경로로 명시해 CWD와 무관하게 항상 같은 .env를 읽도록 고정.
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_ENV_PATH)

from logging_config import attach_uvicorn_file_logging, setup_logging

# uvicorn이 로거를 세팅하기 전에 먼저 호출해야 uvicorn 로거에도 파일 핸들러가 붙는다.
setup_logging()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import models
from auth import router as auth_router
from batch import start_scheduler
from database import SessionLocal, engine

# 이미 ERD 기준으로 테이블이 만들어져 있다면 이 줄은 없어도 됩니다.
# (없는 테이블만 생성하며, 기존 테이블은 건드리지 않습니다.)
models.Base.metadata.create_all(bind=engine)


def seed_defaults():
    """auth/user_status 기본 코드값이 비어 있으면 채워 넣는다."""
    db = SessionLocal()
    try:
        if not db.query(models.Auth).first():
            db.add_all(
                [
                    models.Auth(auth_no=1, auth_nm="사용자"),
                    models.Auth(auth_no=2, auth_nm="총괄관리자"),
                    models.Auth(auth_no=3, auth_nm="중간관리자"),
                    models.Auth(auth_no=4, auth_nm="직원"),
                ]
            )
        if not db.query(models.UserStatus).first():
            # status_no 2=정지, 4=탈퇴는 로그인 차단 로직(auth.py)에서 하드코딩으로 참조한다.
            db.add_all(
                [
                    models.UserStatus(status_no=1, status_nm="활성"),
                    models.UserStatus(status_no=2, status_nm="정지"),
                    models.UserStatus(status_no=3, status_nm="삭제요청"),
                    models.UserStatus(status_no=4, status_nm="탈퇴"),
                ]
            )
        # nationality_no/lang_no는 회원가입 필수값이라, 비어 있으면 가입 자체가
        # FK 제약(R_39 등)에 걸려 항상 실패한다. 최소 시작 데이터만 넣어둔다 —
        # 실제 목록은 팀에서 필요에 맞게 추가/수정하면 된다.
        if not db.query(models.Nationality).first():
            db.add_all(
                [
                    models.Nationality(nationality_no=1, nationality_nm="대한민국"),
                    models.Nationality(nationality_no=2, nationality_nm="미국"),
                    models.Nationality(nationality_no=3, nationality_nm="일본"),
                    models.Nationality(nationality_no=4, nationality_nm="중국"),
                    models.Nationality(nationality_no=5, nationality_nm="기타"),
                ]
            )
        if not db.query(models.Lang).first():
            db.add_all(
                [
                    models.Lang(lang_no=1, lang_nm="한국어"),
                    models.Lang(lang_no=2, lang_nm="English"),
                    models.Lang(lang_no=3, lang_nm="日本語"),
                ]
            )
        # 국적별 기본 언어 매핑. 모든 국적이 매핑을 가져야 하며(/nationalities가
        # inner join으로 조회), 별도 매핑이 없는 국적은 English(lang_no=2)로 채운다.
        if not db.query(models.NatLang).first():
            db.add_all(
                [
                    models.NatLang(nationality_no=1, lang_no=1),  # 대한민국 -> 한국어
                    models.NatLang(nationality_no=2, lang_no=2),  # 미국 -> English
                    models.NatLang(nationality_no=3, lang_no=3),  # 일본 -> 日本語
                    models.NatLang(nationality_no=4, lang_no=2),  # 중국 -> English
                    models.NatLang(nationality_no=5, lang_no=2),  # 기타 -> English
                ]
            )
        db.commit()
    finally:
        db.close()


seed_defaults()

app = FastAPI()
app.include_router(auth_router)

# 로컬 개발 서버 주소 + 배포 서버(EC2) 프론트 주소.
# allow_credentials=True 조합에서는 이 목록에 없는 origin은 브라우저가 응답을
# CORS로 막아버리고, 그 결과가 프론트 쪽에는 "쿠키가 없어서 로그인이 풀린 것"과
# 똑같이(에러 문구 없이 로그인 화면으로 이동) 보인다 — 배포 프론트 주소가
# 아래 목록에 없으면 이게 원인일 가능성이 높음.
_DEV_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://192.168.0.191:5173",
]
# 2026-09-13: EC2(54.180.95.40) 프론트 주소를 코드에 직접 추가 — 서버 .env에
# EXTRA_CORS_ORIGINS를 수동으로 넣어야 하는 방식은 SSH 키 보유자에게 매번
# 의존해야 해서, git push만으로 CI/CD가 자동 반영하도록 소스에 직접 반영한다
# (실측: 포트 80="ktp-frondend-react", 유저용 프론트 — /trip/confirm 등에서
# CORS 에러 재현됨. 포트 8081="FAN:GO Admin", 관리자 패널 — 같은 백엔드를
# 호출할 가능성을 대비해 함께 등록).
_PROD_CORS_ORIGINS = [
    "http://ec2-54-180-95-40.ap-northeast-2.compute.amazonaws.com",
    "http://ec2-54-180-95-40.ap-northeast-2.compute.amazonaws.com:8081",
]
# .env의 EXTRA_CORS_ORIGINS(쉼표 구분)도 계속 지원 — 코드 재배포 없이 추가로
# 필요한 origin이 생기면 여전히 이 방법으로도 넣을 수 있다(하위호환 유지).
_EXTRA_CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("EXTRA_CORS_ORIGINS", "").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEV_CORS_ORIGINS + _PROD_CORS_ORIGINS + _EXTRA_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 프로필 사진 등 업로드 파일을 그대로 서빙 (auth.py의 PROFILE_IMAGE_DIR/URL_PREFIX와 짝).
os.makedirs("uploads/profile_images", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.on_event("startup")
def _start_batch_scheduler():
    # 서버 프로세스 하나당 한 번만 떠야 한다 — uvicorn을 --workers 여러 개로 띄우면
    # 워커마다 스케줄러가 따로 돌아 같은 배치가 중복 실행된다(멱등해서 결과는 같지만
    # 낭비). 지금은 단일 워커 개발 서버라 문제 없음.
    start_scheduler()
    # uvicorn이 자기 로거를 다 세팅한 뒤인 startup 시점에 붙여야
    # uvicorn 쪽에서 핸들러를 갈아끼우며 지우는 일이 없다.
    attach_uvicorn_file_logging()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/env")
async def health_env():
    """값은 절대 노출하지 않고 존재 여부/길이/타임스탬프만 반환하는 진단 엔드포인트
    (2026-09-13 신규) — "KAKAO_REST_API_KEY가 .env에 설정되어 있지 않습니다" 류
    문제를 SSH 접근 없이도 원격으로 확인하려고 추가했다. 인증 없음 — 반환값에
    민감정보(값 자체)가 전혀 없어 노출 위험이 없다(길이만 알 수 있음, 값은 알 수 없음).

    env_file_path: main.py가 실제로 읽으려 시도한 .env 절대경로(로컬/배포 환경이
      다른 위치를 참조하고 있는지 확인용).
    env_file_modified_at: 그 파일이 마지막으로 수정된 시각.
    process_started_at: 이 프로세스가 기동된 시각(워커 1개 고정 구조라 사실상
      "마지막 재시작 시각"과 동일) — env_file_modified_at보다 이전이면, .env를
      고친 뒤 재시작을 안 한 것이 원인일 가능성이 높다.
    vars: 각 환경변수의 존재 여부(present)와 길이(length)만 — 값 자체는 없음.
    """
    def _presence(name: str) -> dict:
        v = os.getenv(name)
        return {"present": bool(v), "length": len(v) if v else 0}

    env_mtime = None
    if os.path.exists(_ENV_PATH):
        env_mtime = datetime.fromtimestamp(os.path.getmtime(_ENV_PATH)).isoformat()

    return {
        "env_file_path": _ENV_PATH,
        "env_file_exists": os.path.exists(_ENV_PATH),
        "env_file_modified_at": env_mtime,
        "process_started_at": _PROCESS_STARTED_AT,
        "vars": {
            "DATABASE_URL": _presence("DATABASE_URL"),
            "KAKAO_REST_API_KEY": _presence("KAKAO_REST_API_KEY"),
            "SECRET_KEY": _presence("SECRET_KEY"),
            "COOKIE_SECURE": _presence("COOKIE_SECURE"),
            "EXTRA_CORS_ORIGINS": _presence("EXTRA_CORS_ORIGINS"),
        },
    }


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)