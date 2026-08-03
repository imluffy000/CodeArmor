import unittest
from unittest.mock import AsyncMock, patch

from app.agents.summary_agent import summary_agent
from app.models.issue import Issue


class TestAgents(unittest.TestCase):
    def test_summary_agent_merges_issues(self):
        state = {
            "security_issues": [
                Issue(
                    file="a.py",
                    severity="HIGH",
                    category="SECURITY",
                    issue="x",
                    suggestion="y",
                )
            ],
            "quality_issues": [],
            "performance_issues": [],
            "testing_issues": [],
            "architecture_issues": [],
        }

        async def run():
            with patch(
                "app.agents.summary_agent.generate_summary_text",
                new=AsyncMock(return_value="Done"),
            ):
                return await summary_agent(state)

        import asyncio

        result = asyncio.run(run())
        self.assertEqual(len(result["all_issues"]), 1)
        self.assertEqual(result["final_summary"], "Done")


if __name__ == "__main__":
    unittest.main()
