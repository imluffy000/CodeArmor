import re

import requests

from app.core.config import GITHUB_TOKEN

GITHUB_PR_URL_RE = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)/?$"
)


def parse_pr_url(pr_url: str) -> dict:
    match = GITHUB_PR_URL_RE.match(pr_url.strip())
    if not match:
        raise ValueError(
            "Invalid GitHub PR URL. Expected: "
            "https://github.com/{owner}/{repo}/pull/{number}"
        )
    return {
        "owner": match.group("owner"),
        "repo": match.group("repo"),
        "pr_number": match.group("number"),
    }


def _validate_github_token() -> None:
    if not GITHUB_TOKEN or GITHUB_TOKEN in ("your_token", "your_github_token"):
        raise ValueError(
            "GITHUB_TOKEN is missing or still set to placeholder in .env"
        )


def fetch_pr_diff(pr_url: str, token: str | None = None) -> str:
    if not token:
        _validate_github_token()
    
    active_token = token or GITHUB_TOKEN
    parsed = parse_pr_url(pr_url)

    api_url = (
        f"https://api.github.com/repos/"
        f"{parsed['owner']}/"
        f"{parsed['repo']}/pulls/"
        f"{parsed['pr_number']}"
    )

    headers = {
        "Authorization": f"Bearer {active_token}",
        "Accept": "application/vnd.github.v3.diff",
    }


    response = requests.get(api_url, headers=headers, timeout=30)

    if response.status_code != 200:
        raise RuntimeError(
            f"GitHub API error ({response.status_code}): {response.text}"
        )

    return response.text
