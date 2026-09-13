# GitHub Actions CI/CD 설정 (FANGO_USER)

같은 EC2(`54.180.95.40`)에서 이미 돌고 있는 adminProject(8001)와 같은 구조를 따른다.
이 프로젝트는 포트 **8000**, systemd 서비스명 **fangouser**를 쓴다.

## 흐름

```
git push (main)
   ├─ CI (ci.yml)      : 클라우드 러너에서 pip install + 문법 검사(compileall)
   └─ Deploy (deploy.yml): SSH로 EC2 접속 → rsync 소스 전송 → pip install
                            → systemctl restart fangouser → health 체크
```

`main.py`는 import 시점에 실제 DB에 접속해 기본 코드값을 seed하므로, DB가 없는
클라우드 러너에서는 import 검증 없이 문법 검사만 한다.

## 1. 서버 최초 셋업 (한 번만)

```
ssh -i D:\team2.pem ec2-user@54.180.95.40
mkdir -p ~/FANGO_USER
# (이 리포를 rsync/scp/git clone 으로 ~/FANGO_USER 에 올린 뒤)
cd ~/FANGO_USER
nano .env   # 아래 "필수 환경변수" 표 참고 — 특히 KAKAO_REST_API_KEY 빠뜨리기 쉬움
chmod +x deploy/*.sh
./deploy/server_setup.sh
```

`server_setup.sh`가 하는 일: Python 3.11 설치 → `.venv` 생성 → 의존성 설치 →
`.env` 확인 → DB 연결 스모크 테스트 → systemd 서비스 등록/시작 → 헬스체크.

이후 GitHub Actions의 `deploy.yml`은 이미 `.venv`와 systemd 서비스가 있다고
가정하고 rsync + restart만 한다. **`deploy.yml`의 rsync는 `.env`를 제외 목록에
넣어두었으므로(로컬 `.env`를 덮어쓰지 않기 위함), 이후 코드 배포로는 서버의
`.env`가 절대 갱신되지 않는다 — 새 환경변수가 필요해지면 서버에 SSH로 들어가
`nano .env`로 수동 추가해야 한다.**

### 필수 환경변수 (`.env`)

DB 연결 스모크 테스트(`server_setup.sh` 4단계)는 `DATABASE_URL`만 확인하므로,
아래 표의 다른 값이 빠져도 최초 셋업은 "성공"으로 보인다 — 그러다 나중에
해당 기능(동선 만들기 등)을 처음 쓸 때가 되어서야 에러가 난다. **최초
`.env` 작성 시 전부 채워 넣을 것.**

| 변수명 | 용도 | 비어 있을 때 |
|---|---|---|
| `DATABASE_URL` | RDS 접속 문자열 | 서버 기동 자체가 실패(seed_defaults가 DB에 접속 못 함) |
| `KAKAO_REST_API_KEY` | 카카오모빌리티 길찾기(동선 만들기 이동시간 계산) | "동선 만들기"가 `KAKAO_REST_API_KEY가 .env에 설정되어 있지 않습니다" 에러로 실패. 서버는 정상 기동되고 헬스체크도 통과하므로 눈치채기 어려움 |
| `SECRET_KEY` | JWT 서명 키 | 코드 기본값(`dev-only-change-me`)으로 대체되어 기동은 되지만, 운영 환경에서 이 기본값 그대로 두면 안 됨(보안 위험) |
| `COOKIE_SECURE` | 배포(HTTPS) 환경이면 `true` | 기본 `false` — HTTPS 배포인데 `true`로 안 바꾸면 로그인 쿠키 관련 문제 가능 |

예: `DATABASE_URL=mysql+pymysql://user:pass@<RDS 엔드포인트>:3306/team2`

## 2. GitHub Secrets 등록 (저장소 Settings → Secrets and variables → Actions)

| 이름 | 값 |
|---|---|
| `EC2_HOST` | `54.180.95.40` |
| `EC2_USER` | `ec2-user` |
| `EC2_SSH_KEY` | `D:\team2.pem` 파일 전체 내용 (`-----BEGIN ...`부터 `-----END ...`까지). 가능하면 배포 전용 키를 새로 만들어 등록하는 걸 권장. |

gh CLI가 있다면:
```
gh secret set EC2_HOST --body "54.180.95.40"
gh secret set EC2_USER --body "ec2-user"
gh secret set EC2_SSH_KEY < D:\team2.pem
```

## 3. 보안그룹

EC2 인바운드에 GitHub 러너가 붙을 **22번(SSH)**과, 테스트용으로 **8000번**이
열려 있어야 한다(추후 nginx 붙이면 8000은 닫고 80/443만 유지).

## 4. 동작 확인

```
git commit --allow-empty -m "ci: trigger deploy"
git push
```

Actions 탭에서 CI/Deploy 진행 확인 후 `http://54.180.95.40:8000/docs` 접속.
