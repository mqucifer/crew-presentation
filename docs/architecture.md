# crew-presentation - architecture

The system as it is in the code, on 2026-10-28.

Crew Presentation is a static site on GitHub Pages that shows how the crew
works: one page per sprint, one page per story card, and a page for a
sprint's events. There is no server and no backend. All of the data it shows
arrives as a **delivery-history package** the crew releases; the site
validates it against the schema the package itself carries, renders the
pages, and is published to Pages when a merge names a new package. The
repository keeps no copy of the crew's data or of any schema, and the site
shows what its package says - it computes no metric itself.

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
        Container(setup, "tools/setup.py", "Python", "The only code that touches the network: installs the pinned dependencies, downloads the package named by delivery-history.tag and the design-system CSS at the pinned tag into .package/")
        Container(pkg, "The delivery-history package", "JSON data and its schemas", "Fetched into .package/ by setup; named by the one line in delivery-history.tag; holds the sprints, the cards, per-day events, the sprint-metrics answers and the schemas the site validates against")
        Container(buildpy, "build.py", "Python, jinja2, jsonschema", "Validates every data file against the schema the package carries, refuses a schema major version outside SUPPORTED_MAJOR_VERSIONS, renders every page from site/templates, and assembles the static site in build/")
        Container(templates, "site/templates", "Jinja2", "base.html, the shared layout that links the design-system stylesheet at its pinned jsDelivr URL and the site's own CSS, plus sprint_overview.html, story_journey.html and replay.html")
        Container(checks, "The checks", "Python, pytest, playwright 1.52.0", "test_contracts.py validates the package and its schema major version; test_browser.py drives the built pages in Chromium, serving the design-system CSS from .package/; test_tokens.py runs the site's own contrast and token rules (tools/token_check.py)")
        Container(designcss, "The design-system CSS at its pinned tag", "CSS", "The tag lives in site/css/design-system.version; the same file is fetched by setup into .package/ for the checks and linked by every page at read time")
        Container(sitepages, "The deployed site", "Static HTML, CSS and JavaScript", "What deploy.yml publishes: one page per sprint, one page per story card, the replay page, a root page that redirects to the newest sprint, site/css/site.css and site/js/replay.js")
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

The three views all extend one shared layout. The build renders the opening
state of the board into the replay page and embeds the sprint's events and
cards as JSON; the player that would animate them is not built yet.

```mermaid
C4Component
    title The deployed site - what the browser loads

    Container(site, "The deployed site", "Static HTML, CSS and JavaScript on GitHub Pages", "Built from the delivery-history package the tag names")

    Component(base, "base.html, the shared layout", "Jinja2, rendered at build time", "Header and navigation between the three views, the theme, the design-system stylesheet link at its pinned jsDelivr URL, and the site's own CSS")
    Component(overview, "The sprint overview pages", "HTML", "One per sprint: the sprint's totals, the attempt chart story by story, the measures that changed, why work did not land first time, and what the crew decided")
    Component(journey, "The story journey pages", "HTML", "One per story card: the card's repository, number and title; the journey itself is not drawn yet")
    Component(replay, "The replay page", "HTML with embedded JSON", "The sprint's board in its opening state, rendered at build time; the sprint's events and cards are embedded as JSON for the player")
    Component(root, "The root page, index.html", "HTML", "Written by the deploy workflow, not by the build: redirects to the newest sprint's page")
    Component(css, "site/css/site.css", "CSS", "The site's own components: the stats row, the sprint grid, the attempt chart, the failure-cause bars, the board columns; design-system tokens only, no raw colours")
    Component(js, "site/js/replay.js", "Vanilla JavaScript", "A placeholder as of 2026-10-28: the player (play, pause, speed, skip-idle, the scrubber, the ticker) is not built yet")

    System_Ext(designcss, "The design-system CSS", "Pinned at a tag in the site's code, served by jsDelivr")

    Rel(overview, base, "extends")
    Rel(journey, base, "extends")
    Rel(replay, base, "extends")
    Rel(base, css, "links the site's own CSS")
    Rel(base, designcss, "links its stylesheet at the pinned tag, via jsDelivr")
    Rel(replay, js, "loads the player, which is a placeholder")
    Rel(root, overview, "redirects to the newest sprint's page")
```

## How it is built and deployed

- `delivery-history.tag` is the one line that names the package. The crew
  releases a new package and opens a pull request here that changes that
  line; the repository keeps no copy of the data or of any schema.
- `checks.yml` runs `tools/setup.py` and then the three checks in the
  project's sandbox image. The pre-merge gate on the package is
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

## What is not there yet

As of 2026-10-28 the code does not yet have:

- The replay player. `site/js/replay.js` is a placeholder; the replay page
  shows the board's opening state, rendered at build time, with the
  sprint's events and cards embedded as JSON for the player.
- The story's journey. The journey pages carry only the card's repository,
  number and title.
- The timeline, event-ticker and who's-working sections on the replay
  page: they are empty containers, awaiting the player.

The boards in `docs/design/mock/` are the design reference to build to; they
are not part of the system.
