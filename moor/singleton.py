from __future__ import annotations
from .sessiongate import SessionGate, active_gate


def require_gate() -> SessionGate:
    conn = active_gate()
    if conn is None:
        raise RuntimeError('Активное соединение Playerok не инициализировано')
    return conn
