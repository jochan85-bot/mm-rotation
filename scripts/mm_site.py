"""정적 페이지 생성 — docs/index.html · longterm.html · guide.html · products.html · products/<티커>.html · data/series/<티커>.json.
MM-PAGE-V3-DESIGN-20261010: 표시층 전면 재구성(렌더러만 교체 — compute·판정 규칙·CSV 형식 무변경).
스타일 = docs/assets/mm.css, 동작 = docs/assets/index.js · chart.js (정적 파일). 외부 라이브러리·외부 스크립트 0, 개인 정보 0."""
import json, html, re, urllib.parse
from pathlib import Path
import numpy as np, pandas as pd
try:
    from mm_lib import DATA, DOCS, ROOT, now_kst, MSCORE_SHA, load_status
    import mm_guide, mm_idxhist
except ImportError:
    from scripts.mm_lib import DATA, DOCS, ROOT, now_kst, MSCORE_SHA, load_status
    from scripts import mm_guide, mm_idxhist
E = html.escape
NAV = (("index.html", "순위"), ("longterm.html", "장기순위"), ("products.html", "종목"), ("guide.html", "Guide"))
NOTICE = mm_guide.NOTICE_TEXT
# 크립토·골드 신호 박스와 같은 방식(색 원 + 흰 글리프)의 아이콘 — 무한매수 ∞ (MM-PAGE-V3.1 §1)
BRAND_SVG = ('<svg class="sig-ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="11" fill="#2f81f7"/>'
             '<text x="12" y="17" font-size="15" font-weight="700" fill="#fff" text-anchor="middle" font-family="Helvetica,Arial">∞</text></svg>')


def pg(title, body, cur, root="", scripts="", pop=False):
    brand = f'<a class="brand" href="{root}index.html" aria-label="무매 M-score">{BRAND_SVG}</a>'
    nav = brand + "".join(f'<a href="{root}{h}" class="{"cur " if h == cur else ""}{"g" if h == "guide.html" else ""}">{n}</a>' for h, n in NAV)
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{E(title)}</title><link rel="stylesheet" href="{root}assets/mm.css"></head><body><nav class="top">{nav}</nav>{body}'
            f'{"<div id=pop hidden></div>" if pop else ""}{scripts}</body></html>')


def nz(x): return x is not None and not (isinstance(x, float) and np.isnan(x))
def f1(x, n=1, sign=False):
    if not nz(x): return "—"
    return f"{x:+,.{n}f}" if sign else f"{x:,.{n}f}"


def short_index(name):
    """공식 지수명 짧게: 상표 표기·'Index'·제공사 접두 일부 제거"""
    n = str(name or "")
    n = re.sub(r"\((R|TM|SM)\)|[®™]|\bSM\b", "", n)
    n = re.sub(r"\s*-\s*gross total return version", " GTR", n); n = re.sub(r"\s*-\s*net total return version", " NTR", n)
    n = re.sub(r"\bMicroSectors\b\s*", "", n); n = re.sub(r"\s+Index\b", "", n); n = re.sub(r"\s{2,}", " ", n).strip()
    return n if len(n) <= 30 else n[:29] + "…"


def jscript(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str).replace("</", "<\\/")


# ---------- 제외 목록 문구 (data/exclusion_text.yaml) ----------
_DEF_TXT = {"excluded": {"조기상환·가속상환": "발행사 조기상환 공지, {date}", "상장폐지·청산": "상장폐지·청산 공지, {date}",
                         "배수 변경": "배수 변경 공지, {date} — 3배 상품인지 재확인할 때까지 제외", "지수 변경": "추종 지수 변경 공지, {date} — 지수 재확인할 때까지 제외"},
            "default_excluded": "발행사 공지로 제외, {date}", "held": [], "default_held": "데이터 확인 중이라 순위에서 일시 제외"}


