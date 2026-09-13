"""build_open_matrix() 빈 문자열(open_tm/close_tm="") 크래시 회귀 테스트 — 2026-09-13.

배경: 로컬 "동선 만들기"(/recommend)에서 500 에러 발생 —
    File "al02_pipeline.py", line 78, in _to_min
        h, m = map(int, str(t).split(":"))
    ValueError: invalid literal for int() with base 10: ''

실DB 전수 확인(event_op_hour, 총 9100행) 결과:
  - open_tm/close_tm이 빈 문자열("")인 행 17건, 전부 open_tm=close_tm="" 쌍으로만
    나타남(한쪽만 빈 경우 0건).
  - 전부 "여행지"(ctg_type_no=3) 카테고리 — 국립중앙박물관/국립현대미술관 과천/
    국립아시아문화전당 등 국공립 박물관·전시관류.
  - 같은 event_no의 다른 요일엔 전부 정상 "HH:MM" 값이 있고 딱 하루(주로 월요일)만
    비어 있음 — 실제로 월요일 휴관인 곳들과 일치. 데이터 오류가 아니라 NULL 대신
    ""로 인코딩된 "그 요일 휴관" 정상 값으로 판단, al02_pipeline.build_open_matrix()가
    빈 문자열을 None으로 정규화해 기존 "둘 다 None=휴무" 분기로 처리하도록 수정.

실DB의 event_no=2965(국립아시아문화전당, 월요일 open_tm=close_tm="")로 실제
크래시 조건을 그대로 재현한다. 실행: python test_open_matrix_empty_tm.py
"""
import sys
sys.path.insert(0, r"C:\workspaces\final")

from dotenv import load_dotenv
load_dotenv(r"C:\workspaces\final\.env")

from database import SessionLocal
import al02_candidates
from al02_pipeline import build_open_matrix

PASS_COUNT = 0
FAIL_COUNT = 0


def check(name, condition):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  [PASS] {name}")
    else:
        FAIL_COUNT += 1
        print(f"  [FAIL] {name}")


print("=== T22: event_op_hour.open_tm/close_tm=''(빈 문자열)여도 크래시 없이 휴무로 판정 ===")

db = SessionLocal()
try:
    # 실측으로 확인된 실제 빈 문자열 사례(국립아시아문화전당, 월요일).
    event_no = 2965
    events = [{"event_no": event_no, "event_nm": "국립아시아문화전당(회귀테스트)"}]
    business_hours = al02_candidates.fetch_business_hours(db, [event_no])
    day_hours = business_hours.get(event_no, {})

    check(f"실DB에 이 이벤트의 월요일 데이터가 빈 문자열로 남아있음(재현 전제 확인)",
          day_hours.get("월") == ("", ""))

    try:
        # 2026-11-02 = 월요일(빈 문자열 재현 날짜), 2026-11-03 = 화요일(정상 데이터 날짜).
        om = build_open_matrix(events, ["2026-11-02", "2026-11-03"], business_hours, 540, 1260)
        check("build_open_matrix()가 예외 없이 완료됨(수정 전엔 ValueError로 크래시)", True)
        check("빈 문자열이었던 월요일은 휴무(False)로 정규화됨", om[0, 0] == False)
        check("정상 데이터인 화요일은 영업(True)으로 판정됨", om[0, 1] == True)
    except ValueError as e:
        check(f"build_open_matrix()가 예외 없이 완료됨 — 실패: {e}", False)
finally:
    db.close()

print(f"\n=== 결과: {PASS_COUNT} PASS / {FAIL_COUNT} FAIL ===")
sys.exit(1 if FAIL_COUNT else 0)
