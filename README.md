# comtrade-dashboard

UN Comtrade 전 세계 양자(bilateral) HS 6단위 무역 패널(2000년~)을 보는 Streamlit 대시보드. Streamlit Community Cloud에서 실행되고, 데이터는 Hugging Face 비공개 Dataset `trade-data-lab/comtrade-hs6-agg`에서 읽는다. 이 repo의 `main`에 push하면 대시보드에 자동 반영된다.

## 페이지 (상단 탭)

| 탭 | 내용 |
|---|---|
| **Overall** | 세계 수출입 합계와 전년 대비, 보고국 수, 상위 수출국·수입국, 대륙→국가 트리맵, 세계 상위 HS2 품목 |
| **Continents** | 대륙별 장기 추이, 대륙별 합계로 색칠한 세계지도(나라를 클릭하면 그 대륙의 HS4 품목 순위), 대륙 간 상품 이동 화살표 지도와 행렬 |
| **Clustering** | 상단 고정 다이제스트(합계·국가 평균·중위, 연도별 상세), 금액·순중량 기준 k-평균 군집, 군별 구분 기준·국가 목록·주요 수출입 품목 |
| **Pairing** | 국가쌍 교역 순위(수출국 보고 / 수입국 보고 / 양방향 합계), 행을 클릭하면 그 쌍의 HS4 품목 순위 |
| **Industries** | ISIC Rev.3 산업별 수출입 순위(2자리·4자리), 행을 클릭하면 그 산업의 수출·수입 상위 국가 |
| **Explorer** | 보고국·상대국·HS 2/4/6단위 품목을 직접 골라 금액·순중량·수량을 보는 상세 조회 |

공통: 왼쪽 사이드바에서 기간(연도 범위 또는 전기간)과 지표(금액 / 순중량)를 고른다. 모든 그래프는 마우스를 올리면 값이 보이고, 오른쪽 고정 배너의 **Excel**은 그 페이지에 쓰인 표를 시트별로 내려받고 **PDF**는 브라우저 인쇄 창(PDF로 저장)을 연다.

## 데이터

| 파일 | 내용 |
|---|---|
| `dash/country`, `pairs`, `country_hs4`, `pair_hs4_top`, `industry` | comtrade-pipeline이 원데이터에서 만든 연도별 소형 집계표 (`year=YYYY.parquet`) |
| `hs2/`, `hs4/`, `hs6/` | Explorer가 쓰는 HS 단위별 집계 (연도당 20~250MB, 고른 연도만 받음) |
| `reference/` | 국가·대륙, HS 품목, 수량 단위, ISIC 이름, 세계지도(GeoJSON) |

파일은 처음 한 번만 서버 디스크에 받아 두고 이후에는 로컬에서 읽는다(앱이 다시 시작되면 다시 받는다). 보고국 연도 합계에서 순중량/금액이 30 kg/USD를 넘는 보고(예: Eswatini 2016 수입, Mexico 수입)는 단위 오류로 보고 순중량 계산에서 뺀다. 사이드바에 목록이 있다.

## 해석 시 주의

- 모든 값은 **각 보고국이 보고한 값**이고, World는 그해 보고한 국가만의 합이다. 최근 연도는 보고국이 적다.
- 같은 거래도 수출국 보고와 수입국 보고가 다를 수 있다 (Pairing의 기준 선택).
- HS 개정판이 연도·국가마다 달라 장기 비교에서 품목 범위가 다를 수 있다.
- 산업은 WITS HS→ISIC Rev.3 대응표(HS 2017·2022는 HS 2012 표로 대체) 기준이며, 대응이 없는 품목은 `99 미분류`다.
- 국가쌍 품목 순위는 연도별 상위 20개 HS4를 합한 값이라 작은 품목은 빠질 수 있다.

## 설정

Streamlit Cloud 앱의 **Settings → Secrets**에 Dataset 읽기 토큰을 넣는다.

```toml
HF_TOKEN = "hf_..."
# 선택: DASHBOARD_DUCKDB_MEMORY = "1GB", DASHBOARD_CACHE_DIR = "/tmp/hf"
```

토큰은 `comtrade-hs6-agg`에 **읽기** 권한만 있으면 된다. 코드나 이 repo에 토큰을 넣지 않는다 (공개 repo).

## 로컬 실행

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\streamlit run app.py
```

`hf auth login`으로 Dataset을 읽을 수 있는 토큰이 있어야 한다.
