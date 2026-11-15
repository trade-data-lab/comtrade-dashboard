"""Clustering: 요약 다이제스트와 국가 군집."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import analysis, data, ui

BASIS = {"value": ["value"], "net_wgt": ["net_wgt"], "both": ["value", "net_wgt"]}
BASIS_KO = {"value": "금액", "net_wgt": "순중량", "both": "금액 + 순중량"}


def render():
    f, ref = st.session_state["filters"], st.session_state["ref"]
    st.title("국가 군집")

    cy = data.country_year(f.years)
    cy["name"] = cy.reporter_code.map(ref["name"])
    per_country = cy.groupby(["reporter_code", "name", "flow"])[["value", "net_wgt"]].sum().reset_index()

    # ---- 상단 고정 다이제스트
    with ui.sticky_box():
        chips = []
        for flow in ("X", "M"):
            p = per_country[per_country.flow == flow]
            chips += [
                (f"{ui.FLOW_KO[flow]} 금액 합계", ui.short(p.value.sum(), " $"), f.label),
                (f"{ui.FLOW_KO[flow]} 순중량 합계", ui.short(p.net_wgt.sum(), " kg"), f"{len(p)}개 보고국"),
                (f"국가 평균 ({ui.FLOW_KO[flow]} 금액)", ui.short(p.value.mean(), " $"), f"중위 {ui.short(p.value.median(), ' $')}"),
                (f"국가 평균 ({ui.FLOW_KO[flow]} 순중량)", ui.short(p.net_wgt.mean(), " kg"), f"중위 {ui.short(p.net_wgt.median(), ' kg')}"),
            ]
        ui.kpis(chips)

    yearly = (cy.groupby(["year", "flow"]).agg(금액_합계=("value", "sum"), 순중량_합계=("net_wgt", "sum"),
                                             금액_국가평균=("value", "mean"), 금액_국가중위=("value", "median"),
                                             순중량_국가평균=("net_wgt", "mean"), 순중량_국가중위=("net_wgt", "median"),
                                             보고국=("reporter_code", "nunique")).reset_index())
    yearly["flow"] = yearly.flow.map(ui.FLOW_KO)
    with st.expander("연도별 상세 (합계·국가 평균·국가 중위)"):
        ui.table(yearly.rename(columns={"year": "연도", "flow": "흐름"}).sort_values(["연도", "흐름"], ascending=[False, True]))
    ui.register("연도별 요약", yearly)

    # ---- 군집 설정
    c1, c2, c3 = st.columns([1, 2, 2])
    flow = c1.radio("흐름", ["X", "M"], format_func=lambda v: ui.FLOW_KO[v], horizontal=True, key="cl_flow")
    basis = c2.radio("군집 기준", list(BASIS), format_func=lambda b: BASIS_KO[b], horizontal=True, key="cl_basis")
    k = c3.slider("군집 수", 2, 6, 4, key="cl_k")
    cols = BASIS[basis]
    primary = cols[0]
    d = analysis.cluster_countries(per_country[per_country.flow == flow], cols, k)
    d["cluster_name"] = "군 " + d.cluster.astype(str)
    ui.note(f"{f.label} 동안 각 국가의 {ui.FLOW_KO[flow]} {BASIS_KO[basis]}을 로그 척도로 표준화해 k-평균으로 {k}개 군으로 나눴습니다. "
            "군 1이 가장 큰 국가들입니다. 0이거나 값이 없는 국가는 제외했습니다.")

    # ---- 산점도
    fig = go.Figure()
    label_top = set(d.nlargest(10, "value").reporter_code)
    for cl in sorted(d.cluster.unique()):
        s = d[d.cluster == cl]
        fig.add_trace(go.Scatter(
            x=s.value, y=s.net_wgt, mode="markers+text", name=f"군 {cl} ({len(s)}개국)",
            marker=dict(size=9, color=ui.PALETTE[cl - 1], line=dict(width=1.5, color="#fcfcfb")),
            text=[n if c in label_top else "" for n, c in zip(s.name, s.reporter_code)], textposition="top center",
            textfont=dict(size=11, color=ui.INK2),
            customdata=np.stack([s.name, ui.short_series(s.value, " $"), ui.short_series(s.net_wgt, " kg")], axis=1),
            hovertemplate="<b>%{customdata[0]}</b><br>금액 %{customdata[1]}<br>순중량 %{customdata[2]}<extra>군 " + str(cl) + "</extra>",
        ))
    fig.update_layout(title=f"국가별 {ui.FLOW_KO[flow]} 금액 × 순중량 (로그 축)", xaxis=dict(type="log", title="금액 (USD)", showgrid=True),
                      yaxis=dict(type="log", title="순중량 (kg)"), legend=dict(orientation="h"))
    ui.plot(fig, height=480)

    # ---- 군 요약: 구분 기준, 평균·중위
    summary = d.groupby("cluster").agg(
        국가수=("reporter_code", "size"), 금액_평균=("value", "mean"), 금액_중위=("value", "median"),
        금액_최소=("value", "min"), 금액_최대=("value", "max"), 순중량_평균=("net_wgt", "mean"),
        순중량_중위=("net_wgt", "median"), 순중량_최소=("net_wgt", "min"), 순중량_최대=("net_wgt", "max"),
    ).reset_index().rename(columns={"cluster": "군"})
    if basis != "both":
        unit = " $" if primary == "value" else " kg"
        bounds = analysis.thresholds(d, primary)
        st.markdown("**구분 기준** · " + " · ".join(
            f"군 {hi}/{lo} 경계 ≈ {ui.short(b, unit)}" for hi, lo, b in bounds))
    else:
        st.markdown("**구분 기준** · 두 지표를 함께 쓰므로 단일 경계값 대신 아래 표의 군별 범위를 참고하세요.")
    ui.table(summary)
    ui.register("군 요약", summary)

    # ---- 군별 국가 목록과 주요 품목
    st.subheader("군별 국가와 주요 품목")
    groups = dict(zip(d.reporter_code, d.cluster))
    items_x = data.hs4_by_group(f.years, "X", groups)
    items_m = data.hs4_by_group(f.years, "M", groups)
    members_all = d.assign(share=lambda t: t[primary] / t[primary].sum() * 100)
    ui.register("군별 국가", members_all[["cluster", "name", "value", "net_wgt"]].rename(
        columns={"cluster": "군", "name": "국가", "value": "금액 (USD)", "net_wgt": "순중량 (kg)"}))
    for cl in sorted(d.cluster.unique()):
        members = members_all[members_all.cluster == cl].sort_values(primary, ascending=False)
        with st.expander(f"군 {cl} · {len(members)}개국 · 금액 평균 {ui.short(members.value.mean(), ' $')} · 중위 {ui.short(members.value.median(), ' $')}",
                         expanded=(cl == 1)):
            c1, c2, c3 = st.columns([2, 2, 2])
            with c1:
                st.markdown("**국가**")
                ui.table(members[["name", "value", "net_wgt"]].rename(
                    columns={"name": "국가", "value": "금액 (USD)", "net_wgt": "순중량 (kg)"}), height=380)
            for col, items, flow_i in ((c2, items_x, "X"), (c3, items_m, "M")):
                top = items[items.grp == cl].sort_values(f.metric, ascending=False).head(10).copy()
                top["label"] = top.hs4.map(ref["hs_label"]).fillna(top.hs4).str.slice(0, 40)
                top["hover"] = [ui.short(v, " " + ui.unit_label(f.metric)) for v in top[f.metric]]
                with col:
                    ui.plot(ui.hbar(top, f.metric, "label", hover="hover", color=ui.FLOW_COLOR[flow_i],
                                    title=f"군 {cl} {ui.FLOW_KO[flow_i]} 상위 10 품목"), height=380)
                ui.register(f"군{cl} {ui.FLOW_KO[flow_i]}품목", top[["hs4", "label", "value", "net_wgt"]])
