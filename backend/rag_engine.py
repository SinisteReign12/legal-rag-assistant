import os
import re
import json
import pickle
import shutil
import pymupdf
import faiss
import numpy as np
import onnxruntime as ort
import gc

from transformers import AutoTokenizer
from dotenv import load_dotenv
from openai import OpenAI
from rank_bm25 import BM25Okapi
from database import get_document
from storage import download_pdf

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-20b"
)

if not GROQ_API_KEY:
    raise ValueError(
        "GROQ_API_KEY is not set in .env"
    )


client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)


EMBEDDING_MODEL_DIR = os.path.join(
    os.path.dirname(__file__),
    "onnx_models",
    "embedding"
)

RERANKER_MODEL_DIR = os.path.join(
    os.path.dirname(__file__),
    "onnx_models",
    "reranker"
)

embedding_tokenizer = None
embedding_session = None

reranker_tokenizer = None
reranker_session = None


def get_embedding_model():
    global embedding_tokenizer
    global embedding_session

    if embedding_session is None:

        print(
            "Loading ONNX embedding model...",
            flush=True
        )

        embedding_tokenizer = AutoTokenizer.from_pretrained(
            EMBEDDING_MODEL_DIR
        )

        embedding_session = ort.InferenceSession(
            os.path.join(
                EMBEDDING_MODEL_DIR,
                "model.onnx"
            ),
            providers=["CPUExecutionProvider"]
        )

        print(
            "ONNX embedding model loaded.",
            flush=True
        )

    return embedding_tokenizer, embedding_session

def release_embedding_model():
    global embedding_tokenizer, embedding_session

    embedding_tokenizer = None
    embedding_session = None

    gc.collect()


def get_reranker():
    global reranker_tokenizer
    global reranker_session

    if reranker_session is None:

        print(
            "Loading ONNX reranker model...",
            flush=True
        )

        reranker_tokenizer = AutoTokenizer.from_pretrained(
            RERANKER_MODEL_DIR
        )

        reranker_session = ort.InferenceSession(
            os.path.join(
                RERANKER_MODEL_DIR,
                "model.onnx"
            ),
            providers=["CPUExecutionProvider"]
        )

        print(
            "ONNX reranker model loaded.",
            flush=True
        )

    return reranker_tokenizer, reranker_session

def encode_embeddings(texts, batch_size=4):
    tokenizer, session = get_embedding_model()
    print(f"Starting embedding of {len(texts)} chunks...", flush=True)
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]

        encoded = tokenizer(
            batch,
            padding=True,
            truncation=True,
            return_tensors="np"
        )

        inputs = {}

        for input_name in session.get_inputs():
            name = input_name.name

            if name in encoded:
                inputs[name] = encoded[name]

        outputs = session.run(None, inputs)

        embeddings = None

        for output in outputs:
            if len(output.shape) == 2 and output.shape[1] == 384:
                embeddings = output
                break

        if embeddings is None:
            raise RuntimeError(
                "Could not find 384-dimensional embedding output."
            )

        norms = np.linalg.norm(
            embeddings,
            axis=1,
            keepdims=True
        )

        embeddings = embeddings / (norms + 1e-12)

        all_embeddings.append(
            embeddings.astype("float32")
        )

        print(
            f"Embedded {min(i + batch_size, len(texts))}/{len(texts)} chunks",
            flush=True
        )

    return np.vstack(all_embeddings)


rag_sessions = {}

query_cache = {}


CURRENT_RAG_CONFIG = {
    "embedding_model": "all-MiniLM-L6-v2-onnx",
    "chunking_version": "v2",
    "index_version": 2,
}

RAG_STORAGE_ROOT = os.getenv("RAG_STORAGE_ROOT", "rag_storage")


def tokenize(text):
    return re.findall(
        r"\b\w+\b",
        text.lower()
    )


def extract_text_from_pdf(pdf_path):

    pages = []
    doc = pymupdf.open(pdf_path)

    for page_number, page in enumerate(doc, start=1):

        text = page.get_text()

        if text.strip():
            pages.append({
                "page": page_number,
                "text": text
            })

    doc.close()
    return pages


def normalize_text(text):

    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_query(user_query):
    return re.sub(r"\s+", " ", user_query.strip().lower())


def extract_article_number(query):
    """
    Returns e.g. "14", "21A", "19" when the query mentions an Article.
    Returns None if no article number is found.
    """
    match = re.search(
        r"\barticle\s+(\d{1,3}[A-Za-z]?)(?:\s*\(.*?\))?\b",
        query,
        re.IGNORECASE
    )
    if not match:
        return None
    return match.group(1)


