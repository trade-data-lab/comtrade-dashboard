"""대시보드 공통 UI: 색, Plotly 템플릿, 숫자 표기, KPI 카드, 고정 배너(Excel·PDF), 사이드바 필터."""

import io
from contextlib import contextmanager

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
import streamlit.components.v1 as components

from .data import CONTINENTS, WEIGHT_MAX_KG_PER_USD, Filters

# 검증된 범주형 팔레트 (고정 순서, 순환하지 않음)
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#1c5cab", "#104281", "#0d366b"]
INK, INK2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
FLOW_COLOR = {"X": PALETTE[0], "M": PALETTE[1]}
FLOW_KO = {"X": "수출", "M": "수입"}
CONTINENT_KO = {"Asia": "아시아", "Europe": "유럽", "North America": "북아메리카", "South America": "남아메리카",
                "Africa": "아프리카", "Oceania": "오세아니아", "Unspecified": "기타·미상", "Antarctica": "남극"}
CONTINENT_COLOR = {c: PALETTE[i] for i, c in enumerate(CONTINENTS[:6])} | {"Unspecified": MUTED, "Antarctica": MUTED}
METRIC_KO = {"value": "금액", "net_wgt": "순중량"}
METRIC_UNIT = {"value": "USD", "net_wgt": "kg"}

PLOT_CONFIG = {"displaylogo": False, "scrollZoom": False,  # 페이지 스크롤이 지도를 확대·축소하지 않게
               "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
               "toImageButtonOptions": {"format": "png", "scale": 2}}


def _template():
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family='system-ui, -apple-system, "Segoe UI", "Malgun Gothic", sans-serif', size=13, color=INK2),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        colorway=PALETTE, margin=dict(l=48, r=16, t=16, b=56),
        hoverlabel=dict(bgcolor="#ffffff", bordercolor=GRID, font=dict(color=INK, size=13)),
        legend=dict(orientation="h", yanchor="top", y=-0.14, x=0, xanchor="left", title=None, font=dict(color=INK2)),
        xaxis=dict(gridcolor=GRID, linecolor=AXIS, zerolinecolor=GRID, tickfont=dict(color=MUTED), showgrid=False,
                   automargin=True),
        yaxis=dict(gridcolor=GRID, linecolor=AXIS, zerolinecolor=GRID, tickfont=dict(color=MUTED), gridwidth=1,
                   automargin=True),
        title=dict(font=dict(size=15, color=INK), x=0, xanchor="left"),
        separators=".,",
    )
    return t


pio.templates["trade"] = _template()
pio.templates.default = "trade"


# ---------- 숫자 표기 ----------

def short(n, unit=""):
    """1.23조, 4.5억, 6.7만 식의 짧은 표기. 달러·kg 공통."""
    if n is None or pd.isna(n):
        return "–"
    sign = "-" if n < 0 else ""
    n = abs(n)
    for size, suffix in ((1e12, "조"), (1e8, "억"), (1e4, "만")):
        if n >= size:
            return f"{sign}{n / size:,.2f}{suffix}{unit}"
    return f"{sign}{n:,.0f}{unit}"


def short_series(s, unit=""):
    return [short(v, unit) for v in s]


def pct(n, digits=1):
    return "–" if n is None or pd.isna(n) else f"{n:+.{digits}f}%"


def unit_label(metric):
    return METRIC_UNIT[metric]


# ---------- 페이지 공통 CSS ----------

