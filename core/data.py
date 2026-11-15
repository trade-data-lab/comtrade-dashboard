"""Hugging Face의 집계 Dataset(`comtrade-hs6-agg`)을 내려받아 DuckDB로 읽는다.

파일은 처음 한 번만 통째로 받아 디스크에 두고(hf_hub_download 캐시), 이후에는 로컬에서 읽는다.
모든 무거운 집계는 DuckDB 안에서 끝내고 작은 결과만 pandas로 돌려준다.
"""

import os
from dataclasses import dataclass

import duckdb
import pandas as pd
import streamlit as st
from huggingface_hub import HfApi, snapshot_download

AGG_REPO = "trade-data-lab/comtrade-hs6-agg"
WORLD = 0
CONTINENTS = ["Asia", "Europe", "North America", "South America", "Africa", "Oceania", "Unspecified"]


@dataclass(frozen=True)
class Filters:
    years: tuple          # 선택한 연도들 (오름차순)
    whole_period: bool    # 전기간 여부
    metric: str           # "value" | "net_wgt"

    @property
    def latest(self):
        return self.years[-1]

    @property
    def label(self):
        if self.whole_period:
            return f"전기간 ({self.years[0]}~{self.years[-1]})"
        return f"{self.years[0]}년" if len(self.years) == 1 else f"{self.years[0]}~{self.years[-1]}년"


def hf_token():
    try:
        return st.secrets.get("HF_TOKEN") or os.environ.get("HF_TOKEN")
    except FileNotFoundError:
        return os.environ.get("HF_TOKEN")


def download_many(paths):
    """여러 파일을 한꺼번에(병렬) 받아 로컬 경로 목록을 돌려준다. 이미 받은 파일은 캐시를 쓴다."""
    paths = list(paths)
    if not paths:
        return []
    root = snapshot_download(AGG_REPO, repo_type="dataset", allow_patterns=paths, max_workers=8,
                             token=hf_token(), cache_dir=os.environ.get("DASHBOARD_CACHE_DIR"))
    return [f"{root}/{p}".replace("\\", "/") for p in paths]


def download(path):
    return download_many([path])[0]


@st.cache_data(ttl=3600, show_spinner=False)
def repo_files():
    return HfApi(token=hf_token()).list_repo_files(AGG_REPO, repo_type="dataset")


def available_years(table):
    prefix = f"dash/{table}/year="
    return sorted(int(f[len(prefix):-8]) for f in repo_files() if f.startswith(prefix))


# 보고국 연도 합계에서 순중량/금액이 이 값(kg/USD)을 넘으면 단위 오류로 보고 순중량을 결측 처리한다.
# 금액 10억$ 이상 보고의 99% 지점이 약 11 kg/USD다. 예: Eswatini 2016 수입 660만 kg/USD, Mexico 수입 약 100 kg/USD.
WEIGHT_MAX_KG_PER_USD = 30


@st.cache_resource
def connect():
    con = duckdb.connect()
    con.execute(f"SET memory_limit = '{os.environ.get('DASHBOARD_DUCKDB_MEMORY', '1GB')}'")
    con.execute("SET threads = 2")
    files = dash_files("country", available_years("country"))
    con.execute(f"""
        CREATE TABLE wgt_bad AS
        SELECT year, reporter_code, flow, net_wgt / value AS kg_per_usd
        FROM read_parquet({files!r})
        WHERE net_wgt / nullif(coalesce(value, value_bilateral), 0) > {WEIGHT_MAX_KG_PER_USD}
    """)
    return con


@st.cache_data(ttl=86400, show_spinner=False)
def weight_outliers():
    """순중량을 제외한 (연도, 보고국, 흐름) 목록."""
    return query("SELECT year, reporter_code, flow, kg_per_usd FROM wgt_bad ORDER BY kg_per_usd DESC")


# 각 조회에서 순중량 이상치를 결측으로 바꾸는 조각
WGT = "CASE WHEN b.year IS NULL THEN t.net_wgt END"
BAD_JOIN = "LEFT JOIN wgt_bad b USING (year, reporter_code, flow)"


def query(sql, params=None):
    return connect().execute(sql, params or []).df()


def dash_files(table, years):
    return download_many(f"dash/{table}/year={y}.parquet" for y in years)


def _src(table, years):
    return f"read_parquet({dash_files(table, years)!r})"


