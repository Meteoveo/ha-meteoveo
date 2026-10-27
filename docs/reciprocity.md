# Reciprocity: give data, get extras

The forecast is **always** available: the conditions now, the next hour, the
hourly and daily forecast and the warnings work for everyone, with or without
a station — and for a station that has gone silent. A silent station's owner
is never worse off than someone who never connected a station.

A station that reports regularly also gives the account **MeteoVeo Plus** —
the paid level of the app and website — for as long as it reports. It follows
the same rules as the station extras below: the 10-minute cadence, the 12-hour
grace window, instant restoration. A subscription is never needed for it, and
losing it is never a penalty: the forecast in Home Assistant is the same either way.

What depends on your station reporting are the **station-specific extras**:
products computed from your own station's readings. Today that is the
best-model verdict (which forecast model performs best at your station).
Your own station's raw data is always yours and is never withheld.

## The rules

- **Expected cadence:** one reading per minute. This is what consumer
  stations report at and what the integration uploads at by default.
- **Maximum spacing:** readings must arrive **at most 10 minutes apart** to
  count as regular reporting. A reading that arrives after a longer gap does
  not count towards your active status — reporting every 11 minutes is
  treated the same as not reporting at all.
- **Grace window:** when your station stops reporting regularly, the extras
  keep flowing for **12 hours**.
- **Reminders:** the account owner is emailed after **1 hour**, **6 hours**
  and at the **12-hour** mark. The 1-hour email distinguishes a station that
  went completely silent from one that still sends, but too sparsely.
- **After 12 hours:** the station-specific extras pause. The
  **Best forecast model** sensor then reads `paused`, with `hours_silent`
  and `grace_hours` as attributes. The forecast, and your station's own
  readings, sensor findings and upload state, stay available the whole time.
- **Restoration is instant:** as soon as two readings arrive no more than
  10 minutes apart, the extras are back — there is no penalty period.

## What this looks like in Home Assistant

The **Station extras remaining** sensor shows how much of the grace window
is left. While your station reports normally it reads the full window; if
uploads stop, it counts down. Its attributes state whether the cadence is
currently considered regular and how long ago the last reading arrived.

## Why the 10-minute rule is strict

A station that reports "roughly hourly" contributes little to nowcasting —
by the time the next reading arrives, the weather it describes has moved on.
The cutoff is deliberately a sharp edge rather than a sliding scale so that
you can reason about it: stay at or under 10 minutes between readings
(the integration's upload interval cannot even be configured beyond that)
and you are always on the right side of it.

## Power cuts and storms

A storm that knocks out your power is also when the weather matters most.
That is one reason the forecast itself never pauses: only the extras that
need your station's own readings wait for it to come back, and they return
the moment it does.