def load_exclusion_text():
    p = DATA / "exclusion_text.yaml"
    try:
        import yaml
        d = yaml.safe_load(open(p, encoding="utf-8")) or {}
    except Exception:
        d = {}
    out = {k: (dict(v) if isinstance(v, dict) else (list(v) if isinstance(v, list) else v)) for k, v in _DEF_TXT.items()}
    for k, v in d.items():
        if k == "excluded" and isinstance(v, dict): out["excluded"].update(v)
        elif v: out[k] = v
    return out


def exclusion_rows(df, st):
    """(공시 제외 [(티커, 사유 문장, 링크)], 데이터 확인 중 [티커]) — 사유가 다른 두 가지를 섞지 않는다(MM-PAGE-V3.1 §9)"""
    tx = load_exclusion_text(); rows = []
    for r in df[df.table == "제외"].itertuples():
        e = st.get("excluded", {}).get(r.ticker, {})
        fmt = tx["excluded"].get(e.get("type", ""), tx["default_excluded"])
        rows.append((r.ticker, fmt.format(date=e.get("date", "날짜 미상")), e.get("url", "")))
    held = [r.ticker for r in df[df.table == "⚠"].itertuples()]
    return rows, held


# ---------- 메인 ----------
ROW_COLS = ["ticker", "rank", "M", "sig", "p_sig", "rsA", "p_rsA", "f1b", "p_f1b", "c1_ma200", "above200", "close3", "adtv", "listed_days", "badges", "d_rank", "proxy", "beta", "r2", "n_beta"]


def _cell(v):
    if v is None: return None
    if isinstance(v, (float, np.floating)):
        if np.isnan(v): return None
        return round(float(v), 6)
    if isinstance(v, (np.integer,)): return int(v)
    return v


def latest_rows(df):
    el = df[df.table == "순위"].copy().sort_values(["rank", "M"], ascending=[True, False])
    out = []
    for r in el.to_dict("records"):
        o = {k: _cell(r.get(k)) for k in ROW_COLS}
        o["rank"] = int(o["rank"]); o["above200"] = int(o["above200"] or 0)
        d = r.get("d_rank")
        o["d_rank"] = "" if (d is None or (isinstance(d, float) and np.isnan(d)) or d == "") else (str(int(d)) if isinstance(d, (int, float, np.integer, np.floating)) else str(d))
        o["badges"] = o["badges"] or ""
        out.append(o)
    return out


def date_list():
    try:
        idx = json.load(open(DOCS / "data" / "index.json", encoding="utf-8"))
        return idx["first"], idx["last"], [x["d"] for x in idx["dates"]]
    except Exception:
        return "", "", []


RC_NOTE = ("◐ 표시 종목은 상장 1년 미만이라 점수 계산 기간의 일부가 실제 지수 가격이 아니라 현재 구성종목으로 되계산한 값입니다. "
           "되계산 구간은 실제보다 유리하게 나올 수 있어(실측 비교: 12개월 수익률이 실제 운용 지수보다 43~51%p 높음) 상대강도·추세 점수는 할인해서 보셔야 합니다.")
RC_LINES = ("◐ 표시 종목은 상장 1년 미만이라 점수 계산 기간의 일부가 실제 지수 가격이 아니라 현재 구성종목으로 되계산한 값입니다.",
            "되계산 구간은 실제보다 유리하게 나올 수 있어(실측 비교: 12개월 수익률이 실제 운용 지수보다 43~51%p 높음) 상대강도·추세 점수는 할인해서 보셔야 합니다.")


def rc_map():
    """{티커: {of, rel}} — ◐ 대상 방법(구성종목 복제 연장이 있는) 종목. 날짜별 ◐ 여부는 JS 가 선택 날짜의 252거래일 창으로 판정한다."""
    return {t: dict(of=it["official_first"], rel=mm_idxhist.eligible_date(it["official_first"])) for t, it in mm_idxhist.load_history().items() if mm_idxhist.is_blocked_method(it)}


