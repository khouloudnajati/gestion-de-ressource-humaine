"""
Moteur assistant RH 100 % IA.
Pipeline : contrôle d'accès → données métier → LLM → synthèse RAG.
"""

from __future__ import annotations

from hr.rag import rag_search
from hr.services import build_user_context, local_chat_answer

from .access import employee_access_denial
from .context_builder import build_live_data_context, build_user_context_summary
from .llm import api_available, build_prompt, call_llm
from .prompts import get_no_context_fallback
from .synthesizer import synthesize_adapted_answer

_POLICY_KEYWORDS = (
    "horaire", "heure", "travail", "règlement", "reglement", "politique",
    "procédure", "procedure", "haccp", "hygiène", "hygiene", "sécurité", "securite",
)


_GENERIC_MARKERS = (
    "je peux répondre à des questions concrètes",
    "je peux répondre sur toute la plateforme rh",
    "je peux répondre sur vos informations personnelles",
    "posez une question précise",
    "je peux vous aider sur",
    "que souhaitez-vous faire",
)


def _is_policy_question(question: str) -> bool:
    q = question.lower()
    # « contrat de travail » = dossier employé, pas règlement / horaires
    if any(k in q for k in ("contrat", "contra", "cdi", "cdd")):
        return False
    return any(k in q for k in _POLICY_KEYWORDS)


def _is_generic(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in _GENERIC_MARKERS)


def pure_ai_answer(question: str, user=None) -> str:
    """
    Réponse assistant adaptée au rôle :
    - RH : plateforme complète + tous les employés
    - Employé : uniquement son dossier personnel + procédures RAG
    """
    question = (question or "").strip()
    if not question:
        return "Posez une question pour que je puisse vous aider."

    ctx = build_user_context(user) if user and user.is_authenticated else {}
    is_hr = bool(ctx.get("is_hr"))

    denial = employee_access_denial(question, ctx)
    if denial:
        return denial

    user_ctx = build_user_context_summary(user)
    live_data = build_live_data_context(question, user)
    rag = rag_search(question)
    rag_text = rag.get("text") or ""
    sources = rag.get("sources") or []

    local = local_chat_answer(question, ctx)
    if local and not _is_generic(local) and not _is_policy_question(question):
        return local

    prompt = build_prompt(
        question,
        user_context=user_ctx,
        live_data=live_data,
        rag_context=rag_text,
        sources=sources,
        is_hr=is_hr,
    )

    llm_response = call_llm(prompt)
    if llm_response:
        if sources and "📎" not in llm_response:
            llm_response += f"\n\n📎 Sources (RAG) : {', '.join(sources[:3])}"
        return llm_response

    adapted = synthesize_adapted_answer(
        question,
        rag_text=rag_text,
        sources=sources,
        live_data=live_data,
        user_name=ctx.get("name", ""),
        is_hr=is_hr,
    )
    if adapted:
        return adapted

    if local:
        return local

    if api_available():
        return get_no_context_fallback(is_hr)

    return (
        "⚠️ Pour des réponses encore plus riches, configurez une clé API valide "
        "(GEMINI_API_KEY) dans le fichier .env.\n\n"
        + get_no_context_fallback(is_hr)
    )
