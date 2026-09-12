# GitHub Actions CI/CD 설정 (FANGO_USER)

같은 EC2(`54.180.95.40`)에서 이미 돌고 있는 adminProject(8001)와 같은 구조를 따른다.
이 프로젝트는 포트 **8002**, systemd 서비스명 **fangouser**를 쓴다.

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
nano .env   # DATABASE_URL=mysql+pymysql://user:pass@<RDS 엔드포인트>:3306/team2 등
chmod +x deploy/*.sh
./deploy/server_setup.sh
```

`server_setup.sh`가 하는 일: Python 3.11 설치 → `.venv` 생성 → 의존성 설치 →
`.env` 확인 → DB 연결 스모크 테스트 → systemd 서비스 등록/시작 → 헬스체크.

이후 GitHub Actions의 `deploy.yml`은 이미 `.venv`와 systemd 서비스가 있다고
가정하고 rsync + restart만 한다.

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

EC2 인바운드에 GitHub 러너가 붙을 **22번(SSH)**과, 테스트용으로 **8002번**이
열려 있어야 한다(추후 nginx 붙이면 8002는 닫고 80/443만 유지).

## 4. 동작 확인

```
git commit --allow-empty -m "ci: trigger deploy"
git push
```

Actions 탭에서 CI/Deploy 진행 확인 후 `http://54.180.95.40:8002/docs` 접속.
