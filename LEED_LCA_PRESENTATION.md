# LEED + LCA 통합 — 발표 자료 / Presentation Notes

> Bechtel Engineering Center (Grimes Hall) 디지털 트윈에 통합된 LEED 자료 4개 패널 설명.
> Bilingual notes — Korean and English versions of the same content.

---

## 어디서 볼 수 있나 / Where to view

| | URL |
|---|---|
| **메인 지도 (배포)** / Deployed map | https://doe2park.github.io/Graduate-Project/grimes-campus-map-arcgis.html |
| **Before/After Preview** (4 패널 한눈에 / all 4 panels side-by-side) | https://doe2park.github.io/Graduate-Project/leed-lca-preview.html |
| GitHub 레포 / Repo | https://github.com/doe2park/Graduate-Project |

**확인 방법 / How to view in the live map:**
1. 메인 지도 열기 / Open the main map
2. **Grimes (Bechtel) 마커 클릭** / Click the **Grimes / Bechtel** marker
3. 우측 상단 토글로 **Engineer ↔ Public** 모드 전환 / Toggle **Engineer ↔ Public** mode at the top-right

---

## 받은 자료가 뭔지 / What materials were received

교수님이 보내주신 **LEED 제출 자료 두 패키지** — 둘 다 같은 프로젝트 (**Bechtel Engineering Center Addition & Renovation · LEED Project ID #1000171106**). 작성은 SOM (Skidmore, Owings & Merrill, 건축 사무소) + Sage Green Strategies (LEED consultant) 가 2023년 11월에 USGBC 에 제출한 공식 자료.

### 패키지 1 — Energy Performance (운영 에너지)

**핵심 파일**: `20240529_Bechtel_LEEDv4MinEnergyPerfCalc.xlsm`

**[KR]** LEED v4 BD+C 에서 요구하는 **EAp2 (Energy Performance prerequisite)** + **EAc1 (Optimize Energy Performance credit)** 컴플라이언스용 계산서. 이 한 파일에 건물의 운영 에너지 모델 결과가 다 들어있음:
- 11개 end-use 별 (난방, 냉방, 펌프, 팬, 조명, 콘센트, IT, 엘리베이터, 급탕 등)
- 두 시나리오 비교: **ASHRAE 90.1-2010 baseline** (법규 최저) vs **proposed** (eQuest 모델 시뮬레이션한 as-designed 값)
- 각 항목별 연간 kWh + peak kW 동시 제공
- Bechtel 결과: baseline 1,501 MWh/yr → designed 824 MWh/yr = **45% 절약**

**[EN]** The compliance workbook for LEED v4 BD+C's **EAp2 (Energy Performance prerequisite)** + **EAc1 (Optimize Energy Performance credit)**. Contains the building's full operational-energy model:
- 11 end-uses (heating, cooling, pumps, fans, lighting, receptacles, IT, elevators, water heating, etc.)
- Two scenarios compared per end-use: **ASHRAE 90.1-2010 baseline** (code minimum) vs **proposed** (as-designed, simulated in eQuest)
- Annual kWh + peak kW for each
- Bechtel result: baseline 1,501 MWh/yr → designed 824 MWh/yr → **45% modeled savings**

### 패키지 2 — Submittal / Life-Cycle (구조 재사용)

**핵심 파일**: `UCB _LEED_LCA credit.xlsx`
**부속 자료**: `LCA Credit - Structural Reuse.pdf` (SOM 도면), `v4.1-Building Life-Cycle Impact Reduction.pdf` (LEED 룰북), `creditForm.pdf` (제출 양식), 그 외 archive PDF 들

**[KR]** LEED v4.1 BD+C 의 **MR Credit "Building Life-Cycle Impact Reduction" — Option 1, Path 1** (Maintain Existing Structural Elements) 컴플라이언스용. 리노베이션 프로젝트에서 기존 구조를 얼마나 보존했는지 element 별로 정량화:
- 4가지 element: 벽 / 바닥 / 지붕 / 외피
- 각각 (a) 기존 면적, (b) 재사용 면적, (c) 프로젝트 area 제공
- Bechtel 결과: project area 의 **70% 가 기존 구조 재사용** → LEED **4점** (60%+ threshold)
- 특이사항: Bechtel 은 multi-terraced 구조라 floor 와 roof 경계가 모호 → 모두 "floor" 로 처리됨 (제출서에 명시)

**[EN]** Compliance package for the LEED v4.1 BD+C **MR Credit "Building Life-Cycle Impact Reduction" — Option 1, Path 1** (Maintain Existing Structural Elements). Quantifies how much of the existing structure was preserved during the renovation, broken down by element:
- 4 elements: walls / floors / roofs / envelope
- For each: (a) existing area, (b) reused area, (c) project area
- Bechtel result: **70% of project area is reused existing structure** → **LEED 4 points** (60%+ band)
- Note: Bechtel is multi-terraced, so floor/roof distinction is blurry — all reuse counted as "floors" per the submittal

### 발표 시 한 줄 / One-line you can say in the presentation

**[KR]** "교수님께 받은 LEED 자료는 두 패키지인데, 하나는 운영 에너지 (eQuest 모델로 시뮬레이션한 연간 사용량 vs 법규 최저) 고, 다른 하나는 구조 재사용 (리노베이션에서 기존 벽/바닥/외피를 얼마나 살렸는지) 입니다. 둘 다 같은 LEED 프로젝트 #1000171106 의 공식 USGBC 제출 자료예요."

**[EN]** "The materials professor shared are two LEED submittal packages: one is operational energy — the eQuest model's predicted annual usage vs the code baseline — and the other is structural reuse, quantifying how much of the existing walls, floors, and envelope was kept during the renovation. Both are official USGBC submittals for the same project, LEED #1000171106."

---

## 한 줄 요약 / One-line summary

**[KR]** Bechtel 의 LEED 제출 자료 두 패키지 (운영 에너지 + 구조 재사용) 를 BMO 라이브 미터 데이터와 같은 팝업 안에서 비교 가능하게 만들었음. 같은 데이터를 **Engineer 모드 (기술자용 SCADA 패널)** 과 **Public 모드 (방문자용 단순 카드)** 두 추상화 레벨로 동시 노출.

**[EN]** Wired Bechtel's two LEED submittal packages (operational energy + structural reuse) into the same popup as live BMO meter readings. The same data is rendered in two layers: an **Engineer SCADA panel** for facility staff and a **plain-English Public card** for visitors.

---

# 패널 1 / Panel 1 — Material Reuse (Engineer)

**위치 / Location:** Grimes popup → Engineer 모드 → 우측 SCADA 패널 안, MEP 그리드 위

## [KR]
**보여주는 것**: Bechtel 리노베이션이 기존 구조를 얼마나 보존했는지.
- 가운데 **도넛 차트**: 전체 reuse 비율 **69.5%** (project area 기준)
- 아래 **수평 막대**: 70% 기존 유지 / 30% 신축 비율을 공간적으로 표현
- 아래 **element 별 행** (벽/바닥/지붕/외피 아이콘 + 막대):
  - 벽 88%, 바닥 94%, 지붕 N/A (terraced 구조), 외피 98% 보존
- 금색 배지: **LEED v4.1 MR Credit 4점 band** (60%+ threshold 충족)

**의미**: 임베디드 카본 = 새로 만든 콘크리트/철강의 양. 재사용이 높을수록 건물의 "초기 탄소 발자국" 이 작음. 운영 에너지 (사용 단계) 와 별개로 건물 라이프사이클 전체를 평가할 수 있는 지표.

**출처 데이터**: `data/bechtel_lca.json` ← LEED-LCA credit calculator (xlsx) 에서 추출

## [EN]
**What it shows**: How much of the existing Bechtel structure was preserved during renovation.
- Center **donut chart**: Overall reuse rate **69.5%** (of project area)
- Below: **horizontal composition bar** visualizing the 70%-existing / 30%-new split spatially
- Below: **per-element rows** (walls/floors/roofs/envelope icons + bars):
  - Walls 88%, Floors 94%, Roofs N/A (multi-terraced design), Envelope 98% kept
- Gold pill: **LEED v4.1 MR Credit 4-point band** (≥60% threshold met)

**Meaning**: Embodied carbon ≈ the amount of new concrete/steel poured. Higher reuse → smaller upfront carbon footprint. Complements operational-energy metrics by capturing the full building lifecycle.

**Data source**: `data/bechtel_lca.json` ← extracted from the LEED-LCA credit calculator (xlsx).

---

# 패널 2 / Panel 2 — Design Intent vs Actual (Engineer)

**위치 / Location:** Grimes popup → Engineer 모드 → Daily Projection 바로 아래

## [KR]
**보여주는 것**: 설계 모델 예측 vs 법규 최저 기준 vs 실제 라이브 미터.
- **3개 수평 막대** (모두 baseline 에 맞춰 스케일):
  - 회색 = ASHRAE 90.1-2010 code minimum (740 MWh/yr)
  - 금색 = eQuest 모델 설계 예측 (405 MWh/yr)
  - 시안색 = 현재 라이브 미터 6시간 평균 × 8760hr 으로 환산 (188 MWh/yr)
- 큰 **녹색 hero "-54%"**: 설계 의도 대비 현재 사용량 차이 — "지금 더 잘 돌아가고 있다"
- 아래 **end-use 테이블**: 상위 5개 항목 (cooling, fans, pumps, heating 등)

**중요한 디테일**: **미터 인식 (meter-aware) 비교** — M76 (mechanical) 미터 보고 있으면 LEED end-use 중 HVAC/pumps/fans 만 합산해서 비교, M77 (plug+lighting) 이면 lighting/receptacles 만. 단일 sub-meter 를 whole-building 모델과 비교하는 oranges-to-apples 문제 해결.

**의미**: 학계에서 자주 인용되는 **"performance gap"** (modeled vs actual energy use) 를 매 15분 실시간으로 가시화. 보통은 연 1회 utility bill 로 사후 확인하는 것.

**출처 데이터**: `data/bechtel_leed.json` ← LEED Energy Performance calculator (xlsm) 에서 추출. 11개 end-use, eQuest 모델 결과.

## [EN]
**What it shows**: Design model prediction vs code baseline vs live meter readings.
- **Three horizontal bars** (all scaled to the baseline length):
  - Gray = ASHRAE 90.1-2010 code minimum (740 MWh/yr)
  - Gold = eQuest design model prediction (405 MWh/yr)
  - Cyan = current live 6-hr meter average × 8760 hr (188 MWh/yr)
- Large **green hero "-54%"**: gap between live and design intent — "running better than designed"
- Below: **end-use table** with top 5 items (cooling, fans, pumps, heating, etc.)

**Key detail**: **Meter-aware comparison** — when viewing the M76 meter (mechanical), the panel sums only LEED end-uses for HVAC/pumps/fans. When viewing M77 (plug+lighting), it sums lighting/receptacles only. This solves the oranges-to-apples problem of comparing a single sub-meter to a whole-building model.

**Meaning**: Visualizes the academic **"performance gap"** (modeled vs actual energy use) in real time, every 15 minutes — typically this is checked only annually via utility bills.

**Data source**: `data/bechtel_leed.json` ← extracted from the LEED Energy Performance calculator (xlsm). 11 end-uses, eQuest model output.

---

# 카드 3 / Card 3 — LEED v4 Certified (Public)

**위치 / Location:** Grimes popup → Public 모드 → "vs typical" 줄 바로 아래

## [KR]
**보여주는 것**: 같은 LEED 에너지 데이터를 비전공자용으로 단순화.
- **38px 거대한 "45%"** (초록색 + glow)
- 옆에 라벨: "less energy / than code minimum"
- 아래 **두 줄 비교 막대**:
  - "Code min" → 회색 100% 길이
  - "Designed" → 초록 그라데이션 55% 길이
  - 막대 길이 차이로 "절약" 이 시각적으로 보임
- 검정 박스 상태 줄: "Tracking **12% below** design intent right now — running cleaner than planned."

**의미**: 같은 데이터, 다른 추상화. 기술자가 보는 SCADA 패널 (패널 2) 과 동일한 소스에서 나오지만, 일반인에게는 "건물이 법규보다 절반 가까이 적게 쓰도록 설계됐고 실제로도 잘 돌아간다" 한 줄로 전달.

## [EN]
**What it shows**: The same LEED energy data simplified for non-technical viewers.
- **38 px giant "45%"** in green with glow
- Adjacent label: "less energy / than code minimum"
- Below: **two-row comparison bar**:
  - "Code min" → gray bar at 100% length
  - "Designed" → green gradient at 55% length
  - The length difference visually conveys the savings
- Black box status line: "Tracking **12% below** design intent right now — running cleaner than planned."

**Meaning**: Same data, different abstraction. Pulls from the same source as the SCADA panel (Panel 2), but for the public it compresses into a single phrase: "the building was designed to use about half what code requires, and it's running on plan."

---

# 카드 4 / Card 4 — Built on Reuse (Public)

**위치 / Location:** Grimes popup → Public 모드 → LEED 카드 바로 아래

## [KR]
**보여주는 것**: 구조 재사용 데이터를 임베디드 카본 메시지로 단순화.
- **80×78 SVG 건물 단면**:
  - 위 30% 영역 = 회색 빗금 사각형 + "NEW 30%" (신축 부분)
  - 아래 70% 영역 = 진한 테라코타 사각형 + 안에 floor 선 + window 사각형 + "KEPT 70%" (기존 유지)
- 옆에 **30px hero "70%"** (테라코타 색)
- 아래 supporting fact: "**94%** of original floors, / **98%** of envelope kept"

**의미**: "이 건물 = 새로 지은 게 아니라 기존 것을 살려 쓴 거다" 라는 메시지를 한 그림으로 전달. 두 카드 (LEED 카드 + 이 카드) 가 서로 다른 색 (초록 vs 테라코타) 이라서 운영 에너지와 임베디드 카본이 다른 두 sustainability 스토리임을 시각적으로 구분.

## [EN]
**What it shows**: The structural-reuse data compressed into an embodied-carbon message.
- **80×78 SVG building cross-section**:
  - Upper 30% = gray hatched rectangle + "NEW 30%" (new construction)
  - Lower 70% = solid terracotta rectangle with floor lines + window squares + "KEPT 70%" (existing kept)
- Adjacent: **30 px hero "70%"** in terracotta
- Supporting line: "**94%** of original floors, / **98%** of envelope kept"

**Meaning**: One image conveys "this building was preserved, not built fresh." The two Public cards (this one + Panel 3) use different colors (green vs terracotta) to visually separate operational energy and embodied carbon as two distinct sustainability stories.

---

## 데이터 출처 / Data sources

| 파일 / File | 출처 / Source | 추출 스크립트 / Extraction script |
|---|---|---|
| `data/bechtel_leed.json` | LEED v4 EAp2 Energy Performance Calculator (`.xlsm` from professor) | `extract_leed.py` |
| `data/bechtel_lca.json` | LEED v4.1 MR Building Life-Cycle Impact Reduction Credit (`.xlsx` from professor) | `extract_lca.py` |

LEED Project **#1000171106** (UCB Bechtel Engineering Center · Addition & Renovation · SOM architect · Sage Green Strategies LEED consultant)

---

## 왜 의미있나 / Why it matters (research framing)

**[KR]**
1. **Performance gap 가시화**: 학계에서 자주 다루는 modeled-vs-actual energy gap 을 실시간으로 노출 — 기존엔 연 1회 utility bill 분석이 한계.
2. **Meter-aware scoping**: 단순 미터 합 ≠ 전체 건물 모델. 미터 → LEED end-use mapping 을 명시적으로 정의 (`meter_end_use_map`) 해서 비교 정확도 확보.
3. **운영 에너지 + 임베디드 카본 동시 가시화**: 일반 BMS 대시보드는 운영 에너지만 다룸. LCA 데이터를 같이 띄움으로써 건물 라이프사이클 전체를 한 화면에.
4. **Audience-tiered communication**: 같은 데이터에서 Engineer 패널과 Public 카드 동시 생성 — facility manager 와 방문자에게 각자 맞는 추상화 레벨로.

**[EN]**
1. **Performance gap visualization**: Surfaces the modeled-vs-actual energy gap discussed in academic literature, in real time — typically this is only checked via annual utility bill reconciliation.
2. **Meter-aware scoping**: Single-meter totals ≠ whole-building model. By explicitly defining a meter → LEED end-use mapping (`meter_end_use_map`), comparisons stay apples-to-apples.
3. **Operational + embodied carbon together**: A typical BMS dashboard shows only operational energy. Pairing it with LCA data on the same screen captures the building's full lifecycle footprint at once.
4. **Audience-tiered communication**: The same data source generates both an Engineer panel and a Public card simultaneously, offering each stakeholder (facility staff vs visitors) the abstraction level appropriate to them.

---

## 발표 한 줄 요약 / One-line pitch

**[KR]** "교수님이 보내주신 LEED 두 패키지를 디지털 트윈에 통합해서, 건물의 운영 에너지와 임베디드 카본을 한 팝업 안에서 stakeholder 별로 동시 노출할 수 있게 만들었습니다."

**[EN]** "I integrated the two LEED submittal packages into the digital twin so that operational energy and embodied carbon are visible on a single popup, layered for different stakeholders."
