"""Background repository sync.

Runs as an in-process asyncio task, which has two consequences the code has to
handle rather than hope about: the event loop only weakly references a bare
task (so it can be collected mid-flight), and a container restart abandons it
with the job row still reading "running". `track_task` fixes the first;
`database._reconcile_interrupted_jobs` fixes the second at startup.

For more than one instance this belongs in a real queue - see the README.
"""
import asyncio
import datetime

from app.core.logging import logger
from app.db.models import Repository, SyncJob
from app.github import client as gh
from app.services.crypto_service import TokenDecryptionError, decrypt_token

# Strong references to in-flight tasks.
_running: set[asyncio.Task] = set()


def track_task(task: asyncio.Task) -> asyncio.Task:
    _running.add(task)
    task.add_done_callback(_on_task_done)
    return task


def _on_task_done(task: asyncio.Task) -> None:
    _running.discard(task)
    if task.cancelled():
        return
    exception = task.exception()
    if exception:
        logger.error("Background sync task failed: %s", exception, exc_info=exception)


async def cancel_running_tasks() -> None:
    """Called on shutdown so jobs are marked interrupted rather than vanishing."""
    for task in list(_running):
        task.cancel()
    if _running:
        await asyncio.gather(*list(_running), return_exceptions=True)


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


async def run_repo_sync(repo_id: int, job_id: int) -> None:
    repo = Repository.get_or_none(Repository.id == repo_id)
    job = SyncJob.get_or_none(SyncJob.id == job_id)
    if repo is None or job is None:
        logger.warning("Sync job %s: repository or job row is missing", job_id)
        return

    job.status = "running"
    job.progress = "Fetching repository metadata"
    job.started_at = _utcnow()
    job.save()
    repo.sync_status = "syncing"
    repo.save()

    try:
        token = decrypt_token(repo.user.access_token_encrypted)

        data = await gh.fetch_repo(token, repo.full_name)
        repo.description = data.get("description")
        repo.language = data.get("language")
        repo.stars = data.get("stargazers_count", 0)
        repo.private = data.get("private", False)
        repo.default_branch = data.get("default_branch", "main")
        repo.html_url = data.get("html_url", repo.html_url)

        job.progress = "Counting open pull requests"
        job.save()

        open_prs = await gh.count_open_prs(token, repo.full_name)
        if open_prs is None:
            # None means GitHub would not tell us - usually the search API's
            # separate rate budget. Keeping the previous number is honest;
            # writing 0 would look like a successful sync of an empty repo.
            logger.info("Open PR count unavailable for %s; keeping previous value", repo.id)
        else:
            repo.open_prs = open_prs

        repo.sync_status = "synced"
        repo.synced_at = _utcnow()
        repo.save()

        job.status = "completed"
        job.progress = (
            "Sync complete" if open_prs is not None else "Sync complete (PR count unavailable)"
        )
        job.finished_at = _utcnow()
        job.save()
        logger.info("Repository %s synced", repo.id)

    except asyncio.CancelledError:
        job.status = "failed"
        job.progress = "Interrupted"
        job.error = "The server shut down before the sync finished. Try again."
        job.finished_at = _utcnow()
        job.save()
        repo.sync_status = "failed"
        repo.save()
        raise

    except TokenDecryptionError:
        logger.warning("Sync %s failed: stored token could not be decrypted", job_id)
        _fail(repo, job, "Your GitHub authorization needs to be renewed. Sign in again.")

    except gh.GitHubError as exc:
        logger.warning("Sync failed for repository %s: %s", repo.id, exc)
        _fail(repo, job, exc.safe_message)

    except Exception:
        logger.exception("Sync failed unexpectedly for repository %s", repo.id)
        _fail(repo, job, "Sync failed. Try connecting the repository again.")


def _fail(repo: Repository, job: SyncJob, message: str) -> None:
    """Record a client-safe message. Upstream text can name private repositories."""
    repo.sync_status = "failed"
    repo.save()
    job.status = "failed"
    job.error = message
    job.progress = "Sync failed"
    job.finished_at = _utcnow()
    job.save()