STRUCTURE_PATTERNS = [
    (re.compile(r"\bpreamble\b", re.IGNORECASE), "preamble"),

    (re.compile(r"\bfundamental\s+duties\b",   re.IGNORECASE), "fundamental_duties"),
    (re.compile(r"\bfundamental\s+rights?\b",  re.IGNORECASE), "fundamental_rights"),
    (re.compile(r"\bdirective\s+principles?\b", re.IGNORECASE), "directive_principles"),

    (re.compile(r"\bpart\s+iva\b",  re.IGNORECASE), "part_iva"),
    (re.compile(r"\bpart\s+iv\b",   re.IGNORECASE), "part_iv"),
    (re.compile(r"\bpart\s+iii\b",  re.IGNORECASE), "part_iii"),
    (re.compile(r"\bpart\s+ii\b",   re.IGNORECASE), "part_ii"),
    (re.compile(r"\bpart\s+i\b",    re.IGNORECASE), "part_i"),
    (re.compile(r"\bpart\s+v\b",    re.IGNORECASE), "part_v"),
    (re.compile(r"\bpart\s+vi\b",   re.IGNORECASE), "part_vi"),

    (re.compile(r"\bemergency\s+provisions?\b",      re.IGNORECASE), "emergency_provisions"),
    (re.compile(r"\bconstitutional\s+amendments?\b", re.IGNORECASE), "constitutional_amendments"),
    (re.compile(r"\bschedules?\b",                   re.IGNORECASE), "schedules"),
]


def detect_structural_section(query):
    for pattern, key in STRUCTURE_PATTERNS:
        if pattern.search(query):
            return key
    return None


_CONTENT_LABEL_TO_PART = {
    "fundamental_rights":   "part_iii",
    "directive_principles": "part_iv",
    "fundamental_duties":   "part_iva",
}

_PART_SECTION_TO_CONTENT_LABEL = {
    "part_iii": ["fundamental_rights"],
    "part_iv":  ["directive_principles"],
    "part_iva": ["fundamental_duties"],
}

_PART_LABEL_MAP = {
    "i":     "part_i",
    "ii":    "part_ii",
    "iii":   "part_iii",
    "iv":    "part_iv",
    "iva":   "part_iva",
    "v":     "part_v",
    "vi":    "part_vi",
    "vii":   "part_vii",
    "viii":  "part_viii",
    "ix":    "part_ix",
    "ixa":   "part_ixa",
    "x":     "part_x",
    "xi":    "part_xi",
    "xii":   "part_xii",
    "xiii":  "part_xiii",
    "xiv":   "part_xiv",
    "xv":    "part_xv",
    "xvi":   "part_xvi",
    "xvii":  "part_xvii",
    "xviii": "part_xviii",
    "xix":   "part_xix",
    "xx":    "part_xx",
    "xxi":   "part_xxi",
    "xxii":  "part_xxii",
}


def _part_label(roman):
    return _PART_LABEL_MAP.get(
        roman.lower().replace(" ", ""),
        f"part_{roman.lower()}"
    )



_PREAMBLE_HEADING_RE = re.compile(
    r"^preamble\s*$",
    re.IGNORECASE
)

_WE_THE_PEOPLE_RE = re.compile(
    r"WE,?\s+THE\s+PEOPLE",
    re.IGNORECASE
)

_PREAMBLE_SIGNAL_RE = re.compile(
    r"\bpreamble\b|WE,?\s+THE\s+PEOPLE\s+OF\s+INDIA",
    re.IGNORECASE
)

_PART_HEADING_RE = re.compile(
    r"^\s*PART\s+([IVXLCDA]+[A-Z]?)\s*$",
    re.IGNORECASE
)

_ARTICLE_HEADING_RE = re.compile(
    r"^\s*(\d{1,3}[A-Za-z]?)\.\s+(.+)$"
)


