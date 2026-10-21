import psycopg2
from psycopg2 import errors

class DatabaseConnection:
    def __init__(self, dbname='hotel_booking', user='postgres',
                 password='password', host='localhost', port=5433):
        self.conn_params = {
            'dbname': dbname, 'user': user, 'password': password,
            'host': host, 'port': port,
        }
        self.conn = None

    def connect(self):
        try:
            self.conn = psycopg2.connect(**self.conn_params)
            print("Успішне підключення до бази даних")
            return True
        except psycopg2.Error as e:
            print(f"Помилка підключення: {e}")
            return False

    def disconnect(self):
        if self.conn:
            self.conn.close()
            print("З'єднання закрито")

    def execute(self, query, params=None, fetch=False):
        """
        fetch=True  -> повертає список рядків (SELECT або ... RETURNING)
        fetch=False -> повертає кількість змінених рядків
        У разі помилки повертає None (перевіряйте через `is None`).
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(query, params)
                result = cur.fetchall() if fetch else cur.rowcount
            self.conn.commit()
            return result
        except errors.ExclusionViolation:
            self.conn.rollback()
            print("❌ Цей номер уже заброньовано на перетинні дати")
        except errors.UniqueViolation as e:
            self.conn.rollback()
            print(f"❌ Таке значення вже існує: {e.diag.message_detail}")
        except errors.ForeignKeyViolation as e:
            self.conn.rollback()
            print(f"❌ Порушення зв'язку між таблицями: {e.diag.message_detail}")
        except errors.CheckViolation as e:
            self.conn.rollback()
            print(f"❌ Порушено обмеження: {e.diag.constraint_name}")
        except psycopg2.Error as e:
            self.conn.rollback()
            print(f"❌ Помилка БД: {e.diag.message_primary or e}")
        return None