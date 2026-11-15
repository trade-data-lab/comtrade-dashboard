"""Continents: 대륙별 추이, 지도, 대륙 간 흐름."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import data, ui

CENTROIDS = {"Asia": (95, 38), "Europe": (15, 52), "North America": (-98, 42), "South America": (-60, -14),
             "Africa": (20, 4), "Oceania": (135, -25)}
MAIN = [c for c in data.CONTINENTS if c != "Unspecified"]


def render():
    f, ref = st.session_state["filters"], st.session_state["ref"]
    m, unit = f.metric, ui.unit_label(f.metric)
    st.title("대륙별 수출입")
    flow = st.segmented_control("흐름", ["X", "M"], format_func=lambda v: ui.FLOW_KO[v], default="X", key="cont_flow") or "X"
    ui.note(f"{f.label} · {ui.METRIC_KO[m]} · 각 보고국의 대세계 {ui.FLOW_KO[flow]}을 대륙별로 더한 값. "
            "보고하지 않은 국가는 빠집니다.")

    cy = data.country_year(f.years)
    cy["continent"] = cy.reporter_code.map(ref["continent"]).fillna("Unspecified")
    d = cy[(cy.flow == flow) & cy.continent.isin(MAIN)]

    # ---- 장기 추이
    trend = d.groupby(["year", "continent"])[m].sum().reset_index()
    fig = go.Figure()
    for c in MAIN:
        s = trend[trend.continent == c]
        if s.empty:
            continue
        fig.add_trace(go.Scatter(
            x=s.year, y=s[m], mode="lines+markers", name=ui.CONTINENT_KO[c],
            line=dict(color=ui.CONTINENT_COLOR[c], width=2), marker=dict(size=6),
            customdata=ui.short_series(s[m]), hovertemplate="%{customdata}<extra>" + ui.CONTINENT_KO[c] + "</extra>",
        ))
        fig.add_annotation(x=s.year.iloc[-1], y=s[m].iloc[-1], text=ui.CONTINENT_KO[c], showarrow=False,
                           xanchor="left", xshift=6, font=dict(color=ui.CONTINENT_COLOR[c], size=11))
    fig.update_layout(title=f"대륙별 {ui.FLOW_KO[flow]} {ui.METRIC_KO[m]} 추이", hovermode="x unified",
                      yaxis=dict(tickformat="~s", rangemode="tozero"), margin=dict(r=70),
                      xaxis=dict(dtick=1 if len(f.years) <= 12 else 2))
    ui.plot(fig, height=400)
    wide = trend.pivot(index="year", columns="continent", values=m).rename(columns=ui.CONTINENT_KO).reset_index()
    ui.register("대륙별 추이", wide)

    # ---- 지도 (대륙별 합계로 색) + 클릭 → 품목 순위
    st.subheader("지도")
    cont_total = d.groupby("continent")[m].sum()
    countries = ref["countries"]
    geo = countries[(countries.continent.isin(MAIN)) & (countries.iso3.str.len() == 3) & ~countries.is_group].copy()
    geo["total"] = geo.continent.map(cont_total).fillna(0)
    geo["hover"] = [f"<b>{n}</b><br>{ui.CONTINENT_KO[c]} {ui.FLOW_KO[flow]} 합계: {ui.short(t, ' ' + unit)}"
                    for n, c, t in zip(geo.name, geo.continent, geo.total)]
    fig = go.Figure(go.Choropleth(
        locations=geo.iso3, z=geo.total, locationmode="ISO-3", customdata=geo.hover,
        colorscale=[[i / (len(ui.SEQUENTIAL) - 1), c] for i, c in enumerate(ui.SEQUENTIAL)],
        marker=dict(line=dict(color="#fcfcfb", width=0.5)), hovertemplate="%{customdata}<extra></extra>",
        colorbar=dict(title=dict(text=unit, side="right"), thickness=10, len=0.6, tickformat="~s", outlinewidth=0),
    ))
    fig.update_geos(projection_type="natural earth", showframe=False, showcoastlines=False,
                    showland=True, landcolor="#efefec", showcountries=False, bgcolor="rgba(0,0,0,0)",
                    lataxis_range=[-58, 84])
    fig.update_layout(title=f"대륙별 {ui.FLOW_KO[flow]} {ui.METRIC_KO[m]} (대륙을 클릭하면 아래에 품목 순위)",
                      margin=dict(l=0, r=0, t=36, b=0), dragmode=False)
    event = ui.plot(fig, key="cont_map", select=True, height=440)
    point = ui.selected_point(event)
    if point is not None and "point_index" in point:
        st.session_state["cont_pick"] = geo.iloc[point["point_index"]].continent

    options = [c for c in MAIN if c in cont_total.index]
    default = st.session_state.get("cont_pick", options[0] if options else None)
    pick = st.selectbox("대륙 (지도 클릭 또는 선택)", options, index=options.index(default) if default in options else 0,
                        format_func=lambda c: ui.CONTINENT_KO[c], key="cont_select")
    items = data.hs4_by_group(f.years, flow, {code: cont for code, cont in ref["continent"].items() if cont == pick})
    items = items.sort_values(m, ascending=False)
    items["label"] = items.hs4.map(ref["hs_label"]).fillna(items.hs4).str.slice(0, 48)
    items["share"] = items[m] / items[m].sum() * 100
    items["hover"] = [f"{ui.short(v, ' ' + unit)} · 비중 {s:.1f}%" for v, s in zip(items[m], items.share)]
    c1, c2 = st.columns([3, 2])
    with c1:
        ui.plot(ui.hbar(items.head(20), m, "label", hover="hover", color=ui.CONTINENT_COLOR[pick],
                        title=f"{ui.CONTINENT_KO[pick]} {ui.FLOW_KO[flow]} 상위 HS 4단위 품목"))
    with c2:
        show = items[["hs4", "label", "value", "net_wgt", "share"]].rename(
            columns={"hs4": "HS4", "label": "품목", "value": "금액 (USD)", "net_wgt": "순중량 (kg)", "share": "비중 (%)"})
        ui.table(show, height=560, formats={"비중 (%)": "%.2f"})
    ui.register(f"{ui.CONTINENT_KO[pick]} 품목 순위", show)

    # ---- 대륙 간 흐름 (화살표 크기 = 교역 규모)
    st.subheader("대륙 간 흐름")
    pr = data.pairs(f.years)
    pr = pr[pr.flow == flow].copy()
    pr["rc"] = pr.reporter_code.map(ref["continent"])
    pr["pc"] = pr.partner_code.map(ref["continent"])
    pr = pr[pr.rc.isin(MAIN) & pr.pc.isin(MAIN)]
    # 상품 이동 방향으로 통일: 수출 보고는 보고국→상대국, 수입 보고는 상대국→보고국
    pr["origin"], pr["dest"] = (pr.rc, pr.pc) if flow == "X" else (pr.pc, pr.rc)
    flows = pr.groupby(["origin", "dest"])[m].sum().reset_index().sort_values(m, ascending=False)
    inter = flows[flows.origin != flows.dest]
    top = inter.head(14)
    ui.note(f"{ui.FLOW_KO[flow]} 보고 기준 상위 {len(top)}개 대륙 간 흐름. 선 굵기와 화살표 크기가 {ui.METRIC_KO[m]}에 비례합니다. "
            "역내(같은 대륙) 교역은 오른쪽 표에 있습니다.")
    c1, c2 = st.columns([3, 2])
    with c1:
        ui.plot(_arrow_map(top, m, unit), height=460)
    with c2:
        mat = flows.pivot(index="origin", columns="dest", values=m).reindex(index=MAIN, columns=MAIN)
        mat.index = [ui.CONTINENT_KO[c] for c in mat.index]
        mat.columns = [ui.CONTINENT_KO[c] for c in mat.columns]
        text = [[ui.short(v) if pd.notna(v) else "" for v in row] for row in mat.values]
        fig = go.Figure(go.Heatmap(
            z=mat.values, x=mat.columns, y=mat.index, text=text, texttemplate="%{text}",
            colorscale=[[i / (len(ui.SEQUENTIAL) - 1), c] for i, c in enumerate(ui.SEQUENTIAL)],
            showscale=False, hovertemplate="%{y} → %{x}<br>%{text}<extra></extra>", xgap=2, ygap=2,
        ))
        fig.update_layout(title="출발 대륙(행) → 도착 대륙(열)", xaxis=dict(side="top"), yaxis=dict(autorange="reversed"),
                          margin=dict(l=8, r=8, t=70, b=8))
        ui.plot(fig, height=460)
    ui.register("대륙 간 흐름", flows.assign(origin=flows.origin.map(ui.CONTINENT_KO), dest=flows.dest.map(ui.CONTINENT_KO)))


def _curve(a, b, n=30, bend=0.18):
    """a→b 사이를 진행 방향의 왼쪽으로 휘는 2차 곡선으로 잇는다 (양방향이 겹치지 않게)."""
    (x0, y0), (x1, y1) = a, b
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    cx, cy = mx - dy * bend, my + dx * bend
    t = np.linspace(0, 1, n)
    xs = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t ** 2 * x1
    ys = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t ** 2 * y1
    return xs, ys


def _arrow_map(top, m, unit):
    fig = go.Figure()
    vmax = top[m].max() if len(top) else 1
    for _, r in top.iterrows():
        xs, ys = _curve(CENTROIDS[r.origin], CENTROIDS[r.dest])
        width = 1.5 + 10 * r[m] / vmax
        label = f"{ui.CONTINENT_KO[r.origin]} → {ui.CONTINENT_KO[r.dest]}<br>{ui.short(r[m], ' ' + unit)}"
        fig.add_trace(go.Scattergeo(
            lon=xs, lat=ys, mode="lines+markers", name=label, showlegend=False,
            line=dict(width=width, color=ui.CONTINENT_COLOR[r.origin]), opacity=0.75,
            marker=dict(symbol="arrow", angleref="previous", color=ui.CONTINENT_COLOR[r.origin],
                        size=[0] * (len(xs) - 1) + [max(9, width * 2.2)]),
            hoverinfo="text", text=[label] * len(xs),
        ))
    for c, (lon, lat) in CENTROIDS.items():
        fig.add_trace(go.Scattergeo(lon=[lon], lat=[lat], mode="markers+text", text=[ui.CONTINENT_KO[c]],
                                    textposition="bottom center", textfont=dict(size=11, color=ui.INK2),
                                    marker=dict(size=9, color=ui.CONTINENT_COLOR[c], line=dict(width=2, color="#fcfcfb")),
                                    hoverinfo="skip", showlegend=False))
    fig.update_geos(projection_type="natural earth", showframe=False, showcoastlines=False, showland=True,
                    landcolor="#efefec", showcountries=False, bgcolor="rgba(0,0,0,0)", lataxis_range=[-58, 84])
    fig.update_layout(title="대륙 간 상품 이동 (출발 대륙 색)", margin=dict(l=0, r=0, t=36, b=0), dragmode=False)
    return fig
