# Changelog

## [Unreleased]

### Added

- The sprint overview now shows a "What got done" section listing the sprint's released epics and achieved Goals from the package's roster; when a kind has none, it says so explicitly (mqucifer/crew-presentation#279)
- The site accepts delivery-history packages on schema major 3 (e.g. 3.0.0); major 3 is now in SUPPORTED_MAJOR_VERSIONS (mqucifer/crew-presentation#266)
- The sprint overview's "Decided by the crew" panel now lists design-revision merges and technical epics filed during the sprint, derived from events and cards, when the package carries no analysis `decided` list for that sprint; when analysis is present the panel shows the analysis entries as before (mqucifer/crew-presentation#266)
- The sprint overview now shows DORA's four measures (release frequency, lead time for changes, change failure rate, mean time to recovery) in a "How releases went" card; when the package carries no DORA data for the sprint, the card shows "no release data for this sprint" (mqucifer/crew-presentation#279)

### Changed

- The sprint overview's story list now falls back to the cards' own fields when the package carries no analysis: cards with status "Done" and matching sprint are shown as delivered stories (excluding those closed as "not_planned"), each linking to its story page; the attempt chart's blocks, status and legend are absent in this case, and when no card qualifies the section shows "No stories were delivered this sprint" (mqucifer/crew-presentation#266)
- The sprint overview's "What changed" section now shows how each measure moved from the prior sprint, derived from the sprint-metrics answers' `prior` field, when the package carries no analysis `changed` list for that sprint; when `prior` is null the section is absent (mqucifer/crew-presentation#266)
- The story's journey page now shows the path strip's stages as reached when the package carries no analysis for the card and the card's own status is "Done" with closed_as "completed"; when the card is not in that state, no stage is marked reached. The "What it cost" section remains absent without analysis cost data (mqucifer/crew-presentation#266)

### Fixed

- The replay page's title and h1 were byte-identical to the sprint overview's (both showed the sprint name alone), making the two pages indistinguishable in a browser tab; the replay page now carries its own identifying title "Sprint N · Replay" (mqucifer/crew-presentation#279)

## [0.3.2] - 2026-10-31

### Fixed

- The story's journey timeline printed raw internal event kind codes (e.g. `gate_checked`, `tool_call`, `session_turn`) verbatim and showed one row per model call, making it unreadable at ~150 rows; per-tool-call and per-turn internals (`model_call`, `tool_call`, `session_turn`, `session_compacted`) are now omitted, and every remaining event kind is mapped to a readable sentence (mqucifer/crew-presentation#252)
- The sprint overview's "The Architect's split, story by story" section now shows "No stories were delivered this sprint" instead of an orphaned legend when a sprint delivered zero stories (mqucifer/crew-presentation#252)
- Story-detail pages and sprint pages overflow past 375px at phone width when a card title is a long unbreakable string or the sprint carries wide data; card titles, analysis text, timeline text, failure-cause labels, decision text and trend text now wrap with `overflow-wrap: break-word`, and the phone grid columns use `minmax(0, 1fr)` so they can shrink below their content's minimum width (mqucifer/crew-presentation#248)
- The story journey page's timeline now shows the calendar date (e.g. "Oct 2, 02:58") when a story's events span more than one day, so multi-day stories read in the correct chronological order rather than appearing to run backwards (mqucifer/crew-presentation#252)
- The sprint overview's "Sprint totals" row rendered four stats in a five-column grid, leaving an empty track to the right of the last stat after the escalations stat was dropped in v0.3.0; the desktop grid now uses four equal columns so the stats span the content width (mqucifer/crew-presentation#252)

## [0.3.1] - 2026-10-30

### Fixed

- The replay page's board overflows past 375px at phone width when a card title contains a long unbreakable word; the board column now uses `minmax(0, 1fr)` and cards wrap long words with `overflow-wrap: anywhere` (mqucifer/crew-presentation#246)

## [0.3.0] - 2026-10-30

### Added

- The story's journey page now shows a "What happened, in order" timeline of the story's recorded events (timestamps and column moves) and a "What it cost" section with developer calls and wall-clock time, drawn from the package's events and analysis (mqucifer/crew-presentation#223)
- The site accepts delivery-history packages on schema major 2 (e.g. 2.0.0); major 2 is now in SUPPORTED_MAJOR_VERSIONS (mqucifer/crew-presentation#215)

### Changed

- The sprint overview no longer shows an escalations stat or an escalation entry in the "What changed" card; sprint-metrics' escalation_count and escalation_rate_percent are dropped from the displayed figures (mqucifer/crew-presentation#211)
- The "Why work didn't land first time" chart now reads a 2.0.0 package's top_failure_causes (a list of {class, role, count}) and shows each entry's class and count, instead of rendering every row as "Cause not recorded"; 1.x map shapes and empty/absent causes still build unchanged (mqucifer/crew-presentation#211)

### Fixed

- The story pages' "A story's journey" and "Replay" header nav links were relative paths that resolved to non-existent files under stories/; they now use a prefix so they resolve to the root-level pages (mqucifer/crew-presentation#223)
- The story-journey root page scrolls horizontally at phone widths when card titles are long; story list links now wrap with `overflow-wrap: break-word` (mqucifer/crew-presentation#223)
- The "Sprint" nav link on non-sprint pages (replay, story-journey, and every story under stories/) had an empty href, so it only reloaded the current page; it now links to the newest sprint's overview page (mqucifer/crew-presentation#223)
- The sprint overview's cycle-time stat now renders an em dash (—) when sprint-metrics reports no value, consistent with the other four stats on that row (mqucifer/crew-presentation#223)
- The replay page's board columns rendered at unconstrained width on a phone, causing sideways scroll; the board now stacks in one column (mqucifer/crew-presentation#223). A long unbroken word in a card title can still overflow (mqucifer/crew-presentation#246)
- The replay page's board cards now render their reference as a real hyperlink (repo#number as the visible label, the issue URL as the href) instead of printing the literal markdown link text (mqucifer/crew-presentation#223)

## [0.2.0] - 2026-10-30

### Added

- The story's journey page shows the path through the board's stages: a strip of five steps (Refined, Built, Reviewed, QA, Merged) with the stage colours when the story was delivered (mqucifer/crew-presentation#100)

### Fixed

- The sprint overview's story rows now show each story's own pattern from the package (first try, retried, crew fix, etc.) instead of assigning badges by position to match the first-attempt stat; stories are listed by their delivery date within the sprint's days, not cut to the stat's denominator (mqucifer/crew-presentation#193)
- The sprint overview's stats row rendered the programming literal "None" when sprint-metrics reports null for a sprint with no delivered stories; it now renders an em dash (—) for missing values (mqucifer/crew-presentation#176)
- The story-journey root page rendered two h1 headings and an empty content area; it now renders a single h1 in the header and a list of story links in the content (mqucifer/crew-presentation#176)
- Story pages load the site stylesheet: the CSS link now uses a path correct for the stories/ subdirectory (mqucifer/crew-presentation#176)
- The trend card's value lines show human-readable measure names for all measures (throughput, blocked_aging_days, superseded_count, crew_fixes_merged, wip_violations), not just those already in the label map (mqucifer/crew-presentation#176)
- Unknown failure-cause codes (such as 'REVIEW' or 'QA') now display as "Cause not recorded" instead of the raw code (mqucifer/crew-presentation#176)
- The sprint navigation strip now shows each sprint's start date beside its name, so the list reads as chronology even when sprint numbers are non-sequential (mqucifer/crew-presentation#176)

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
