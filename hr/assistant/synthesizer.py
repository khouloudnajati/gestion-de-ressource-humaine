"""
Synthèse adaptée à la question — sans LLM.
Transforme les fragments RAG + données live en réponse personnalisée.
"""

from __future__ import annotations

import re
import unicodedata

from django.urls import reverse

INTRO_BY_TOPIC = {
    "horaires": "Voici les horaires de travail chez PeopleFlow :",
    "conges": "Concernant les congés et absences :",
    "documents": "Pour les documents administratifs :",
    "contrats": "Concernant votre contrat de travail :",
    "hygiene": "Voici les règles d'hygiène et de sécurité :",
    "paie": "Concernant la paie et les bulletins de salaire :",
    "formations": "Pour les formations :",
    "services": "Voici les services disponibles sur PeopleFlow :",
    "reglement": "D'après le règlement intérieur PeopleFlow :",
}

TOPIC_KEYWORDS = {
    "horaires": {"horaire", "heure", "planning", "bureau", "production", "3x8"},
    "conges": {"congé", "conge", "absence", "vacance", "vacances", "maladie", "repos"},
    "contrats": {"contrat", "contra", "cdi", "cdd", "stage", "interim"},
    "documents": {"document", "attestation", "certificat", "papier", "administratif"},
    "hygiene": {"hygiène", "hygiene", "haccp", "epi", "sécurité", "securite", "qualité", "qualite"},
    "paie": {"paie", "salaire", "bulletin", "paiement", "fiche", "revenu"},
    "formations": {"formation", "training", "cours", "apprentissage"},
    "services": {"service", "disponible", "aide", "menu", "fonctionnalité", "plateforme", "peopleflow"},
    "reglement": {"règlement", "reglement", "politique", "procédure", "procedure", "règle", "regle"},
}

STOPWORDS = {
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "ou", "en", "au", "aux",
    "pour", "par", "sur", "dans", "avec", "est", "sont", "que", "qui", "quoi", "comment",
    "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa", "ses", "notre", "votre", "leur",
    "je", "tu", "il", "elle", "nous", "vous", "ils", "elles", "ce", "cette", "ces",
    "quel", "quelle", "quels", "quelles", "combien", "donne", "donner", "peux", "peut",
}


def _normalize(text: str) -> str:
    text = text.lower().strip()
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _question_words(question: str) -> set[str]:
    words = set()
    for token in re.findall(r"[\wàâäéèêëïîôùûüç\-']+", _normalize(question)):
        if len(token) > 2 and token not in STOPWORDS:
            words.add(token)
    return words


def _detect_topics(question: str) -> list[str]:
    q = _normalize(question)
    if any(k in q for k in ("contrat", "contra", "cdi", "cdd")):
        return ["contrats"]
    scores: list[tuple[int, str]] = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in q)
        if score:
            scores.append((score, topic))
    scores.sort(reverse=True)
    return [t for _, t in scores]


def _parse_rag_chunks(rag_text: str) -> list[tuple[str, str]]:
    """Découpe le texte RAG en (source, contenu) sans préfixe brut."""
    if not rag_text:
        return []
    parts = re.split(r"\n---\n", rag_text)
    chunks: list[tuple[str, str]] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        match = re.match(r"^\[(.+?)\]\s*(.*)", part, re.DOTALL)
        if match:
            chunks.append((match.group(1).strip(), match.group(2).strip()))
        else:
            chunks.append(("Document RH", part))
    return chunks


def _score_text(text: str, q_words: set[str], topics: list[str]) -> float:
    tl = _normalize(text)
    score = 0.0
    for w in q_words:
        if w in tl:
            score += 2.0
    for topic in topics:
        for kw in TOPIC_KEYWORDS.get(topic, set()):
            if kw in tl:
                score += 1.5
    if "comment" in q_words and any(v in tl for v in ("demande", "demander", "procedure", "procede", "via")):
        score += 3.0
    return score


