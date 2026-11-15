"""Overall: 세계 무역 전반 통계."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import data, ui


def render():
    f, ref = st.session_state["filters"], st.session_state["ref"]
    m, unit = f.metric, ui.unit_label(f.metric)
    st.title("세계 무역 개요")
    ui.note(f"{f.label} · {ui.METRIC_KO[m]} 기준 · 각 보고국이 보고한 대세계 합계를 더한 값")

    cy = data.country_year(f.years)
    cy["name"] = cy.reporter_code.map(ref["name"])
    cy["continent"] = cy.reporter_code.map(ref["continent"]).fillna("Unspecified")

    # ---- 연도별 세계 합계와 보고국 수
    yearly = (cy.groupby(["year", "flow"]).agg(total=(m, "sum"), reporters=("reporter_code", "nunique"))
              .reset_index())
    piv = yearly.pivot(index="year", columns="flow", values="total")
    rep = yearly.pivot(index="year", columns="flow", values="reporters")
    latest = f.latest
    prev = latest - 1 if (latest - 1) in piv.index else None

    def yoy(flow):
        if prev is None or pd.isna(piv.loc[prev, flow]) or piv.loc[prev, flow] == 0:
            return None
        return (piv.loc[latest, flow] / piv.loc[prev, flow] - 1) * 100

    period = cy.groupby(["reporter_code", "name", "continent", "flow"])[m].sum().reset_index()
    exp = period[period.flow == "X"].sort_values(m, ascending=False)
    imp = period[period.flow == "M"].sort_values(m, ascending=False)
    top5_share = exp.head(5)[m].sum() / exp[m].sum() * 100 if len(exp) else None

    ui.kpis([
        (f"{latest}년 세계 수출 ({unit})", ui.short(piv.loc[latest, "X"]),
         f"전년 대비 {ui.pct(yoy('X'))}" if prev else "전년 자료 없음", ui.delta_dir(yoy("X"))),
        (f"{latest}년 세계 수입 ({unit})", ui.short(piv.loc[latest, "M"]),
         f"전년 대비 {ui.pct(yoy('M'))}" if prev else "전년 자료 없음", ui.delta_dir(yoy("M"))),
        (f"{latest}년 보고국 수", f"{int(rep.loc[latest, 'X'])}개국", "수출 기준"),
        (f"상위 5개국 수출 비중 ({f.label})", f"{top5_share:.1f}%" if top5_share else "–", "집중도"),
    ])

    c1, c2 = st.columns([3, 2])
    with c1:
        ui.chart_title(f"연도별 세계 {ui.METRIC_KO[m]} 합계", unit)
        fig = go.Figure()
        for flow in ("X", "M"):
            s = piv[flow]
            fig.add_trace(go.Scatter(
                x=s.index, y=s.values, mode="lines+markers", name=ui.FLOW_KO[flow],
                line=dict(color=ui.FLOW_COLOR[flow], width=2), marker=dict(size=7),
                customdata=ui.short_series(s.values), hovertemplate="%{customdata}<extra>" + ui.FLOW_KO[flow] + "</extra>",
            ))
        fig.update_layout(hovermode="x unified", yaxis=dict(tickformat="~s", rangemode="tozero"),
                          xaxis=dict(dtick=1 if len(piv) <= 12 else 2, range=[piv.index.min() - 0.4, piv.index.max() + 0.4]))
        ui.plot(fig, height=360)
    with c2:
        ui.chart_title("연도별 보고국 수", "수출 기준")
        fig = go.Figure(go.Bar(x=rep.index, y=rep["X"], marker=dict(color=ui.PALETTE[0], cornerradius=4),
                               hovertemplate="%{y}개국<extra></extra>"))
        fig.update_layout(bargap=0.35, yaxis=dict(rangemode="tozero"), xaxis=dict(dtick=1 if len(rep) <= 12 else 2),
                          margin=dict(b=8))
        ui.plot(fig, height=360)
    ui.note("최근 연도는 아직 보고하지 않은 국가가 많아 합계가 작게 나옵니다. 보고국 수와 함께 해석하세요.")
    ui.register("연도별 합계", yearly.assign(flow=yearly.flow.map(ui.FLOW_KO)))

    # ---- 상위 수출국·수입국
    st.subheader("상위 국가")
    c1, c2 = st.columns(2)
    for col, d, flow in ((c1, exp, "X"), (c2, imp, "M")):
        top = d.head(15).copy()
        top["share"] = top[m] / d[m].sum() * 100
        top["hover"] = [f"{ui.short(v, ' ' + unit)} · 비중 {s:.1f}%" for v, s in zip(top[m], top.share)]
        with col:
            ui.plot(ui.hbar(top, m, "name", hover="hover", color=ui.FLOW_COLOR[flow],
                            title=f"{ui.FLOW_KO[flow]} 상위 15개국 ({f.label})"))
        ui.register(f"상위 {ui.FLOW_KO[flow]}국", d.rename(columns={m: ui.METRIC_KO[m]})[["name", "continent", ui.METRIC_KO[m]]])

    # ---- 대륙 → 국가 트리맵, 세계 품목 순위
    st.subheader("구성")
    c1, c2 = st.columns([3, 2])
    with c1:
        ui.plot(_treemap(exp, m, unit, f.label), height=460)
    with c2:
        hs2 = data.world_hs(f.years, "X", 2).head(15)
        hs2["label"] = hs2.hs.map(ref["hs_label"]).fillna(hs2.hs).str.slice(0, 42)
        hs2["hover"] = [f"{ui.short(v, ' ' + unit)}" for v in hs2[m]]
        ui.plot(ui.hbar(hs2, m, "label", hover="hover", title=f"세계 수출 상위 HS 2단위 ({f.label})"), height=460)
        ui.register("세계 수출 HS2", hs2[["hs", "label", "value", "net_wgt"]])

    with st.expander("표 보기: 국가별 합계"):
        show = period.pivot_table(index=["name", "continent"], columns="flow", values=m, aggfunc="sum").reset_index()
        show.columns = ["국가", "대륙", "수입", "수출"] if list(show.columns[2:]) == ["M", "X"] else show.columns
        show["대륙"] = show["대륙"].map(ui.CONTINENT_KO)
        ui.table(show.sort_values("수출", ascending=False), height=420)
        ui.register("국가별 합계", show)


def _treemap(exp, m, unit, label):
    d = exp[exp.continent != "Unspecified"].copy()
    d["cont_ko"] = d.continent.map(ui.CONTINENT_KO)
    total = d[m].sum()
    cont = d.groupby(["continent", "cont_ko"])[m].sum().reset_index()
    ids = ["World"] + cont.continent.tolist() + (d.continent + "/" + d.name).tolist()
    labels = ["세계"] + cont.cont_ko.tolist() + d.name.tolist()
    parents = [""] + ["World"] * len(cont) + d.continent.tolist()
    values = [total] + cont[m].tolist() + d[m].tolist()
    colors = ["#ffffff"] + [ui.CONTINENT_COLOR[c] for c in cont.continent] + [ui.CONTINENT_COLOR[c] for c in d.continent]
    hover = [f"{ui.short(v, ' ' + unit)} · {v / total * 100:.1f}%" for v in values]
    fig = go.Figure(go.Treemap(
        ids=ids, labels=labels, parents=parents, values=values, branchvalues="total",
        marker=dict(colors=colors, line=dict(width=2, color="#fcfcfb"), depthfade=True),
        customdata=hover, hovertemplate="<b>%{label}</b><br>%{customdata}<extra></extra>",
        textinfo="label", textfont=dict(color="#ffffff"), pathbar=dict(visible=True), maxdepth=2,
    ))
    fig.update_layout(title=f"대륙별 · 국가별 수출 구성 ({label})", margin=dict(l=4, r=4, t=36, b=4))
    return fig