@st.cache_data(ttl=86400, show_spinner="코드표를 불러오는 중...")
def reference():
    ref = {}
    coverage_files = [f for f in repo_files() if f.startswith("coverage/")]
    download_many(["reference/continents.csv", "reference/reporters.csv", "reference/partners.csv",
                   "reference/hs.csv", "reference/quantity_units.csv", "reference/isic3.csv"] + coverage_files)
    countries = pd.read_csv(download("reference/continents.csv"), keep_default_na=False)
    reporters = pd.read_csv(download("reference/reporters.csv"), keep_default_na=False)
    partners = pd.read_csv(download("reference/partners.csv"), keep_default_na=False)
    groups = set(reporters.loc[reporters.is_group.astype(str) == "True", "code"]) | \
        set(partners.loc[partners.is_group.astype(str) == "True", "code"])
    countries["is_group"] = countries.code.isin(groups)
    ref["countries"] = countries                                  # code, name, iso3, continent, is_group
    ref["name"] = dict(zip(countries.code, countries.name))
    ref["continent"] = dict(zip(countries.code, countries.continent))
    ref["iso3"] = dict(zip(countries.code, countries.iso3))
    hs = pd.read_csv(download("reference/hs.csv"), dtype={"code": str}, keep_default_na=False)
    ref["hs"] = hs                                                # code, label, level, standard_unit
    ref["hs_label"] = dict(zip(hs.code, hs.label))
    units = pd.read_csv(download("reference/quantity_units.csv"), keep_default_na=False)
    ref["unit"] = dict(zip(units.qtyCode, units.qtyAbbr))
    isic = pd.read_csv(download("reference/isic3.csv"), dtype=str, keep_default_na=False)
    ref["isic_name"] = dict(zip(isic.code, isic.description))
    cov = download_many(coverage_files)
    ref["coverage"] = query(f"SELECT * FROM read_parquet({cov!r}) ORDER BY year, flow")
    return ref


# ---------- 대시보드 집계표 조회 (모두 보고국이 보고한 값) ----------

@st.cache_data(ttl=86400, show_spinner="국가별 합계를 읽는 중...")
def country_year(years):
    """연도 × 보고국 × 흐름. value는 대세계(partner 0) 합계, 없으면 양자 합계로 대신한다."""
    return query(f"""
        SELECT year, reporter_code, flow,
               coalesce(value, value_bilateral) AS value, {WGT} AS net_wgt, partners, items,
               b.year IS NOT NULL AS wgt_excluded
        FROM {_src('country', years)} t {BAD_JOIN}
    """)


@st.cache_data(ttl=86400, show_spinner="국가쌍 합계를 읽는 중...")
def pairs(years):
    """선택 기간 합계: 보고국 × 상대국 × 흐름."""
    return query(f"""
        SELECT reporter_code, partner_code, flow, sum(value) AS value, sum({WGT}) AS net_wgt
        FROM {_src('pairs', years)} t {BAD_JOIN} GROUP BY ALL
    """)


@st.cache_data(ttl=86400, show_spinner="품목별 합계를 읽는 중...")
def hs4_by_group(years, flow, groups):
    """보고국을 묶음(groups: {code: group})별로 합친 HS4 순위. 대륙·클러스터 품목 순위에 쓴다."""
    mapping = pd.DataFrame(list(groups.items()), columns=["reporter_code", "grp"])
    con = connect()
    con.register("grp_map", mapping)
    df = con.execute(f"""
        SELECT m.grp, t.hs4, sum(t.value) AS value, sum({WGT}) AS net_wgt
        FROM {_src('country_hs4', years)} t JOIN grp_map m USING (reporter_code) {BAD_JOIN}
        WHERE t.flow = ? GROUP BY ALL
    """, [flow]).df()
    con.unregister("grp_map")
    return df


@st.cache_data(ttl=86400, show_spinner="세계 품목 합계를 읽는 중...")
def world_hs(years, flow, level=2):
    return query(f"""
        SELECT left(hs4, {level}) AS hs, sum(value) AS value, sum({WGT}) AS net_wgt
        FROM {_src('country_hs4', years)} t {BAD_JOIN} WHERE t.flow = ? GROUP BY ALL ORDER BY value DESC
    """, [flow])


@st.cache_data(ttl=86400, show_spinner="국가쌍 품목을 읽는 중...")
def pair_items(years, reporter, partner, flow):
    """연도별 상위 20개 HS4를 선택 기간에 걸쳐 합친 값."""
    return query(f"""
        SELECT hs4, sum(value) AS value, sum({WGT}) AS net_wgt, count(*) AS years_in_top
        FROM {_src('pair_hs4_top', years)} t {BAD_JOIN}
        WHERE reporter_code = ? AND partner_code = ? AND flow = ?
        GROUP BY hs4 ORDER BY value DESC
    """, [reporter, partner, flow])


@st.cache_data(ttl=86400, show_spinner="산업별 합계를 읽는 중...")
def industry(years):
    """선택 기간 합계: 보고국 × 흐름 × ISIC 4자리."""
    return query(f"""
        SELECT reporter_code, flow, isic, sum(value) AS value, sum({WGT}) AS net_wgt
        FROM {_src('industry', years)} t {BAD_JOIN} GROUP BY ALL
    """)
