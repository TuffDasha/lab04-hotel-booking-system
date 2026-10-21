from datetime import datetime
from database import DatabaseConnection

BOOKING_STATUSES = ['confirmed', 'checked_in', 'checked_out', 'cancelled']
ROOM_STATUSES = ['available', 'maintenance']


# ---------- допоміжні функції введення/виведення ----------
def ask(prompt, required=True):
    while True:
        value = input(prompt).strip()
        if value or not required:
            return value or None
        print("Поле обов'язкове")


def ask_int(prompt, min_value=None):
    while True:
        try:
            value = int(input(prompt).strip())
            if min_value is not None and value < min_value:
                print(f"Значення має бути не менше {min_value}")
                continue
            return value
        except ValueError:
            print("Введіть ціле число")


def ask_date(prompt, required=True):
    while True:
        value = input(prompt + " (РРРР-ММ-ДД): ").strip()
        if not value and not required:
            return None
        try:
            return datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            print("Невірний формат дати")


def ask_choice(prompt, options):
    print(f"{prompt}: {', '.join(options)}")
    while True:
        value = input("> ").strip()
        if value in options:
            return value
        print("Оберіть одне зі значень зі списку")


def print_table(headers, rows):
    if not rows:
        print("Нічого не знайдено")
        return
    data = [['—' if c is None else str(c) for c in row] for row in rows]
    widths = [max(len(h), *(len(r[i]) for r in data)) for i, h in enumerate(headers)]
    print()
    print(' | '.join(h.ljust(w) for h, w in zip(headers, widths)))
    print('-+-'.join('-' * w for w in widths))
    for r in data:
        print(' | '.join(c.ljust(w) for c, w in zip(r, widths)))


# ---------- гості ----------
def list_guests(db):
    rows = db.execute("""
        SELECT guest_id, first_name, last_name, email, phone, birth_date
        FROM guests ORDER BY last_name, first_name
    """, fetch=True)
    if rows is not None:
        print_table(['ID', "Ім'я", 'Прізвище', 'Email', 'Телефон', 'Дата нар.'], rows)


def search_guests(db):
    term = ask("Ім'я, прізвище або email: ")
    pattern = f"%{term}%"
    rows = db.execute("""
        SELECT guest_id, first_name, last_name, email, phone
        FROM guests
        WHERE first_name ILIKE %s OR last_name ILIKE %s OR email ILIKE %s
        ORDER BY last_name
    """, (pattern, pattern, pattern), fetch=True)
    if rows is not None:
        print_table(['ID', "Ім'я", 'Прізвище', 'Email', 'Телефон'], rows)


def add_guest(db):
    print("\n--- Новий гість ---")
    first = ask("Ім'я: ")
    last = ask("Прізвище: ")
    email = ask("Email: ")
    phone = ask("Телефон (Enter - пропустити): ", required=False)
    birth = ask_date("Дата народження (Enter - пропустити)", required=False)
    rows = db.execute("""
        INSERT INTO guests (first_name, last_name, email, phone, birth_date)
        VALUES (%s, %s, %s, %s, %s) RETURNING guest_id
    """, (first, last, email, phone, birth), fetch=True)
    if rows:
        print(f"✅ Гостя додано, ID: {rows[0][0]}")


def update_guest(db):
    list_guests(db)
    guest_id = ask_int("\nID гостя для редагування: ", 1)
    print("Залиште поле порожнім, щоб не змінювати")
    email = ask("Новий email: ", required=False)
    phone = ask("Новий телефон: ", required=False)
    count = db.execute("""
        UPDATE guests
        SET email = COALESCE(%s, email), phone = COALESCE(%s, phone)
        WHERE guest_id = %s
    """, (email, phone, guest_id))
    if count is not None:
        print("✅ Дані оновлено" if count else "Гостя з таким ID не знайдено")


