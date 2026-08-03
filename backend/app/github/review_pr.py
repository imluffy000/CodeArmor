from app.github.github_client import (
    github_post
)


def create_pr_review(
    owner,
    repo,
    pr_number,
    body,
    event="REQUEST_CHANGES",
    token=None
):

    url = (
        f"https://api.github.com/repos/"
        f"{owner}/{repo}/pulls/"
        f"{pr_number}/reviews"
    )

    payload = {

        "body": body,

        "event": event
    }

    return github_post(
        url,
        payload,
        token=token
    )