# The daily rain probability

The percentage in the daily forecast answers one question: **how likely is it
that at least 0.2 mm of rain falls that day** at your place.

It is MeteoVeo's own figure. It comes from the rain **amount** we expect for
the day, matched against our own verified history — how often that much
expected rain has actually turned into measurable rain. That is why it is
**not the same number** as the percentage in AEMET's municipal forecast,
which is what we use for the daily maximum and minimum temperature and for
the sky condition.

## Why two days in a row can show the same percentage

Because the figure follows the expected amount rather than the calendar: two
days whose expected rain is similar get the same probability. Three days
reading the same percentage is the method working as intended, not a value
that got stuck.

## What the percentage does not say

- **Not how much.** That is the `precipitation` figure next to it, in
  millimetres.
- **Not a share of the day or of the area.** 60 % means that of days with
  this much expected rain, about six in ten end with at least 0.2 mm
  measured somewhere at the place.
- **Not a threshold for "a wet day".** 0.2 mm is a measurable trace, not a
  downpour; a day can be 80 % likely to see rain and still see very little
  of it.

## Where you see it

In Home Assistant it is the `precipitation_probability` field of the daily
forecast of `weather.meteoveo_<town>` (the service `weather.get_forecasts`
returns), and the percentage in the daily list of the MeteoVeo card. The
same figure is what the MeteoVeo app and website show.
