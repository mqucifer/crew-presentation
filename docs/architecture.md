# crew-presentation - architecture

The system as it is in the code, on 2026-11-12.

Crew Presentation is a static site on GitHub Pages that shows how the crew
works: one page per sprint, one page per story card behind an index of every
card, and a replay page for a sprint's events. There is no server and no
backend. All of the data it shows arrives as a **delivery-history package**
the crew releases; the site validates it against the schema the package
itself carries, renders the pages, and is published to Pages when a merge
names a new package. The repository keeps no copy of the crew's data or of
any schema, and the site shows what its package says - it computes no metric
itself.

## Context

The site serves two readers. Its only data source is the crew: the package
the one line in `delivery-history.tag` names, shipped as a release asset and
updated by the crew opening a pull request that changes that line.
sprint-metrics is upstream of the crew (its answers ride inside every
package); the site never reads it directly.

```mermaid
C4Context
    title Crew Presentation - context

    Person(sponsor, "The Sponsor", "Watches how the crew is going: what got done, how long the steps took, and whether the crew is getting better across sprints")
    Person(visitor, "A public visitor", "Has never seen the crew; reads the same three views in plain language")

    System_Ext(crew, "The crew (mqucifer/crew)", "A team of AI agents that delivers software from Goals; releases dated delivery-history packages of sprints, cards, events, the sprint-metrics answers and their schemas")
    System_Ext(metrics, "sprint-metrics", "Computes the sprint metrics; its answers are embedded by the crew in every package. The site never reads it directly")
    System_Ext(design, "Design system (mqucifer/design-system)", "The look of the site: its stylesheet, pinned once in the site's code at a tag and bumped by pull request")
    System_Ext(pages, "GitHub Pages", "Hosts the built site at mqucifer.github.io/crew-presentation")

    System(site, "Crew Presentation", "A static site: one page per sprint, one page per story card, and a replay page. It shows what its package says; it computes nothing itself")

    Rel(sponsor, site, "reads the sprint overview, the replay and a story's journey")
    Rel(visitor, site, "reads the same three views")
    Rel(crew, site, "ships the delivery-history package the tag names; the site reads the crew's work only through it")
    Rel(metrics, crew, "its answers for each sprint, which the crew embeds in every package")
    Rel(design, site, "styles.css at the pinned tag, which the pages link at read time (served by jsDelivr)")
    Rel(site, pages, "is built and deployed to, and served from")
```

## Containers

The build side lives in this repository; the product is the static site it
publishes. `tools/setup.py` is the only code that touches the network. The
pre-merge gate is `checks.yml`, which runs the checks in the sandbox - the
package's schema major version is refused there, so a package the site cannot
display never reaches a deploy. `deploy.yml` fires after a merge that changes
`delivery-history.tag`: it checks out the latest release tag of the site's
code, points the build at the package the merge named, and publishes to
Pages.

