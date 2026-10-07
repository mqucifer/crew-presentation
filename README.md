# crew-presentation

How the crew works, as visuals anyone can read: how each sprint went, and a
story's path from a Goal to merged, played back. Published on GitHub Pages.

The crew is a team of AI agents that delivers software from Goals a person sets.
This site shows its work to people who have never seen it.

## How it works

1. **The data comes in by pull request.** At its cadence, the crew asks the
   sprint-metrics service for its metrics, exports its own replay feed, and opens
   a pull request here with both as a JSON snapshot.
2. **Each snapshot is checked against its contract.** sprint-metrics publishes
   JSON Schemas for its answers, and the crew publishes one for its replay feed.
   A snapshot that doesn't match fails its pull request; the site never sees it.
3. **Merging a snapshot publishes the site.** The site is built from its latest
   released version, with every snapshot it has been sent, and deployed to Pages.
   Snapshots stay in the repository, so a trend reaches back as far as the data.

The site shows what sprint-metrics computes; it doesn't compute metrics itself.
Nothing it publishes carries what the crew was told or thought.

## What's here

- [`docs/design/mock/`](docs/design/mock/): the design reference. Build to it.
- The look comes from [mqucifer/design-system](https://github.com/mqucifer/design-system),
  pinned by its release tag. Pages link its tagged stylesheet from jsDelivr; it isn't
  a package on PyPI or npm.

The site's code is written by the crew, from the Goals filed on this repository.
