import unittest
import unittest.mock

from app.github.fetch_pr import parse_pr_url
from app.services.diff_parser_service import parse_diff_files, summarize_diff
from app.visualizer.folder_tree import build_folder_tree
from app.visualizer.review_output import build_files_with_issues, build_structured_review
from app.models.issue import Issue


class TestGithub(unittest.TestCase):
    def test_parse_pr_url(self):
        parsed = parse_pr_url("https://github.com/acme/repo/pull/42")
        self.assertEqual(parsed["owner"], "acme")
        self.assertEqual(parsed["repo"], "repo")
        self.assertEqual(parsed["pr_number"], "42")

    def test_parse_pr_url_rejects_invalid(self):
        with self.assertRaises(ValueError):
            parse_pr_url("https://github.com/acme/repo")

        with self.assertRaises(ValueError):
            parse_pr_url("https://gitlab.com/acme/repo/-/merge_requests/1")

    def test_summarize_diff(self):
        diff = (
            "diff --git a/src/a.py b/src/a.py\n"
            "+++ b/src/a.py\n"
            "+added line\n"
            "-removed line\n"
        )
        summary = summarize_diff(diff)
        self.assertIn("src/a.py", parse_diff_files(diff))
        self.assertEqual(summary["added_lines_count"], 1)
        self.assertEqual(summary["removed_lines_count"], 1)

    def test_folder_tree_keeps_multiple_issues_per_file(self):
        issues = [
            Issue(
                file="a.py",
                severity="HIGH",
                category="SECURITY",
                issue="one",
                suggestion="s1",
            ),
            Issue(
                file="a.py",
                severity="LOW",
                category="QUALITY",
                issue="two",
                suggestion="s2",
            ),
        ]
        tree = build_folder_tree(issues)
        self.assertEqual(len(tree["a.py"]), 2)
        self.assertIn("recommendation", tree["a.py"][0])

    def test_structured_review_output(self):
        issues = [
            Issue(
                file="src/api.py",
                severity="HIGH",
                category="SECURITY",
                issue="Missing auth",
                suggestion="Add authentication middleware",
            ),
        ]
        tree = build_folder_tree(issues)
        out = build_structured_review("Summary text", issues, tree)

        self.assertEqual(out["stats"]["total_issues"], 1)
        self.assertEqual(out["files_with_issues"][0]["path"], "src/api.py")
        self.assertEqual(
            out["files_with_issues"][0]["issues"][0]["recommendation"],
            "Add authentication middleware",
        )
        self.assertIn("src", out["folder_view"])

    @unittest.mock.patch("app.services.review_service.fetch_pr_diff")
    @unittest.mock.patch("app.services.review_service.parse_diff_files")
    @unittest.mock.patch("app.services.review_service.graph.ainvoke")
    @unittest.mock.patch("app.services.review_service.create_pr_review")
    def test_run_pr_review_handles_github_post_failure(
        self, mock_create, mock_ainvoke, mock_parse, mock_fetch
    ):
        import asyncio
        from app.services.review_service import run_pr_review

        mock_fetch.return_value = "dummy diff"
        mock_parse.return_value = []
        mock_ainvoke.return_value = {
            "final_summary": "Summary text",
            "all_issues": [],
            "folder_tree": {},
        }
        mock_create.side_effect = Exception("Resource not accessible by personal access token")

        response = asyncio.run(run_pr_review("https://github.com/acme/repo/pull/42"))

        self.assertEqual(response.summary, "Summary text")
        self.assertEqual(response.github_error, "Resource not accessible by personal access token")


if __name__ == "__main__":
    import unittest.mock
    unittest.main()
