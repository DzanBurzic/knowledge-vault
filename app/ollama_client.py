"""Thin client for the local Ollama server (chat + embeddings). No cloud AI (R58)."""

import numpy as np
import requests


class OllamaError(Exception):
    pass


def base_url(cfg: dict) -> str:
    return cfg.get("ollama_url", "http://localhost:11434").rstrip("/")


def is_up(cfg: dict, timeout: float = 3.0) -> bool:
    try:
        r = requests.get(f"{base_url(cfg)}/api/tags", timeout=timeout)
        return r.status_code == 200
    except requests.RequestException:
        return False


def list_models(cfg: dict) -> list[str]:
    try:
        r = requests.get(f"{base_url(cfg)}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except requests.RequestException:
        return []


def has_model(cfg: dict, name: str) -> bool:
    wanted = name.split(":")[0]
    for m in list_models(cfg):
        if m == name or m.split(":")[0] == wanted:
            return True
    return False


def status(cfg: dict) -> tuple[bool, str]:
    """(ok, plain-language message) used by the dashboard status area (R31)."""
    if not is_up(cfg):
        return False, "Ollama is not running — start it and processing will resume."
    missing = [
        m for m in (cfg["chat_model"], cfg["embedding_model"]) if not has_model(cfg, m)
    ]
    if missing:
        return False, (
            "Ollama is running but these models are missing: "
            + ", ".join(missing)
            + ". Run the setup again (or `ollama pull <model>`) and processing will resume."
        )
    return True, "Ollama is running."


def chat(cfg: dict, messages: list[dict], schema: dict | None = None,
         timeout: float = 600.0) -> str:
    """One chat call with thinking disabled (R29) and optional structured output (R25)."""
    payload = {
        "model": cfg["chat_model"],
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.3, "num_ctx": 16384},
    }
    if schema is not None:
        payload["format"] = schema
    try:
        r = requests.post(f"{base_url(cfg)}/api/chat", json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()["message"]["content"]
    except requests.RequestException as e:
        raise OllamaError(f"Ollama chat call failed: {e}") from e
    except (KeyError, ValueError) as e:
        raise OllamaError(f"Unexpected Ollama response: {e}") from e


def embed(cfg: dict, text: str, timeout: float = 120.0) -> np.ndarray:
    """Return a unit-normalized float32 embedding vector (R30)."""
    try:
        r = requests.post(
            f"{base_url(cfg)}/api/embed",
            json={"model": cfg["embedding_model"], "input": [text]},
            timeout=timeout,
        )
        r.raise_for_status()
        vec = np.asarray(r.json()["embeddings"][0], dtype=np.float32)
    except requests.RequestException as e:
        raise OllamaError(f"Ollama embedding call failed: {e}") from e
    except (KeyError, IndexError, ValueError) as e:
        raise OllamaError(f"Unexpected Ollama embed response: {e}") from e
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm
    return vec