def inject_css():
    st.markdown("""
    <style>
      .block-container { padding-top: 1.2rem; padding-bottom: 4rem; max-width: 1400px; }
      @media (min-width: 1100px) { .block-container { padding-right: 170px; } }
      h1, h2, h3 { letter-spacing: -0.01em; }
      .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 4px 0 14px; }
      .kpi { background: #ffffff; border: 1px solid rgba(11,11,11,0.08); border-radius: 14px; padding: 14px 16px;
             box-shadow: 0 1px 2px rgba(11,11,11,0.04); }
      .kpi .label { font-size: 12px; color: #898781; margin-bottom: 6px; letter-spacing: .01em; }
      .kpi .value { font-size: 24px; font-weight: 600; color: #0b0b0b; line-height: 1.15; }
      .kpi .delta { font-size: 12px; margin-top: 6px; color: #52514e; }
      .kpi .delta.up { color: #006300; } .kpi .delta.down { color: #d03b3b; }
      .section-note { color: #52514e; font-size: 13px; margin: -6px 0 10px; }
      .chart-title { font-size: 15px; font-weight: 600; color: #0b0b0b; margin: 6px 0 -4px; }
      .chart-title .chart-sub { font-weight: 400; color: #898781; font-size: 12px; margin-left: 8px; }
      .st-key-floating_tools { position: fixed; right: 18px; top: 42%; z-index: 999; width: 128px;
             background: rgba(255,255,255,0.86); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
             border: 1px solid rgba(11,11,11,0.08); border-radius: 16px; padding: 10px 10px 6px;
             box-shadow: 0 8px 28px rgba(11,11,11,0.10); }
      .st-key-floating_tools .stDownloadButton button, .st-key-floating_tools .stButton button { width: 100%; border-radius: 10px; }
      .st-key-floating_tools p { font-size: 11px; color: #898781; text-align: center; margin: 0 0 6px; }
      /* 고정 박스: Streamlit은 요소를 감싸는 래퍼 높이만큼만 sticky가 움직이므로 래퍼 자체를 고정한다 */
      [data-testid="stLayoutWrapper"]:has(> .st-key-digest_box) { position: sticky; top: 3.2rem; z-index: 50;
             background: #fcfcfb; padding-top: 4px; }
      .st-key-digest_box { background: #fcfcfb; border: 1px solid rgba(11,11,11,0.08); border-radius: 14px;
             padding: 10px 14px 4px; margin-bottom: 14px; box-shadow: 0 6px 18px rgba(11,11,11,0.06); }
      .st-key-digest_box .kpi-grid { margin: 0 0 6px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
      .st-key-digest_box .kpi { padding: 8px 12px; box-shadow: none; }
      .st-key-digest_box .kpi .value { font-size: 18px; }
      @media print {
        .st-key-floating_tools, [data-testid="stSidebar"], header, [data-testid="stToolbar"],
        [data-testid="stHeader"], [data-testid="stAppViewBlockContainer"] > div:first-child nav { display: none !important; }
        .block-container { max-width: 100% !important; padding: 0 !important; }
        .st-key-digest_box { position: static; box-shadow: none; }
      }
    </style>
    """, unsafe_allow_html=True)


# ---------- KPI 카드 ----------