def delete_guest(db):
    list_guests(db)
    guest_id = ask_int("\nID гостя для видалення: ", 1)
    if input("Ви впевнені? (так/ні): ").strip().lower() != 'так':
        return
    count = db.execute("DELETE FROM guests WHERE guest_id = %s", (guest_id,))
    if count is not None:
        print("✅ Гостя видалено" if count else "Гостя з таким ID не знайдено")


# ---------- номери ----------
def list_rooms(db):
    rows = db.execute("""
        SELECT r.room_id, r.room_number, r.floor, rt.name, rt.capacity,
               rt.base_price, r.status
        FROM rooms r
        INNER JOIN room_types rt ON rt.room_type_id = r.room_type_id
        ORDER BY r.room_number
    """, fetch=True)
    if rows is not None:
        print_table(['ID', 'Номер', 'Поверх', 'Тип', 'Місць', 'Ціна/ніч', 'Статус'], rows)


def available_rooms(db, check_in, check_out, guests_count):
    return db.execute("""
        SELECT r.room_id, r.room_number, rt.name, rt.capacity, rt.base_price
        FROM rooms r
        INNER JOIN room_types rt ON rt.room_type_id = r.room_type_id
        WHERE r.status = 'available'
          AND rt.capacity >= %s
          AND NOT EXISTS (
              SELECT 1 FROM bookings b
              WHERE b.room_id = r.room_id
                AND b.status <> 'cancelled'
                AND daterange(b.check_in, b.check_out) && daterange(%s, %s)
          )
        ORDER BY rt.base_price
    """, (guests_count, check_in, check_out), fetch=True)


def find_available_rooms(db):
    check_in = ask_date("Дата заїзду")
    check_out = ask_date("Дата виїзду")
    if check_out <= check_in:
        print("❌ Дата виїзду має бути пізніше дати заїзду")
        return
    guests_count = ask_int("Кількість гостей: ", 1)
    rows = available_rooms(db, check_in, check_out, guests_count)
    if rows is not None:
        print_table(['ID', 'Номер', 'Тип', 'Місць', 'Ціна/ніч'], rows)


def change_room_status(db):
    list_rooms(db)
    room_id = ask_int("\nID номера: ", 1)
    status = ask_choice("Новий статус", ROOM_STATUSES)
    count = db.execute("UPDATE rooms SET status = %s WHERE room_id = %s", (status, room_id))
    if count is not None:
        print("✅ Статус оновлено" if count else "Номер не знайдено")


# ---------- бронювання ----------
def list_bookings(db):
    rows = db.execute("""
        SELECT b.booking_id,
               g.first_name || ' ' || g.last_name,
               r.room_number, rt.name,
               b.check_in, b.check_out, b.guests_count,
               b.status, b.total_price
        FROM bookings b
        INNER JOIN guests g      ON g.guest_id = b.guest_id
        INNER JOIN rooms r       ON r.room_id = b.room_id
        INNER JOIN room_types rt ON rt.room_type_id = r.room_type_id
        ORDER BY b.booking_id
    """, fetch=True)
    if rows is not None:
        print_table(['ID', 'Гість', 'Номер', 'Тип', 'Заїзд', 'Виїзд',
                     'Гостей', 'Статус', 'Сума'], rows)


def create_booking(db):
    print("\n--- Нове бронювання ---")
    list_guests(db)
    guest_id = ask_int("\nID гостя: ", 1)
    check_in = ask_date("Дата заїзду")
    check_out = ask_date("Дата виїзду")
    if check_out <= check_in:
        print("❌ Дата виїзду має бути пізніше дати заїзду")
        return
    guests_count = ask_int("Кількість гостей: ", 1)

    rooms = available_rooms(db, check_in, check_out, guests_count)
    if not rooms:
        print("На ці дати вільних підходящих номерів немає")
        return
    print_table(['ID', 'Номер', 'Тип', 'Місць', 'Ціна/ніч'], rooms)
    room_id = ask_int("\nID номера: ", 1)

    # Сума = кількість ночей * ціна за ніч типу номера.
    # Підзапит одразу перевіряє, що номер доступний і вміщує гостей.
    rows = db.execute("""
        INSERT INTO bookings (guest_id, room_id, check_in, check_out,
                              guests_count, total_price)
        SELECT %s, r.room_id, %s, %s, %s, rt.base_price * (%s::date - %s::date)
        FROM rooms r
        INNER JOIN room_types rt ON rt.room_type_id = r.room_type_id
        WHERE r.room_id = %s AND r.status = 'available' AND rt.capacity >= %s
        RETURNING booking_id, total_price
    """, (guest_id, check_in, check_out, guests_count,
          check_out, check_in, room_id, guests_count), fetch=True)
    if rows is None:
        return
    if not rows:
        print("❌ Номер не знайдено, на ремонті або замалий для такої кількості гостей")
        return
    print(f"✅ Бронювання створено, ID: {rows[0][0]}, сума: {rows[0][1]} грн")


