"""Внутренняя модель текущего пользователя (transport object, не API schema)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """Текущий аутентифицированный пользователь.

    Frozen — user context не должен мутироваться в ходе запроса.
    """

    id: str
    email: str
    is_admin: bool