def build_index(df, meta):
    st = load_status()
    try:
        pinfo = {r["ticker"]: r for r in pd.read_csv(DATA / "product_info.csv").to_dict("records")}
    except Exception:
        pinfo = {}
    tk = {}
    for r in df.itertuples():
        tk[r.ticker] = {"iss": str(r.issuer), "typ": str(r.type), "ix": short_index(pinfo.get(r.ticker, {}).get("index_name", "")) or str(getattr(r, "proxy", ""))}
    rows = latest_rows(df)
    first, last, dates = date_list()
    if not dates: first = last = meta["asof"]; dates = [meta["asof"]]
    data = {"asof": meta["asof"], "first": first, "last": last, "dates": dates, "latest": rows, "tk": tk, "rc": rc_map(), "histWin": mm_idxhist.WINDOW, "rcNote": RC_NOTE}
    prov = meta.get("provisional")
    pill = (f'<span class="pill prov" title="{E("SPY 일봉 최신 행(" + prov["raw_last"] + ")이 " + prov["reason"] + " → 직전 확정일로 산출")}">잠정</span>' if prov else "")
    banner = ""                                                   # 예약 실행 확인(2026-10-09 17:18 launchd) 후 배너 제거
    xr, held = exclusion_rows(df, st)
    heldhtml = f'<p class="meta hold">데이터 확인 중: <b>{E(", ".join(held))}</b></p>' if held else ""
    if xr:
        trs = "".join(f'<tr><td><b>{E(t)}</b></td><td>{E(s)}</td><td>{("<a href=" + chr(34) + E(u, quote=True) + chr(34) + " rel=noopener>공지</a>") if u else "—"}</td></tr>' for t, s, u in xr)
        xhtml = f'<div class="wrap"><table class="pl"><thead><tr><th>티커</th><th>사유</th><th>공지</th></tr></thead><tbody>{trs}</tbody></table></div>'
    else:
        xhtml = '<div class="empty">현재 없음</div>'
    body = f"""<h1>{BRAND_SVG}무매 M-score<small>3배 레버리지 ETF·ETN 상대 순위 · 참고용</small></h1>
<div class="meta" id="top1">기준일 <b>{E(meta['asof'])}</b> · 종목 수 <b>{len(rows)}</b> {pill}</div>
{banner}
<div id="calbox"></div>
<div class="tbar"><div class="ttl" id="ttl"></div><div class="acts"><button class="btn" id="todaybtn" hidden>오늘로</button><button class="btn" id="modebtn">상세보기</button></div></div>
<div class="capt">변동성·상대강도·추세 = 유니버스 내 상대 점수, 100=최상위 · 열 머리를 누르면 정렬(다시 누르면 반대 방향)</div>
<div class="capt rcn" id="rcnote" hidden></div>
<div class="wrap"><table class="rk" id="rk"></table></div>
{heldhtml}<h2>제외 목록</h2>{xhtml}
<h2>안내</h2><div class="notice">{E(NOTICE)}</div>
<p class="meta" style="margin-top:8px"><a href="guide.html">산출 방식·데이터 출처는 가이드 페이지</a></p>
<script id="mmdata" type="application/json">{jscript(data)}</script>"""
    return pg("무매 M-score", body, "index.html", scripts='<script src="assets/index.js"></script>', pop=True)



# ---------- 장기순위 (§11) ----------
LT_TABS = ((5, "1주"), (20, "1달"), (60, "3달"), (120, "6달"), (250, "1년"))


def _why_text(r):
    o = []
    for b in str(r.get("badges") or "").split(" · "):
        if b == "신규": o.append(f"신규 {int(r['listed_days'])}일")
        elif b == "저유동": o.append(f"${r['adtv']:,.2f}M")
        elif b.startswith("무거래"): o.append(f"무거래 {b[3:]}일")
        elif b == "표본부족": o.append(f"표본 {int(r['n_beta'])}")
    return " · ".join(o)


def _why_full(r, HI, dates, asof):
    """기존 사유 + 재구성 N% — 메인 표 JS 의 why() 와 같은 순서·같은 문구"""
    a = _why_text(r); b = mm_idxhist.reason(HI.get(r["ticker"]), dates, asof)
    return " · ".join(x for x in (a, b) if x)


