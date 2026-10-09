"""1x 시계열 중 yfinance 에 없는 '공식 지수 레벨' 계열을 만든다 (MM-PROXY-FIX-20261014).

규칙(원칙: 1x = 발행사가 공시한 공식 지수 하나):
  kind=yahoo    Yahoo 지수 티커(^NDX 등)를 그대로 키 이름으로 저장.
  kind=official MicroSectors 가 공시하는 일별 지수 레벨(JSON). 출시일 이전은 data/ext/<key>.csv(동결 연장),
                공식 레벨이 최신 기준일보다 뒤처지면(발행사 갱신 지연) 꼬리 구간만 tail 소스 수익률로 연장하고 info 에 표기한다.
  kind=splice   TPOR: 2022-07-29 까지 동결 구간(^DJT) + 이후 IYT(S&P Transportation Select Industry FMC Capped, exact).
출력은 yfinance history 와 같은 형식의 FETCHED/<key>.csv (Volume=0) — mm_lib.clean_all 이 그대로 처리한다."""
import json, time, urllib.request
import numpy as np, pandas as pd

OFFICIAL_URL="https://microsectors.com/wp-content/themes/uncode-child/json/{sym}_index1.json"

def _specs(DATA): return json.load(open(DATA/"proxy_specs.json",encoding="utf-8"))
def synthetic_keys(DATA): return list(_specs(DATA)["specs"])

def yahoo_aliases(DATA):
    """key -> yfinance 티커 (kind=yahoo). fetch_all 이 '^NDX.csv' 로 저장한 파일을 key 이름으로 복사한다."""
    return {k:sp["ticker"] for k,sp in _specs(DATA)["specs"].items() if sp["kind"]=="yahoo"}

def full_fetch_tickers(DATA):
    """전 이력이 필요한 실 티커: yahoo 지수 + splice 후반부 ETF."""
    s=_specs(DATA)["specs"]; out=set()
    for sp in s.values():
        if sp["kind"]=="yahoo": out.add(sp["ticker"])
        if sp["kind"]=="splice": out.add(sp["then"]["ticker"])
    return sorted(out)

def tail_fetch_tickers(DATA):
    """꼬리 연장용 최근 시세만 필요한 티커 (SG 인증서·복제 구성종목·추적 ETF)."""
    sp=_specs(DATA); out=set()
    for v in sp["specs"].values():
        if v["kind"]!="official": continue
        t=v["tail"]
        if t["kind"] in ("yahoo","sg","etf_tr"): out.add(t["ticker"])
        elif t["kind"]=="replica": out|=set(sp["replicas"][t["name"]]["w"])
    return sorted(out)

def fetch_recent(tickers, dest, period="3mo"):
    import yfinance as yf
    dest.mkdir(parents=True,exist_ok=True); fails=[]
    for t in tickers:
        ok=False
        for k in range(3):
            try:
                h=yf.Ticker(t).history(period=period,auto_adjust=False,actions=False)
                if len(h)>0: h.to_csv(dest/f"{t}.csv"); ok=True; break
            except Exception: time.sleep(2*(k+1))
        if not ok: fails.append(t)
        time.sleep(0.1)
    return fails

def _rd(p, col="Close"):
    h=pd.read_csv(p,index_col=0); idx=pd.to_datetime(h.index.astype(str).str[:10]); s=pd.Series(h[col].values.astype(float),index=idx)
    s=s[~s.index.duplicated(keep="last")].sort_index(); return s[s>0]

def _adj(p): return "Adj Close" if "Adj Close" in pd.read_csv(p,nrows=1).columns else "Close"

def fetch_official(sym, cache_dir):
    """공식 JSON -> Series(index=날짜). 실패 시 캐시. 반환 (series, from_cache)"""
    cache_dir.mkdir(parents=True,exist_ok=True); cp=cache_dir/f"{sym}.json"
    try:
        req=urllib.request.Request(OFFICIAL_URL.format(sym=sym),headers={"User-Agent":"Mozilla/5.0 (mm-rotation research)"})
        raw=urllib.request.urlopen(req,timeout=40).read(); d=json.loads(raw)
        if not isinstance(d,list) or len(d)<30: raise ValueError("JSON 형식/길이 이상")
        cp.write_bytes(raw); cached=False
    except Exception:
        if not cp.exists(): raise
        d=json.load(open(cp)); cached=True
    s=pd.Series([x[1] for x in d],index=pd.to_datetime([pd.Timestamp(x[0],unit="ms").date() for x in d]))
    return s[~s.index.duplicated(keep="last")].sort_index(), cached

