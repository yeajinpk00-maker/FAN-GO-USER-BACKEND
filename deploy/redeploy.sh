#!/usr/bin/env bash
# 코드 갱신 후 재배포. (파일 다시 전송한 뒤 서버에서 실행)
set -euo pipefail
cd /home/ec2-user/FANGO_USER
./.venv/bin/pip install -r requirements.txt
sudo systemctl restart fangouser
sleep 2
sudo systemctl status fangouser --no-pager | head -n 10
curl -s http://127.0.0.1:8002/health && echo
