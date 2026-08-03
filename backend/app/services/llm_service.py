from app.core.logging import logger
from app.models.issue import Issue
from app.utils.helpers import load_prompt, truncate_diff
from app.utils.openrouter_client import llm
from app.utils.parser import parse_llm_json_array


async def review_diff(prompt_name: str, diff: str) -> list[Issue]:
    template = load_prompt(prompt_name)
    prompt = template.format(diff=truncate_diff(diff))
    response = await llm.ainvoke(prompt)

    try:
        items = parse_llm_json_array(response.content)
        return [Issue(**item) for item in items]
    except Exception as exc:
        logger.warning(
            "Failed to parse %s agent response: %s",
            prompt_name,
            exc,
        )
        return []


async def generate_summary_text(
    issue_count: int,
    categories: list[str],
    issues_text: str,
) -> str:
    template = load_prompt("summary")
    prompt = template.format(
        issue_count=issue_count,
        categories=", ".join(categories) or "none",
        issues_text=issues_text or "No issues found.",
    )
    response = await llm.ainvoke(prompt)
    return str(response.content).strip()


async def review_chat(message: str, history: list[dict], issues: list[dict]) -> str:
    # Build context from issues
    issues_summary = []
    for issue in issues:
        file = issue.get("file") or issue.get("path") or "unknown"
        severity = issue.get("severity") or "info"
        category = issue.get("category") or "general"
        problem = issue.get("issue") or issue.get("problem") or "N/A"
        suggestion = issue.get("suggestion") or issue.get("recommendation") or "N/A"
        code_snippet = issue.get("code_snippet") or "N/A"
        suggestion_snippet = issue.get("suggestion_snippet") or "N/A"
        
        issues_summary.append(
            f"File: {file}\n"
            f"Severity: {severity}\n"
            f"Category: {category}\n"
            f"Problem/Issue: {problem}\n"
            f"Recommendation/Suggestion: {suggestion}\n"
            f"Code snippet: {code_snippet}\n"
            f"Suggested fix: {suggestion_snippet}\n"
            f"---"
        )
    issues_text = "\n".join(issues_summary) if issues_summary else "No issues found in this PR."

    system_prompt = (
        "You are an expert AI code reviewer. You have completed reviewing a pull request and the developer is asking you questions.\n"
        "Here are the findings from the automated code review:\n"
        f"{issues_text}\n\n"
        "Answer the developer's questions about the code, the review findings, and suggest fixes. "
        "Use the chat history for context if appropriate. Be concise, precise, and polite. "
        "Keep your responses in clean markdown format.\n"
        "When you provide a code fix, make it COMPLETE and copy-paste ready:\n"
        "- Include any required import statements (e.g. include 'import os' if the fix uses the os module)\n"
        "- Show every line that must change, including all usages affected by the fix, not just one fragment\n"
        "- Present the full corrected function or block in a single fenced code block so it can be applied without guessing context"
    )

    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        role = "assistant" if msg.get("sender") == "ai" else "user"
        messages.append({"role": role, "content": msg.get("text", "")})
    
    messages.append({"role": "user", "content": message})

    response = await llm.ainvoke(messages)
    return str(response.content).strip()

