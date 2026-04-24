#!/usr/bin/env python3
"""
LlamaIndex MCP Server for Research Memory and RAG
Provides persistent memory and semantic search capabilities for ALS Research Agent

This server enables the agent to remember all research it encounters, build
knowledge over time, and discover connections between papers.
"""

from mcp.server.fastmcp import FastMCP
import logging
import os
import json
import hashlib
from typing import Optional, List, Dict, Any
from pathlib import Path
import sys
from datetime import datetime
import asyncio

# Add parent directory to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared import config

# Configure logging — force=True overrides any root handler installed by FastMCP/anyio
# at import time. Without force=True the basicConfig call is a no-op and INFO logs
# from this module never surface in the Space log output.
logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)

# Initialize MCP server
mcp = FastMCP("llamaindex-rag")

# Import LlamaIndex components (will be installed)
try:
    from llama_index.core import (
        VectorStoreIndex,
        Document,
        StorageContext,
        Settings,
        load_index_from_storage
    )
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.vector_stores.chroma import ChromaVectorStore
    import chromadb
    LLAMAINDEX_AVAILABLE = True
except ImportError as e:
    LLAMAINDEX_AVAILABLE = False
    logger.warning(f"LlamaIndex core not installed: {e}. Install with: pip install llama-index-core llama-index-vector-stores-chroma chromadb")

# HuggingFace embeddings are optional — we prefer fastembed (lightweight, no PyTorch).
# This import is only needed as a fallback when USE_FASTEMBED=false.
HUGGINGFACE_EMBEDDINGS_AVAILABLE = False
try:
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    HUGGINGFACE_EMBEDDINGS_AVAILABLE = True
except ImportError:
    HuggingFaceEmbedding = None  # type: ignore

# Try fastembed (lightweight, no PyTorch needed — 68MB vs 469MB)
FASTEMBED_AVAILABLE = False
try:
    from fastembed import TextEmbedding as FastTextEmbedding
    FASTEMBED_AVAILABLE = True
except ImportError:
    pass

# Configuration
_default_chroma_path = "./chroma_db"
_hf_tmp_chroma_path = "/tmp/chroma_db"

# Sync config — reading here so both path resolution and manager init share the values
CHROMA_SYNC_REPO = os.getenv("CHROMA_SYNC_REPO", "").strip()
HF_TOKEN = os.getenv("HF_TOKEN", "").strip() or None
CHROMA_SYNC_BATCH_SIZE = int(os.getenv("CHROMA_SYNC_BATCH_SIZE", "5"))

logger.info(
    "Chroma sync config: SPACE_ID=%s, CHROMA_DB_PATH=%s, CHROMA_SYNC_REPO=%s, HF_TOKEN=%s, batch_size=%d",
    bool(os.environ.get("SPACE_ID")),
    os.getenv("CHROMA_DB_PATH", "(unset)"),
    CHROMA_SYNC_REPO or "(unset)",
    "set" if HF_TOKEN else "(unset)",
    CHROMA_SYNC_BATCH_SIZE,
)


def _resolve_chroma_path() -> str:
    """Resolve ChromaDB path and bootstrap it.

    Priority:
      1. CHROMA_DB_PATH env (used on HF Spaces with Persistent Storage, e.g. /data/chroma_db)
      2. On HF Spaces without CHROMA_DB_PATH: /tmp/chroma_db (ephemeral legacy path)
      3. Local dev: ./chroma_db (git-committed seed, unchanged)

    Bootstrap on Spaces (paths 1 and 2): if the resolved directory is empty, try
    to pull the latest snapshot from the HF Dataset repo; fall back to the
    git-committed seed at ./chroma_db.
    """
    # Import inside the function so a missing dep in chroma_sync can't crash server import
    sys.path.insert(0, str(Path(__file__).parent.parent))
    try:
        import chroma_sync
    except ImportError:
        chroma_sync = None

    configured = os.getenv("CHROMA_DB_PATH", "").strip()
    on_hf_space = bool(os.environ.get("SPACE_ID"))

    if configured:
        target = Path(configured)
    elif on_hf_space:
        target = Path(_hf_tmp_chroma_path)
    else:
        # Local dev: use the committed snapshot in-place
        return _default_chroma_path

    # We're on Spaces (either /data or /tmp). Make sure target is populated.
    target.mkdir(parents=True, exist_ok=True)

    if chroma_sync is not None and chroma_sync.is_populated(target):
        logger.info(f"Using existing chroma_db at {target}")
        return str(target)

    # Empty — try Dataset first, then git seed
    if chroma_sync is not None and CHROMA_SYNC_REPO and HF_TOKEN:
        logger.info(f"chroma_db at {target} is empty — attempting Dataset restore from {CHROMA_SYNC_REPO}")
        if chroma_sync.download_latest(CHROMA_SYNC_REPO, target, HF_TOKEN):
            return str(target)

    # Fallback: seed from git-committed snapshot
    if chroma_sync is not None:
        seed = Path(_default_chroma_path)
        if chroma_sync.seed_from_committed(seed, target):
            return str(target)

    logger.warning(f"chroma_db at {target} is empty and no fallback worked — starting fresh")
    return str(target)


