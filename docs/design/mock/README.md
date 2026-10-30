# The design reference

The Sponsor's picture of the site, drawn on 2026-09-29 and restyled with
[mqucifer/design-system](https://github.com/mqucifer/design-system) v0.1.0.
Build to it: the pages should look and read like these boards.

Open any board in a browser. Each is one self-contained HTML file, with the
design system's styles inlined so it renders on its own. The site itself pins the
design system by version instead.

## The boards

| Board | What it shows | For |
|---|---|---|
| [sprint-overview.html](sprint-overview.html) | A sprint as the crew ran it: totals, the split story by story with each attempt, why work didn't land first time, and what the crew decided on its own | Goal 1 |
| [sprint-overview-2.html](sprint-overview-2.html) | The sprint overview after delivery-history 2.0.0, at 1280px and 375px: what this is, the sprints in date order, the totals with no escalations, what changed with each line's numbers in its sentence's units, the stories by epic with time worked and model time, why work didn't land first time and what sent it back in plain words, what was left open, what the crew decided, and what the data can't show yet. Its values are the 2.0.0 mock's Sprint 6 | the overview Goal (2026-10-30) |
| [big-numbers.html](big-numbers.html) | Three styles for the large stat values. **C, Public Sans**, is the chosen one: bold, tabular figures, -0.01em letter spacing | Goal 1 |
| [replay.html](replay.html) | A Goal to merged, played back: play and pause, 1×, 30× and 60×, skip idle, a timeline marking merges, blocks, crew fixes and design decisions, the board as it stood, who's working, and a ticker of events | Goal 2 |
| [replay-dark.html](replay-dark.html) | The same replay in the dark theme: the same markup, with the dark tokens | Goal 2 |
| [story-journey.html](story-journey.html) | One card's timeline, what it cost, and the pattern behind it | Goal 2 |
| [model-settings.html](model-settings.html) | First-try rate, attempts and reasoning tokens for each model setting | Later: the performance project, not a Goal here yet |

## What comes from the design system, and what is the site's own

- **The design system's components:** the header, cards, stats, the stage path,
  status badges, replay events, the agents list and the feature panel.
- **The site's own:** the scrubber, the speed control, the board columns and the
  attempt chart. They become design-system components if a second page needs them.

## The data on the boards is illustrative

The numbers and cards are taken from real sprints (Sprint 6, Sprint 10, and the
night of 25 September), to make the boards believable. The site shows what its
package says, never these values. Some placeholders were left unfilled, such as
`[AVG]` and `[TOTAL]`.

Nothing here carries what the crew was told or thought: only summaries,
card numbers, file names and refusal messages. The site keeps to the same rule.
