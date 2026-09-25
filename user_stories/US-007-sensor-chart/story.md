# US-007 — Time chart of the sensors, with a checkbox filter

**As a** developer testing control rules on the MiP,
**I want** a time chart of every available sensor next to the status panel, with
checkboxes to pick which ones are shown,
**so that** I can see how the robot's values move together over time — battery
sagging while the motors pull, the position flipping while it tries to balance —
instead of reading single numbers.

Replaces the small trend chart from US-002, which only ever showed battery and
position markers.

## Decisions (from refinement interview, 2026-09-25)

| Topic | Decision |
|---|---|
| Layout | **One lane per sensor**, stacked, each with its own scale and a shared time axis. Readable no matter how different the ranges are. |
| Sampling | **1 s while the chart is open**, and only for the sensors that are ticked; otherwise the existing 5 s status poll. Still paused while a hold-to-drive is active. |
| Non-numeric sensors | Shown as **coloured state bands** — each state a bar over the time it lasted, so balance wobble and mode changes are obvious at a glance. Selectable like any other. |
| Persistence | None. A 60-minute window in the browser, cleared on reconnect, as today. |

## What can be charted

| Lane | Source | Kind |
|---|---|---|
| Battery % | `0x79` | line, 0–100, red below 40 |
| Position | `0x79` | state band (7 states, the colours the status panel already uses) |
| Odometer | `0x85` | line, auto-scaled; rises monotonically |
| Weight / tilt | `0x81` | line, −128…127 — the one sensor fast enough to show balancing |
| Volume | `0x16` | line, 0–7 |
| Game mode | `0x82` | state band |
| Radar | `0x0C` event | state band (no object / 10–30 cm / < 10 cm) |
| Gesture | `0x0A` event | markers on a band |
| Claps | `0x1D` event | markers with the count |
| Chest LED | `0x83` | band in the actual colour |
| Head LEDs | `0x8B` | four thin bands |

Events arrive on their own; the rest come from the poll, so a lane's resolution
is the poll interval, not finer.

## Sampling — the part that needs care

`Hub._poll_loop` currently asks for a fixed set (`POLL_OPCODES`) every 5 s. This
story adds a second, faster cadence driven by what the page has ticked:

- the page tells the server which sensors are charted (a WebSocket message or a
  small POST), and the hub polls exactly those at 1 s;
- nothing is charted, or no page is open → back to 5 s and the usual set;
- the hold-to-drive hold-off stays: a 1 s poll must not compete with the 40 ms
  drive stream, or the robot stutters;
- `Get weight` (`0x81`) is not polled at all today and has to be added — it is
  also the only lane where 1 s is arguably still too slow to show a fall.

Each extra polled sensor is one more request/response per second over a link
that is already marginal at −80 dBm. The story therefore polls **only what is
ticked**, rather than everything at the faster rate.

## Out of scope

- Saving or exporting the history (decided against for now; a CSV button is the
  obvious follow-up if the battery question comes back).
- Zooming and panning the time axis; the window is the last 60 minutes.
- Charting anything from a running block program beyond the sensors above.
- Server-side recording without a browser.

## Acceptance criteria

See `sensor-chart.feature`.
