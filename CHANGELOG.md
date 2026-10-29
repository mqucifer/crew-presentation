# Changelog

## [Unreleased]

### Fixed

- The sprint overview's stats row rendered the programming literal "None" when sprint-metrics reports null for a sprint with no delivered stories; it now renders an em dash (—) for missing values (mqucifer/crew-presentation#176)
- The story-journey root page rendered two h1 headings and an empty content area; it now renders a single h1 in the header and a list of story links in the content (mqucifer/crew-presentation#176)

## [Unreleased]

### Added

- The story's journey page shows the path through the board's stages: a strip of five steps (Refined, Built, Reviewed, QA, Merged) with the stage colours when the story was delivered (mqucifer/crew-presentation#100)

## [Unreleased]

### Fixed

- Story pages load the site stylesheet: the CSS link now uses a path correct for the stories/ subdirectory (mqucifer/crew-presentation#176)

## [Unreleased]

### Fixed

- The trend card's value lines show human-readable measure names for all measures (throughput, blocked_aging_days, superseded_count, crew_fixes_merged, wip_violations), not just those already in the label map (mqucifer/crew-presentation#176)

## [Unreleased]

### Fixed

- Unknown failure-cause codes (such as 'REVIEW' or 'QA') now display as "Cause not recorded" instead of the raw code (mqucifer/crew-presentation#176)

## [Unreleased]

### Fixed

- The attempt chart's rows now match the first-attempt stat: the number of rows equals the stat's denominator, and the 'first try' badge appears on exactly the stat's numerator rows, even when the cards array is missing entries for some stories (mqucifer/crew-presentation#176)

## [0.1.2] - 2026-10-17

Goal mqucifer/crew-presentation#100: every sprint page tells one consistent story, on a phone or a laptop.

### Changed

- The cycle-time stat reads in hours and minutes, not days, so a one-day sprint no longer shows "0 days" (mqucifer/crew-presentation#119)
- The trend card's time measures read in hours and minutes (mqucifer/crew-presentation#120)
- The trend card names each measure in words, not by its field name (mqucifer/crew-presentation#146)
- The failure causes read in words, such as "A test's assertion failed", not as the crew's codes (mqucifer/crew-presentation#147)

### Added

- Each row of the attempt chart links to that story's journey page (mqucifer/crew-presentation#130)
- Checks that the page agrees with itself: the cycle-time stat matches the trend card (mqucifer/crew-presentation#127), the lead time matches the package (mqucifer/crew-presentation#128), and the attempt chart's rows match the first-attempt stat (mqucifer/crew-presentation#129)

### Fixed

- On a phone: the main sections stack (mqucifer/crew-presentation#121), the attempt chart's rows fit (mqucifer/crew-presentation#122), the failure-cause labels fit (mqucifer/crew-presentation#123), the stats row wraps (mqucifer/crew-presentation#124), and the nav links are large enough to tap (mqucifer/crew-presentation#125)

## [0.1.1] - 2026-10-16

### Fixed

- On a phone, every page rendered at desktop width, shrunk to fit. Pages now fit the screen they're on (mqucifer/crew-presentation#98)

### Added

- The deploy workflow: a merged change to `delivery-history.tag` builds the site from the latest release tag with the package it names, and publishes it to GitHub Pages (mqucifer/crew-presentation#74)

## [0.1.0] - 2026-10-15

The first release: the site that Goal mqucifer/crew-presentation#10 builds, deployed from this tag.

### Added

- `build.py` validates the delivery-history package against the schema it carries, checks its major version, and writes the site to `build/` (mqucifer/crew-presentation#73)
- One sprint-overview page per sprint, with a navigation strip between them (mqucifer/crew-presentation#77)
- The sprint overview's header and big numbers: throughput, points, first-attempt rate, escalations and cycle time, in the design system's light and dark themes (mqucifer/crew-presentation#79)
- The attempt chart: each story's attempts, story by story, with a legend (mqucifer/crew-presentation#80)
- The trend card: what changed from the sprint before, on each sprint page (mqucifer/crew-presentation#78)
- The failure-causes bar chart, from sprint-metrics' answers in the package (mqucifer/crew-presentation#81)
- The crew-decisions panel: what the crew decided in the sprint, with timestamps (mqucifer/crew-presentation#82)
- A browser test that loads the sprint overview page and checks the package's data appears on it (mqucifer/crew-presentation#83)
- Contrast and token checks: every colour in the site's CSS comes from a design-system token, and every text-on-background pair meets 4.5:1 in both themes (mqucifer/crew-presentation#84)
