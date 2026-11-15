"""Industries: ISIC 산업별 수출입과 산업별 상위 국가."""

import streamlit as st

from core import data, ui

LEVELS = {2: "대분류 (ISIC 2자리)", 4: "세분류 (ISIC 4자리)"}


def render():
    f, ref = st.session_state["filters"], st.session_state["ref"]
    m, unit = f.metric, ui.unit_label(f.metric)
    st.title("산업별 수출입")

    c1, c2, c3 = st.columns([1, 2, 2])
    flow = c1.radio("흐름", ["X", "M"], format_func=lambda v: ui.FLOW_KO[v], horizontal=True, key="ind_flow")
    level = c2.radio("분류 수준", list(LEVELS), format_func=lambda v: LEVELS[v], horizontal=True, key="ind_level")
    top_n = c3.slider("표시 순위", 10, 150, 40, step=10, key="ind_n")

    ind = data.industry(f.years)
    ind["code"] = ind.isic.str.slice(0, level)
    names = ref["isic_name"]
    ranked = ind[ind.flow == flow].groupby("code")[["value", "net_wgt"]].sum().reset_index()
    ranked = ranked.sort_values(m, ascending=False).reset_index(drop=True)
    ranked["share"] = ranked[m] / ranked[m].sum() * 100
    ranked.insert(0, "rank", ranked.index + 1)
    ranked["name"] = ranked.code.map(lambda c: names.get(c, "미분류" if c.startswith("99") else c))
    ranked["label"] = ranked.code + " " + ranked.name.str.slice(0, 44)
    unmapped = ranked.loc[ranked.code.str.startswith("99"), "share"].sum()
    ui.note(f"{f.label} · {ui.METRIC_KO[m]} · ISIC Rev.3 기준 (WITS HS→ISIC 대응표). "
            f"대응표에 없는 품목은 '99 미분류'로 묶였고 비중은 {unmapped:.1f}%입니다.")

    show = ranked.head(top_n)
    c1, c2 = st.columns([2, 3])
    with c1:
        top = show.head(20).copy()
        top["hover"] = [f"{ui.short(v, ' ' + unit)} · 비중 {s:.1f}%" for v, s in zip(top[m], top.share)]
        ui.plot(ui.hbar(top, m, "label", hover="hover", color=ui.FLOW_COLOR[flow],
                        title=f"{ui.FLOW_KO[flow]} 상위 20 산업"), height=620)
    with c2:
        table = show[["rank", "code", "name", "value", "net_wgt", "share"]].rename(
            columns={"rank": "순위", "code": "ISIC", "name": "산업", "value": "금액 (USD)", "net_wgt": "순중량 (kg)", "share": "비중 (%)"})
        st.caption("행을 클릭하면 아래에 그 산업의 수출·수입 상위 국가가 나옵니다.")
        event = ui.table(table, key="ind_table", select=True, height=580, formats={"비중 (%)": "%.2f"})
    ui.register("산업 순위", table)

    row = ui.selected_row(event)
    sel = show.iloc[row if row is not None else 0]
    st.subheader(f"{sel.code} {sel['name']} · 상위 국가")
    by_country = ind[ind.code == sel.code].groupby(["reporter_code", "flow"])[["value", "net_wgt"]].sum().reset_index()
    by_country["name"] = by_country.reporter_code.map(ref["name"])
    c1, c2 = st.columns(2)
    for col, flow_i in ((c1, "X"), (c2, "M")):
        d = by_country[by_country.flow == flow_i].sort_values(m, ascending=False)
        d["share"] = d[m] / d[m].sum() * 100
        top = d.head(15).copy()
        top["hover"] = [f"{ui.short(v, ' ' + unit)} · 비중 {s:.1f}%" for v, s in zip(top[m], top.share)]
        with col:
            ui.plot(ui.hbar(top, m, "name", hover="hover", color=ui.FLOW_COLOR[flow_i],
                            title=f"{ui.FLOW_KO[flow_i]} 상위 15개국"), height=460)
            ui.table(d[["name", "value", "net_wgt", "share"]].rename(
                columns={"name": "국가", "value": "금액 (USD)", "net_wgt": "순중량 (kg)", "share": "비중 (%)"}),
                height=280, formats={"비중 (%)": "%.2f"})
        ui.register(f"{sel.code} {ui.FLOW_KO[flow_i]} 국가", d[["name", "value", "net_wgt", "share"]])
