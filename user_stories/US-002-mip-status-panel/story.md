# US-002 — MiP status panel

**As a** developer testing control rules on the MiP,
**I want** the dashboard to show the robot's current state at a glance — battery, connection, position, volume, game mode, odometer, versions —
**so that** I can see the effect of my commands and catch problems (low battery, robot fallen over, link dropped) without reading the raw log.

Builds on US-001 (same page, same connection). The connection *indicator* from US-001 is extended here into a full status panel.

## Decisions and assumptions

Battery threshold and session trend were decided on 2026-09-21 after a balancing
test: the MiP reported 47–55 % all along, never sagged under load, yet fell over
within ~1 s every time while the position flipped between "face down" and
"on back" several times per second. A slow decline (0x67 → 0x64 in 15 min idle)
was the only hint in the numbers — hence the trend view. The remaining rows are
assumptions.

| Topic | Decision / assumption |
|---|---|
| Battery warning | **Decided:** red bar and warning icon below **40 %** (not 20 %) — the MiP fails to balance long before the indicator looks empty. |
| Session trend | **Decided:** the panel keeps every polled battery value and every position change since connect and shows them as a small time chart, so slow battery decline and balance wobble (rapid position flips) are visible. |
| Placement | A fixed panel at the top of the dashboard, visible regardless of scroll position. |
| Refresh | Values that need a query (status, odometer, volume, game mode) are polled every 5 s while connected; a "Refresh now" button forces an immediate poll. Polling pauses while a hold-to-drive button is held so it does not compete with the 50 ms drive stream. |
| Events | Values reported by unsolicited notifications (position changes, clap, gesture, radar) update the panel immediately when they arrive, in addition to the poll. |
| Battery | Shown as a percentage derived from the raw 0x4D–0x7C range, plus a bar (see warning threshold above). |
| Signal | RSSI from the scan is shown at connect time; it is not re-measured while connected (bleak does not expose live RSSI on all platforms). |
| Versions | Software and hardware version are queried once at connect and not polled. |
| Mock MiP | The mock answers all status queries with fixed values and lets tests inject position/battery changes. |

## Status fields

| Field | Source opcode | Display |
|---|---|---|
| Connection | link state | "Disconnected" / "Connecting…" / "Connected to \<name\>" + address |
| Signal | scan RSSI | dBm with a 0–4 bar icon |
| Battery | 0x79 | percentage + bar, red below 40 % |
| Position | 0x79 | text: on back / face down / upright / picked up / hand stand / face down on tray / on back with kickstand |
| Session trend | 0x79 history | time chart of battery % and position since connect; "position changes in last 5 s" counter, highlighted above 5 (balance wobble). **Superseded by US-007**, which turns this into one lane per sensor with a checkbox filter. |
| Volume | 0x16 | 0–7 |
| Game mode | 0x82 | app / cage / tracking / dance / default / stack / trick / roam |
| Odometer | 0x85 | cm since last reset, with "Reset" button |
| Chest LED | 0x83 | colour swatch |
| Head LEDs | 0x8B | four dots off / on / blinking |
| Gesture/radar mode | 0x0D | off / gesture / radar |
| Clap detection | 0x1F | enabled / disabled + delay |
| Software / hardware version | 0x14 / 0x19 | text |
| Last update | local clock | "updated 3 s ago" |

## Out of scope

- Persisting the trend across sessions or exporting it.
- Alerts outside the browser (sound, notifications).
