"""UN Comtrade 전 세계 양자 HS6 무역 대시보드 (Streamlit).

탭: Overall · Continents · Clustering · Pairing · Industries
데이터: Hugging Face `trade-data-lab/comtrade-hs6-agg`의 대시보드용 집계표(dash/)와 코드표(reference/).
"""

import streamlit as st
from huggingface_hub.errors import HfHubHTTPError

from core import data, ui
from views import clustering, continents, explorer, industries, overall, pairing

st.set_page_config(page_title="Global Trade Dashboard", page_icon="🌐", layout="wide",
                   initial_sidebar_state="expanded")
ui.inject_css()

try:
    ref = data.reference()
    years_available = data.available_years("country")
except HfHubHTTPError as e:
    status = getattr(e.response, "status_code", None)
    st.error("Hugging Face 데이터에 접근하지 못했습니다" + (f" (HTTP {status})." if status else ".")
             + " 앱 설정의 Secrets에 `HF_TOKEN = \"hf_...\"`가 있는지, 그 토큰에 "
             "`trade-data-lab/comtrade-hs6-agg` 읽기 권한이 있는지 확인해 주세요.")
    st.stop()

if not years_available:
    st.error("대시보드용 집계표(`dash/`)가 아직 Hugging Face에 없습니다. "
             "comtrade-pipeline의 **Rebuild aggregates** 워크플로를 `scope=dash`로 실행해 주세요.")
    st.stop()

outliers = data.weight_outliers()
outliers["reporter"] = outliers.reporter_code.map(ref["name"])
outliers["flow"] = outliers.flow.map(ui.FLOW_KO)
filters = ui.sidebar_filters(years_available, outliers[["year", "reporter", "flow", "kg_per_usd"]])
st.session_state["filters"] = filters
st.session_state["ref"] = ref

pages = [
    st.Page(overall.render, title="Overall", icon=":material/public:", default=True),
    st.Page(continents.render, title="Continents", icon=":material/map:", url_path="continents"),
    st.Page(clustering.render, title="Clustering", icon=":material/bubble_chart:", url_path="clustering"),
    st.Page(pairing.render, title="Pairing", icon=":material/swap_horiz:", url_path="pairing"),
    st.Page(industries.render, title="Industries", icon=":material/factory:", url_path="industries"),
    st.Page(explorer.render, title="Explorer", icon=":material/search:", url_path="explorer"),
]
page = st.navigation(pages, position="top")

ui.begin_page()
page.run()
ui.floating_tools(page.title, filters.label)
