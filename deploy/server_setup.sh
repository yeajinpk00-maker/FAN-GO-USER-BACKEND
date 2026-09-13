#!/usr/bin/env bash
# EC2 (Amazon Linux 2023) 에서 최초 1회 실행. 프로젝트 파일을 이미 전송한 상태여야 한다.
#   전송 위치: /home/ec2-user/FANGO_USER
set -euo pipefail

APP_DIR="/home/ec2-user/FANGO_USER"
cd "$APP_DIR"

echo "== 1. Python 3.11 설치 =="
sudo dnf install -y python3.11 python3.11-pip

echo "== 2. 가상환경 생성 & 의존성 설치 =="
python3.11 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

echo "== 3. .env 확인 =="
if [ ! -f .env ]; then
  echo "!! .env 가 없다. 아래 값을 채운 .env 를 먼저 만들고 다시 실행하라." >&2
  echo "   DATABASE_URL=mysql+pymysql://user:pass@<RDS 엔드포인트>:3306/team2" >&2
  echo "   KAKAO_REST_API_KEY=<카카오 REST API 키>   # 없으면 '동선 만들기'만 조용히 실패함(서버 기동/헬스체크는 정상)" >&2
  echo "   SECRET_KEY=<임의의 긴 랜덤 문자열>          # JWT 서명용, 운영 환경 필수" >&2
  exit 1
fi

echo "== 3-1. 필수 환경변수 존재 여부만 확인(값은 출력하지 않음) =="
for var in DATABASE_URL KAKAO_REST_API_KEY SECRET_KEY; do
  if grep -q "^${var}=." .env; then
    echo "  - ${var}: 있음"
  else
    echo "  - ${var}: !! 없음 또는 빈 값 (.env에 ${var}=... 추가 필요)"
  fi
done

echo "== 4. DB 연결 스모크 테스트 =="
./.venv/bin/python -c "
from sqlalchemy import text
from database import engine
with engine.connect() as c:
    print('DB OK:', c.execute(text('SELECT 1')).scalar())
"

echo "== 5. systemd 서비스 등록 =="
sudo cp deploy/fangouser.service /etc/systemd/system/fangouser.service
sudo systemctl daemon-reload
sudo systemctl enable --now fangouser
sleep 2
sudo systemctl status fangouser --no-pager || true

echo "== 6. 헬스체크 =="
curl -s http://127.0.0.1:8000/health && echo

echo
echo "완료. 보안그룹에서 8000 포트를 열면 http://<EC2-공인IP>:8000/docs 로 접속 가능."
