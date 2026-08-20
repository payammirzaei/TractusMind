from contextvars import ContextVar, Token
from dataclasses import dataclass, field

from opentelemetry import trace


@dataclass
class AnswerTrace:
    stage_durations: dict[str, float] = field(default_factory=dict)


_TRACE_CONTEXT: ContextVar[AnswerTrace | None] = ContextVar(
    "tractusmind_answer_trace",
    default=None,
)


def begin_answer_trace() -> Token:
    return _TRACE_CONTEXT.set(AnswerTrace())


def record_stage_duration(stage: str, duration_seconds: float) -> None:
    current = _TRACE_CONTEXT.get()
    if current is not None:
        current.stage_durations[stage] = (
            current.stage_durations.get(stage, 0.0) + duration_seconds
        )


def finish_answer_trace(token: Token) -> AnswerTrace:
    current = _TRACE_CONTEXT.get() or AnswerTrace()
    _TRACE_CONTEXT.reset(token)
    return current


def current_trace_id() -> str | None:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None
    return f"{span_context.trace_id:032x}"
