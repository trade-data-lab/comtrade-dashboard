"""Continents: 대륙별 추이, 지도, 대륙 간 흐름."""

import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
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
    ui.chart_title(f"대륙별 {ui.FLOW_KO[flow]} {ui.METRIC_KO[m]} 추이", unit)
    fig = go.Figure()
    ymax = trend[m].max() if len(trend) else 1
    labelled = []
    for c in MAIN:
        s = trend[trend.continent == c]
        if s.empty:
            continue
        fig.add_trace(go.Scatter(
            x=s.year, y=s[m], mode="lines+markers", name=ui.CONTINENT_KO[c],
            line=dict(color=ui.CONTINENT_COLOR[c], width=2), marker=dict(size=6),
            customdata=ui.short_series(s[m]), hovertemplate="%{customdata}<extra>" + ui.CONTINENT_KO[c] + "</extra>",
        ))
        last = s[m].iloc[-1]
        # 끝점 이름표는 서로 겹치지 않는 계열에만 (나머지는 범례로)
        if all(abs(last - other) > 0.05 * ymax for other in labelled):
            labelled.append(last)
            fig.add_annotation(x=s.year.iloc[-1], y=last, text=ui.CONTINENT_KO[c], showarrow=False,
                               xanchor="left", xshift=6, font=dict(color=ui.CONTINENT_COLOR[c], size=11))
    fig.update_layout(hovermode="x unified", yaxis=dict(tickformat="~s", rangemode="tozero"), margin=dict(r=80),
                      xaxis=dict(dtick=1 if len(f.years) <= 12 else 2, range=[min(f.years) - 0.4, max(f.years) + 0.4]))
    ui.plot(fig, height=420)
    wide = trend.pivot(index="year", columns="continent", values=m).rename(columns=ui.CONTINENT_KO).reset_index()
    ui.register("대륙별 추이", wide)

    # ---- 지도 (대륙별 합계로 색) + 나라 클릭 → 그 대륙의 품목 순위
    st.subheader("지도")
    cont_total = d.groupby("continent")[m].sum()
    marks = [c for c in MAIN if c in cont_total.index]
    if st.session_state.get("cont_select") not in marks:
        st.session_state["cont_select"] = marks[0]
    ui.chart_title(f"대륙별 {ui.FLOW_KO[flow]} {ui.METRIC_KO[m]}", "나라를 클릭하면 그 대륙의 품목 순위가 아래에 나옵니다 · 마우스를 올리면 값")
    event = st.pydeck_chart(_continent_map(ref, cont_total, unit, flow), on_select="rerun",
                            selection_mode="single-object", key="cont_map", height=440, width="stretch")
    picked = None
    try:
        objects = event.selection.objects.get("countries", [])
        picked = objects[0] if objects else None
    except AttributeError:
        pass
    if picked:
        props = picked.get("properties", picked)
        if props.get("continent") in marks:
            # 선택 상자는 자기 상태를 기억하므로, 지도 클릭은 상자의 상태를 직접 바꾼다
            st.session_state["cont_select"] = props["continent"]
    st.markdown(f'<div class="section-note">색이 진할수록 {ui.FLOW_KO[flow]} {ui.METRIC_KO[m]}이 큰 대륙 · '
                + " · ".join(f"{ui.CONTINENT_KO[k]} {ui.short(cont_total[k])}" for k in marks) + "</div>", unsafe_allow_html=True)
    pick = st.selectbox("대륙 (지도 클릭 또는 선택)", marks, format_func=lambda c: ui.CONTINENT_KO[c], key="cont_select")
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
        fig.update_layout(title="출발 대륙(행) → 도착 대륙(열)", xaxis=dict(tickangle=0, tickfont=dict(size=11)),
                          yaxis=dict(autorange="reversed", tickfont=dict(size=11)), margin=dict(l=8, r=8, t=44, b=8))
        ui.plot(fig, height=460)
    ui.register("대륙 간 흐름", flows.assign(origin=flows.origin.map(ui.CONTINENT_KO), dest=flows.dest.map(ui.CONTINENT_KO)))


@st.cache_data(ttl=86400, show_spinner=False)
def _world():
    with open(data.download("reference/world_110m.geojson"), encoding="utf-8") as fh:
        return json.load(fh)


def _ramp(values):
    """값 크기에 따라 순차 파랑 램프의 색을 고른다 (0 → 가장 연한 색)."""
    vmax = max(float(values.max()), 1e-9)
    steps = len(ui.SEQUENTIAL) - 1
    return [ui.SEQUENTIAL[int(round(steps * (0 if pd.isna(v) else v) / vmax))] for v in values]


def _rgb(hex_color, alpha=255):
    h = hex_color.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)] + [alpha]


def _continent_map(ref, cont_total, unit, flow):
    iso_cont = {}
    for code, iso in ref["iso3"].items():
        cont = ref["continent"].get(code)
        if cont in MAIN and isinstance(iso, str) and len(iso) == 3:
            iso_cont[iso] = cont
    color = dict(zip(cont_total.index, _ramp(cont_total)))
    features = []
    for f in _world()["features"]:
        iso = f["properties"]["iso3"]
        cont = iso_cont.get(iso)
        features.append({"type": "Feature", "geometry": f["geometry"], "properties": {
            "name": f["properties"]["name"], "continent": cont or "",
            "continent_ko": ui.CONTINENT_KO.get(cont, "기타·미상"),
            "total_text": ui.short(cont_total.get(cont, 0), " " + unit) if cont else "–",
            "fill": _rgb(color.get(cont, "#e8e8e4")) if cont else _rgb("#e8e8e4"),
        }})
    layer = pdk.Layer(
        "GeoJsonLayer", {"type": "FeatureCollection", "features": features}, id="countries",
        pickable=True, stroked=True, filled=True, get_fill_color="properties.fill",
        get_line_color=[252, 252, 251, 255], line_width_min_pixels=0.6,
        auto_highlight=True, highlight_color=[11, 11, 11, 40],
    )
    view = pdk.ViewState(latitude=18, longitude=12, zoom=0.85, min_zoom=0.5, max_zoom=4)
    tooltip = {"html": "<b>{name}</b><br/>{continent_ko} " + ui.FLOW_KO[flow] + " 합계 {total_text}<br/>"
                       "<span style='color:#898781'>클릭하면 이 대륙의 품목 순위</span>",
               "style": {"backgroundColor": "#ffffff", "color": "#0b0b0b", "fontSize": "13px",
                         "border": "1px solid #e1e0d9", "borderRadius": "8px", "padding": "8px 10px"}}
    return pdk.Deck(layers=[layer], initial_view_state=view, map_style=None, map_provider=None, tooltip=tooltip)


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
