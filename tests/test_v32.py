"""MM-PAGE-V3.2 단위 테스트 — 구성 격자(티커 우선·링크·전체 보기·상위 100 표기)·소개 문단. python3 tests/test_v32.py"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT / "scripts"))
import mm_site as S
ok = 0; bad = []
def check(name, cond, detail=""):
    global ok
    if cond: ok += 1; print("PASS", name)
    else: bad.append(name); print("FAIL", name, detail)

# 링크
check("네이버 코드 있으면 해외종목 페이지", S.naver_url({"t": "AMD", "nv": "AMD.O"}) == "https://m.stock.naver.com/worldstock/stock/AMD.O")
check("코드 없으면 검색 대체(티커+주가)", S.naver_url({"t": "BRK.B"}) == "https://m.search.naver.com/search.naver?query=BRK.B+%EC%A3%BC%EA%B0%80")
check("티커 없으면 회사명 검색", "query=Foo+Corp+" in S.naver_url({"t": None, "n": "Foo Corp"}))
# 셀: 티커 우선, 회사명 작은 글씨, 새 탭
c = S.holdings_cell({"t": "AMD", "n": "Advanced Micro Devices", "w": 7.4, "nv": "AMD.O"})
check("티커 우선 + 비중", '<span class="s">AMD</span><span class="w">7.40%</span>' in c, c)
check("회사명 작은 글씨", '<span class="nm">Advanced Micro Devices</span>' in c)
check("새 탭·noopener", 'target="_blank"' in c and "noopener" in c)
c2 = S.holdings_cell({"t": None, "n": "Some ADR", "w": 1.0})
check("티커 모르면 회사명만", '<span class="s">Some ADR</span>' in c2 and 'class="nm"' not in c2, c2)
c3 = S.holdings_cell({"n": "NVDA", "w": 8.36})
check("구 형식(n=티커) 호환", '<span class="s">NVDA</span>' in c3 and 'class="nm"' not in c3, c3)
# 격자: 기본 10 + 전체 보기
items = [{"t": f"T{i}", "n": f"Name {i}", "w": 100 - i, "nv": None} for i in range(100)]
h = S.holdings_html({"basis": "1x ETF SPY 보유", "as_of": "2026-10-08", "total": 503, "scope": "전체 503종 중 상위 100", "items": items})
check("기본 격자 10종", h.split('<details')[0].count('class="hc"') == 10)
check("전체 보기 100종", h.count('class="hc"') == 100)
check("상위 100 표기(요약·주석)", "전체 503종 중 상위 100" in h and h.count("전체 503종 중 상위 100") == 2, h[-300:])
h2 = S.holdings_html({"basis": "지수 구성종목", "as_of": "2026-10-08", "total": 8, "items": items[:8]})
check("10종 이하는 전체 보기 없음", "<details" not in h2)
h3 = S.holdings_html({"basis": "1x ETF SMH 보유", "as_of": "2026-10-01", "stale": True, "total": 3, "items": items[:3]})
check("갱신 실패 표기", "갱신 실패" in h3 and "2026-10-01" in h3)
check("빈 구성은 안내문", "확인하지 못했습니다" in S.holdings_html({}))
# 소개 문단
ip = S.intro_html("첫째 문장.\n\n둘째 문장. 셋째 문장.")
check("소개 문단 분리", ip == "<p>첫째 문장.</p><p>둘째 문장. 셋째 문장.</p>", ip)
check("소개 이스케이프", "&lt;b&gt;" in S.intro_html("<b>x</b>"))
print(f"{ok} PASS, {len(bad)} FAIL"); sys.exit(1 if bad else 0)