def compute_longterm(latest_df, asof):
    """기간 N거래일 M-score 단순평균(결측일 제외, 창의 80% 미만이면 결측)을 당일 모집단 안에서 순위. docs/data/scores 소급분에서 산출."""
    import math
    first, last, dates = date_list()
    if not dates or dates[-1] != asof: return None
    cache = {}

    def day(d):
        if d not in cache:
            try: cache[d] = pd.read_csv(DOCS / "data" / "scores" / f"{d}.csv", skiprows=1, usecols=["ticker", "M", "p_sig", "p_rsA", "p_f1b"]).set_index("ticker")
            except Exception: cache[d] = None
        return cache[d]
    pop = latest_df[latest_df.table == "순위"]
    out = []
    for N, label in LT_TABS:
        win = dates[-N:]; acc = {t: [] for t in pop.ticker}
        for d in win:
            x = day(d)
            if x is None: continue
            for t in acc:
                if t in x.index and pd.notna(x.at[t, "M"]):
                    acc[t].append((float(x.at[t, "M"]), float(x.at[t, "p_sig"]) * 100, float(x.at[t, "p_rsA"]) * 100, float(x.at[t, "p_f1b"]) * 100))
        need = math.ceil(0.8 * N); rows = []
        HI = mm_idxhist.load_history()
        for r in pop.to_dict("records"):
            v = acc[r["ticker"]]
            if len(v) >= need:
                a = np.mean(v, axis=0); rows.append(dict(t=r["ticker"], m=round(float(a[0]), 6), v=int(round(a[1])), rs=int(round(a[2])), tr=int(round(a[3])), n=len(v), w=_why_full(r, HI, dates, asof)))
            else:
                rows.append(dict(t=r["ticker"], m=None, v=None, rs=None, tr=None, n=len(v), w=_why_full(r, HI, dates, asof)))
        ok = sorted([x for x in rows if x["m"] is not None], key=lambda x: (-x["m"], x["t"]))
        rk = {}
        for i, x in enumerate(ok):
            rk[x["t"]] = 1 + sum(1 for y in ok if y["m"] > x["m"])
        for x in rows: x["r"] = rk.get(x["t"])
        rows.sort(key=lambda x: (x["r"] is None, x["r"] or 0, x["t"]))
        out.append(dict(k=N, label=label, days=min(N, len(dates)), rows=rows))
    rc = {}
    for t, it in HI.items():
        ic = mm_idxhist.recon_icon(it, dates, asof)
        if ic and t in set(pop.ticker): rc[t] = dict(p=ic["pct"], of=ic["of"], rel=ic["rel"])
    return dict(asof=asof, n_pop=len(pop), tabs=out, rc=rc, note=RC_NOTE)


def build_longterm(lt, meta):
    prov = meta.get("provisional")
    pill = '<span class="pill prov">잠정</span>' if prov else ""
    if lt is None:
        body = '<h1>장기순위</h1><div class="empty">장기순위 데이터를 만들지 못했습니다.</div>'
        return pg("무매 장기순위", body, "longterm.html")
    body = f"""<h1>장기순위<small>기간별 평균 M-score 순위 · 참고용</small></h1>
<div class="meta">기준일 <b>{E(lt['asof'])}</b> · 종목 수 <b>{lt['n_pop']}</b> {pill}</div>
<div class="rangebar" id="ltabs"></div>
<div class="tbar"><div class="ttl" id="ltl"></div></div>
<div class="capt">평균 변동성·상대강도·추세 = 유니버스 내 상대 점수의 기간 평균, 100=최상위 · 열 머리를 누르면 정렬(다시 누르면 반대 방향)</div>
<div class="capt rcn" id="rcnote" hidden></div>
<div class="wrap"><table class="rk" id="lt"></table></div>
<p class="meta" style="margin-top:8px">기간 평균 M-score = 그 기간 거래일별 M-score(그날 모집단 안의 상대 점수)의 단순평균이며, 이 평균을 오늘 모집단 안에서 다시 순위 매깁니다. 기간 안에 점수가 있는 날이 창의 80% 미만이면 "—"입니다. 평균 변동성·상대강도·추세도 같은 기간의 일별 점수 평균입니다. 자세한 설명은 <a href="guide.html#longterm">Guide</a>.</p>
<script id="ltdata" type="application/json">{jscript(lt)}</script>"""
    return pg("무매 장기순위", body, "longterm.html", scripts='<script src="assets/longterm.js"></script>', pop=True)