def kpis(items):
    """items: [(label, value_text, delta_text|None, direction|None)] -> 카드 묶음."""
    cards = []
    for label, value, *rest in items:
        delta = rest[0] if rest else None
        direction = rest[1] if len(rest) > 1 else None
        cls = f" {direction}" if direction in ("up", "down") else ""
        delta_html = f'<div class="delta{cls}">{delta}</div>' if delta else ""
        cards.append(f'<div class="kpi"><div class="label">{label}</div><div class="value">{value}</div>{delta_html}</div>')
    st.markdown(f'<div class="kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def delta_dir(v):
    return None if v is None or pd.isna(v) else ("up" if v >= 0 else "down")


def note(text):
    st.markdown(f'<div class="section-note">{text}</div>', unsafe_allow_html=True)


# ---------- 차트 출력 ----------

def plot(fig, key=None, select=False, height=None):
    if height:
        fig.update_layout(height=height)
    kwargs = dict(width="stretch", theme=None, config=PLOT_CONFIG, key=key)
    if select:
        kwargs.update(on_select="rerun", selection_mode="points")
    return st.plotly_chart(fig, **kwargs)


def clip(text, n=36):
    text = str(text)
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def chart_title(text, sub=None):
    """범례가 있는 차트는 Plotly 제목 대신 이 제목을 쓴다 (범례와 겹치지 않게)."""
    sub_html = f'<span class="chart-sub">{sub}</span>' if sub else ""
    st.markdown(f'<div class="chart-title">{text}{sub_html}</div>', unsafe_allow_html=True)


def hbar(df, x, y, text=None, color=PALETTE[0], hover=None, title=None, height=None, label_width=36):
    """순위형 가로 막대: 한 계열, 한 색. 큰 값이 위. 긴 이름은 줄이고 전체 이름은 툴팁에 둔다."""
    d = df.iloc[::-1]
    full = d[y].astype(str).tolist()
    labels = [clip(s, label_width) for s in full]
    detail = d[hover].tolist() if hover else [f"{v:,.0f}" for v in d[x]]
    fig = go.Figure(go.Bar(
        x=d[x], y=labels, orientation="h", marker=dict(color=color, line=dict(width=0)),
        text=d[text] if text else None, textposition="outside", cliponaxis=False,
        customdata=list(zip(full, detail)),
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>",
        marker_cornerradius=4,
    ))
    fig.update_layout(title=title, bargap=0.32, height=height or max(260, 24 * len(d) + 70),
                      xaxis=dict(showgrid=True, tickformat="~s", title=None),
                      yaxis=dict(title=None, automargin=True, tickfont=dict(size=12)),
                      margin=dict(l=8, r=64, t=44 if title else 8, b=8), showlegend=False)
    return fig


def table(df, key=None, select=False, height=None, formats=None):
    """숫자 열은 천 단위 구분으로. select=True면 한 행 선택 이벤트를 돌려준다."""
    config = {}
    for col in df.columns:
        if pd.api.types.is_float_dtype(df[col]) or pd.api.types.is_integer_dtype(df[col]):
            fmt = (formats or {}).get(col, "%,.0f")
            config[col] = st.column_config.NumberColumn(col, format=fmt)
    kwargs = dict(hide_index=True, width="stretch", column_config=config, key=key)
    if height:
        kwargs["height"] = height
    if select:
        kwargs.update(on_select="rerun", selection_mode="single-row")
    return st.dataframe(df, **kwargs)


def selected_row(event):
    try:
        rows = event.selection.rows
    except AttributeError:
        return None
    return rows[0] if rows else None


def selected_point(event):
    try:
        points = event.selection.points
    except AttributeError:
        return None
    return points[0] if points else None


# ---------- 페이지 데이터 수집 → Excel, PDF 배너 ----------

def begin_page():
    st.session_state["_page_data"] = {}


def register(name, df):
    """이 페이지에서 쓴 표를 Excel 내려받기에 포함한다."""
    if df is not None and len(df):
        st.session_state.setdefault("_page_data", {})[name[:31]] = df
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def _excel_bytes(frames):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in frames.items():
            df.head(200_000).to_excel(xw, sheet_name=name, index=False)
    return buf.getvalue()


def floating_tools(page_title, period_label):
    frames = st.session_state.get("_page_data", {})
    with st.container(key="floating_tools"):
        st.markdown("<p>내보내기</p>", unsafe_allow_html=True)
        if frames:
            st.download_button("Excel", _excel_bytes(frames), f"{page_title}_{period_label}.xlsx",
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               icon=":material/table_view:", help="이 페이지에 쓰인 데이터 (시트별)", key="dl_xlsx")
        else:
            st.button("Excel", disabled=True, icon=":material/table_view:", key="dl_xlsx_off")
        if st.button("PDF", icon=":material/picture_as_pdf:", help="브라우저 인쇄 창에서 'PDF로 저장'", key="print_pdf"):
            components.html("<script>setTimeout(() => window.parent.print(), 300);</script>", height=0)


@contextmanager
def sticky_box():
    with st.container(key="digest_box"):
        yield


# ---------- 사이드바 전역 필터 ----------

def sidebar_filters(years_available, outliers=None):
    with st.sidebar:
        st.markdown("### 조건")
        whole = st.toggle("전기간", value=False, help=f"{years_available[0]}~{years_available[-1]}년 전체")
        if whole:
            years = tuple(years_available)
        else:
            default = (max(years_available[0], years_available[-1] - 9), years_available[-1])
            lo, hi = st.select_slider("기간", options=years_available, value=default)
            years = tuple(y for y in years_available if lo <= y <= hi)
        metric = st.radio("지표", list(METRIC_KO), format_func=lambda m: f"{METRIC_KO[m]} ({METRIC_UNIT[m]})",
                          horizontal=True)
        st.caption("금액은 각 보고국이 보고한 USD(수출 FOB·수입 CIF), 순중량은 kg입니다. "
                   "World는 그해 보고한 국가만의 합입니다.")
        if outliers is not None and len(outliers):
            with st.expander(f"순중량 제외 보고 {len(outliers)}건"):
                st.caption(f"순중량이 금액의 {int(WEIGHT_MAX_KG_PER_USD)} kg/USD를 넘는 보고는 단위 오류로 보고 "
                           "순중량 계산에서만 뺐습니다. 금액은 그대로 씁니다.")
                st.dataframe(outliers, hide_index=True, width="stretch",
                             column_config={"kg_per_usd": st.column_config.NumberColumn("kg/USD", format="%,.0f")})
    return Filters(years=years, whole_period=whole, metric=metric)
