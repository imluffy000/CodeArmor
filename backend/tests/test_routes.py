import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.issue import Issue
from app.models.response_models import ReviewResponse


class TestRoutes(unittest.TestCase):
    def test_home_route_exists(self):
        client = TestClient(app)
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "running")
        self.assertIn("health", data["endpoints"])

    def test_health_route_exists(self):
        client = TestClient(app)
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)

    def test_review_route_success(self):
        client = TestClient(app)
        mock_response = ReviewResponse(
            summary="ok",
            stats={
                "total_issues": 1,
                "files_affected": 1,
                "by_severity": {"LOW": 1},
                "by_category": {"QUALITY": 1},
            },
            files_with_issues=[
                {
                    "path": "a.py",
                    "issue_count": 1,
                    "issues": [
                        {
                            "severity": "LOW",
                            "category": "QUALITY",
                            "problem": "n/a",
                            "recommendation": "n/a",
                        }
                    ],
                }
            ],
            folder_tree={"a.py": []},
            folder_view="📁 Files with issues:\n└── a.py",
            issues=[
                Issue(
                    file="a.py",
                    severity="LOW",
                    category="QUALITY",
                    issue="n/a",
                    suggestion="n/a",
                )
            ],
        )

        with patch(
            "app.api.routes.review_routes.run_pr_review",
            new=AsyncMock(return_value=mock_response),
        ):
            response = client.post(
                "/review",
                json={"pr_url": "https://github.com/acme/repo/pull/1"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["summary"], "ok")


if __name__ == "__main__":
    unittest.main()
