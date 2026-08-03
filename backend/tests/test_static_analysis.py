import tempfile
import unittest
from pathlib import Path

from app.static_analysis.shared.detector import scan_repository_languages
from app.static_analysis.shared.registry import get_tools_for_languages


class TestStaticAnalysis(unittest.TestCase):
    def test_scans_mixed_language_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "backend").mkdir()
            (repo / "backend" / "main.py").write_text("print('hello')\n")
            (repo / "frontend").mkdir()
            (repo / "frontend" / "package.json").write_text("{}\n")
            (repo / "frontend" / "app.tsx").write_text("export default null\n")
            (repo / "database").mkdir()
            (repo / "database" / "migration.sql").write_text("select 1;\n")

            languages = scan_repository_languages(str(repo))

        self.assertEqual(languages, {"python", "javascript", "typescript", "sql"})

    def test_tool_selection_deduplicates_shared_language_tools(self):
        tools = get_tools_for_languages({"javascript", "typescript"})

        self.assertEqual([tool.name for tool in tools], ["semgrep", "eslint"])

    def test_tool_selection_includes_language_specific_and_common_tools(self):
        tools = get_tools_for_languages({"python", "java", "csharp", "sql"})

        self.assertEqual(
            [tool.name for tool in tools],
            ["semgrep", "roslyn", "spotbugs", "bandit", "pylint", "sqlfluff"],
        )


if __name__ == "__main__":
    unittest.main()
