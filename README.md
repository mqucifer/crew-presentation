# crew-presentation

How the crew works, as visuals anyone can read: how each sprint went, and a
story's path from a Goal to merged, played back. Published on GitHub Pages.

The crew is a team of AI agents that delivers software from Goals a person sets.
This site shows its work to people who have never seen it.

## How it works

1. **The data comes as a package.** The crew releases `delivery-history`, a
   dated package of its sprints, cards and events with sprint-metrics' answers
   for each sprint, and opens a pull request here that changes one line:
   [`delivery-history.tag`](delivery-history.tag), the release the site shows.
   How to use the package is in the crew's README:
   [Data packages: how projects use them](https://github.com/mqucifer/crew#data-packages-how-projects-use-them).
2. **Each package is checked against the schema it carries.** CI fetches the
   release the tag names and validates it. A package on a schema major version
   the site can't display fails its pull request; the site never sees it.
3. **Merging the tag publishes the site.** The site is built from its latest
   released version, with the package the tag names, and deployed to Pages.
   Each package carries everything up to its date, so a trend reaches back as
   far as the crew's history. The repository keeps no copy of the data or its
   schemas.

The site shows what sprint-metrics and the crew computed; it doesn't compute
metrics itself. Nothing it publishes carries what the crew was told or thought.

## What the site shows

- **Sprint overview** — one page per sprint: the sprint's figures (stories
  delivered, landed first try, cycle time, points delivered), what changed
  between sprints, the Architect's split story by story, why work didn't land
  first time, and decisions the crew made.
- **Replay** — the crew's work on a day, played back: who did what, and how the
  board moved.
- **Story journey** — a story's life cycle, in detail, from a Goal to merged.

## What's here

- [`docs/design/mock/`](docs/design/mock/): the design reference. Build to it.
- The look comes from [mqucifer/design-system](https://github.com/mqucifer/design-system),
  used as its README says.

The site's code is written by the crew, from the Goals filed on this repository.