def create_legal_chunks(pages):
    """
    Improved legal-document chunker with Preamble and Part detection.
    Logic is unchanged from the working version — only persistence
    and retrieval-performance changes were made elsewhere in this file.
    """

    documents = []
    metadata  = []

    current_article = None
    current_section = None
    current_part    = None
    current_text    = []
    current_page    = None

    def flush_chunk():
        nonlocal current_article, current_text

        if not current_text:
            return

        text = " ".join(current_text).strip()

        if not text:
            current_text = []
            return

        documents.append(text)

        metadata.append({
            "page":    current_page,
            "article": current_article,
            "section": current_section,
            "part":    current_part,
        })

        current_text = []

    for page in pages:

        page_number = page["page"]
        raw_lines   = page["text"].splitlines()

        for line in raw_lines:

            stripped = line.strip()

            if not stripped:
                continue

            if _PREAMBLE_HEADING_RE.match(stripped):

                flush_chunk()

                current_article = None
                current_section = "preamble"
                current_part    = None
                current_page    = page_number
                current_text    = [stripped]
                continue

            if _WE_THE_PEOPLE_RE.match(stripped):

                if current_section != "preamble":
                    flush_chunk()
                    current_article = None
                    current_section = "preamble"
                    current_part    = None
                    current_page    = page_number

                current_text.append(stripped)
                continue

            part_match = _PART_HEADING_RE.match(stripped)

            if part_match:

                flush_chunk()

                roman           = part_match.group(1)
                current_part    = _part_label(roman)
                current_article = None
                current_section = current_part
                current_page    = page_number
                current_text    = [stripped]
                continue

            article_match = _ARTICLE_HEADING_RE.match(stripped)

            if article_match:

                number    = article_match.group(1)
                remainder = article_match.group(2)

                try:
                    numeric_part = int(
                        re.match(r"\d+", number).group()
                    )
                except Exception:
                    numeric_part = 9999

                if numeric_part <= 400:

                    flush_chunk()

                    current_article = number
                    current_section = current_part
                    current_page    = page_number
                    current_text    = [f"{number}. {remainder}"]
                    continue

            if current_page is None:
                current_page = page_number

            if not current_text and current_section is None:
                current_section = "intro"

            current_text.append(stripped)

            if (
                current_section in ("intro", None)
                and _PREAMBLE_SIGNAL_RE.search(stripped)
            ):
                current_section = "preamble"

    flush_chunk()

    if len(documents) < 10:

        documents = []
        metadata  = []

        for page in pages:

            text  = normalize_text(page["text"])
            words = text.split()

            chunk_size = 350

            for i in range(0, len(words), chunk_size):

                chunk = " ".join(words[i : i + chunk_size])

                if chunk.strip():

                    documents.append(chunk)

                    metadata.append({
                        "page":    page["page"],
                        "article": None,
                        "section": None,
                        "part":    None,
                    })

    return documents, metadata


def build_rag_from_pdf(pdf_path):

    pages = extract_text_from_pdf(pdf_path)

    if not pages:
        raise ValueError(
            "The PDF contains no readable text."
        )

    documents, metadata = create_legal_chunks(pages)

    if not documents:
        raise ValueError(
            "Could not create chunks from PDF."
        )


    tokenized_docs = [
        tokenize(doc)
        for doc in documents
    ]

    bm25 = BM25Okapi(tokenized_docs)

    embeddings = encode_embeddings(documents)

    embeddings = np.asarray(
        embeddings,
        dtype="float32"
    )


    index = faiss.IndexFlatL2(
        embeddings.shape[1]
    )

    index.add(embeddings)

    print("RAG INDEX BUILT")

    return {
        "documents": documents,
        "metadata":  metadata,
        "bm25":      bm25,
        "index":     index,
    }


def _storage_dir(conversation_id):
    return os.path.join(RAG_STORAGE_ROOT, str(conversation_id))


def _storage_paths(conversation_id):
    base = _storage_dir(conversation_id)
    return {
        "dir":      base,
        "index":    os.path.join(base, "index.faiss"),
        "metadata": os.path.join(base, "metadata.json"),
        "bm25":     os.path.join(base, "bm25.pkl"),
    }


def save_rag_to_disk(conversation_id, rag_data):
    """
    Persist FAISS index + chunk metadata + BM25 to disk so the PDF
    does not need to be reprocessed after a server restart.
    Failures here are logged but never raise — persistence is a
    best-effort optimization, not a hard requirement for the
    request to succeed.
    """

    paths = _storage_paths(conversation_id)

    try:
        os.makedirs(paths["dir"], exist_ok=True)

        faiss.write_index(rag_data["index"], paths["index"])

        tokenized_docs = [
            tokenize(doc)
            for doc in rag_data["documents"]
        ]

        with open(paths["metadata"], "w", encoding="utf-8") as f:
            json.dump(
                {
                    "documents":      rag_data["documents"],
                    "metadata":       rag_data["metadata"],
                    "tokenized_docs": tokenized_docs,
                    "config":         CURRENT_RAG_CONFIG,
                },
                f
            )

        try:
            with open(paths["bm25"], "wb") as f:
                pickle.dump(rag_data["bm25"], f)
        except Exception as bm25_err:
            print(f"[RAG PERSIST] Could not pickle BM25 directly, "
                  f"will reconstruct from tokenized docs on load: {bm25_err}")
            if os.path.exists(paths["bm25"]):
                os.remove(paths["bm25"])

        print(f"RAG INDEX SAVED (conversation_id={conversation_id})")

    except Exception as e:
        print(f"[RAG PERSIST] Failed to save RAG index to disk: {e}")