# ---------- 가이드 ----------
def build_guide(df, meta, uni):
    return pg("무매 M-score 가이드", mm_guide.guide_body(df, meta, uni, load_status()), "guide.html")


# ---------- 종목 페이지 ----------
def load_page_items():
    p = DATA / "products_page.json"
    try:
        return json.load(open(p, encoding="utf-8")).get("items", {})
    except Exception:
        return {}


def load_holdings():
    try:
        return json.load(open(DATA / "holdings.json", encoding="utf-8")).get("items", {})
    except Exception:
        return {}


_RULES_DEF = {"base": "https://m.stock.naver.com", "overview_path": "/worldstock/stock/{code}/overview", "total_path": "/worldstock/stock/{code}",
              "search_url": "https://m.search.naver.com/search.naver?query={query}+주가"}
_RULES = None


def link_rules():
    """data/link_rules.yaml (실측 규칙) — 없거나 깨지면 기본값. 프로세스당 1회 읽는다."""
    global _RULES
    if _RULES is None:
        r = dict(_RULES_DEF)
        try:
            import yaml
            r.update({k: v for k, v in (yaml.safe_load(open(DATA / "link_rules.yaml", encoding="utf-8")) or {}).items() if k in _RULES_DEF})
        except Exception: pass
        _RULES = r
    return _RULES


GRID_N = 10                                                     # 기본 격자 종 수(나머지는 '전체 보기')


def naver_url(x):
    """구성 종목 1개의 링크 — 네이버 코드(nv)가 검증돼 있으면 해외종목 페이지: lk='o' 이면 기업개요 탭, 그 밖(종합 대체·미기록)은 종합 페이지. 코드가 없으면 네이버 검색 '{티커} 주가'(티커 없으면 회사명)."""
    r = link_rules(); nv, t = x.get("nv"), x.get("t")
    if nv:
        path = r["overview_path"] if x.get("lk") == "o" else r["total_path"]
        return r["base"] + path.format(code=urllib.parse.quote(str(nv), safe="."))
    return urllib.parse.quote(r["search_url"].format(query=urllib.parse.quote_plus(str(t or x.get("n", "")))), safe=":/?=&+%.-_~")


def _hold_item(x):
    """holdings.json 항목을 (티커|None, 회사명, 비중) 로 정규화 — 구 형식(n=티커, t 없음)도 읽는다."""
    t, n = x.get("t"), str(x.get("n", ""))
    if "t" not in x and "nv" not in x: t, n = n, ""             # V3.1 이전 형식: n 이 티커
    return t, n, float(x["w"])


def holdings_cell(x):
    t, n, w = _hold_item(x)
    top = t or n
    sub = f'<span class="nm">{E(n)}</span>' if (t and n and n != t) else ""
    return (f'<a class="hc" href="{E(naver_url(x), quote=True)}" target="_blank" rel="noopener noreferrer">'
            f'<span class="r1"><span class="s">{E(top)}</span><span class="w">{f1(w, 2)}%</span></span>{sub}</a>')


