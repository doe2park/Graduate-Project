# LEED + LCA 데이터 통합 — 발표 정리

> Bechtel Engineering Center digital twin에 LEED 제출 자료 두 패키지를 통합한 작업.
> 발표용 한국어 정리.

---

## 받은 자료 두 패키지

| 패키지 | 핵심 파일 | 데이터 종류 |
|---|---|---|
| **1. Minimum_Optimize Energy Performance** | `LEEDv4MinEnergyPerfCalc.xlsm` | 운영 에너지 — ASHRAE 90.1-2010 baseline vs eQuest as-designed 모델, end-use별 연간 kWh + peak kW |
| **2. Submittal (Life-Cycle)** | `UCB _LEED_LCA credit.xlsx` | 구조 재사용 — 기존 벽/바닥/외피를 얼마나 유지했는지 (LEED v4.1 MR Credit) |

LEED 프로젝트 ID **#1000171106** 으로 두 자료 동일 프로젝트.

---

## 1단계 — 추출 스크립트 두 개 작성

### `extract_leed.py` (이전 주에 완료)
- `Performance_Outputs_Summary` 시트 파싱
- 11개 active end-use 추출 (Space heating/cooling, Pumps, Fans, Lighting, Receptacles, IT, Elevators 등)
- 결과: `data/bechtel_leed.json`

### `extract_lca.py` (이번 주 신규)
- LCA credit xlsx 파싱 (Walls / Floors / Roofs / Envelope 4행)
- 각 element에 대해:
  - `reuse_pct_of_project` (LEED 점수 산정 기준)
  - `kept_pct_of_existing` (renovation 완성도)
- 전체 reuse % → LEED 점수 band 매핑 (15/30/45/60/75/90% threshold)
- 결과: `data/bechtel_lca.json`

---

## 2단계 — 핵심 숫자

### 운영 에너지 (Energy Performance)

| 항목 | 값 |
|---|---|
| Conditioned area | 72,108 sqft |
| Baseline (ASHRAE 90.1-2010) | 1,501 MWh/yr |
| Designed (eQuest 모델) | 824 MWh/yr |
| **Design savings** | **~45%** |
| EUI (designed) | 11.4 kWh/sqft/yr ≈ 39 kBtu/sqft/yr |

### 구조 재사용 (Life-Cycle)

| Element | 기존 면적 | 재사용 면적 | 기존 유지율 |
|---|---|---|---|
| Walls | 23,142 sqft | 20,346 sqft | **87.9%** |
| Floors | 74,583 sqft | 70,308 sqft | **94.3%** |
| Envelope | 3,367 sqft | 3,297 sqft | **97.9%** |
| Roofs | — | — | (terraced 구조라 floors와 통합) |
| **Total** | **101,092 sqft** | **93,951 sqft** | — |

**Project area 대비 전체 reuse: 69.5%** → LEED MR Credit 4점 band (60%+ threshold) 달성.

---

## 3단계 — 디지털 트윈에 어떻게 활용했나

자료의 정적 데이터를 라이브 BMO 미터 데이터와 같은 화면에서 비교 가능하게 만들었어요.
**모드별로 노출 방식을 다르게 설계.**

### Engineer 모드 (Grimes popup 안)

두 개의 새 SCADA-스타일 패널이 추가됨:

**(a) Design Intent vs Actual** — 운영 에너지
- "Designed" (eQuest 연간 MWh) ↔ "Projected" (현재 6시간 평균 kW × 8760) ↔ "Gap %"
- **미터 인식 (meter-aware) 비교** — M76 (mechanical)을 보고 있으면 LEED end-use 중 HVAC/pumps/fans만 합산, M77 (plug+lighting)이면 lighting/receptacles/IT만 합산. 단일 sub-meter를 whole-building 모델과 비교하지 않도록.
- Top 5 end-use 표 (Baseline / Designed / Saved %)

**(b) Material Reuse** — 임베디드 카본
- 전체 reuse %, 재사용 sqft, project sqft → LEED 점수 band 표시
- Element별 % bar (Walls 88% / Floors 94% / Envelope 98%)

### Public 모드 (같은 Grimes popup)

기술 용어 없이 한 줄 카피로 전달:

**(a) "LEED v4 CERTIFIED" badge (green)**
> "Designed to use **45% less energy** than ASHRAE 90.1-2010 code minimum. Right now [±N%] vs design intent."

**(b) "BUILT ON REUSE" badge (terracotta)**
> "Roughly **70%** of this building is reused existing structure — including **94%** of the original floors."

