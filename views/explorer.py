"""Explorer: 보고국·상대국·HS 품목을 직접 골라 보는 상세 조회 (HS 2·4·6단위, 금액·순중량·수량)."""

import plotly.graph_objects as go
import streamlit as st

from core import data, ui

METRICS = {"value": "금액 (USD)", "net_wgt": "순중량 (kg)", "qty": "수량"}
VIEWS = ["연도별 추이", "품목별 순위", "상대국별 순위"]


@st.cache_data(ttl=86400, show_spinner="HS 집계 파일을 읽는 중... (처음 고른 단위·연도는 내려받느라 오래 걸릴 수 있습니다)")
def query(level, years, reporter, flow, partners, hs_codes, by):
    """보고국 하나의 행만 읽어 by(연도·품목·상대국)별로 합친다. 파일이 보고국 순으로 정렬돼 있어 빠르다."""
    files = data.download_many(f"hs{level}/year={y}.parquet" for y in years)
    where = ["reporter_code = ?", "flow = ?"]
    params = [reporter, flow]
    if partners:
        where.append(f"partner_code IN ({', '.join('?' for _ in partners)})")
        params += partners
    if hs_codes:
        where.append("(" + " OR ".join("starts_with(hs, ?)" for _ in hs_codes) + ")")
        params += hs_codes
    one_unit = "min(qty_unit) = max(qty_unit) AND count(qty_unit) = count(*)"
    return data.query(f"""
        SELECT {by}, sum(value) AS value, sum(net_wgt) AS net_wgt,
               CASE WHEN {one_unit} THEN sum(qty) END AS qty,
               CASE WHEN {one_unit} THEN min(qty_unit) END AS qty_unit
        FROM read_parquet({files!r}) WHERE {' AND '.join(where)} GROUP BY {by}
    """, params)


