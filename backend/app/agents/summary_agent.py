from app.services.issue_service import merge_issues
from app.services.llm_service import generate_summary_text
from app.visualizer.folder_tree import build_folder_tree


async def summary_agent(state):
    all_issues = merge_issues(
        state["security_issues"],
        state["quality_issues"],
        state["performance_issues"],
        state["testing_issues"],
        state["architecture_issues"],
    )

    folder_tree = build_folder_tree(all_issues)

    categories = sorted({issue.category for issue in all_issues})
    issues_text = "\n".join(
        f"- [{issue.severity}] {issue.file}: {issue.issue}"
        for issue in all_issues[:20]
    )

    try:
        summary = await generate_summary_text(
            issue_count=len(all_issues),
            categories=categories,
            issues_text=issues_text,
        )
    except Exception:
        summary = (
            f"AI PR Review Completed\n\nTotal Issues Found: {len(all_issues)}"
        )

    return {
        "all_issues": all_issues,
        "folder_tree": folder_tree,
        "final_summary": summary,
    }
