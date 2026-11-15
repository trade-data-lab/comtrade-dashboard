"""Pairing: 국가쌍 교역 순위와 품목."""

import pandas as pd
import streamlit as st

from core import data, ui

BASIS = {"X": "수출국 보고 (A → B)", "M": "수입국 보고 (A ← B)", "both": "양방향 합계 (A ↔ B, 수출 보고 기준)"}


def render():
    f, ref = st.session_state["filters"], st.session_state["ref"]
    m, unit = f.metric, ui.unit_label(f.metric)
    st.title("국가쌍 교역 순위")

    c1, c2, c3 = st.columns([3, 2, 2])
    basis = c1.radio("기준", list(BASIS), format_func=lambda b: BASIS[b], horizontal=True, key="pair_basis")
    top_n = c2.slider("표시 순위", 10, 200, 50, step=10, key="pair_n")
    exclude = c3.toggle("미상·특수 지역 제외", value=True, help="Areas nes, Free Zones, Bunkers 같은 특수 코드와 지역 묶음을 뺍니다.", key="pair_excl")

    pr = data.pairs(f.years)
    countries = ref["countries"]
    special = set(countries.loc[countries.is_group | (countries.continent == "Unspecified"), "code"])
    if exclude:
        pr = pr[~pr.reporter_code.isin(special) & ~pr.partner_code.isin(special)]

    if basis == "both":
        x = pr[pr.flow == "X"].copy()
        x["a"] = x[["reporter_code", "partner_code"]].min(axis=1)
        x["b"] = x[["reporter_code", "partner_code"]].max(axis=1)
        ranked = x.groupby(["a", "b"])[["value", "net_wgt"]].sum().reset_index()
        arrow = "↔"
    else:
        d = pr[pr.flow == basis].rename(columns={"reporter_code": "a", "partner_code": "b"})
        ranked = d[["a", "b", "value", "net_wgt"]]
        arrow = "→" if basis == "X" else "←"
    ranked = ranked.sort_values(m, ascending=False).reset_index(drop=True)
    ranked["share"] = ranked[m] / ranked[m].sum() * 100
    ranked.insert(0, "rank", ranked.index + 1)
    ranked["A"] = ranked.a.map(ref["name"])
    ranked["B"] = ranked.b.map(ref["name"])
    ranked["pair"] = ranked.A + f" {arrow} " + ranked.B
    ui.note(f"{f.label} · {ui.METRIC_KO[m]} 기준 · {BASIS[basis]}. 같은 거래도 수출국과 수입국의 보고가 서로 다를 수 있습니다.")

    show = ranked.head(top_n)
    c1, c2 = st.columns([2, 3])
    with c1:
        top = show.head(20).copy()
        top["hover"] = [f"{ui.short(v, ' ' + unit)} · 비중 {s:.2f}%" for v, s in zip(top[m], top.share)]
        ui.plot(ui.hbar(top, m, "pair", hover="hover", title=f"상위 20 국가쌍"), height=620)
    with c2:
        table = show[["rank", "A", "B", "value", "net_wgt", "share"]].rename(
            columns={"rank": "순위", "A": "국가 A", "B": "국가 B", "value": "금액 (USD)", "net_wgt": "순중량 (kg)", "share": "비중 (%)"})
        st.caption("행을 클릭하면 아래에 그 국가쌍의 품목 순위가 나옵니다.")
        event = ui.table(table, key="pair_table", select=True, height=580, formats={"비중 (%)": "%.2f"})
    ui.register("국가쌍 순위", table)

    row = ui.selected_row(event)
    sel = show.iloc[row if row is not None else 0]
    st.subheader(f"{sel.pair} · 품목 순위")
    ui.note("각 연도의 상위 20개 HS 4단위 품목을 선택 기간에 걸쳐 합한 값이라, 작은 품목은 빠질 수 있습니다.")
    if basis == "both":
        c1, c2 = st.columns(2)
        _items(c1, f, ref, int(sel.a), int(sel.b), "X", f"{sel.A} → {sel.B}")
        _items(c2, f, ref, int(sel.b), int(sel.a), "X", f"{sel.B} → {sel.A}")
    else:
        _items(st.container(), f, ref, int(sel.a), int(sel.b), basis, sel.pair, wide=True)


def _items(container, f, ref, reporter, partner, flow, title, wide=False):
    m, unit = f.metric, ui.unit_label(f.metric)
    items = data.pair_items(f.years, reporter, partner, flow)
    with container:
        if items.empty:
            st.info("이 방향의 품목 자료가 없습니다.")
            return
        items["label"] = items.hs4.map(ref["hs_label"]).fillna(items.hs4).str.slice(0, 48)
        items["share"] = items[m] / items[m].sum() * 100
        items["hover"] = [f"{ui.short(v, ' ' + unit)} · 비중 {s:.1f}%" for v, s in zip(items[m], items.share)]
        fig = ui.hbar(items.head(15), m, "label", hover="hover", color=ui.FLOW_COLOR[flow], title=f"{title} 상위 품목")
        show = items[["hs4", "label", "value", "net_wgt", "share"]].rename(
            columns={"hs4": "HS4", "label": "품목", "value": "금액 (USD)", "net_wgt": "순중량 (kg)", "share": "비중 (%)"})
        if wide:
            c1, c2 = st.columns([3, 2])
            with c1:
                ui.plot(fig, height=460)
            with c2:
                ui.table(show, height=460, formats={"비중 (%)": "%.2f"})
        else:
            ui.plot(fig, height=460)
            ui.table(show, height=300, formats={"비중 (%)": "%.2f"})
        ui.register(f"품목 {title[:24]}", show)
