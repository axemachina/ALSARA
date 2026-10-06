"""Deploy ALSARA code to the HuggingFace Space.

Usage:
    ./venv/bin/python deploy.py [commit message]

Uploads only code files (.py, .md, .txt, config) — skips chroma_db/, venv/,
__pycache__/, .claude/, internal notes, and logs. The Space's existing
chroma_db stays intact; runtime updates to it flow through the separate
HF Dataset repo via chroma_sync.py.

Requires an HF token with WRITE scope on the Space, from either:
  - HF_TOKEN in .env (same variable chroma_sync.py uses), or
  - a cached login (~/.cache/huggingface/token) via `hf auth login`.
A fine-grained token scoped only to the chroma Dataset repo is NOT enough —
it also needs write on the Space itself.
"""

import sys
from dotenv import load_dotenv
from huggingface_hub import HfApi

# HF_TOKEN lives in .env alongside the rest of the project's secrets
# (chroma_sync.py uses the same variable). .env is gitignored and matches
# no ALLOW_PATTERNS below, so it is never uploaded to the Space.
load_dotenv()

REPO_ID = "axegameon/ALSARA"
REPO_TYPE = "space"

ALLOW_PATTERNS = [
    "*.py",
    "servers/*.py",
    "shared/**/*.py",
    "*.md",
    "*.txt",
    ".gitignore",
    ".gitattributes",
    ".env.example",
]

IGNORE_PATTERNS = [
    "chroma_db/**",
    "__pycache__/**", "**/__pycache__/**",
    "venv/**", ".venv/**",
    ".claude/**", ".git/**",
    "NOTES.md", "TODO.md", "implementation_plan.md",
    "claude.md", "CLAUDE.md",  # agent instructions; the Space is public
    "app.log", "*.log",
    "archive/**", "flagged/**",
    "deploy.py",
]


def main() -> int:
    msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Deploy from local"
    api = HfApi()
    api.upload_folder(
        folder_path=".",
        repo_id=REPO_ID,
        repo_type=REPO_TYPE,
        commit_message=msg,
        allow_patterns=ALLOW_PATTERNS,
        ignore_patterns=IGNORE_PATTERNS,
    )
    print(f"Deployed to https://huggingface.co/spaces/{REPO_ID}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
