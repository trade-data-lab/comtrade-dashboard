# comtrade-dashboard

UN Comtrade 전 세계 양자(bilateral) HS 6단위 무역 패널(2000년~)을 보는 Streamlit 대시보드. Streamlit Community Cloud에서 실행되고, 데이터는 Hugging Face 비공개 Dataset `trade-data-lab/comtrade-hs6-agg`에서 읽는다. 이 repo의 `main`에 push하면 대시보드에 자동 반영된다.

## 기능

| 조건 | 내용 |
|---|---|
| 흐름 | 수출 / 수입 |
| 보고국 | 수출이면 수출국, 수입이면 수입국. World(보고국 전체 합계) 포함 |
| 상대국 | 여러 개 선택, World(대세계) 포함. 비우면 모든 상대국 |
| 기간 | 연도 범위 또는 전기간(2000~최근) |
| 품목 | HS 2·4·6단위, 단일·복수 선택. 비우면 전체 |
| 지표 | 금액(USD) / 순중량(kg) / 수량 |
| 보기 | 연도별 추이, 품목별 순위, 상대국별 순위. 오름·내림차순, 상위 개수 |

결과는 차트와 표로 보여 주고 CSV로 내려받을 수 있다.

## 설정

Streamlit Cloud 앱의 **Settings → Secrets**에 Dataset 읽기 토큰을 넣는다. 최상위 키는 환경 변수로도 전달된다.

```toml
HF_TOKEN = "hf_..."
# 선택: DASHBOARD_DUCKDB_MEMORY = "1GB", DASHBOARD_DEFAULT_LEVEL = "4"
```

토큰은 `comtrade-hs6-agg`, `comtrade-hs6-raw`에 **읽기** 권한만 있으면 된다. 코드나 이 repo에 토큰을 넣지 않는다 (공개 repo).

## 속도

처음 고른 HS 단위·연도의 집계 파일은 서버 디스크에 통째로 받아 두고(연도당 HS2 약 20MB, HS4 약 100MB, HS6 약 250MB), 이후에는 로컬에서 읽는다. 앱이 다시 시작되면 다시 받는다.

## 로컬 실행

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
$env:DASHBOARD_DEFAULT_LEVEL = '2'   # 디스크가 작으면 가벼운 HS2로 시작
.venv\Scripts\streamlit run app.py
```

`hf auth login`으로 Dataset을 읽을 수 있는 토큰이 있어야 한다.
