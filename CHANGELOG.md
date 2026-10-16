# Changelog

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
