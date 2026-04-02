from __future__ import annotations
from .conn import Conn, active_conn


def get_account() -> Conn:
    conn = active_conn()
    if conn is None:
        raise RuntimeError('Активное соединение Playerok не инициализировано')
    return conn
