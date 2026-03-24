"""RAG pipeline: scrape, embed, store, retrieve, generate.

Uses ChromaDB for local vector storage, sentence-transformers for
embeddings, and Claude API for generation.
"""

import hashlib
import os
from pathlib import Path

KNOWLEDGE_DIR = Path("data/knowledge")
SCRAPED_DIR = KNOWLEDGE_DIR / "scraped"
MANUAL_DIR = KNOWLEDGE_DIR / "manual"
CHROMA_DIR = KNOWLEDGE_DIR / "chroma_db"
COLLECTION_NAME = "spam_knowledge"

# Pages to scrape from mapspam.info
SCRAPE_URLS = [
    ("https://www.mapspam.info/about/", "about.md"),
    ("https://www.mapspam.info/methodology/", "methodology.md"),
    ("https://www.mapspam.info/data/", "data.md"),
    ("https://www.mapspam.info/publications/", "publications.md"),
    ("https://www.mapspam.info/faq/", "faq.md"),
]


def scrape_mapspam_pages():
    """Scrape key pages from mapspam.info and save as markdown."""
    import requests
    from bs4 import BeautifulSoup

    SCRAPED_DIR.mkdir(parents=True, exist_ok=True)
    scraped = []

    for url, filename in SCRAPE_URLS:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
            }
            resp = requests.get(url, timeout=30, headers=headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract main content (skip nav, footer, etc.)
            content = soup.find("main") or soup.find("article") or soup.find("body")
            if content:
                # Remove scripts and styles
                for tag in content.find_all(["script", "style", "nav", "footer"]):
                    tag.decompose()
                text = content.get_text(separator="\n", strip=True)
            else:
                text = soup.get_text(separator="\n", strip=True)

            path = SCRAPED_DIR / filename
            path.write_text(f"# Source: {url}\n\n{text}")
            scraped.append(filename)
            print(f"  Scraped: {url} -> {filename} ({len(text)} chars)")
        except Exception as e:
            print(f"  Failed: {url}: {e}")

    return scraped


def collect_documents() -> list[dict]:
    """Collect all documents from internal docs, scraped pages, and manual additions."""
    docs = []

    # Internal project docs
    internal_files = [
        Path("CLAUDE.md"),
        Path("docs/design/hld.md"),
        Path("docs/design/lld.md"),
        Path("CONTRACTS.md"),
        Path("CHANGELOG.md"),
    ]
    for f in internal_files:
        if f.exists():
            docs.append({
                "text": f.read_text(),
                "source": str(f),
                "type": "internal",
            })

    # Crop metadata from crops.py
    from src.crops import CROPS, TECH_LEVELS, VARIABLES

    crop_text = "# Crop Registry\n\n"
    crop_text += "## 46 Crops by Category\n"
    by_cat = {}
    for code, info in CROPS.items():
        by_cat.setdefault(info["category"], []).append(
            f"- {info['name']} ({code})"
        )
    for cat, items in sorted(by_cat.items()):
        crop_text += f"\n### {cat}\n" + "\n".join(items) + "\n"

    crop_text += "\n## Variables\n"
    for code, info in VARIABLES.items():
        crop_text += f"- {code}: {info['name']} ({info['unit']})\n"

    crop_text += "\n## Technology Levels\n"
    for code, name in TECH_LEVELS.items():
        crop_text += f"- {code}: {name}\n"

    docs.append({
        "text": crop_text,
        "source": "src/crops.py",
        "type": "internal",
    })

    # Scraped pages
    if SCRAPED_DIR.exists():
        for f in SCRAPED_DIR.glob("*.md"):
            docs.append({
                "text": f.read_text(),
                "source": f"scraped/{f.name}",
                "type": "scraped",
            })

    # Manual additions (markdown, txt, or PDF)
    if MANUAL_DIR.exists():
        for f in MANUAL_DIR.iterdir():
            if f.suffix in (".md", ".txt"):
                docs.append({
                    "text": f.read_text(),
                    "source": f"manual/{f.name}",
                    "type": "manual",
                })
            elif f.suffix == ".pdf":
                try:
                    from pypdf import PdfReader

                    reader = PdfReader(f)
                    text = "\n".join(
                        page.extract_text() or "" for page in reader.pages
                    )
                    docs.append({
                        "text": text,
                        "source": f"manual/{f.name}",
                        "type": "manual",
                    })
                except ImportError:
                    print(f"  Skip PDF {f.name} (install pypdf)")

    return docs


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """Split text into overlapping chunks by words."""
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def build_vector_store(docs: list[dict] | None = None):
    """Build or rebuild the ChromaDB vector store from documents."""
    import chromadb

    if docs is None:
        docs = collect_documents()

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    # Delete existing collection if rebuilding
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    all_chunks = []
    all_ids = []
    all_metadata = []

    for doc in docs:
        chunks = chunk_text(doc["text"])
        for i, chunk in enumerate(chunks):
            chunk_id = hashlib.md5(
                f"{doc['source']}:{i}".encode()
            ).hexdigest()
            all_chunks.append(chunk)
            all_ids.append(chunk_id)
            all_metadata.append({
                "source": doc["source"],
                "type": doc["type"],
                "chunk_idx": i,
            })

    if all_chunks:
        # ChromaDB handles embedding internally with its default model
        # or we can use sentence-transformers
        collection.add(
            documents=all_chunks,
            ids=all_ids,
            metadatas=all_metadata,
        )

    print(f"  Indexed {len(all_chunks)} chunks from {len(docs)} documents")
    return collection


def get_collection():
    """Get the existing ChromaDB collection."""
    import chromadb

    if not CHROMA_DIR.exists():
        return None

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    try:
        return client.get_collection(COLLECTION_NAME)
    except Exception:
        return None


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """Retrieve top-k relevant chunks for a query."""
    collection = get_collection()
    if collection is None:
        return []

    results = collection.query(query_texts=[query], n_results=top_k)

    chunks = []
    for i, doc in enumerate(results["documents"][0]):
        chunks.append({
            "text": doc,
            "source": results["metadatas"][0][i]["source"],
        })
    return chunks


def generate_answer(
    question: str,
    session_context: str = "",
    chat_history: list[dict] | None = None,
) -> str:
    """Retrieve relevant context and generate answer using Claude API."""
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "Please set ANTHROPIC_API_KEY to use the AI assistant."

    # Retrieve relevant chunks
    chunks = retrieve(question, top_k=5)
    context = "\n\n---\n\n".join(
        f"[Source: {c['source']}]\n{c['text']}" for c in chunks
    )

    system_prompt = (
        "You are an expert assistant for the MapSPAM 2020 Crop Production Analyzer. "
        "Answer questions about the SPAM dataset, methodology, crops, and this tool. "
        "Use the provided context to give accurate, concise answers. "
        "If the context doesn't contain enough information, say so honestly. "
        "Format answers in markdown.\n\n"
        f"## Retrieved Knowledge\n{context}"
    )

    if session_context:
        system_prompt += f"\n\n## Current Session\n{session_context}"

    messages = []
    if chat_history:
        for msg in chat_history[-10:]:  # Last 10 messages for context
            messages.append(msg)
    messages.append({"role": "user", "content": question})

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    )

    return response.content[0].text
