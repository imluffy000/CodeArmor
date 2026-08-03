import requests

from app.core.config import GITHUB_TOKEN


def _headers():
    if not GITHUB_TOKEN or GITHUB_TOKEN in ("your_token", "your_github_token"):
        raise ValueError(
            "GITHUB_TOKEN is missing or still set to placeholder in .env"
        )
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }


def github_post(url, payload, token=None):
    if token:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }
    else:
        headers = _headers()

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=30,
    )


    if response.status_code >= 300:

        raise Exception(
            f"GitHub API Error: {response.text}"
        )

    return response.json()