def change_booking_status(db):
    list_bookings(db)
    booking_id = ask_int("\nID бронювання: ", 1)
    status = ask_choice("Новий статус", BOOKING_STATUSES)
    count = db.execute("UPDATE bookings SET status = %s WHERE booking_id = %s",
                       (status, booking_id))
    if count is not None:
        print("✅ Статус оновлено" if count else "Бронювання не знайдено")


def change_booking_dates(db):
    list_bookings(db)
    booking_id = ask_int("\nID бронювання: ", 1)
    check_in = ask_date("Нова дата заїзду")
    check_out = ask_date("Нова дата виїзду")
    count = db.execute("""
        UPDATE bookings b
        SET check_in = %s, check_out = %s,
            total_price = rt.base_price * (%s::date - %s::date)
        FROM rooms r
        INNER JOIN room_types rt ON rt.room_type_id = r.room_type_id
        WHERE r.room_id = b.room_id AND b.booking_id = %s
    """, (check_in, check_out, check_out, check_in, booking_id))
    if count is not None:
        print("✅ Дати та суму оновлено" if count else "Бронювання не знайдено")


def delete_booking(db):
    list_bookings(db)
    booking_id = ask_int("\nID бронювання для видалення: ", 1)
    print("Разом із бронюванням буде видалено його оплати та послуги.")
    if input("Ви впевнені? (так/ні): ").strip().lower() != 'так':
        return
    count = db.execute("DELETE FROM bookings WHERE booking_id = %s", (booking_id,))
    if count is not None:
        print("✅ Бронювання видалено" if count else "Бронювання не знайдено")


# ---------- меню ----------
MENU = [
    ("ГОСТІ", None),
    ("Переглянути гостей", list_guests),
    ("Знайти гостя", search_guests),
    ("Додати гостя", add_guest),
    ("Редагувати гостя", update_guest),
    ("Видалити гостя", delete_guest),
    ("НОМЕРИ", None),
    ("Переглянути номери", list_rooms),
    ("Знайти вільні номери на дати", find_available_rooms),
    ("Змінити статус номера", change_room_status),
    ("БРОНЮВАННЯ", None),
    ("Переглянути бронювання", list_bookings),
    ("Створити бронювання", create_booking),
    ("Змінити статус бронювання", change_booking_status),
    ("Змінити дати бронювання", change_booking_dates),
    ("Видалити бронювання", delete_booking),
]


def main():
    db = DatabaseConnection()
    if not db.connect():
        return

    actions = {}
    n = 0
    for title, func in MENU:
        if func:
            n += 1
            actions[str(n)] = func

    while True:
        print("\n" + "=" * 50)
        print("СИСТЕМА БРОНЮВАННЯ ГОТЕЛІВ")
        print("=" * 50)
        n = 0
        for title, func in MENU:
            if func is None:
                print(f"\n  [{title}]")
            else:
                n += 1
                print(f"  {n:>2}. {title}")
        print("\n   0. Вихід")

        choice = input("\nОберіть опцію: ").strip()
        if choice == '0':
            break
        if choice in actions:
            actions[choice](db)
            input("\nНатисніть Enter для продовження...")
        else:
            print("❌ Невірна опція")

    db.disconnect()


if __name__ == "__main__":
    main()