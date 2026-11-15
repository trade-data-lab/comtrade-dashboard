"""UN Comtrade HS 6단위 양자 무역 대시보드 (Hugging Face 집계본을 DuckDB로 원격 조회)."""

import os

import altair as alt
import duckdb
import pandas as pd
import streamlit as st
from huggingface_hub import hf_hub_download

AGG_REPO = "trade-data-lab/comtrade-hs6-agg"
AGG = f"hf://datasets/{AGG_REPO}"
WORLD = 0
FLOWS = {"수출": "X", "수입": "M"}
METRICS = {"금액 (USD)": "value", "순중량 (kg)": "net_wgt", "수량": "qty"}
VIEWS = ["연도별 추이", "품목별 순위", "상대국별 순위"]

st.set_page_config(page_title="Comtrade 무역 대시보드", layout="wide")


@st.cache_resource
def connect():
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{os.environ.get('DASHBOARD_DUCKDB_MEMORY', '1GB')}'")
    token = os.environ.get("HF_TOKEN")
    if token:
        con.execute("CREATE SECRET hf (TYPE huggingface, TOKEN ?)", [token])
    else:
        con.execute("CREATE SECRET hf (TYPE huggingface, PROVIDER credential_chain)")
    return con


@st.cache_data(ttl=86400, show_spinner="코드표 불러오는 중...")
def reference():
    con = connect()
    reporters = con.sql(f"SELECT code, name FROM read_csv('{AGG}/reference/reporters.csv') WHERE NOT is_group").df()
    partners = con.sql(f"SELECT code, name FROM read_csv('{AGG}/reference/partners.csv')").df()
    hs = con.sql(f"SELECT code, label, level FROM read_csv('{AGG}/reference/hs.csv', types={{'code': 'VARCHAR'}})").df()
    units = con.sql(f"SELECT qtyCode AS code, qtyAbbr AS unit FROM read_csv('{AGG}/reference/quantity_units.csv')").df()
    coverage = con.sql(f"SELECT * FROM '{AGG}/coverage/*.parquet' ORDER BY year, flow").df()
    return reporters, partners, hs, units, coverage


def local_files(level, years):
    """연도 파일을 처음 한 번만 통째로 받아 디스크에 두고 이후에는 로컬에서 읽는다.

    원격으로 조금씩 읽으면 요청이 많아 느리다. 파일이 갱신되면 hf_hub_download가 새로 받는다.
    """
    paths = []
    for y in years:
        path = hf_hub_download(AGG_REPO, f"hs{level}/year={y}.parquet", repo_type="dataset",
                               cache_dir=os.environ.get("DASHBOARD_CACHE_DIR"))
        paths.append(path.replace("\\", "/"))
    return paths


@st.cache_data(ttl=86400, show_spinner="데이터를 읽는 중... (처음 고른 연도·단위는 내려받느라 오래 걸릴 수 있습니다)")
def query(level, years, reporter, flow, partners, hs_codes, by):
    """보고국 하나의 행만 읽어 by(연도·품목·상대국)별로 합친다."""
    files = local_files(level, years)
    where = ["reporter_code = ?", "flow = ?"]
    params = [reporter, flow]
    if partners:
        where.append(f"partner_code IN ({', '.join('?' for _ in partners)})")
        params += partners
    if hs_codes:
        where.append("(" + " OR ".join("starts_with(hs, ?)" for _ in hs_codes) + ")")
        params += hs_codes
    # qty는 단위가 하나로 같고 모든 행에 단위가 있을 때만 더한다.
    one_unit = "min(qty_unit) = max(qty_unit) AND count(qty_unit) = count(*)"
    sql = f"""
        SELECT {by},
               sum(value) AS value,
               sum(net_wgt) AS net_wgt,
               CASE WHEN {one_unit} THEN sum(qty) END AS qty,
               CASE WHEN {one_unit} THEN min(qty_unit) END AS qty_unit
        FROM read_parquet({files!r})
        WHERE {' AND '.join(where)}
        GROUP BY {by}
    """
    return connect().execute(sql, params).df()


def country_options(df, world_label):
    names = dict(zip(df.code, df.name))
    names[WORLD] = world_label
    order = [WORLD] + sorted((c for c in names if c != WORLD), key=lambda c: names[c])
    return order, names


reporters, partners, hs, units, coverage = reference()
unit_names = dict(zip(units.code, units.unit))
years_available = sorted(coverage.year.unique())