두 카드는 색상이 다름 (LEED energy = green, LCA reuse = terracotta) — 두 가지 다른 sustainability 스토리임을 시각적으로 구분.

---

## 4단계 — 왜 의미 있는가 (Research 관점)

이게 단순한 "LEED 데이터 보여주기"가 아닌 이유:

1. **Performance gap 가시화** — 학계에서 자주 인용되는 "modeled vs actual energy use gap"을 실시간으로 보여줌. 보통은 연 1회 utility bill로 사후 확인하는 것을 매 15분마다 갱신.

2. **Meter-aware scoping** — 단순히 미터 합을 LEED 총량과 비교하면 oranges-to-apples. 미터 → LEED end-use mapping을 명시적으로 정의해서 (`meter_end_use_map`) 어느 sub-meter가 어느 end-use를 측정하는지 추적 가능. 추후 더 많은 sub-meter가 활성화되면 mapping만 확장.

3. **Operational + Embodied 두 측면 동시 표현** — 일반적인 BMS 대시보드는 운영 에너지만 다룸. LCA reuse 데이터를 함께 띄움으로써 "이 건물의 sustainability 풋프린트"라는 더 큰 그림을 한 화면에 압축.

4. **Audience-tiered communication** — 같은 데이터 소스에서 Engineer 패널과 Public 카드를 동시 생성. Stakeholder 별 다른 추상화 레벨 — facility manager는 미터별 gap을 보고, 방문자는 한 문장 narrative를 봄.

---

## 5단계 — 이전에 만든 것과의 연결

이번 통합이 기존 작업과 어떻게 맞물리는지:

| 기존 작업 | LEED/LCA 통합과의 연결 |
|---|---|
| Time-of-week baseline (`build_baselines.py` + 4-tier fallback) | Engineer "Projected" 계산에 6hr avg 사용 — baseline과 비교 가능. Public "vs typical" 라인은 baseline에서 직접 나옴. |
| Meter ID mapping (M3 / M76 / M77) | LEED `meter_end_use_map`이 이 mapping을 LEED end-use 카테고리로 확장. 같은 미터 ID가 양쪽에서 일관성 있게 사용됨. |
| Engineer/Public mode toggle | 두 모드 인프라가 이미 있어서 LEED/LCA 카드도 같은 패턴으로 양쪽에 노출. 새 모드 만들 필요 없음. |
| SCADA-스타일 popup 디자인 | 새 패널이 기존 `pe-sec` / `pe-metric` 클래스를 재사용. 시각적 일관성 유지. |

---

## 6단계 — 다음 단계 (남은 자료 활용)

LCA 패키지에는 아직 활용 안 한 PDF도 있음:

- `v4.1-Building Life-Cycle Impact Reduction.pdf` — LEED 룰북 (참고용)
- `LCA Credit - Structural Reuse.pdf` — SOM의 plan view 도면 (시각화 자료, 추후 popup에 이미지 미리보기로 추가 가능)
- `_archive/Bechtel Center HRE_Final_7-15-2022.pdf` — Historic Resource Evaluation (역사적 평가, 캠퍼스 narrative 강화용)

운영 에너지 쪽도:
- 11개 end-use 중 현재 top 5만 패널에 노출 — 클릭 시 전체 11개 펼치는 인터랙션 추가 가능
- LEED designed 값을 baseline ghost line과 함께 차트에 horizontal line으로 그릴 수도 있음

---

## 생성/수정된 파일

| 파일 | 상태 | 내용 |
|---|---|---|
| `extract_lca.py` | **신규** | LCA xlsx → JSON 추출 스크립트 |
| `data/bechtel_lca.json` | **신규** | 4 elements + totals + LEED 점수 band |
| `grimes-campus-map-arcgis.html` | 수정 | LCA fetch, Engineer Material Reuse 패널, Public LCA 카드, Engineer LEED 패널을 meter-aware로 개선 |

(이전 주 작업: `extract_leed.py`, `data/bechtel_leed.json`, Engineer Design Intent 패널, Public LEED badge)

---

## 발표 한 줄 요약

> "교수님이 보내주신 LEED 자료 두 패키지를 디지털 트윈에 통합했어요. Energy Performance는 modeled vs actual gap을 미터 단위로 보여주는 Engineer 패널 + 'LEED 인증' 한 줄 Public 카드로, Life-Cycle은 'Built on reuse' 카드 + 구조 element별 reuse % bar로. 결과적으로 한 건물 popup 안에서 운영 에너지와 임베디드 카본을 stakeholder 레벨별로 동시에 볼 수 있는 형태가 됐어요."