def load_rag_from_disk(conversation_id):
    """
    Attempt to load a previously persisted RAG index.
    Returns None (never raises) if nothing valid is found, so the
    caller can safely fall back to rebuilding from the PDF.
    """

    paths = _storage_paths(conversation_id)

    if not (os.path.exists(paths["index"]) and os.path.exists(paths["metadata"])):
        return None

    try:
        with open(paths["metadata"], "r", encoding="utf-8") as f:
            blob = json.load(f)

        config = blob.get("config", {})

        if config != CURRENT_RAG_CONFIG:
            print(
                "[RAG PERSIST] Persisted RAG index config is stale "
                "(embedding model / chunking / index version changed). "
                "Rebuilding from PDF."
            )
            return None

        documents      = blob["documents"]
        metadata       = blob["metadata"]
        tokenized_docs = blob["tokenized_docs"]

        index = faiss.read_index(paths["index"])

        bm25 = None

        if os.path.exists(paths["bm25"]):
            try:
                with open(paths["bm25"], "rb") as f:
                    bm25 = pickle.load(f)
            except Exception as bm25_err:
                print(
                    f"[RAG PERSIST] Could not unpickle BM25 "
                    f"({bm25_err}); reconstructing from tokenized docs."
                )
                bm25 = None

        if bm25 is None:
            bm25 = BM25Okapi(tokenized_docs)

        print(f"RAG INDEX LOADED FROM DISK (conversation_id={conversation_id})")

        return {
            "documents": documents,
            "metadata":  metadata,
            "bm25":      bm25,
            "index":     index,
        }

    except Exception as e:
        print(f"[RAG PERSIST] Failed to load persisted RAG index "
              f"(will rebuild from PDF): {e}")
        return None


def delete_persisted_rag(conversation_id):
    """
    Remove any persisted RAG data for a conversation. Safe to call
    even if nothing was ever persisted.
    """
    storage_dir = _storage_dir(conversation_id)

    if os.path.exists(storage_dir):
        try:
            shutil.rmtree(storage_dir)
            print(f"RAG INDEX REMOVED FROM DISK (conversation_id={conversation_id})")
        except Exception as e:
            print(f"[RAG PERSIST] Failed to remove persisted RAG data: {e}")


def clear_query_cache(conversation_id):
    query_cache.pop(conversation_id, None)


def process_uploaded_pdf(
    conversation_id,
    pdf_path
):
    """
    Called on upload AND on replacement. Any old persisted index /
    cached answers for this conversation are invalidated first so a
    replaced PDF can never serve stale data.
    """

    delete_persisted_rag(conversation_id)
    clear_query_cache(conversation_id)

    rag_data = build_rag_from_pdf(pdf_path)

    rag_sessions[conversation_id] = rag_data

    save_rag_to_disk(conversation_id, rag_data)

    return {
        "message": "PDF processed successfully.",
        "chunks":  len(rag_data["documents"]),
    }


def remove_pdf_session(conversation_id):
    """
    Call this from your existing PDF-removal flow (in addition to
    whatever already deletes the PDF file / DB record) so persisted
    RAG data and cached answers don't outlive the PDF.
    """
    rag_sessions.pop(conversation_id, None)
    delete_persisted_rag(conversation_id)
    clear_query_cache(conversation_id)