```mermaid
C4Container
    title Crew Presentation - build, checks and the deployed site

    Person(sponsor, "The Sponsor", "Reads the site")
    Person(visitor, "A public visitor", "Reads the site")

    System_Ext(crew, "The crew (mqucifer/crew)", "Releases delivery-history packages as GitHub release assets")
    System_Ext(design, "Design system (mqucifer/design-system)", "Publishes styles.css per tag")
    System_Ext(pages, "GitHub Pages", "Hosts the built site")

    System_Boundary(boundary, "Crew Presentation - this repository") {
        Container(actions, "GitHub Actions", "workflows: checks.yml, deploy.yml", "checks.yml gates every pull request, in the project's sandbox image; deploy.yml builds and publishes after a merge that names a new package, asserting the published pages answer 200")
        Container(setup, "tools/setup.py", "Python", "The only code that touches the network: installs the pinned dependencies, downloads the package named by delivery-history.tag and the design-system CSS at the pinned tag into .package/, retrying a transient download failure a bounded number of times")
        Container(pkg, "The delivery-history package", "JSON data and its schemas", "Fetched into .package/ by setup; named by the one line in delivery-history.tag; holds the sprints, the cards, per-day events, the sprint-metrics answers and the schemas the site validates against")
        Container(buildpy, "build.py", "Python, jinja2, jsonschema", "Validates every data file against the schema the package carries, refuses a schema major version outside SUPPORTED_MAJOR_VERSIONS, renders every page from site/templates, copies site/css and site/js, and assembles the static site in build/")
        Container(templates, "site/templates", "Jinja2", "base.html, the shared layout that links the design-system stylesheet at its pinned jsDelivr URL and the site's own CSS, plus sprint_overview.html, story_journey.html and replay.html")
        Container(checks, "The checks", "Python, pytest, playwright 1.52.0", "test_contracts.py validates the package and its schema major version; test_browser.py drives the built pages in Chromium, serving the design-system CSS from .package/; test_tokens.py runs the site's own contrast and token rules (tools/token_check.py)")
        Container(designcss, "The design-system CSS at its pinned tag", "CSS", "The tag lives in site/css/design-system.version; the same file is fetched by setup into .package/ for the checks and linked by every page at read time")
        Container(sitepages, "The deployed site", "Static HTML, CSS and JavaScript", "What deploy.yml publishes: one page per sprint, a story-journey index and one page per story card, the replay page, a root page that redirects to the newest sprint, site/css/site.css and site/js/replay.js")
    }

    Rel(crew, setup, "the release asset: a tarball at the tag delivery-history.tag names")
    Rel(design, setup, "styles.css at the pinned tag, via jsDelivr")
    Rel(setup, pkg, "downloads and extracts into .package/")
    Rel(setup, designcss, "stores the pinned stylesheet in .package/")
    Rel(pkg, buildpy, "the data: every file validated against the schema the package carries")
    Rel(templates, buildpy, "the layout and the views, rendered per sprint and per card")
    Rel(buildpy, sitepages, "renders and assembles into build/, which the workflow uploads to Pages")
    Rel(checks, pkg, "validates it; an unsupported schema major version fails the pull request")
    Rel(checks, sitepages, "the browser tests load the pages built into build/")
    Rel(checks, designcss, "the token checks run against the fetched stylesheet")
    Rel(actions, setup, "runs it first, in the step that has the network")
    Rel(actions, buildpy, "runs the build")
    Rel(actions, checks, "runs them on every pull request, as the sandbox does")
    Rel(sitepages, pages, "served from, at the site's address")
    Rel(sponsor, sitepages, "reads the sprints, the replay and a story's journey")
    Rel(visitor, sitepages, "reads the same three views")
    Rel(sitepages, designcss, "every page links its stylesheet at the pinned tag, via jsDelivr")
```

## The deployed site, in detail

The three views all extend one shared layout, which opens every page with
the "What this is" orientation, before any measure. The build renders the
opening state of the board into the replay page and embeds the sprint's
events and cards as JSON for the player.

