"""Sync chroma_db to/from a private HuggingFace Dataset repo.

Used to make the RAG snapshot durable across HF Spaces restarts and
portable back to local dev. All failures are swallowed and logged —
sync never raises into the agent loop.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _hf_hub():
    """Import huggingface_hub lazily so a missing dep can't crash the server."""
    try:
        from huggingface_hub import snapshot_download, upload_folder
        return snapshot_download, upload_folder
    except ImportError as e:
        logger.warning(f"huggingface_hub not installed, sync disabled: {e}")
        return None, None


def download_latest(repo_id: str, dest: Path, token: Optional[str]) -> bool:
    """Pull the latest snapshot of a Dataset repo into `dest`.

    Returns True if at least one file was downloaded. False on any failure
    (missing repo, bad token, network error). Destination is created if missing.
    """
    snapshot_download, _ = _hf_hub()
    if snapshot_download is None:
        return False
    try:
        dest.mkdir(parents=True, exist_ok=True)
        # snapshot_download returns the local path it wrote to
        downloaded = snapshot_download(
            repo_id=repo_id,
            repo_type="dataset",
            local_dir=str(dest),
            token=token,
        )
        # Sanity check: did we get the key files?
        sqlite = dest / "chroma.sqlite3"
        if sqlite.exists() and sqlite.stat().st_size > 0:
            logger.info(f"Downloaded chroma_db from {repo_id} to {dest}")
            return True
        logger.info(f"Dataset {repo_id} is empty (no chroma.sqlite3)")
        return False
    except Exception as e:
        logger.warning(f"Failed to download from {repo_id}: {type(e).__name__}: {e}")
        return False


def upload_snapshot(
    repo_id: str,
    src: Path,
    token: Optional[str],
    commit_message: Optional[str] = None,
) -> bool:
    """Push the contents of `src` to the Dataset repo.

    Uploads the whole folder to the root of the repo. Returns True on success.
    """
    _, upload_folder = _hf_hub()
    if upload_folder is None:
        return False
    if not src.exists():
        logger.warning(f"Cannot upload — {src} does not exist")
        return False
    try:
        msg = commit_message or f"chroma_db snapshot {datetime.utcnow().isoformat(timespec='seconds')}Z"
        upload_folder(
            repo_id=repo_id,
            repo_type="dataset",
            folder_path=str(src),
            path_in_repo=".",
            token=token,
            commit_message=msg,
        )
        logger.info(f"Uploaded chroma_db ({_human_size(src)}) to {repo_id}")
        return True
    except Exception as e:
        logger.warning(f"Failed to upload to {repo_id}: {type(e).__name__}: {e}")
        return False


def _human_size(path: Path) -> str:
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    for unit in ("B", "KB", "MB", "GB"):
        if total < 1024:
            return f"{total:.1f}{unit}"
        total /= 1024
    return f"{total:.1f}TB"


def seed_from_committed(src: Path, dest: Path) -> bool:
    """Copy the git-committed chroma_db snapshot as a fallback seed."""
    if not src.exists():
        logger.warning(f"No committed seed at {src}")
        return False
    try:
        dest.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            target = dest / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)
        logger.info(f"Seeded chroma_db from committed snapshot {src} → {dest}")
        return True
    except Exception as e:
        logger.warning(f"Failed to seed from {src}: {type(e).__name__}: {e}")
        return False


def is_populated(path: Path) -> bool:
    """Check whether a chroma_db directory has a usable sqlite file."""
    sqlite = path / "chroma.sqlite3"
    return sqlite.exists() and sqlite.stat().st_size > 0
