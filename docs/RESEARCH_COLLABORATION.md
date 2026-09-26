# Research collaboration guide

Updated September 25, 2026. [Project overview and demonstrations](../README.md)

## Research focus

The proposed contribution is evidence-aware integration of site appearance, BIM identity and operational data for existing buildings with incomplete information. Reconstruction is one component, not the research claim by itself.

A proposed evaluation compares photo-based navigation against reconstruction-assisted navigation, holding BIM and operating data constant. Candidate outcomes are equipment-location accuracy, task completion time, and unsupported conclusions. These benefits have not yet been established by a completed study.

## A short review path

1. Open the campus map and energy dashboard for the building-level context.
2. Inspect a BIM element and distinguish design properties, meter context and modelled allocations.
3. Compare the same location in Scan ↔ BIM. Check the capture date and alignment status.
4. Read the [raw-video reconstruction note](RAW_VIDEO_RECONSTRUCTION.md) for the separate local SfM/Gaussian experiment.
5. Use the [JSON guide](DATA_SHARING.md) to identify the appropriate dataset for analysis.

## Useful collaboration questions

- Which facility-management tasks would genuinely benefit from linked site views, BIM objects and operating observations?
- What independent landmarks/check points and tolerances are appropriate for the intended task?
- Which equipment schedules, panel/circuit records and BAS point lists can support verified object-to-data links?
- How should measured, modelled, inferred and missing information be displayed to prevent false confidence?
- What participant groups, baseline interface and task set would make the proposed evaluation credible?

## Current boundaries

The public viewer is a research prototype, not an automated control system or certified inspection tool. Element-level consumption, complete circuit membership, reliable hidden-service detection, surveyed registration and implemented clash detection are not claimed. The September public capture and the independent September raw-video pilot are different pipelines.

## Suggested sharing message

> Here is my Campus Digital Twin research repository: https://github.com/doe2park/Graduate-Project
>
> The README links to the public demonstrations and explains the data sources, BIM element identities, registration methods and current limitations. It also distinguishes the deployed photo/mesh comparison from the local SfM and Gaussian reconstruction experiments. I would particularly appreciate feedback on useful facility-management tasks, validation requirements and the proposed user evaluation. The full Revit property JSON can be shared separately if needed.