CHROMA_DB_PATH = _resolve_chroma_path()
EMBED_MODEL = os.getenv("LLAMAINDEX_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
USE_FASTEMBED = os.getenv("USE_FASTEMBED", "true").lower() == "true"
CHUNK_SIZE = int(os.getenv("LLAMAINDEX_CHUNK_SIZE", "1024"))
CHUNK_OVERLAP = int(os.getenv("LLAMAINDEX_CHUNK_OVERLAP", "200"))

# Global index storage
research_index = None
chroma_client = None
collection = None
papers_metadata = {}  # Store paper metadata separately


if LLAMAINDEX_AVAILABLE:
    from llama_index.core.embeddings import BaseEmbedding

    class FastEmbedEmbedding(BaseEmbedding):
        """LlamaIndex-compatible wrapper for fastembed (no PyTorch, 6x smaller)."""

        model_name: str = "BAAI/bge-small-en-v1.5"

        def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", **kwargs):
            super().__init__(model_name=model_name, **kwargs)
            self._ft_model = None

        def _ensure_model(self):
            if self._ft_model is None:
                self._ft_model = FastTextEmbedding(self.model_name)

        def _get_text_embedding(self, text: str) -> list:
            self._ensure_model()
            return list(self._ft_model.embed([text]))[0].tolist()

        def _get_text_embeddings(self, texts: list) -> list:
            self._ensure_model()
            return [e.tolist() for e in self._ft_model.embed(texts)]

        def _get_query_embedding(self, query: str) -> list:
            return self._get_text_embedding(query)

        async def _aget_query_embedding(self, query: str) -> list:
            return self._get_text_embedding(query)


class ResearchMemoryManager:
    """Manages persistent research memory using LlamaIndex and ChromaDB"""

    def __init__(self):
        self.index = None
        self.chroma_client = None
        self.collection = None
        self.metadata_path = Path(CHROMA_DB_PATH) / "metadata.json"
        # Sync state — counts indexes since the last successful upload
        self._indexes_since_sync = 0
        self._sync_in_flight = False

        if LLAMAINDEX_AVAILABLE:
            self._initialize_index()

    def _initialize_index(self):
        """Initialize or load existing index from ChromaDB"""
        try:
            # Create directory if it doesn't exist
            Path(CHROMA_DB_PATH).mkdir(parents=True, exist_ok=True)

            # Initialize ChromaDB client
            self.chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

            # Get or create collection
            try:
                self.collection = self.chroma_client.get_collection("als_research")
                logger.info(f"Loaded existing ChromaDB collection with {self.collection.count()} papers")
            except:
                self.collection = self.chroma_client.create_collection("als_research")
                logger.info("Created new ChromaDB collection")

            # Initialize embedding model
            # Prefer fastembed (68MB, no PyTorch) over HuggingFace (469MB, needs PyTorch)
            if USE_FASTEMBED and FASTEMBED_AVAILABLE:
                embed_model = FastEmbedEmbedding(model_name=EMBED_MODEL)
                logger.info(f"Using fastembed model: {EMBED_MODEL} (lightweight, no PyTorch)")
            elif HUGGINGFACE_EMBEDDINGS_AVAILABLE:
                try:
                    embed_model = HuggingFaceEmbedding(
                        model_name=EMBED_MODEL,
                        cache_folder="./embed_cache"
                    )
                    logger.info(f"Using HuggingFace embedding model: {EMBED_MODEL}")
                except Exception as e:
                    logger.warning(f"Failed to load {EMBED_MODEL}, falling back to default")
                    embed_model = HuggingFaceEmbedding(
                        model_name="sentence-transformers/all-MiniLM-L6-v2",
                        cache_folder="./embed_cache"
                    )
            else:
                raise RuntimeError(
                    "No embedding backend available. Install fastembed (recommended) "
                    "or llama-index-embeddings-huggingface + sentence-transformers."
                )

            # Configure settings
            Settings.embed_model = embed_model
            Settings.chunk_size = CHUNK_SIZE
            Settings.chunk_overlap = CHUNK_OVERLAP

            # Initialize vector store
            vector_store = ChromaVectorStore(chroma_collection=self.collection)
            storage_context = StorageContext.from_defaults(vector_store=vector_store)

            # Create or load index
            if self.collection.count() > 0:
                # Load existing index
                self.index = VectorStoreIndex.from_vector_store(
                    vector_store,
                    storage_context=storage_context
                )
                logger.info("Loaded existing vector index")
            else:
                # Create new index
                self.index = VectorStoreIndex(
                    [],
                    storage_context=storage_context
                )
                logger.info("Created new vector index")

            # Load metadata
            self._load_metadata()

        except Exception as e:
            logger.error(f"Failed to initialize index: {e}")
            self.index = None

    def _load_metadata(self):
        """Load paper metadata from disk"""
        global papers_metadata
        if self.metadata_path.exists():
            try:
                with open(self.metadata_path, 'r') as f:
                    papers_metadata = json.load(f)
                logger.info(f"Loaded metadata for {len(papers_metadata)} papers")
            except Exception as e:
                logger.error(f"Failed to load metadata: {e}")
                papers_metadata = {}
        else:
            papers_metadata = {}

    def _save_metadata(self):
        """Save paper metadata to disk"""
        try:
            with open(self.metadata_path, 'w') as f:
                json.dump(papers_metadata, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")

    def generate_paper_id(self, title: str, doi: Optional[str] = None) -> str:
        """Generate unique ID for a paper"""
        if doi:
            return hashlib.md5(doi.encode()).hexdigest()
        return hashlib.md5(title.lower().encode()).hexdigest()

    async def index_paper(
        self,
        title: str,
        abstract: str,
        authors: List[str],
        doi: Optional[str] = None,
        journal: Optional[str] = None,
        year: Optional[int] = None,
        findings: Optional[str] = None,
        url: Optional[str] = None,
        paper_type: str = "research"
    ) -> Dict[str, Any]:
        """Index a research paper with metadata"""

        if not self.index:
            return {"status": "error", "message": "Index not initialized"}

        # Generate unique ID
        paper_id = self.generate_paper_id(title, doi)

        # Check if already indexed
        if paper_id in papers_metadata:
            return {
                "status": "already_indexed",
                "paper_id": paper_id,
                "title": title,
                "message": "Paper already in research memory"
            }

        # Prepare document text
        doc_text = f"Title: {title}\n\n"
        doc_text += f"Authors: {', '.join(authors)}\n\n"

        if journal:
            doc_text += f"Journal: {journal}\n"
        if year:
            doc_text += f"Year: {year}\n\n"

        doc_text += f"Abstract: {abstract}\n\n"

        if findings:
            doc_text += f"Key Findings: {findings}\n\n"

        # Create document with metadata (ChromaDB only accepts strings, not lists)
        metadata = {
            "paper_id": paper_id,
            "title": title,
            "authors": ", ".join(authors) if authors else "",  # Convert list to string
            "doi": doi,
            "journal": journal,
            "year": year,
            "url": url,
            "paper_type": paper_type,
            "indexed_at": datetime.now().isoformat()
        }

        document = Document(
            text=doc_text,
            metadata=metadata
        )

        try:
            # Add to index
            self.index.insert(document)

            # Store metadata
            papers_metadata[paper_id] = metadata
            self._save_metadata()

            logger.info(f"Indexed paper: {title}")

            # Trigger a batched Dataset backup if configured
            self._indexes_since_sync += 1
            if (
                CHROMA_SYNC_REPO
                and HF_TOKEN
                and not self._sync_in_flight
                and self._indexes_since_sync >= CHROMA_SYNC_BATCH_SIZE
            ):
                try:
                    asyncio.create_task(self._sync_upload())
                except RuntimeError:
                    # No running loop — skip silently, the shutdown hook will catch up
                    pass

            return {
                "status": "success",
                "paper_id": paper_id,
                "title": title,
                "message": f"Successfully indexed paper into research memory"
            }

        except Exception as e:
            logger.error(f"Failed to index paper: {e}")
            return {
                "status": "error",
                "message": f"Failed to index paper: {str(e)}"
            }

    async def _sync_upload(self) -> bool:
        """Push the current chroma_db to the configured HF Dataset repo.

        Fire-and-forget: never raises, logs errors, resets counter only on success.
        """
        if not (CHROMA_SYNC_REPO and HF_TOKEN):
            logger.info("_sync_upload skipped: CHROMA_SYNC_REPO=%s HF_TOKEN=%s",
                        CHROMA_SYNC_REPO or "(unset)", "set" if HF_TOKEN else "(unset)")
            return False
        if self._sync_in_flight:
            logger.info("_sync_upload skipped: another upload already in flight")
            return False
        self._sync_in_flight = True
        try:
            # Import inside to keep the server import light if huggingface_hub is missing
            try:
                import chroma_sync
            except ImportError:
                logger.warning("chroma_sync module not available — skipping upload")
                return False

            pending = self._indexes_since_sync
            commit_msg = f"Runtime snapshot: +{pending} papers since last sync"
            logger.info("Starting chroma upload → %s (pending=%d, path=%s)",
                        CHROMA_SYNC_REPO, pending, CHROMA_DB_PATH)
            # Run the blocking upload in a thread so we don't stall the event loop
            ok = await asyncio.to_thread(
                chroma_sync.upload_snapshot,
                CHROMA_SYNC_REPO,
                Path(CHROMA_DB_PATH),
                HF_TOKEN,
                commit_msg,
            )
            if ok:
                self._indexes_since_sync = 0
                logger.info("chroma upload succeeded → %s", CHROMA_SYNC_REPO)
            else:
                logger.warning("chroma upload returned False → %s", CHROMA_SYNC_REPO)
            return ok
        finally:
            self._sync_in_flight = False

    async def search_similar(
        self,
        query: str,
        top_k: int = 5,
        include_scores: bool = True
    ) -> List[Dict[str, Any]]:
        """Search for similar research in memory"""

        if not self.index:
            return []

        try:
            # Use retriever for direct vector search (no LLM needed)
            retriever = self.index.as_retriever(
                similarity_top_k=top_k
            )

            # Search using retriever
            nodes = retriever.retrieve(query)

            results = []
            for node in nodes:
                result = {
                    "text": node.text[:500] + "..." if len(node.text) > 500 else node.text,
                    "metadata": node.metadata,
                    "score": node.score if include_scores else None
                }
                results.append(result)

            return results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []


# Global manager - will be initialized on first use
memory_manager = None
_initialization_lock = asyncio.Lock()  # Prevent race conditions during initialization
_initialization_started = False


async def ensure_initialized():
    """Ensure the memory manager is initialized (lazy initialization)."""
    global memory_manager, _initialization_started

    # Quick check without lock
    if memory_manager is not None:
        return True

    # Thread-safe initialization
    async with _initialization_lock:
        # Double-check after acquiring lock
        if memory_manager is not None:
            return True

        if not LLAMAINDEX_AVAILABLE:
            return False

        if _initialization_started:
            # Another thread is initializing, wait for it
            while memory_manager is None and _initialization_started:
                await asyncio.sleep(0.1)
            return memory_manager is not None

        try:
            _initialization_started = True
            logger.info("🔄 Initializing LlamaIndex RAG system (this may take 20-30 seconds)...")
            logger.info("  Loading BioBERT embedding model...")

            # Initialize the memory manager
            memory_manager = ResearchMemoryManager()

            logger.info("✅ LlamaIndex RAG system initialized successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize LlamaIndex: {e}")
            _initialization_started = False
            return False


@mcp.tool()
async def index_paper(
    title: str,
    abstract: str,
    authors: str,
    doi: Optional[str] = None,
    journal: Optional[str] = None,
    year: Optional[int] = None,
    findings: Optional[str] = None,
    url: Optional[str] = None
) -> str:
    """Index a research paper into persistent memory for future retrieval.

    The agent's research memory persists across sessions, building knowledge over time.

    Args:
        title: Paper title
        abstract: Paper abstract or summary
        authors: Comma-separated list of authors
        doi: Digital Object Identifier (optional)
        journal: Journal or preprint server name (optional)
        year: Publication year (optional)
        findings: Key findings or implications (optional)
        url: URL to paper (optional)

    Returns:
        Status of indexing operation
    """

    if not LLAMAINDEX_AVAILABLE:
        return json.dumps({
            "status": "error",
            "error": "LlamaIndex not installed",
            "message": "Install with: pip install llama-index chromadb sentence-transformers"
        }, indent=2)

    # Lazy initialization on first use
    if not await ensure_initialized():
        return json.dumps({
            "status": "error",
            "error": "Memory manager initialization failed",
            "message": "Check LlamaIndex configuration and dependencies"
        }, indent=2)

    try:
        # Parse authors
        authors_list = [a.strip() for a in authors.split(",")]

        result = await memory_manager.index_paper(
            title=title,
            abstract=abstract,
            authors=authors_list,
            doi=doi,
            journal=journal,
            year=year,
            findings=findings,
            url=url
        )

        if result["status"] == "success":
            return json.dumps({
                "status": "success",
                "paper_id": result["paper_id"],
                "title": result["title"],
                "message": f"✅ Indexed into research memory. Total papers: {len(papers_metadata)}",
                "total_papers_indexed": len(papers_metadata)
            }, indent=2)

        elif result["status"] == "already_indexed":
            return json.dumps({
                "status": "already_indexed",
                "paper_id": result["paper_id"],
                "title": result["title"],
                "message": "ℹ️ Paper already in research memory",
                "total_papers_indexed": len(papers_metadata)
            }, indent=2)

        else:
            return json.dumps({"status": "error", "error": "Indexing failed", "message": result.get("message", "Unknown error")}, indent=2)

    except Exception as e:
        logger.error(f"Error indexing paper: {e}")
        return json.dumps({"status": "error", "error": "Indexing error", "message": str(e)}, indent=2)


@mcp.tool()
async def semantic_search(
    query: str,
    max_results: int = 5
) -> str:
    """Search research memory using semantic similarity.

    Finds papers similar to your query across all indexed research,
    even if they don't contain exact keywords.

    Args:
        query: Search query (can be a question, topic, or paper abstract)
        max_results: Maximum number of results to return (default: 5)

    Returns:
        Similar papers from research memory
    """

    if not LLAMAINDEX_AVAILABLE:
        return json.dumps({
            "status": "error",
            "error": "LlamaIndex not installed",
            "message": "Install with: pip install llama-index chromadb sentence-transformers"
        }, indent=2)

    # Lazy initialization on first use
    if not await ensure_initialized():
        return json.dumps({
            "status": "error",
            "error": "Memory manager initialization failed",
            "message": "Check LlamaIndex configuration and dependencies"
        }, indent=2)

    if not memory_manager.index:
        return json.dumps({
            "status": "error",
            "error": "No research memory available",
            "message": "No papers have been indexed yet"
        }, indent=2)

    try:
        results = await memory_manager.search_similar(
            query=query,
            top_k=max_results
        )

        if not results:
            return json.dumps({
                "status": "no_results",
                "query": query,
                "message": "No similar research found in memory"
            }, indent=2)

        # Format results
        formatted_results = []
        for i, result in enumerate(results, 1):
            metadata = result["metadata"]
            formatted_results.append({
                "rank": i,
                "title": metadata.get("title", "Unknown"),
                "authors": metadata.get("authors", []),
                "year": metadata.get("year"),
                "journal": metadata.get("journal"),
                "doi": metadata.get("doi"),
                "url": metadata.get("url"),
                "similarity_score": round(result["score"], 3) if result["score"] else None,
                "excerpt": result["text"][:300] + "..."
            })

        return json.dumps({
            "status": "success",
            "query": query,
            "num_results": len(formatted_results),
            "results": formatted_results,
            "message": f"Found {len(formatted_results)} similar papers in research memory"
        }, indent=2)

    except Exception as e:
        logger.error(f"Search error: {e}")
        return json.dumps({"status": "error", "error": "Search failed", "message": str(e)}, indent=2)


@mcp.tool()
async def get_research_connections(
    paper_title: str,
    connection_type: str = "similar",
    max_connections: int = 5
) -> str:
    """Discover connections between research papers in memory.

    Finds related papers that might share themes, methods, or findings.

    Args:
        paper_title: Title of paper to find connections for
        connection_type: Type of connections - "similar", "citations", "authors"
        max_connections: Maximum connections to return

    Returns:
        Connected papers with relationship descriptions
    """

    if not LLAMAINDEX_AVAILABLE:
        return json.dumps({
            "status": "error",
            "error": "LlamaIndex not installed",
            "message": "Install with: pip install llama-index chromadb sentence-transformers"
        }, indent=2)

    # Lazy initialization on first use
    if not await ensure_initialized():
        return json.dumps({
            "status": "error",
            "error": "Memory manager initialization failed",
            "message": "Check LlamaIndex configuration and dependencies"
        }, indent=2)

    try:
        # For now, we'll use similarity search
        # Future: implement citation networks, co-authorship graphs

        if connection_type == "similar":
            # Search for papers similar to this title
            results = await memory_manager.search_similar(
                query=paper_title,
                top_k=max_connections + 1  # +1 because it might include itself
            )

            # Filter out the paper itself
            filtered_results = []
            for result in results:
                if result["metadata"].get("title", "").lower() != paper_title.lower():
                    filtered_results.append(result)

            if not filtered_results:
                return json.dumps({
                    "status": "no_connections",
                    "paper": paper_title,
                    "message": "No connections found in research memory"
                }, indent=2)

            connections = []
            for result in filtered_results[:max_connections]:
                metadata = result["metadata"]
                connections.append({
                    "title": metadata.get("title", "Unknown"),
                    "authors": metadata.get("authors", []),
                    "year": metadata.get("year"),
                    "connection_strength": round(result["score"], 3) if result["score"] else None,
                    "connection_type": "semantic_similarity",
                    "url": metadata.get("url")
                })

            return json.dumps({
                "status": "success",
                "paper": paper_title,
                "connection_type": connection_type,
                "num_connections": len(connections),
                "connections": connections,
                "message": f"Found {len(connections)} connected papers"
            }, indent=2)

        else:
            return json.dumps({
                "status": "not_implemented",
                "message": f"Connection type '{connection_type}' not yet implemented. Use 'similar' for now."
            }, indent=2)

    except Exception as e:
        logger.error(f"Error finding connections: {e}")
        return json.dumps({"status": "error", "error": "Connection search failed", "message": str(e)}, indent=2)


@mcp.tool()
async def list_indexed_papers(
    limit: int = 20,
    sort_by: str = "date"
) -> str:
    """List papers currently in research memory.

    Shows what research the agent has learned from previously.

    Args:
        limit: Maximum papers to list (default: 20)
        sort_by: Sort order - "date" (indexed date) or "year" (publication year)

    Returns:
        List of indexed papers with metadata
    """

    if not papers_metadata:
        return json.dumps({
            "status": "empty",
            "message": "No papers indexed yet. Research memory is empty.",
            "total_papers": 0
        }, indent=2)

    try:
        # Get papers list
        papers_list = []
        for paper_id, metadata in papers_metadata.items():
            # Convert authors string back to list
            authors_str = metadata.get("authors", "")
            authors_list = authors_str.split(", ") if authors_str else []

            papers_list.append({
                "paper_id": paper_id,
                "title": metadata.get("title", "Unknown"),
                "authors": authors_list,
                "year": metadata.get("year"),
                "journal": metadata.get("journal"),
                "doi": metadata.get("doi"),
                "indexed_at": metadata.get("indexed_at"),
                "url": metadata.get("url")
            })

        # Sort
        if sort_by == "date":
            papers_list.sort(key=lambda x: x.get("indexed_at", ""), reverse=True)
        elif sort_by == "year":
            papers_list.sort(key=lambda x: x.get("year", 0), reverse=True)

        # Limit
        papers_list = papers_list[:limit]

        return json.dumps({
            "status": "success",
            "total_papers": len(papers_metadata),
            "showing": len(papers_list),
            "sort_by": sort_by,
            "papers": papers_list,
            "message": f"Research memory contains {len(papers_metadata)} papers"
        }, indent=2)

    except Exception as e:
        logger.error(f"Error listing papers: {e}")
        return json.dumps({"status": "error", "error": "Failed to list papers", "message": str(e)}, indent=2)


@mcp.tool()
async def clear_research_memory(
    confirm: bool = False
) -> str:
    """Clear all papers from research memory.

    ⚠️ This will permanently delete all indexed research!

    Args:
        confirm: Must be True to actually clear memory

    Returns:
        Confirmation of memory clearing
    """
    global papers_metadata

    if not confirm:
        return json.dumps({
            "status": "confirmation_required",
            "message": "⚠️ This will delete all research memory. Set confirm=True to proceed.",
            "current_papers": len(papers_metadata)
        }, indent=2)

    try:
        # Check if memory manager needs initialization
        # Only initialize if we have papers to clear
        if papers_metadata and not memory_manager:
            await ensure_initialized()

        # Clear ChromaDB collection
        if memory_manager and memory_manager.collection:
            # Delete and recreate collection
            memory_manager.chroma_client.delete_collection("als_research")
            memory_manager.collection = memory_manager.chroma_client.create_collection("als_research")

            # Reinitialize index
            memory_manager._initialize_index()

        # Clear metadata
        num_papers = len(papers_metadata)
        papers_metadata = {}

        # Save empty metadata
        if memory_manager:
            memory_manager._save_metadata()

        logger.info(f"Cleared research memory: {num_papers} papers removed")

        return json.dumps({
            "status": "success",
            "message": f"✅ Research memory cleared. Removed {num_papers} papers.",
            "papers_removed": num_papers
        }, indent=2)

    except Exception as e:
        logger.error(f"Error clearing memory: {e}")
        return json.dumps({"status": "error", "error": "Failed to clear memory", "message": str(e)}, indent=2)


@mcp.tool()
async def upload_now() -> str:
    """Force an immediate upload of chroma_db to the configured HF Dataset repo.

    Used by the app on graceful shutdown to flush pending runtime indexes.
    Returns quickly if sync is not configured or a sync is already in flight.
    """
    logger.info("upload_now called (CHROMA_SYNC_REPO=%s, HF_TOKEN=%s, manager=%s)",
                CHROMA_SYNC_REPO or "(unset)",
                "set" if HF_TOKEN else "(unset)",
                "yes" if memory_manager else "no")
    if not CHROMA_SYNC_REPO or not HF_TOKEN:
        return json.dumps({"status": "skipped", "reason": "CHROMA_SYNC_REPO or HF_TOKEN not set"})

    if not memory_manager:
        # Manager not initialized — still try to upload what's on disk
        try:
            import chroma_sync
            logger.info("upload_now: manager unavailable, direct upload from %s", CHROMA_DB_PATH)
            ok = await asyncio.to_thread(
                chroma_sync.upload_snapshot,
                CHROMA_SYNC_REPO,
                Path(CHROMA_DB_PATH),
                HF_TOKEN,
                "Shutdown snapshot (no manager)",
            )
            logger.info("upload_now (no manager) result: %s", ok)
            return json.dumps({"status": "success" if ok else "failed"})
        except Exception as e:
            logger.warning("upload_now (no manager) failed: %s", e)
            return json.dumps({"status": "error", "message": str(e)})

    try:
        ok = await memory_manager._sync_upload()
        logger.info("upload_now (via manager) result: %s", ok)
        return json.dumps({"status": "success" if ok else "failed"})
    except Exception as e:
        logger.warning(f"upload_now failed: {e}")
        return json.dumps({"status": "error", "message": str(e)})


if __name__ == "__main__":
    # Check for required packages
    if not LLAMAINDEX_AVAILABLE:
        logger.error("LlamaIndex dependencies not installed!")
        logger.info("Install with: pip install llama-index-core llama-index-vector-stores-chroma")
        logger.info("              pip install chromadb sentence-transformers transformers")
    else:
        logger.info(f"LlamaIndex RAG server starting...")
        logger.info(f"ChromaDB path: {CHROMA_DB_PATH}")
        logger.info(f"Embedding model: {EMBED_MODEL}")
        logger.info(f"Papers in memory: {len(papers_metadata)}")

    # Run the MCP server
    mcp.run(transport="stdio")