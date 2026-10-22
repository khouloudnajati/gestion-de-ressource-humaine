"""Appels LLM pour l'assistant purement IA."""

from __future__ import annotations

import os

from .prompts import USER_PROMPT_TEMPLATE, get_platform_guide, get_system_prompt


def _has_api_key() -> bool:
    return bool(
        (
            os.getenv("OPENROUTER_API_KEY", "")
            or os.getenv("OPENAI_API_KEY", "")
            or os.getenv("GEMINI_API_KEY", "")
            or ""
        ).strip()
    )


def build_prompt(
    question: str,
    *,
    user_context: str,
    live_data: str,
    rag_context: str,
    sources: list[str],
    is_hr: bool = False,
) -> str:
    sources_note = f"\nSources RAG : {', '.join(sources[:5])}" if sources else ""
    return USER_PROMPT_TEMPLATE.format(
        system=get_system_prompt(is_hr),
        user_context=user_context,
        live_data=live_data,
        rag_context=rag_context or "Aucun extrait documentaire pertinent.",
        sources_note=sources_note,
        platform_guide=get_platform_guide(is_hr),
        question=question,
    )


def call_llm(prompt: str) -> str | None:
    """Essaie le fournisseur choisi puis les fournisseurs compatibles disponibles."""
    if not _has_api_key():
        return None

    provider = (os.getenv("LLM_PROVIDER", "openrouter") or "openrouter").lower()
    providers = [provider]
    for fallback in ("openrouter", "openai", "gemini"):
        if fallback not in providers:
            providers.append(fallback)

    for current_provider in providers:
        text = _call_provider(current_provider, prompt)
        if text:
            return text
    return None


def _call_provider(provider: str, prompt: str) -> str | None:
    if provider in {"openrouter", "openai"}:
        env_name = "OPENROUTER_API_KEY" if provider == "openrouter" else "OPENAI_API_KEY"
        api_key = os.getenv(env_name, "").strip()
        if not api_key:
            return None
        try:
            from openai import OpenAI
        except Exception:
            return None
        try:
            client_kwargs = {"api_key": api_key}
            if provider == "openrouter":
                client_kwargs["base_url"] = "https://openrouter.ai/api/v1"
                client_kwargs["default_headers"] = {
                    "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:8000"),
                    "X-Title": os.getenv("OPENROUTER_APP_NAME", "PeopleFlow RH"),
                }
            client = OpenAI(**client_kwargs)
            model = os.getenv(
                "OPENROUTER_MODEL" if provider == "openrouter" else "OPENAI_MODEL",
                "openai/gpt-4o-mini" if provider == "openrouter" else "gpt-4o-mini",
            )
            response = client.responses.create(model=model, input=prompt)
            text = getattr(response, "output_text", None)
            if not text:
                output = getattr(response, "output", None) or []
                text = ""
                for item in output:
                    for part in getattr(item, "content", None) or []:
                        text_part = getattr(part, "text", None)
                        if text_part:
                            text += text_part
            return (text or "").strip() or None
        except Exception:
            return None

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import google.generativeai as genai
    except Exception:
        return None

    try:
        genai.configure(api_key=api_key)
        model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        response = genai.GenerativeModel(model_name).generate_content(prompt)
        return (getattr(response, "text", None) or "").strip() or None
    except Exception:
        return None


def api_available() -> bool:
    return _has_api_key()
