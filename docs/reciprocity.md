# Reciprocity: give data, get data

MeteoVeo is built on a simple exchange: **stations that contribute readings
get the derived products back** — forecasts, the best-model recommendation,
nowcasts. Your own station's raw data is always yours and is never withheld.

## The rules

- **Expected cadence:** one reading per minute. This is what consumer
  stations report at and what the integration uploads at by default.
- **Maximum spacing:** readings must arrive **at most 10 minutes apart** to
  count as regular reporting. A reading that arrives after a longer gap does
  not count towards your active status — reporting every 11 minutes is
  treated the same as not reporting at all.
- **Grace window:** when your station stops reporting regularly, derived
  data keeps flowing for **12 hours**.
- **Reminders:** the account owner is emailed after **1 hour**, **6 hours**
  and at the **12-hour** mark. The 1-hour email distinguishes a station that
  went completely silent from one that still sends, but too sparsely.
- **After 12 hours:** requests for derived data are answered with an
  explanatory error instead of data. Your own station's readings remain
  fully accessible the whole time.
- **Restoration is instant:** as soon as two readings arrive no more than
  10 minutes apart, access is restored — there is no penalty period.

## What this looks like in Home Assistant

The **Forecast access remaining** sensor shows how much of the grace window
is left. While your station reports normally it reads the full window; if
uploads stop, it counts down. The sensor's attributes state whether the
cadence is currently considered regular and how long ago the last reading
arrived.

## Why the 10-minute rule is strict

A station that reports "roughly hourly" contributes little to nowcasting —
by the time the next reading arrives, the weather it describes has moved on.
The cutoff is deliberately a sharp edge rather than a sliding scale so that
you can reason about it: stay at or under 10 minutes between readings
(the integration's upload interval cannot even be configured beyond that)
and you are always on the right side of it.

## Power cuts and storms

The 12-hour window consciously accepts one hard case: a storm that knocks
out your power is also the moment the forecasts are most interesting. Twelve
hours covers the typical outage; restoration is instant once the station is
back.