def holdings_html(h):
    """구성 표: 기본 상위 10종 격자(모바일 2열·데스크톱 3열) + 나머지는 '전체 보기'로 펼침. 티커 우선·회사명 작은 글씨·박스 전체가 새 탭 링크(MM-PAGE-V3.2 §3·§4·§6)"""
    if not h or not h.get("items"): return '<div class="empty">구성 종목 데이터를 확인하지 못했습니다.</div>'
    items = sorted(h["items"], key=lambda x: -float(x["w"]))
    head, rest = items[:GRID_N], items[GRID_N:]
    out = f'<div class="hgrid">{"".join(holdings_cell(x) for x in head)}</div>'
    total = int(h.get("total") or len(items))
    if rest:
        out += f'<details class="hmore"><summary>전체 보기 ({len(items)}종' + (f' · 전체 {total}종 중 상위 {len(items)}' if total > len(items) else '') + f')</summary><div class="hgrid">{"".join(holdings_cell(x) for x in rest)}</div></details>'
    sc = h.get("scope", "")
    if not sc and total > len(items): sc = f"전체 {total}종 중 상위 {len(items)}"
    note = f'기준: {E(h.get("basis", ""))} · {E(str(h.get("as_of", "")))}' + (f' · {E(sc)}' if sc else '')
    if h.get("stale"): note += ' · 갱신 실패 — 직전 값 표시'
    src = h.get("source") or {}
    if src.get("name"): note += f' · 출처 {E(str(src["name"]))}'
    return out + f'<div class="chartnote">{note}</div>'


def intro_html(text):
    """소개 문단 — '\n\n' 로 구분된 문단마다 <p>"""
    ps = [x.strip() for x in str(text or "").split("\n\n") if x.strip()] or ["—"]
    return "".join(f"<p>{E(x)}</p>" for x in ps)


def hist_line(t):
    """기본 정보 아래 한 줄 — '지수 공식 이력 시작 YYYY-MM-DD' (공식 지수 레벨 경로 18종만)"""
    h = mm_idxhist.load_history().get(t)
    if not h: return ""
    out = f'<div class="chartnote">지수 공식 이력 시작 {E(h["official_first"])}</div>'
    dates = mm_idxhist.trading_dates(); ic = mm_idxhist.recon_icon(h, dates, dates[-1]) if dates else None
    if ic:
        out += f'<div class="chartnote rcl"><b>{mm_idxhist.RC_GLYPH}</b> {E(RC_LINES[0][2:])}<br>{E(RC_LINES[1])}</div><div class="chartnote">{E(mm_idxhist.recon_tip(ic))}</div>'
    return out


def build_product(t, u, it, hold=None):
    """종목 페이지 1개. u = universe 행(Series/namedtuple), it = products_page.json 항목(없으면 {}), hold = holdings.json 항목."""
    tx = it.get("text", {}); b = it.get("basic", {})
    sub = f'{E(b.get("issuer", u.issuer))} · {E(b.get("type", u.type))} · {E(b.get("leverage", ""))}'
    comp = (f'<table class="info"><tr><th>섹터·테마</th><td>{E(it.get("sector", ""))}</td></tr>'
            f'<tr><th>구성 방식</th><td>{E(tx.get("construction", "—"))}</td></tr></table>{holdings_html(hold)}')
    fee = b.get("fee") or tx.get("fee") or "—"
    basic = (f'<table class="info" style="table-layout:auto"><tr><th style="width:auto">발행사</th><th style="width:auto">구분</th><th style="width:auto">배수</th><th style="width:auto">보수</th><th style="width:auto">상장일</th></tr>'
             f'<tr><td>{E(b.get("issuer", ""))}</td><td>{E(b.get("type", ""))}</td><td>{E(b.get("leverage", ""))}</td><td>{E(fee)}</td><td>{E(str(b.get("inception") or "—"))}</td></tr></table>')
    chart_html = ('<div class="rangebar"><button class="btn" data-range="m3">3개월</button><button class="btn" data-range="m6">6개월</button><button class="btn on" data-range="y1">1년</button><button class="btn" data-range="all">전체</button></div>'
        f'<div class="chartbox"><div id="chart" data-t="{E(t)}"></div>'
        '<div class="legend"><span><i style="background:#f59e0b"></i>M-score (좌축)</span><span><i style="background:#3b82f6"></i>순위 (우축·1위가 위)</span></div>'
        '<div class="chartnote" id="creadout">불러오는 중…</div></div>')
    risks = "".join(f'<li>{E(x)}</li>' for x in tx.get("risk", [])) or '<li>—</li>'
    body = f"""<h1>{E(t)}<small>{sub}</small></h1>
<h2>소개</h2><div class="intro">{intro_html(tx.get("intro"))}</div>
{chart_html}
<h2>구성</h2>{comp}
<h2>기본 정보</h2>{basic}{hist_line(t)}
<h2>구조 리스크</h2><ul class="risk">{risks}</ul>
<div class="stamp">마지막 수정일 {E(str(it.get("modified", "—")))} · <a href="../products.html">상품 목록</a> · <a href="../index.html">순위표</a></div>"""
    return pg(f"{t} — 무매 M-score", body, "products.html", root="../", scripts='<script src="../assets/chart.js"></script>')