def restore_rag_session(conversation_id):
    if conversation_id in rag_sessions:
        return rag_sessions[conversation_id]

    rag_data = load_rag_from_disk(conversation_id)

    if rag_data:
        rag_sessions[conversation_id] = rag_data
        print(
            f"RAG INDEX RESTORED "
            f"(conversation_id={conversation_id})"
        )
        return rag_data

    document = get_document(conversation_id)

    if not document:
        return None

    storage_path = document.get("filepath")

    if not storage_path:
        return None

    temp_pdf_path = os.path.join(
        RAG_STORAGE_ROOT,
        f"{conversation_id}_temp.pdf"
    )

    try:
        os.makedirs(RAG_STORAGE_ROOT, exist_ok=True)

        print(
            f"Downloading PDF from Supabase: "
            f"{storage_path}"
        )

        download_pdf(
            storage_path,
            temp_pdf_path
        )

        rag_data = build_rag_from_pdf(
            temp_pdf_path
        )

        rag_sessions[conversation_id] = rag_data

        save_rag_to_disk(
            conversation_id,
            rag_data
        )

        return rag_data

    finally:
        if os.path.exists(temp_pdf_path):
            try:
                os.remove(temp_pdf_path)
                print(
                    f"Temporary PDF removed: "
                    f"{temp_pdf_path}"
                )
            except Exception as e:
                print(
                    f"Could not remove temporary PDF: {e}"
                )


def get_exact_article_docs(
    documents,
    metadata,
    article_number
):
    if not article_number:
        return []

    results = []

    for i, meta in enumerate(metadata):

        if (
            str(meta.get("article", "")).lower()
            == str(article_number).lower()
        ):

            results.append({
                "content": documents[i],
                "page":    meta["page"],
                "article": meta.get("article"),
                "section": meta.get("section"),
                "part":    meta.get("part"),
                "index":   i,
            })

    return results



def get_exact_section_docs(
    documents,
    metadata,
    section_key
):
    if not section_key:
        return []

    target_keys = {section_key}

    if section_key in _CONTENT_LABEL_TO_PART:
        target_keys.add(_CONTENT_LABEL_TO_PART[section_key])

    if section_key in _PART_SECTION_TO_CONTENT_LABEL:
        for alias in _PART_SECTION_TO_CONTENT_LABEL[section_key]:
            target_keys.add(alias)

    results = []

    for i, meta in enumerate(metadata):

        chunk_section = meta.get("section") or ""
        chunk_part    = meta.get("part")    or ""

        if chunk_section in target_keys or chunk_part in target_keys:

            results.append({
                "content": documents[i],
                "page":    meta["page"],
                "article": meta.get("article"),
                "section": meta.get("section"),
                "part":    meta.get("part"),
                "index":   i,
            })

    return results


def rerank(
    query,
    docs,
    top_k=5,
    batch_size=4
):
    if not docs:
        return []

    tokenizer, session = get_reranker()

    all_results = []

    for i in range(0, len(docs), batch_size):
        batch_docs = docs[i:i + batch_size]

        queries = [query] * len(batch_docs)
        documents = [doc["content"] for doc in batch_docs]

        encoded = tokenizer(
            queries,
            documents,
            padding=True,
            truncation=True,
            return_tensors="np"
        )

        inputs = {}

        for input_name in session.get_inputs():
            name = input_name.name

            if name in encoded:
                inputs[name] = encoded[name]

        outputs = session.run(None, inputs)

        scores = None

        for output in outputs:
            if len(output.shape) == 2 and output.shape[0] == len(batch_docs):
                scores = output.reshape(-1)
                break

        if scores is None:
            raise RuntimeError(
                "Could not find reranker score output."
            )

        all_results.extend(
            zip(batch_docs, scores)
        )

    ranked = sorted(
        all_results,
        key=lambda x: float(x[1]),
        reverse=True
    )

    return [
        doc
        for doc, _ in ranked[:top_k]
    ]


