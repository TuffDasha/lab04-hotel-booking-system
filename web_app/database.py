import os
import psycopg2
from psycopg2 import errors
from psycopg2.extras import RealDictCursor

DSN = {
    'dbname':   os.getenv('DB_NAME', 'hotel_booking'),
    'user':     os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'password'),
    'host':     os.getenv('DB_HOST', 'localhost'),
    'port':     int(os.getenv('DB_PORT', 5433)),
}


def _run(sql, params, mode):
    # нове з'єднання на кожен запит: просто і безпечно для багатопоточного Flask
    conn = psycopg2.connect(**DSN)
    try:
        with conn:  # commit при успіху, rollback при помилці
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                if mode == 'all':
                    return cur.fetchall()
                if mode == 'one':
                    return cur.fetchone()
                return cur.rowcount
    finally:
        conn.close()


def fetch_all(sql, params=None):
    return _run(sql, params, 'all')


def fetch_one(sql, params=None):
    return _run(sql, params, 'one')


def execute(sql, params=None):
    return _run(sql, params, 'count')


def friendly_error(e):
    """Перетворює помилку PostgreSQL на повідомлення для користувача."""
    if isinstance(e, errors.ExclusionViolation):
        return "Цей номер уже заброньовано на перетинні дати"
    if isinstance(e, errors.UniqueViolation):
        return "Запис з такими даними вже існує (перевірте email)"
    if isinstance(e, errors.ForeignKeyViolation):
        return "Операція неможлива: запис пов’язаний з іншими даними (наприклад, у гостя є бронювання)"
    if isinstance(e, errors.CheckViolation):
        return f"Порушено обмеження: {e.diag.constraint_name}"
    # RAISE EXCEPTION з наших процедур і тригерів
    return getattr(e.diag, 'message_primary', None) or str(e)