```mermaid
C4Component
    title Crew Presentation - the deployed site, as built on 2026-11-12

    Container(buildpy, "build.py", "Python, jinja2, jsonschema", "Validates the package against the schema it carries, refuses a schema major version outside SUPPORTED_MAJOR_VERSIONS (today 1, 2, 3, 4), renders every page from site/templates, and copies site/css and site/js into build/")
    Container(pkg, "The delivery-history package", "JSON data and its schemas", "Pinned by delivery-history.tag, now delivery-history-2026-11-11 (schema 4.0.0, sprint-metrics release 4.5.0): 48 sprints, the cards, the per-day events (71,142 of them, by the manifest) and sprint-metrics' answers, with prior embedded. The 4.x answer fields (working time, model time and its planning/building split, idle, DORA values, per-story session times) carry values in most sprints and are null in a few")
    Container(designcss, "The design-system CSS at its pinned tag", "CSS", "The look of the site (v0.1.0), served by jsDelivr at read time")

    Container(site, "The deployed site", "Static HTML, CSS and JavaScript on GitHub Pages", "One page per sprint, a story-journey index and one page per story card, the replay page, and a root page that redirects to the newest sprint")

    Component(base, "base.html, the shared layout", "Jinja2", "The header, the top navigation between the views (Sprint, A story's journey, Replay, and 'About the crew', an in-page anchor to the orientation), the theme, the stylesheets, and the 'What this is' orientation section that opens every page before any measure, with no crew term left unexplained")
    Component(overview, "The sprint overview pages", "HTML", "One page per sprint, rendered by build.py from the package; the existing sections (failure causes, 'Decided by the crew') stay as they are")
    Component(headline, "Headline totals and how each measure moved", "HTML", "The sprint's five totals - stories delivered with points, landed first try with the share, start to delivered, filed to delivered, days blocked with what was superseded - every number carrying its unit, and, for each measure that moved, its two numbers with their units and, where the measure has a settled direction, a mark saying better or worse against the previous sprint, from the answer and its embedded prior")
    Component(roster, "The 'What got done' roster card", "HTML", "The sprint's released epics and achieved Goals, from the answer's roster; says so explicitly when a kind has none")
    Component(stories, "What got done, story by story", "HTML", "The sprint's stories grouped under their epics (cards' parent and repo), each with its number, title, attempt blocks, status, working time and model time and a line saying what happened to it; each epic's heading with its done count, times and status; when the package carries analysis, the delivered stories' attempt chart instead")
    Component(rework, "Sent back, and left open at the end", "HTML", "Every send-back from the sprint's sent_back events - which step sent it, back to which, by which rule, when - with the sprint's count, and what was still open at the sprint's end: waiting, blocked and refused, each with how long it has been in that state")
    Component(dora, "The 'How releases went' DORA card", "HTML", "DORA's four measures, each with its unit; 'no value yet' while the package carries no value for a measure")
    Component(wheretime, "Where the time went", "HTML", "The model time split between planning and building as a proportion with both numbers in minutes, and the time with no session running against the sprint's total time; renders absent while the package's fields are null")
    Component(journey, "The story journey pages", "HTML", "A story-journey.html index listing every card, plus one page per card under stories/: the card's repository, number and title, a path strip (refined, built, reviewed, QA, merged, with the stages reached marked), its event timeline, omitting the per-tool and per-turn internal events, and, when the package carries analysis cost data, its developer calls and wall clock")
    Component(replay, "The replay page", "HTML with embedded JSON", "The sprint's board in its opening state, rendered at build time; the sprint's events and cards embedded as JSON for the player")
    Component(js, "site/js/replay.js", "Vanilla JavaScript", "The replay player: play/pause, speed (1x, 30x, 60x), skip-idle, the timeline scrubber, the event ticker, the who's-working panel, and board-state animation driven by the embedded events")
    Component(root, "The root page, index.html", "HTML", "Written by the deploy workflow, not by the build: redirects to the newest sprint's page")
    Component(css, "site/css/site.css", "CSS", "The site's own components - the stats row, the sprint grid, the epic groups, the attempt blocks, the failure-cause bars, the DORA grid, the model-time and idle bars, the orientation block, the journey timeline - design-system tokens only")

    Rel(pkg, buildpy, "the data: every file validated against the schema the package carries")
    Rel(buildpy, site, "renders and assembles into build/, which the workflow publishes")
    Rel(overview, base, "extends")
    Rel(journey, base, "extends")
    Rel(replay, base, "extends")
    Rel(base, designcss, "links its stylesheet at the pinned tag, via jsDelivr")
    Rel(base, css, "links the site's own CSS")
    Rel(root, overview, "redirects to the newest sprint's page")
    Rel(headline, overview, "is the page's totals and trend card")
    Rel(roster, overview, "is the page's roster card")
    Rel(stories, overview, "is the page's central card")
    Rel(rework, overview, "is the page's friction card")
    Rel(dora, overview, "is the page's DORA card")
    Rel(wheretime, overview, "is the page's time card")
    Rel(replay, js, "loads the replay player")
```

## How it is built and deployed

- `delivery-history.tag` is the one line that names the package. The crew
  releases a new package and opens a pull request here that changes that
  line; the repository keeps no copy of the data or of any schema.