def build_products_dir(df, uni, items):
    rows = sorted(((u.ticker, items.get(u.ticker, {}).get("sector", ""), u.type, str(u.issuer)) for u in uni.itertuples()), key=lambda x: x[0])
    trs = "".join(f'<tr><td><a href="products/{E(t)}.html"><b>{E(t)}</b></a></td><td>{E(sec)}</td><td>{E(ty)}</td><td>{E(iss)}</td></tr>' for t, sec, ty, iss in rows)
    body = f"""<h1>종목<small>유니버스 {len(uni)}종 · 티커를 누르면 종목 페이지로 이동 · 열 머리를 누르면 정렬</small></h1>
<div class="wrap" style="margin-top:8px"><table class="dir" id="dir"><thead><tr><th data-c="0">티커</th><th data-c="1">섹터·테마</th><th data-c="2">구분</th><th data-c="3">발행사</th></tr></thead><tbody>{trs}</tbody></table></div>"""
    return pg("무매 종목", body, "products.html", scripts='<script src="assets/sortable.js"></script>')


# ---------- 차트 데이터 ----------
def write_series(uni):
    """docs/data/series/<티커>.json — scores CSV 전 구간에서 티커별 (날짜, M-score, 순위, 그날 모집단 수) 생성"""
    sd = DOCS / "data" / "scores"
    acc = {}
    for f in sorted(sd.glob("*.csv")):
        try:
            head = open(f, encoding="utf-8").readline()
            m = re.search(r"N=(\d+)", head); n = int(m.group(1)) if m else 0
            x = pd.read_csv(f, skiprows=1, usecols=["ticker", "rank", "M"])
        except Exception:
            continue
        for t, rk, mm in zip(x.ticker, x["rank"], x.M):
            if pd.isna(mm) or pd.isna(rk): continue
            a = acc.setdefault(t, {"d": [], "m": [], "r": [], "n": []})
            a["d"].append(f.stem); a["m"].append(round(float(mm), 1)); a["r"].append(int(rk)); a["n"].append(n)
    out = DOCS / "data" / "series"; out.mkdir(parents=True, exist_ok=True)
    want = set(uni.ticker)
    for t, a in acc.items():
        if t in want:
            json.dump(dict(t=t, **a), open(out / f"{t}.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    for f in out.glob("*.json"):                                    # 유니버스에서 빠졌거나 순위 이력이 전혀 없는(이력부족 등) 종목의 묵은 파일 정리
        if f.stem not in want or f.stem not in acc: f.unlink()
    return len(acc)


def write_tickers_json(uni, p0):
    pinfo = {r["ticker"]: r for r in p0.to_dict("records")}; out = {}
    for r in uni.itertuples():
        pi = pinfo.get(r.ticker, {}); ptip = r.proxy_tip if isinstance(r.proxy_tip, str) else ""
        out[r.ticker] = dict(ix=short_index(pi.get("index_name", "")), tip=f"{pi.get('index_name', '')} | 경로: {pi.get('onex_path', '')} | 1x 계열 {r.proxy}" + (f" | {ptip}" if ptip else ""),
                             iss=r.issuer, typ=r.type, proxy=r.proxy)
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    json.dump(out, open(DOCS / "data" / "tickers.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))


def rebuild_products_only():
    """종목 페이지(products/*.html)만 현재 data/products_page.json·holdings.json 으로 다시 그린다 — 점수·docs/data 무접촉(표시층 수정용)."""
    import pandas as pd
    uni = pd.read_csv(DATA / "universe.csv"); items = load_page_items(); hold = load_holdings()
    pd_ = DOCS / "products"; pd_.mkdir(exist_ok=True)
    for u in uni.itertuples():
        (pd_ / f"{u.ticker}.html").write_text(build_product(u.ticker, u, items.get(u.ticker, {}), hold.get(u.ticker)), encoding="utf-8")
    return len(uni)


def rebuild_guide_only():
    """guide.html 만 현재 코드·데이터로 다시 그린다 — '산출 시각'은 기존 페이지 값을 그대로 쓴다(점수·docs/data 무접촉, 표시층 수정용)."""
    import pandas as pd
    df = pd.read_csv(DATA / "scores_latest.csv"); uni = pd.read_csv(DATA / "universe.csv")
    cur = (DOCS / "guide.html").read_text(encoding="utf-8")
    m = re.search(r"산출 (\d{4}-\d\d-\d\d \d\d:\d\d) KST", cur)
    rd = lambda n, k: (json.load(open(DATA / n, encoding="utf-8")).get(k, []) if (DATA / n).exists() else [])
    meta = dict(asof=str(df.date.iloc[0]), generated=m.group(1) if m else "", provisional=None, new_products=rd("new_products.json", "candidates"),
                pipeline=rd("pipeline.json", "items"), dropped=[], manual=False, anomalies=pd.read_csv(DATA / "anomalies.csv"))
    (DOCS / "guide.html").write_text(build_guide(df, meta, uni), encoding="utf-8")


def build_all(latest_df, uni, meta, p0, score_files):
    DOCS.mkdir(exist_ok=True)
    try:
        import mm_page_text
        s = mm_page_text.ensure(use_llm=True)                     # products.yaml 이 바뀐 종목만 재생성(바뀐 게 없으면 호출 0)
        if s["failed"]:
            try:
                from mm_lib import log
                log(f"[page_text] 재생성 실패(기존 문구 유지): {s['failed']}", "alerts")
            except Exception: pass
    except Exception as e:                                       # 문구 생성 실패가 순위 페이지 갱신을 막지 않는다
        try:
            from mm_lib import log
            log(f"[page_text] 종목 문구 갱신 건너뜀: {type(e).__name__}: {str(e)[:150]}", "alerts")
        except Exception: pass
    items = load_page_items(); hold = load_holdings()
    (DOCS / "index.html").write_text(build_index(latest_df, meta), encoding="utf-8")
    (DOCS / "guide.html").write_text(build_guide(latest_df, meta, uni), encoding="utf-8")
    lt = compute_longterm(latest_df, meta["asof"])
    if lt is not None:
        json.dump(lt, open(DOCS / "data" / "longterm.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    (DOCS / "longterm.html").write_text(build_longterm(lt, meta), encoding="utf-8")
    (DOCS / "products.html").write_text(build_products_dir(latest_df, uni, items), encoding="utf-8")
    pd_ = DOCS / "products"; pd_.mkdir(exist_ok=True)
    for u in uni.itertuples():
        (pd_ / f"{u.ticker}.html").write_text(build_product(u.ticker, u, items.get(u.ticker, {}), hold.get(u.ticker)), encoding="utf-8")
    write_series(uni)
    write_tickers_json(uni, p0)
    h = DOCS / "history.html"
    if h.exists(): h.unlink()                                    # 달력은 메인에 통합 — 구 이력 페이지 삭제
    (DOCS / ".nojekyll").write_text("")