with st.sidebar:
    st.header("조건")
    flow_label = st.radio("흐름", list(FLOWS), horizontal=True)
    flow = FLOWS[flow_label]

    rep_codes, rep_names = country_options(reporters, "World (보고국 전체 합계)")
    default_rep = rep_codes.index(410) if 410 in rep_codes else 0
    reporter = st.selectbox(
        f"보고국 ({flow_label}국)", rep_codes, index=default_rep,
        format_func=lambda c: f"{rep_names[c]} ({c})",
    )

    par_codes, par_names = country_options(partners, "World (대세계)")
    partner_sel = st.multiselect(
        "상대국", par_codes, default=[WORLD], format_func=lambda c: f"{par_names[c]} ({c})",
        help="비우면 모든 상대국. World(대세계)와 개별 국가를 함께 고르면 이중 계산이 됩니다.",
    )

    whole = st.toggle("전기간", value=False, help=f"{years_available[0]}~{years_available[-1]}년 전체")
    if whole:
        years = years_available
    else:
        lo, hi = st.select_slider("기간", options=years_available,
                                  value=(max(years_available[0], years_available[-1] - 9), years_available[-1]))
        years = [y for y in years_available if lo <= y <= hi]

    level = st.radio("HS 단위", [2, 4, 6], index=[2, 4, 6].index(int(os.environ.get("DASHBOARD_DEFAULT_LEVEL", 4))), horizontal=True, format_func=lambda v: f"{v}단위")
    level_hs = hs[hs.level == level]
    labels = dict(zip(level_hs.code, level_hs.label))
    hs_sel = st.multiselect(f"품목 (HS {level}단위)", list(labels), format_func=lambda c: labels[c],
                            help="비우면 전체 품목. 여러 개를 고를 수 있습니다.")

    metric_label = st.radio("지표", list(METRICS), horizontal=False)
    metric = METRICS[metric_label]

    view = st.radio("보기", VIEWS)
    if view != "연도별 추이":
        top_n = st.slider("상위 개수", 5, 100, 20, step=5)
    descending = st.toggle("내림차순 정렬", value=True)

st.title("UN Comtrade 양자 무역 대시보드")
period = f"{years[0]}~{years[-1]}년" + (" (전기간)" if whole else "")
st.caption(f"{rep_names[reporter]}의 {flow_label} · {period} · HS {level}단위 · {metric_label}")

if not years:
    st.warning("기간을 선택해 주세요.")
    st.stop()

if WORLD in partner_sel and len(partner_sel) > 1 and view != "상대국별 순위":
    st.warning("World(대세계)와 개별 상대국을 함께 고르면 합계가 이중 계산됩니다.")

# 상대국별 순위는 개별 국가끼리 비교하므로 World(대세계) 행을 뺀다.
partner_filter = [p for p in partner_sel if p != WORLD] if view == "상대국별 순위" else partner_sel
by = {"연도별 추이": "year", "품목별 순위": "hs", "상대국별 순위": "partner_code"}[view]
df = query(level, tuple(years), reporter, flow, tuple(partner_filter), tuple(hs_sel), by)
if view == "상대국별 순위" and not partner_filter:
    df = df[df.partner_code != WORLD]

if df.empty:
    st.info("조건에 맞는 데이터가 없습니다.")
    st.stop()

unit = "USD" if metric == "value" else "kg" if metric == "net_wgt" else None
if metric == "qty":
    known = df.qty_unit.dropna().unique()
    unit = unit_names.get(int(known[0]), "") if len(known) == 1 else None
    if df.qty.isna().any():
        st.info("수량은 단위가 서로 다른 품목을 더할 수 없어, 단위가 섞인 행은 비워 두었습니다. 여러 품목을 묶을 때는 순중량을 쓰세요.")

if by == "hs":
    df["이름"] = df.hs.map(labels)
elif by == "partner_code":
    df["이름"] = df.partner_code.map(par_names)

total = df[metric].sum()
if view == "연도별 추이":
    df = df.sort_values("year", ascending=not descending)
else:
    df = df.sort_values(metric, ascending=not descending, na_position="last").head(top_n)
    df["비중 (%)"] = (df[metric] / total * 100).round(2)

def short(n):
    for size, suffix in ((1e12, "조"), (1e8, "억"), (1e4, "만")):
        if abs(n) >= size:
            return f"{n / size:,.1f}{suffix}"
    return f"{n:,.0f}"


c1, c2, c3 = st.columns(3)
c1.metric(f"합계 ({unit or '단위 혼합'})", short(total), help=f"{total:,.0f}")
c2.metric("기간", period)
if reporter == WORLD:
    cov = coverage[(coverage.flow == flow) & coverage.year.isin(years)]
    c3.metric("보고국 수", f"{cov.reporters.min()}~{cov.reporters.max()}개국",
              help="World는 그해 보고한 국가만의 합입니다. 최근 연도는 보고국이 적습니다.")

if view == "연도별 추이":
    chart = alt.Chart(df).mark_line(point=True).encode(
        x=alt.X("year:O", title="연도"), y=alt.Y(f"{metric}:Q", title=metric_label, axis=alt.Axis(format="~s")),
        tooltip=["year", alt.Tooltip(f"{metric}:Q", format=",.0f")],
    )
else:
    chart = alt.Chart(df).mark_bar().encode(
        y=alt.Y("이름:N", sort=None, title=None), x=alt.X(f"{metric}:Q", title=metric_label, axis=alt.Axis(format="~s")),
        tooltip=["이름", alt.Tooltip(f"{metric}:Q", format=",.0f"), "비중 (%)"],
    )
st.altair_chart(chart, width="stretch")

show = df.drop(columns=["qty_unit"]).rename(columns={
    "year": "연도", "hs": "HS 코드", "partner_code": "상대국 코드",
    "value": "금액 (USD)", "net_wgt": "순중량 (kg)", "qty": f"수량 ({unit})" if metric == "qty" and unit else "수량",
})
st.dataframe(show, hide_index=True, width="stretch")
st.download_button("CSV 내려받기", show.to_csv(index=False).encode("utf-8-sig"), "comtrade.csv", "text/csv")

st.caption(
    "출처: UN Comtrade (각 보고국이 보고한 값). HS 개정판이 연도·국가마다 달라 장기 비교 시 품목 범위가 다를 수 있습니다. "
    "World 보고국은 보고한 국가만의 합계입니다."
)
