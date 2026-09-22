"""Static-analysis runners - deliberately NOT wired into the review pipeline.

These wrap bandit, pylint, semgrep, eslint, SpotBugs, Roslyn and sqlfluff, and
`shared.registry.run_static_analysis` selects the right ones for a repository's
languages. They are good code with a real design, and they are not called by the
review pipeline, on purpose.

The reason: a static analyser needs a checkout, and CodeArmor never clones the
pull request. The previous wiring pointed the runners at a server-side
`STATIC_ANALYSIS_ROOT` directory, so it analysed *the CodeArmor server's own
source tree* and attributed the findings to the user's pull request - then
offered to post them to that repository, leaking the server's file layout and
source into a third party's repo. Findings also carried absolute host paths.

To turn this on properly:

1. Clone the PR head into a temp directory (`git clone --depth 1`, then
   `git checkout <head_sha>`), inside a sandbox with no network and a timeout.
2. Call `run_static_analysis(<that temp dir>)`.
3. Filter findings to files that appear in the PR diff, and rewrite the absolute
   paths to repository-relative ones.
4. Map them through `visualizer.issue_mapper` and merge them into the review.

Until that exists, the runners stay importable and tested, and the pipeline does
not pretend to run them.
"""