def query_uploaded_pdf(
    conversation_id,
    user_query
):

    print(f"QUERY: {user_query}")


    normalized_query = normalize_query(user_query)
    cached_answer = query_cache.get(conversation_id, {}).get(normalized_query)

    if cached_answer is not None:
        print("QUERY CACHE HIT — skipping FAISS/BM25/rerank/Groq")
        return cached_answer

    rag_data = restore_rag_session(conversation_id)

    if not rag_data:
        return (
            "No PDF has been processed "
            "for this conversation."
        )


    documents = rag_data["documents"]
    metadata  = rag_data["metadata"]
    bm25      = rag_data["bm25"]
    index     = rag_data["index"]

    if not documents:
        return "No legal documents loaded."


    article_number = extract_article_number(user_query)

    detected_section = None

    if not article_number:
        detected_section = detect_structural_section(user_query)

    print(f"DETECTED ARTICLE: {article_number}")
    print(f"DETECTED SECTION: {detected_section}")


    exact_article_docs = []
    exact_section_docs = []

    if article_number:

        exact_article_docs = get_exact_article_docs(
            documents,
            metadata,
            article_number
        )

    elif detected_section:

        exact_section_docs = get_exact_section_docs(
            documents,
            metadata,
            detected_section
        )

    print(f"EXACT MATCH COUNT: {len(exact_article_docs) + len(exact_section_docs)}")

    q_emb = encode_embeddings([user_query])
    
    release_embedding_model()

    faiss_k = min(15, len(documents))

    _, faiss_indices = index.search(q_emb, faiss_k)

    faiss_docs = []

    for i in faiss_indices[0]:

        if 0 <= i < len(documents):

            faiss_docs.append({
                "content": documents[i],
                "page":    metadata[i]["page"],
                "article": metadata[i].get("article"),
                "section": metadata[i].get("section"),
                "part":    metadata[i].get("part"),
                "index":   int(i),
            })

    print(f"FAISS RESULTS: {len(faiss_docs)}")


    bm25_scores = bm25.get_scores(
        tokenize(user_query)
    )

    bm25_k = min(15, len(documents))

    top_bm25_indices = np.argsort(
        bm25_scores
    )[-bm25_k:][::-1]

    bm25_docs = []

    for i in top_bm25_indices:

        if 0 <= i < len(documents):

            bm25_docs.append({
                "content": documents[i],
                "page":    metadata[i]["page"],
                "article": metadata[i].get("article"),
                "section": metadata[i].get("section"),
                "part":    metadata[i].get("part"),
                "index":   int(i),
            })

    print(f"BM25 RESULTS: {len(bm25_docs)}")


    combined     = []
    seen_indices = set()

    def add_docs(doc_list):
        for doc in doc_list:
            idx = doc["index"]
            if idx not in seen_indices:
                seen_indices.add(idx)
                combined.append(doc)

    add_docs(exact_article_docs)
    add_docs(exact_section_docs)
    add_docs(faiss_docs)
    add_docs(bm25_docs)

    print(f"COMBINED RESULTS: {len(combined)}")

    if not combined:
        return "No relevant legal content found."


    exact_docs = exact_article_docs or exact_section_docs

    if exact_docs:

        exact_ranked = rerank(user_query, exact_docs, top_k=3)

        exact_indices = {doc["index"] for doc in exact_docs}

        other_docs = [
            doc for doc in combined
            if doc["index"] not in exact_indices
        ]

        other_ranked = rerank(user_query, other_docs, top_k=2)

        best_docs = exact_ranked + other_ranked

    else:

        best_docs = rerank(user_query, combined, top_k=5)

    print(f"FINAL RERANKED RESULTS: {len(best_docs)}")


    context_parts = [doc["content"] for doc in best_docs]

    context = "\n\n".join(context_parts)


    prompt = f"""Answer the user's question using ONLY the uploaded
legal document context below.

DOCUMENT CONTEXT:

{context}


QUESTION:

{user_query}


INSTRUCTIONS:

- Give a clear and direct answer.
- Explain what the document says in simple language
  when appropriate.
- Preserve the legal meaning of the document.
- Use only information supported by the supplied context.
- Do not use outside legal knowledge.
- Do not invent legal provisions, facts, or interpretations.
- Do not mention pages.
- Do not mention sources.
- Do not provide a Sources section.
- Do not mention retrieval, chunks, FAISS, BM25,
  embeddings, reranking, or internal processing.
- Do not talk about the context itself unless necessary.
- Answer the actual question directly.
- If the supplied context genuinely does not contain
  enough information to answer the question, say:
  "The information was not found in the uploaded document."
"""


    try:
        response = client.chat.completions.create(

            model=GROQ_MODEL,

            messages=[

                {
                    "role": "system",

                    "content": (
                        "You are a legal document assistant. "
                        "Answer questions strictly using the "
                        "uploaded document context. "
                        "Give clear and direct answers based "
                        "only on what the document says. "
                        "Do not use outside legal knowledge. "
                        "Do not invent legal provisions, facts, "
                        "or interpretations. "
                        "Do not mention pages, sources, retrieval, "
                        "chunks, embeddings, FAISS, BM25, "
                        "reranking, or internal processing. "
                        "If the supplied context genuinely does "
                        "not contain enough information to answer "
                        "the question, say that the information "
                        "was not found in the uploaded document."
                    )
                },

                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
    except Exception as e:
        print(f"[GROQ] Request failed: {e}")
        return (
            "There was a problem generating an answer. "
            "Please try again."
        )

    answer = (
        response
        .choices[0]
        .message
        .content
    )

    query_cache.setdefault(conversation_id, {})[normalized_query] = answer

    return answer