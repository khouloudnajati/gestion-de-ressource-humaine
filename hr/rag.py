"""
Moteur RAG PeopleFlow RH (cahier des charges ch.9).
Recherche vectorielle ChromaDB + sentence-transformers, avec repli lexical.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from django.conf import settings

CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "150"))
TOP_K = int(os.getenv("RAG_TOP_K", "4"))
EMBED_MODEL = os.getenv(
    "RAG_EMBED_MODEL",
    "paraphrase-multilingual-MiniLM-L12-v2",
)
COLLECTION_NAME = "peopleflow_rh"
_client = None
_collection = None


def _chroma_dir() -> Path:
    return Path(getattr(settings, "CHROMA_DIR", settings.BASE_DIR / "chroma_db"))


def _embedding_function():
    from chromadb.utils import embedding_functions
    return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)


def _get_client():
    global _client
    if _client is None:
        import chromadb
        _chroma_dir().mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(_chroma_dir()))
    return _client


def _get_collection(*, create: bool = True):
    global _collection
    if _collection is not None:
        return _collection
    client = _get_client()
    ef = _embedding_function()
    if create:
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    else:
        _collection = client.get_collection(name=COLLECTION_NAME, embedding_function=ef)
    return _collection


def _read_file(path: Path) -> str:
    from pypdf import PdfReader
    if path.suffix.lower() == ".pdf":
        return " ".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def _chunk_text(text: str, source: str, prefix: str) -> list[dict]:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 30:
        return []
    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        piece = text[start:end].strip()
        if len(piece) >= 40:
            chunk_id = f"{prefix}-{hashlib.md5(piece.encode()).hexdigest()[:10]}-{idx}"
            chunks.append({
                "id": chunk_id,
                "text": piece,
                "meta": {"source": source, "chunk": idx},
            })
            idx += 1
        if end >= len(text):
            break
        start = end - CHUNK_OVERLAP
    return chunks


def _collect_chunks() -> list[dict]:
    from .models import RHDocument, Announcement, Department

    all_chunks: list[dict] = []

    for doc in RHDocument.objects.filter(active=True):
        try:
            path = Path(doc.file.path)
            if not path.exists():
                continue
            content = _read_file(path)
            label = doc.title or path.name
            all_chunks.extend(_chunk_text(content, label, f"doc-{doc.pk}"))
        except Exception:
            continue

    docs_dir = Path(settings.RH_DOCUMENTS_DIR)
    docs_dir.mkdir(parents=True, exist_ok=True)
    for path in docs_dir.glob("*"):
        if path.is_file():
            try:
                content = _read_file(path)
                all_chunks.extend(_chunk_text(content, path.name, f"fs-{path.name}"))
            except Exception:
                continue

    # Connaissances structurées issues de la base (politiques / organisation)
    dept_lines = [f"- {d.name} : {d.description or 'sans description'}" for d in Department.objects.all()]
    if dept_lines:
        org_text = "Organisation de l'entreprise laitière :\n" + "\n".join(dept_lines)
        all_chunks.extend(_chunk_text(org_text, "Base RH – Départements", "db-depts"))

    announcements = Announcement.objects.filter(active=True)[:15]
    if announcements:
        ann_text = "Annonces RH internes :\n" + "\n".join(
            f"• {a.title} ({a.get_priority_display()}) : {a.content}" for a in announcements
        )
        all_chunks.extend(_chunk_text(ann_text, "Base RH – Annonces", "db-ann"))

    policy_path = docs_dir / "reglement_interieur.txt"
    if not policy_path.exists():
        _write_default_policy(policy_path)

    return all_chunks


def _write_default_policy(path: Path):
    """Document de démarrage pour alimenter le RAG (procédures RH type entreprise laitière)."""
    path.write_text(
        """RÈGLEMENT INTÉRIEUR – ENTREPRISE LAITIÈRE PeopleFlow

HORAIRES DE TRAVAIL
- Production et logistique : postes en 3×8 (06h-14h, 14h-22h, 22h-06h) selon planning hebdomadaire.
- Bureaux (RH, commercial, finance) : 08h30 – 17h30 du lundi au vendredi.
- Ramadan et jours fériés : aménagement communiqué par la direction RH.