def _extract_bullets(text: str, q_words: set[str], max_items: int = 5) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^[-•*]\s*", "", line)
        if len(line) < 8:
            continue
        lines.append(line)

    if not lines:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        lines = [s.strip() for s in sentences if len(s.strip()) > 15]

    scored = [( _score_text(line, q_words, []), line) for line in lines]
    scored.sort(key=lambda x: x[0], reverse=True)

    picked: list[str] = []
    seen: set[str] = set()
    for sc, line in scored:
        if sc <= 0 and picked:
            continue
        key = line[:60]
        if key in seen:
            continue
        seen.add(key)
        picked.append(line if line.startswith("-") else f"• {line}")
        if len(picked) >= max_items:
            break

    if not picked and lines:
        picked = [f"• {lines[0]}"]
    return picked


def _intro_for_question(question: str, topics: list[str]) -> str:
    q = _normalize(question)
    if any(x in q for x in ("bonjour", "salut", "hello", "bonsoir", "coucou")):
        return "greeting"
    if any(x in q for x in ("merci", "thanks", "parfait", "d'accord")):
        return "thanks"
    if topics:
        return INTRO_BY_TOPIC.get(topics[0], "Voici la réponse à votre question :")
    if q.startswith(("comment", "ou ", "où ", "ou ")):
        return "Voici la procédure :"
    return "Voici ce que j'ai trouvé pour vous :"


def synthesize_adapted_answer(
    question: str,
    *,
    rag_text: str = "",
    sources: list[str] | None = None,
    live_data: str = "",
    user_name: str = "",
    is_hr: bool = False,
) -> str:
    """Construit une réponse adaptée à la question, sans coller le RAG brut."""
    q_words = _question_words(question)
    topics = _detect_topics(question)
    intro_kind = _intro_for_question(question, topics)

    if intro_kind == "greeting":
        name = f" {user_name}" if user_name else ""
        if is_hr:
            return (
                f"Bonjour{name} ! Je suis SmartZIZ, votre assistant RH PeopleFlow.\n\n"
                "En tant que responsable RH, je peux répondre sur toute la plateforme : employés, "
                "congés, documents, paie, formations, rapports, recrutement et procédures internes."
            )
        return (
            f"Bonjour{name} ! Je suis SmartZIZ, votre assistant RH PeopleFlow.\n\n"
            "Je peux répondre sur votre profil, vos congés, documents, paie, contrats, "
            "planning, formations et les procédures RH qui vous concernent."
        )

    if intro_kind == "thanks":
        return "Avec plaisir ! N'hésitez pas si vous avez d'autres questions RH."

    parts: list[str] = []
    if intro_kind not in ("greeting", "thanks"):
        parts.append(intro_kind)

    live_bullets = _extract_bullets(live_data, q_words, max_items=4) if live_data and "Aucune donnée" not in live_data else []
    if live_bullets:
        parts.append("\n".join(live_bullets))

    rag_chunks = _parse_rag_chunks(rag_text)
    if rag_chunks:
        ranked = sorted(
            rag_chunks,
            key=lambda c: _score_text(c[1], q_words, topics),
            reverse=True,
        )
        best_source, best_content = ranked[0]
        bullets = _extract_bullets(best_content, q_words, max_items=5)
        if bullets:
            if not live_bullets:
                parts.append("\n".join(bullets))
            elif _score_text(best_content, q_words, topics) > 2:
                parts.append("\n".join(bullets))

        if not bullets and best_content:
            snippet = best_content[:400].strip()
            if len(best_content) > 400:
                snippet += "…"
            parts.append(snippet)

        if "conges" in topics and not is_hr:
            parts.append(
                "\nSur la plateforme : menu « Congés » → « + Nouvelle demande », "
                "puis suivez vos demandes sur la même page."
            )
        if "contrats" in topics and not is_hr:
            parts.append(
                "\nConsultez le détail dans « Mes contrats » ou demandez une copie via « Documents administratifs »."
            )

        src_list = sources or [best_source]
        if src_list:
            unique_sources = list(dict.fromkeys(src_list))[:3]
            parts.append(f"\n📎 Source : {', '.join(unique_sources)}")
    elif not live_bullets:
        return ""

    if len(parts) == 1 and parts[0].startswith("Voici"):
        parts.append(
            "Je n'ai pas trouvé de détail précis. Reformulez votre question ou consultez "
            + ("le Centre d'actions ou le tableau de bord." if is_hr else "le menu correspondant (Congés, Mon profil, Documents…).")
        )

    return "\n\n".join(p for p in parts if p)
