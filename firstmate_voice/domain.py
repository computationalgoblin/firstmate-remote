"""Semantic state and the sole boundary from final assistant text to voice."""
import json
import re
from dataclasses import dataclass
from enum import StrEnum


class State(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting_for_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TRANSITIONS = {
    State.QUEUED: {State.RUNNING, State.CANCELLED},
    State.RUNNING: {State.WAITING, State.COMPLETED, State.FAILED, State.CANCELLED},
    State.WAITING: {State.QUEUED, State.CANCELLED},
    State.COMPLETED: set(), State.FAILED: set(), State.CANCELLED: set(),
}
TERMINAL = {State.COMPLETED, State.FAILED, State.CANCELLED}


def validate_transition(old: str, new: str) -> None:
    if new not in TRANSITIONS[State(old)]:
        raise ValueError(f"Invalid transition: {old} -> {new}")


@dataclass(frozen=True)
class Outcome:
    state: State
    spoken_response: str
    full_response: str = ""
    question: str = ""
    error: str = ""


def failed(error: str) -> Outcome:
    return Outcome(State.FAILED, "La petición no pudo completarse. Consulta el detalle en la CLI.", error=error)


def cancelled() -> Outcome:
    return Outcome(State.CANCELLED, "Petición cancelada.")


def parse_answer(answer: str) -> Outcome:
    # Only the causal final answer from the voice extension reaches this function.
    # No heuristic reading of prose, transcripts, screen output or diagnostics.
    candidates = re.findall(r"```json\s*(.*?)\s*```", answer, re.S)
    raw = candidates[-1] if candidates else answer
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Expected object")
        for key in ("spoken_response", "full_response", "question"):
            if not isinstance(value.get(key), str):
                raise ValueError(f"Missing or invalid {key}")
        if type(value.get("needs_input")) is not bool:
            raise ValueError("needs_input must be boolean")
        if not value["spoken_response"].strip() or len(value["spoken_response"]) > 900:
            raise ValueError("spoken_response must contain 1–900 characters")
        if value["needs_input"] and not 0 < len(value["question"].strip()) <= 900:
            raise ValueError("needs_input requires a concise question")
        return Outcome(State.WAITING if value["needs_input"] else State.COMPLETED,
                       value["spoken_response"], value["full_response"],
                       value["question"] if value["needs_input"] else "")
    except (ValueError, TypeError):
        return failed("Invalid structured voice response; raw answer withheld from user events")


def transcript(prompt: str, job_id: str, voice_session_id: str, kind: str) -> str:
    return (
        '[Interfaz de voz] Trabaja de forma autónoma. No expongas razonamiento, '
        'logs ni salida de herramientas. Termina con un único bloque ```json con '
        'spoken_response (1–3 frases, máximo 900 caracteres), full_response (detalle para el usuario), '
        'needs_input (booleano: true solo si necesitas intervención) y question '
        '(pregunta concisa o cadena vacía).\n'
        f'Conversación de voz: {voice_session_id}; trabajo: {job_id}; tipo: {kind}.\n'
        f'Petición del usuario:\n{prompt}'
    )
