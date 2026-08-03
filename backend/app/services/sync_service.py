"""Background repo sync: fetches metadata after a repo is first connected.

Runs as an asyncio task spawned from the connect endpoint — the HTTP
request returns immediately while this job updates DB state.
"""
import datetime

from app.core.logging import logger
from app.db.models import Repository, SyncJob
from app.services.crypto_service import decrypt_token
from app.services.github_oauth_service import count_open_prs, fetch_repo


async def run_repo_sync(repo_id: int, job_id: int):
    repo = Repository.get_or_none(Repository.id == repo_id)
    job = SyncJob.get_or_none(SyncJob.id == job_id)
    if repo is None or job is None:
        logger.warning("Sync job %s: repo or job row missing", job_id)
        return

    job.status = "running"
    job.progress = "Fetching repository metadata"
    job.started_at = datetime.datetime.utcnow()
    job.save()
    repo.sync_status = "syncing"
    repo.save()

    try:
        token = decrypt_token(repo.user.access_token_encrypted)

        data = await fetch_repo(token, repo.full_name)
        repo.description = data.get("description")
        repo.language = data.get("language")
        repo.stars = data.get("stargazers_count", 0)
        repo.private = data.get("private", False)
        repo.default_branch = data.get("default_branch", "main")
        repo.html_url = data.get("html_url", repo.html_url)

        job.progress = "Counting open pull requests"
        job.save()
        repo.open_prs = await count_open_prs(token, repo.full_name)

        repo.sync_status = "synced"
        repo.synced_at = datetime.datetime.utcnow()
        repo.save()

        job.status = "completed"
        job.progress = "Sync complete"
        job.finished_at = datetime.datetime.utcnow()
        job.save()
        logger.info("Repo %s synced successfully", repo.full_name)
    except Exception as exc:
        logger.error("Sync failed for repo %s: %s", repo.full_name, exc)
        repo.sync_status = "failed"
        repo.save()
        job.status = "failed"
        job.error = str(exc)
        job.progress = "Sync failed"
        job.finished_at = datetime.datetime.utcnow()
        job.save()