def render():
    f, ref = st.session_state["filters"], st.session_state["ref"]
    st.title("상세 조회")
    ui.note("보고국·상대국·품목을 직접 골라 봅니다. 보고국 World는 모든 보고국의 합, 상대국 World는 대세계 합계입니다. "
            "HS 6단위는 연도당 약 250MB를 처음 한 번 내려받습니다.")

    countries = ref["countries"]
    reporters = countries[~countries.is_group & countries.code.isin(
        set(data.country_year(f.years).reporter_code))].sort_values("name")
    rep_codes = [data.WORLD] + reporters.code.tolist()
    rep_names = dict(zip(reporters.code, reporters.name)) | {data.WORLD: "World (보고국 전체 합계)"}
    par_codes = [data.WORLD] + countries[countries.code != data.WORLD].sort_values("name").code.tolist()
    par_names = dict(zip(countries.code, countries.name)) | {data.WORLD: "World (대세계)"}

    c1, c2, c3 = st.columns([1, 2, 3])
    flow = c1.radio("흐름", ["X", "M"], format_func=lambda v: ui.FLOW_KO[v], horizontal=True, key="ex_flow")
    reporter = c2.selectbox(f"보고국 ({ui.FLOW_KO[flow]}국)", rep_codes, index=rep_codes.index(410) if 410 in rep_codes else 0,
                            format_func=lambda c: f"{rep_names[c]} ({c})", key="ex_rep")
    partner_sel = c3.multiselect("상대국", par_codes, default=[data.WORLD], format_func=lambda c: f"{par_names[c]} ({c})",
                                 help="비우면 모든 상대국. World(대세계)와 개별 국가를 함께 고르면 이중 계산이 됩니다.", key="ex_par")
    c1, c2 = st.columns([1, 4])
    level = c1.radio("HS 단위", [2, 4, 6], index=0, horizontal=True, format_func=lambda v: f"{v}단위", key="ex_level")
    hs = ref["hs"]
    level_hs = hs[hs.level == level]
    labels = dict(zip(level_hs.code, level_hs.label))
    hs_sel = c2.multiselect(f"품목 (HS {level}단위, 비우면 전체)", list(labels), format_func=lambda c: labels[c], key="ex_hs")
    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
    metric = c1.radio("지표", list(METRICS), format_func=lambda m: METRICS[m], horizontal=True, key="ex_metric")
    view = c2.radio("보기", VIEWS, horizontal=True, key="ex_view")
    top_n = c3.slider("상위 개수", 5, 100, 20, step=5, key="ex_n") if view != "연도별 추이" else None
    descending = c4.toggle("내림차순", value=True, key="ex_desc")

    if data.WORLD in partner_sel and len(partner_sel) > 1 and view != "상대국별 순위":
        st.warning("World(대세계)와 개별 상대국을 함께 고르면 합계가 이중 계산됩니다.")
    partner_filter = [p for p in partner_sel if p != data.WORLD] if view == "상대국별 순위" else partner_sel
    by = {"연도별 추이": "year", "품목별 순위": "hs", "상대국별 순위": "partner_code"}[view]
    df = query(level, tuple(f.years), reporter, flow, tuple(partner_filter), tuple(hs_sel), by)
    if view == "상대국별 순위" and not partner_filter:
        df = df[df.partner_code != data.WORLD]
    if df.empty:
        st.info("조건에 맞는 데이터가 없습니다.")
        return

    unit = {"value": "USD", "net_wgt": "kg"}.get(metric)
    if metric == "qty":
        known = df.qty_unit.dropna().unique()
        unit = ref["unit"].get(int(known[0]), "") if len(known) == 1 else None
        if df.qty.isna().any():
            st.info("수량은 단위가 서로 다른 품목을 더할 수 없어, 단위가 섞인 행은 비워 두었습니다. 여러 품목을 묶을 때는 순중량을 쓰세요.")
    if by == "hs":
        df["name"] = df.hs.map(labels).fillna(df.hs)
    elif by == "partner_code":
        df["name"] = df.partner_code.map(par_names)

    total = df[metric].sum()
    if view == "연도별 추이":
        df = df.sort_values("year")
    else:
        df = df.sort_values(metric, ascending=not descending, na_position="last").head(top_n)
        df["share"] = (df[metric] / total * 100).round(2)

    ui.kpis([(f"합계 ({unit or '단위 혼합'})", ui.short(total), f.label),
             ("보고국", rep_names[reporter], ui.FLOW_KO[flow]),
             ("상대국", "전체" if not partner_sel else ", ".join(par_names[p] for p in partner_sel[:3]) + ("…" if len(partner_sel) > 3 else ""), None)])

    if view == "연도별 추이":
        ui.chart_title(f"{rep_names[reporter]} {ui.FLOW_KO[flow]} 추이", unit or "")
        fig = go.Figure(go.Scatter(x=df.year, y=df[metric], mode="lines+markers", line=dict(color=ui.FLOW_COLOR[flow], width=2),
                                   marker=dict(size=7), customdata=ui.short_series(df[metric]),
                                   hovertemplate="%{x}년 %{customdata}<extra></extra>"))
        fig.update_layout(yaxis=dict(tickformat="~s", rangemode="tozero"), showlegend=False, margin=dict(b=8),
                          xaxis=dict(dtick=1 if len(df) <= 12 else 2))
        ui.plot(fig, height=380)
        show = df[["year", "value", "net_wgt", "qty"]].rename(columns={"year": "연도", "value": "금액 (USD)", "net_wgt": "순중량 (kg)", "qty": "수량"})
    else:
        df["hover"] = [f"{ui.short(v, ' ' + unit if unit else '')} · 비중 {s:.1f}%" for v, s in zip(df[metric], df.share)]
        ui.plot(ui.hbar(df, metric, "name", hover="hover", color=ui.FLOW_COLOR[flow], title=f"{view} ({METRICS[metric]})", label_width=44))
        key = "hs" if by == "hs" else "partner_code"
        show = df[[key, "name", "value", "net_wgt", "qty", "share"]].rename(
            columns={key: "코드", "name": "이름", "value": "금액 (USD)", "net_wgt": "순중량 (kg)", "qty": "수량", "share": "비중 (%)"})
    ui.table(show, formats={"비중 (%)": "%.2f"})
    ui.register("상세 조회", show)
