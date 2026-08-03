from app.visualizer.review_output import build_files_with_issues, build_folder_view


def generate_review_message(issues, folder_tree: dict | None = None) -> str:
    if not issues:
        return "✅ **AI PR Review**\n\nNo issues found. LGTM."

    files = build_files_with_issues(issues)

    message = "# AI PR Review\n\n"
    message += f"**Total issues:** {len(issues)} across **{len(files)}** file(s)\n\n"

    if folder_tree:
        message += "## Folder view\n\n```\n"
        message += build_folder_view(folder_tree)
        message += "\n```\n\n"

    message += "## Issues by file\n\n"

    for file_group in files:
        message += f"### `{file_group['path']}` ({file_group['issue_count']} issue(s))\n\n"
        for idx, item in enumerate(file_group["issues"], 1):
            message += (
                f"{idx}. **[{item['severity']}] {item['category']}**\n"
                f"   - **Problem:** {item['problem']}\n"
                f"   - **Recommendation:** {item['recommendation']}\n\n"
            )

    return message