- `checks.yml` runs the setup and then the checks the project record names -
  `test_contracts.py`, the build, `test_browser.py` and `test_tokens.py` -
  in the project's sandbox image. The pre-merge gate on the package is
  `test_contracts.py` and `build.py`'s `SUPPORTED_MAJOR_VERSIONS`: a package
  on a schema major version the site cannot display fails its pull request,
  so the site never sees it.
- `deploy.yml` runs only on `main`, after a merge that changed
  `delivery-history.tag`. It checks out the latest release tag of the site's
  code, overwrites the tag file with the merged one, runs setup and the
  build, writes a root page that redirects to the newest sprint, uploads
  `build/`, deploys to Pages, and asserts the root and the named pages
  answer 200.
- The design system is pinned once, in `site/css/design-system.version`, and
  bumped by pull request. It reaches the site two ways: the browser links
  `styles.css` at that tag via jsDelivr at read time, and setup fetches the
  same file into `.package/` so the token and browser checks run without a
  network.
- `board.yml` also lives in this repository but is not part of the site's
  pipeline: it moves the cards this repository's own board holds that no
  crew role moves, which the crew's recorded events - and so the site - see.

## Where the build differs from the target

The diagram above starts from the Goal's target diagram and is corrected to
what the code shows on 2026-11-12. The code differs from the target in these
places:

- **The pinned package.** The target names `delivery-history-2026-11-04`
  (schema 3.0.0, sprint-metrics 4.2.1, 41 sprints, 58,170 events). The code's
  `delivery-history.tag` pins `delivery-history-2026-11-11` instead: schema
  4.0.0, sprint-metrics release 4.5.0, 48 sprints, and 71,142 events by the
  manifest.
- **The version gate.** The target says the gate refuses a schema major
  version outside 1, 2, 3. The code's `SUPPORTED_MAJOR_VERSIONS` is
  `(1, 2, 3, 4)` in both `build.py` and `test_contracts.py`; a 4.0.0 package
  passes the gate, which is how the pinned package builds.
- **The 4.x answer fields.** The target records them as null or empty in
  every sprint, which was true of the package it named. In the pinned
  `delivery-history-2026-11-11` package they carry values in most sprints
  (working time, model time and its planning/building split, idle, DORA,
  per-story session times), and are null in a few. `prior` is null for seven
  of the 48 sprints, and the package carries no `analysis` section, so the
  build takes its fallback paths: the epic-grouped story list from the
  cards, "What changed" from the answer's embedded prior, and "Decided by
  the crew" from events and cards.
- **The orientation block.** The target draws "What this is" as its own
  element that "opens the sprint page before any measure". The build has it
  as a section of `base.html`, the shared layout: it opens every page
  (sprint, journey and replay) before any measure, and the navigation's
  "About the crew" item is an in-page anchor to that section, not a separate
  view. The diagram folds it into the shared layout rather than carrying it
  as a separate component.
- **Two sprint-page cards the target's component list omits.** The "What got
  done" roster card (the sprint's released epics and achieved Goals, from the
  answer's roster) and the "How releases went" DORA card (DORA's four
  measures, "no value yet" while the package carries no value for a
  measure). Both predate the Goal; the diagram adds them as components.
- **"What changed" lines.** The target says a line for each measure against
  the previous sprint. The build gives a line only to a measure that moved
  (one equal to its prior, or null on either side, gets none), and the
  better/worse mark appears only where a measure has a settled direction -
  the six headline measures; "Stories superseded" shows its two numbers
  without a direction word.
- **The journey pages carry more than the event timeline.** The target names
  only "the card's repository, number and title and its event timeline".
  Each card page also carries a path strip (refined, built, reviewed, QA,
  merged, with the stages reached marked) and a "What it cost" block
  (developer calls, wall clock) when the package carries analysis cost data,
  and the timeline omits the per-tool and per-turn internal events. The view
  also has an index page, `story-journey.html` (the navigation's "A story's
  journey"), listing every card; the per-card pages live under `stories/`.
- **The target's diagram omits the replay player.** The build ships
  `site/js/replay.js`, which the replay page loads and which drives
  play/pause, the speed control, skip-idle, the timeline scrubber, the event
  ticker, the who's-working panel and the board animation.

The boards in `docs/design/mock/` are the design reference to build to; they
are not part of the system.