def _tail_returns(tail, spec, tail_dir, fetched):
    """꼬리 소스의 일간 수익률 Series"""
    k=tail["kind"]
    if k in ("yahoo","sg"):
        p=(fetched/f"{tail['ticker']}.csv") if k=="yahoo" and (fetched/f"{tail['ticker']}.csv").exists() else tail_dir/f"{tail['ticker']}.csv"
        return _rd(p,"Close").pct_change().dropna()
    if k=="etf_tr":
        return _rd(tail_dir/f"{tail['ticker']}.csv",_adj(tail_dir/f"{tail['ticker']}.csv")).pct_change().dropna()
    if k=="replica":
        w=pd.Series(spec["replicas"][tail["name"]]["w"],dtype=float)
        R=pd.concat({t:_rd(tail_dir/f"{t}.csv",_adj(tail_dir/f"{t}.csv")).pct_change() for t in w.index if (tail_dir/f"{t}.csv").exists()},axis=1)
        ww=w.reindex(R.columns); ww=ww/ww.sum()
        return (R.fillna(0.0)*ww).sum(axis=1).iloc[1:]
    raise ValueError(k)

def write_fetched(key, s, fetched):
    d=pd.DataFrame({"Open":s,"High":s,"Low":s,"Close":s,"Volume":0,"Dividends":0.0,"Stock Splits":0.0})
    d.index=[f"{x:%Y-%m-%d} 12:00:00+00:00" for x in s.index]; d.index.name="Date"; d.to_csv(fetched/f"{key}.csv")

def build_all(DATA, FETCHED, LOCAL, log=print):
    """FETCHED 에 합성 키 파일을 쓰고 info(dict) 반환. 호출 전에 full_fetch_tickers/tail_fetch_tickers 수신이 끝나 있어야 한다."""
    sp=_specs(DATA); tail_dir=FETCHED/"tail"; info={}; cal=_rd(FETCHED/"SPY.csv").index
    for key,v in sp["specs"].items():
        try:
            if v["kind"]=="yahoo":
                src=FETCHED/f"{v['ticker']}.csv"; h=pd.read_csv(src,index_col=0); h.to_csv(FETCHED/f"{key}.csv")
                info[key]=dict(kind="yahoo",ticker=v["ticker"],last=str(pd.to_datetime(h.index.astype(str).str[:10]).max().date())); continue
            if v["kind"]=="splice":
                pre=_rd(DATA.parent/v["pre"]); e=_rd(FETCHED/f"{v['then']['ticker']}.csv")
                cut=pd.Timestamp(v["pre_until"]); scale=pre.loc[cut]/e.loc[cut]
                s=pd.concat([pre[pre.index<=cut],(e[e.index>cut]*scale)]).sort_index(); write_fetched(key,s,FETCHED)
                info[key]=dict(kind="splice",last=str(s.index.max().date())); continue
            # official
            off,cached=fetch_official(v["symbol"],LOCAL/"official"); pre=_rd(DATA.parent/v["pre"])
            s=pd.concat([pre[pre.index<off.index.min()],off]).sort_index()
            last_off=off.index.max(); tail_n=0; tail_src=None
            target=cal.max()
            if last_off<target:
                tr=_tail_returns(v["tail"],sp,tail_dir,FETCHED); tr=tr[(tr.index>last_off)&(tr.index<=target)]
                if len(tr):
                    ext=off.iloc[-1]*(1+tr).cumprod(); s=pd.concat([s,ext]).sort_index(); tail_n=len(tr); tail_src=v["tail"].get("ticker") or (v["tail"].get("name","")+" 구성종목 복제")
            write_fetched(key,s,FETCHED)
            info[key]=dict(kind="official",symbol=v["symbol"],official_last=str(last_off.date()),official_from_cache=bool(cached),tail_days=tail_n,tail_src=tail_src,last=str(s.index.max().date()))
        except Exception as e:
            info[key]=dict(kind=v["kind"],error=f"{type(e).__name__}: {str(e)[:120]}"); log(f"[mm_proxy] {key} 생성 실패: {info[key]['error']}")
    json.dump(info,open(LOCAL/"proxy_build_info.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
    return info