CONGÉS ET ABSENCES
- Toute absence doit faire l'objet d'une demande via la plateforme PeopleFlow au moins 5 jours ouvrés à l'avance.
- Congé annuel : 18 jours ouvrés par an, selon ancienneté et accord du responsable.
- Congé maladie : certificat médical transmis au service RH sous 48 h.
- Le responsable RH valide ou refuse chaque demande sous 3 jours ouvrés.

DOCUMENTS ADMINISTRATIFS
- Attestation de travail, certificat de salaire et copie de contrat : demande via « Mes documents » sur PeopleFlow.
- Délai de traitement moyen : 3 à 5 jours ouvrés.

HYGIÈNE ET SÉCURITÉ (secteur laitier)
- Port des EPI obligatoire en zone de production.
- Respect des normes HACCP et traçabilité des lots.
- Signaler tout incident qualité au département Qualité.

PAIE
- Les bulletins de salaire sont publiés sur PeopleFlow avant le 5 de chaque mois.
- Questions paie : contacter le département Financier ou le service RH.

FORMATIONS
- Les formations obligatoires (hygiène, sécurité) sont planifiées par le service RH.
- Inscription via la rubrique « Formations » de la plateforme.
""",
        encoding="utf-8",
    )


def rebuild_index() -> int:
    """Réindexe tous les documents RH. Retourne le nombre de fragments indexés."""
    global _collection
    client = _get_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    _collection = None
    chunks = _collect_chunks()
    if not chunks:
        return 0
    collection = _get_collection()
    batch = 100
    for i in range(0, len(chunks), batch):
        part = chunks[i:i + batch]
        collection.add(
            ids=[c["id"] for c in part],
            documents=[c["text"] for c in part],
            metadatas=[c["meta"] for c in part],
        )
    return len(chunks)


def rag_status() -> dict:
    """État du moteur RAG pour l'interface."""
    try:
        collection = _get_collection()
        count = collection.count()
        if count == 0:
            count = rebuild_index()
        return {
            "active": count > 0,
            "chunks": count,
            "model": EMBED_MODEL,
            "engine": "ChromaDB + sentence-transformers",
        }
    except Exception as exc:
        return {"active": False, "chunks": 0, "model": EMBED_MODEL, "engine": "indisponible", "error": str(exc)}


def rag_search(question: str, top_k: int | None = None) -> dict:
    """
    Recherche sémantique dans le corpus RH.
    Retourne : text (contexte), sources (liste), chunks (nombre), scores.
    """
    top_k = top_k or TOP_K
    try:
        collection = _get_collection()
        if collection.count() == 0:
            rebuild_index()
        if collection.count() == 0:
            return {"text": "", "sources": [], "chunks": 0, "scores": []}

        n = min(top_k, collection.count())
        results = collection.query(query_texts=[question], n_results=n, include=["documents", "metadatas", "distances"])
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        if not docs:
            return {"text": "", "sources": [], "chunks": 0, "scores": []}

        parts = []
        sources = []
        scores = []
        for i, doc in enumerate(docs):
            src = metas[i].get("source", "Document RH")
            similarity = round(max(0, 1 - distances[i]), 3) if i < len(distances) else 0
            if similarity < 0.25 and i > 0:
                continue
            parts.append(f"[{src}]\n{doc}")
            sources.append(src)
            scores.append(similarity)

        sources = list(dict.fromkeys(sources))
        return {
            "text": "\n\n---\n\n".join(parts),
            "sources": sources,
            "chunks": len(parts),
            "scores": scores,
        }
    except Exception:
        return {"text": "", "sources": [], "chunks": 0, "scores": []}


def rag_answer_from_chunks(question: str, rag_result: dict) -> str:
    """Synthèse locale à partir des fragments RAG (sans API Gemini)."""
    if not rag_result.get("text"):
        return ""
    q_words = {w for w in question.lower().split() if len(w) > 3}
    sentences = re.split(r"(?<=[.!?])\s+", rag_result["text"])
    picked = []
    for s in sentences:
        sl = s.lower()
        if any(w in sl for w in q_words) or len(picked) < 2:
            picked.append(s.strip())
        if len(picked) >= 4:
            break
    if not picked:
        picked = [rag_result["text"][:500]]
    body = " ".join(picked)
    sources = ", ".join(rag_result.get("sources", [])[:3])
    footer = f"\n\n📎 Sources consultées (RAG) : {sources}" if sources else ""
    return body + footer
