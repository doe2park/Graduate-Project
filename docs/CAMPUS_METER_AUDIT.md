# Campus meter audit (BMO), October 23–24, 2026

Source: Building Manager Online, client "UC Berkeley", AcquiSuite Inventory (131 loggers) and each
logger's device list, read on 2026-10-24. Configuration lives in `BUILDINGS` in `bmo_fetch_campus.py`;
each entry records the BMO meter names it uses (`basis`) and any caveat (`note`).

## Rules
- Use the logger BMO lists under the building's name (the "New (as of …)" logger when an older one stopped).
- Use only meters BMO names as building mains. Exclude submeters, PV generation, EV chargers, cell sites,
  fire pumps and other buildings' meters on the same logger.
- Device #250 pulse channels are used only by exact column name (`pulse`), e.g. Stanley "Main # 1–4 Demand".
- A building with no identifiable main meter shows "no reading" rather than a guessed value.

## Included: 94 buildings
37 previously listed buildings (corrected) plus 57 added on 2026-10-24.

## Not included (and why)
| Logger(s) | Reason |
|---|---|
| 2000 Carleton St, 2222/2224/2240 Piedmont Ave, 2251 College Ave, 2537 Haste St, Anna Head E&F | Street-address properties outside the core campus |
| 2232 Piedmont Ave New | Campus feeder / cogeneration / LBL meters, not a building |
| Alumni House, Cal Memorial Stadium (Water & Steam), Haas Cheit Hall (Water), Haas Student Services (Water) | No electric meter |
| McCone Hall, SRB1 & Oxford Tract, Edwards Stadium East/West | Main meter ambiguous in BMO names |
| Tang Center (last upload Jul 10 2026) and loggers silent for years (Tolman, Art Museum, King Union, old Cory/Soda/Tan/Koshland/LSA/Silver/Wurster/Boalt/University Hall, etc.) | Not uploading |
| UC Berkeley Housing client (21 loggers) | Residence halls, not campus buildings |

## Open questions for Facilities
- Cory Hall: only panel submeters (5A1–5B8) are in BMO; which meter is the building main?
- Soda Hall: are device #250 Electric Main #1 and #2 separate services (safe to sum)?
- Grimes: is roof meter #3 separate from the 480 V meter #76?
- Evans Hall and Valley Life Sciences: do the switchgear / electric-room meters cover the whole building without overlap?
- Moffitt Library: main meter #76 is in Alarm status; University Hall logger silent since Oct 27 2023.
