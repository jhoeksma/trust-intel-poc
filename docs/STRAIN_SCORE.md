# Strain score

Status at 20 October 2026: **v0 live; v1 parked** (Jon: "come back to this later"; no change to be made yet).

## Scale
1 to 5, where **5 is the highest strain**: 1 Low, 2 Moderate-low, 3 Moderate, 4 High, 5 Very high. A blank means no NOF data.

## v0 definition (live)
The NHS Oversight Framework adjusted segment (`nof:of5200`) used directly, clamped to 1-5. Segment 1 is the best-performing trusts, segment 4 the worst, so segment N gives strain N. `inputs` on the scorecard records the metric, period and value. Code: `app/indicators.py` (`SEGMENT_CODE`, `strain_from_metrics`).

Distribution on Q1 2026/27 (202 trusts): strain 1: 28, 2: 43, 3: 109, 4: 22, 5: none.

## Known limits of v0
- It is NHS England's performance verdict relabelled, not an independent strain measure.
- Nobody scores 5: the Q1 2026/27 release has no segment 5 (under the earlier framework it meant the Recovery Support Programme). The top of the dashboard scale is "High" for now.
- 109 of 202 trusts sit at 3, so it separates trusts poorly in the middle.
- The 2026/27 framework changed method; scores are not comparable with 2025/26.
- Covers 202 NOF trusts (acute, ambulance, mental health and community); other organisations show "No data".

## v1 idea (parked, not started)
Blend the NOF segment with measures the NOF does not weigh together, all already loaded: 52-week waiters and median/92nd-percentile waits (RTT), estates backlog per m² and share rated high or significant risk (ERIC site), workforce pressure (workforce), finance override flag and rank uncertainty (NOF league table). Keep the NOF segment visible as one input and record every input on the scorecard. Compare against the plain segment to see how the 202 trusts re-rank before adopting. Weights to be agreed with Jon; see D-006 and D-025.

## Recommendation
Do not present v0 to clients as "strain". Use it internally, or label it as the NHS England segment, until v1 exists.
