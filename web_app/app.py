import os
import psycopg2
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_wtf.csrf import CSRFProtect

import database as db
import validators as v

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-change-in-production')
CSRFProtect(app)

STATUSES = ('confirmed', 'checked_in', 'checked_out', 'cancelled')
NEXT_STATUS = {'confirmed': 'checked_in', 'checked_in': 'checked_out'}
STATUS_UA = {
    'confirmed': 'Підтверджено', 'checked_in': 'Заселено',
    'checked_out': 'Виселено', 'cancelled': 'Скасовано',
    'free': 'Вільний', 'occupied': 'Зайнятий', 'maintenance': 'На ремонті',
}
app.jinja_env.filters['ua'] = lambda s: STATUS_UA.get(s, s)


def attempt(fn, *args):
    """Виконує запит; повертає (результат, текст_помилки)."""
    try:
        return fn(*args), None
    except psycopg2.Error as e:
        return None, db.friendly_error(e)


def notify(err, ok_message):
    flash(err or ok_message, 'error' if err else 'success')


@app.errorhandler(404)
def not_found(_):
    return render_template('error.html', message='Сторінку не знайдено'), 404


@app.errorhandler(psycopg2.Error)
def db_error(e):
    return render_template('error.html', message=db.friendly_error(e)), 500


# ======================= Головна =======================
@app.route('/')
def index():
    stats = db.fetch_one("""
        SELECT (SELECT COUNT(*) FROM guests) AS guests,
               (SELECT COUNT(*) FROM bookings
                 WHERE status IN ('confirmed', 'checked_in')) AS active_bookings,
               (SELECT COUNT(*) FROM v_room_status_today
                 WHERE current_state = 'occupied') AS occupied,
               (SELECT COUNT(*) FROM v_room_status_today
                 WHERE current_state = 'free') AS free_rooms,
               (SELECT COALESCE(SUM(balance_due), 0) FROM v_booking_details) AS debt
    """)
    return render_template('index.html', s=stats)


# ======================= Гості =======================
@app.route('/guests')
def guests():
    q = request.args.get('q', '').strip()
    rows = db.fetch_all("""
        SELECT * FROM v_guest_summary
        WHERE %(q)s = '' OR guest_name ILIKE %(p)s OR email ILIKE %(p)s
        ORDER BY guest_name
    """, {'q': q, 'p': f'%{q}%'})
    return render_template('guests.html', guests=rows, q=q)


@app.route('/guests/new', methods=['GET', 'POST'])
@app.route('/guests/<int:guest_id>/edit', methods=['GET', 'POST'])
def guest_form(guest_id=None):
    form, errors = {}, {}
    if guest_id:
        row = db.fetch_one("SELECT * FROM guests WHERE guest_id = %s", (guest_id,))
        if not row:
            abort(404)
        form = {k: '' if val is None else str(val) for k, val in row.items()}

    if request.method == 'POST':
        form = request.form.to_dict()
        data, errors = v.validate_guest(form)
        if not errors:
            values = (data['first_name'], data['last_name'], data['email'],
                      data['phone'], data['birth_date'])
            if guest_id:
                _, err = attempt(db.execute, """
                    UPDATE guests SET first_name=%s, last_name=%s, email=%s,
                                      phone=%s, birth_date=%s
                    WHERE guest_id=%s""", values + (guest_id,))
                notify(err, 'Дані гостя оновлено')
            else:
                _, err = attempt(db.execute, """
                    INSERT INTO guests (first_name, last_name, email, phone, birth_date)
                    VALUES (%s, %s, %s, %s, %s)""", values)
                notify(err, 'Гостя додано')
            if not err:
                return redirect(url_for('guests'))

    title = 'Редагування гостя' if guest_id else 'Новий гість'
    return render_template('guest_form.html', form=form, errors=errors, title=title)


@app.post('/guests/<int:guest_id>/delete')
def guest_delete(guest_id):
    count, err = attempt(db.execute, "DELETE FROM guests WHERE guest_id = %s", (guest_id,))
    if not err and count == 0:
        err = 'Гостя не знайдено'
    notify(err, 'Гостя видалено')
    return redirect(url_for('guests'))


# ======================= Номери =======================
AVAILABLE_SQL = """
    SELECT r.room_id, r.room_number, rt.name AS room_type, rt.capacity, rt.base_price,
           rt.base_price * (%(co)s::date - %(ci)s::date) AS total
    FROM rooms r
    INNER JOIN room_types rt ON rt.room_type_id = r.room_type_id
    WHERE r.status = 'available'
      AND rt.capacity >= %(g)s
      AND NOT EXISTS (
          SELECT 1 FROM bookings b
          WHERE b.room_id = r.room_id AND b.status <> 'cancelled'
            AND daterange(b.check_in, b.check_out) && daterange(%(ci)s, %(co)s))
    ORDER BY rt.base_price
"""


@app.route('/rooms')
def rooms():
    search, found, search_errors = request.args.to_dict(), None, {}
    if search.get('check_in') or search.get('check_out'):
        data, search_errors = v.validate_search(search)
        if not search_errors:
            found = db.fetch_all(AVAILABLE_SQL, {
                'ci': data['check_in'], 'co': data['check_out'], 'g': data['guests_count']})
    all_rooms = db.fetch_all("SELECT * FROM v_room_status_today ORDER BY room_number")
    return render_template('rooms.html', rooms=all_rooms, found=found,
                           search=search, search_errors=search_errors)


@app.post('/rooms/<int:room_id>/status')
def room_status(room_id):
    status = request.form.get('status')
    if status not in ('available', 'maintenance'):
        flash('Недопустимий статус', 'error')
    else:
        count, err = attempt(db.execute,
                             "UPDATE rooms SET status = %s WHERE room_id = %s", (status, room_id))
        if not err and count == 0:
            err = 'Номер не знайдено'
        notify(err, 'Статус номера оновлено')
    return redirect(url_for('rooms'))


# ======================= Бронювання =======================
@app.route('/bookings')
def bookings():
    status = request.args.get('status', '')
    if status not in STATUSES:
        status = ''
    rows = db.fetch_all("""
        SELECT * FROM v_booking_details
        WHERE %s = '' OR status = %s
        ORDER BY check_in DESC, booking_id DESC
    """, (status, status))
    return render_template('bookings.html', bookings=rows, status=status, statuses=STATUSES)


@app.route('/bookings/new', methods=['GET', 'POST'])
@app.route('/bookings/<int:booking_id>/edit', methods=['GET', 'POST'])
def booking_form(booking_id=None):
    booking, errors = None, {}
    if booking_id:
        booking = db.fetch_one("SELECT * FROM bookings WHERE booking_id = %s", (booking_id,))
        if not booking:
            abort(404)
        if booking['status'] not in ('confirmed', 'checked_in'):
            flash('Редагувати можна лише активні бронювання', 'error')
            return redirect(url_for('booking_detail', booking_id=booking_id))
        form = {k: str(booking[k]) for k in ('room_id', 'check_in', 'check_out', 'guests_count')}
    else:
        form = {k: request.args.get(k, '') for k in
                ('guest_id', 'room_id', 'check_in', 'check_out', 'guests_count')}
        form['guests_count'] = form['guests_count'] or '1'

    if request.method == 'POST':
        form = request.form.to_dict()
        data, errors = v.validate_booking(form, creating=booking is None)
        if not errors:
            if booking is None:
                row, err = attempt(db.fetch_one,
                                   "SELECT create_booking(%s, %s, %s, %s, %s) AS booking_id",
                                   (data['guest_id'], data['room_id'], data['check_in'],
                                    data['check_out'], data['guests_count']))
                target = row['booking_id'] if row else None
                notify(err, 'Бронювання створено')
            else:
                _, err = attempt(db.execute, """
                    UPDATE bookings
                    SET room_id=%s, check_in=%s, check_out=%s, guests_count=%s
                    WHERE booking_id=%s""",
                    (data['room_id'], data['check_in'], data['check_out'],
                     data['guests_count'], booking_id))
                target = booking_id
                notify(err, 'Бронювання оновлено, суму перераховано автоматично')
            if not err:
                return redirect(url_for('booking_detail', booking_id=target))

    guests_list = db.fetch_all(
        "SELECT guest_id, first_name || ' ' || last_name AS name FROM guests ORDER BY last_name")
    rooms_list = db.fetch_all("""
        SELECT r.room_id, r.room_number, rt.name, rt.capacity, rt.base_price
        FROM rooms r INNER JOIN room_types rt ON rt.room_type_id = r.room_type_id
        WHERE r.status = 'available' ORDER BY r.room_number""")
    return render_template('booking_form.html', form=form, errors=errors, booking=booking,
                           guests_list=guests_list, rooms_list=rooms_list)


@app.route('/bookings/<int:booking_id>')
def booking_detail(booking_id):
    b = db.fetch_one("SELECT * FROM v_booking_details WHERE booking_id = %s", (booking_id,))
    if not b:
        abort(404)
    invoice = db.fetch_all("SELECT * FROM get_booking_invoice(%s)", (booking_id,))
    payments = db.fetch_all(
        "SELECT * FROM payments WHERE booking_id = %s ORDER BY paid_at", (booking_id,))
    history = db.fetch_all(
        "SELECT * FROM booking_audit WHERE booking_id = %s ORDER BY changed_at, audit_id",
        (booking_id,))
    services = db.fetch_all("SELECT service_id, name, price FROM services ORDER BY name")
    return render_template('booking_detail.html', b=b, invoice=invoice, payments=payments,
                           history=history, services=services,
                           next_status=NEXT_STATUS.get(b['status']))


@app.post('/bookings/<int:booking_id>/status')
def booking_status(booking_id):
    row = db.fetch_one("SELECT status FROM bookings WHERE booking_id = %s", (booking_id,))
    if not row:
        abort(404)
    new_status = NEXT_STATUS.get(row['status'])   # допустимий перехід визначає сервер
    if not new_status:
        flash('Для цього статусу зміна неможлива', 'error')
    else:
        _, err = attempt(db.execute,
                         "UPDATE bookings SET status = %s WHERE booking_id = %s",
                         (new_status, booking_id))
        notify(err, f'Статус змінено: {STATUS_UA[new_status]}')
    return redirect(url_for('booking_detail', booking_id=booking_id))


@app.post('/bookings/<int:booking_id>/cancel')
def booking_cancel(booking_id):
    row, err = attempt(db.fetch_one, "CALL cancel_booking(%s, NULL::numeric)", (booking_id,))
    notify(err, f"Бронювання скасовано. До повернення гостю: "
                f"{row['p_refund'] if row else 0} грн")
    return redirect(url_for('booking_detail', booking_id=booking_id))


@app.post('/bookings/<int:booking_id>/services')
def booking_add_service(booking_id):
    data, errors = v.validate_service(request.form)
    if errors:
        flash('; '.join(errors.values()), 'error')
    else:
        _, err = attempt(db.execute, "CALL add_service_to_booking(%s, %s, %s)",
                         (booking_id, data['service_id'], data['quantity']))
        notify(err, 'Послугу додано')
    return redirect(url_for('booking_detail', booking_id=booking_id))


@app.post('/bookings/<int:booking_id>/payments')
def booking_add_payment(booking_id):
    data, errors = v.validate_payment(request.form)
    if errors:
        flash('; '.join(errors.values()), 'error')
    else:
        _, err = attempt(db.execute,
                         "INSERT INTO payments (booking_id, amount, method) VALUES (%s, %s, %s)",
                         (booking_id, data['amount'], data['method']))
        notify(err, 'Оплату зареєстровано')
    return redirect(url_for('booking_detail', booking_id=booking_id))


@app.post('/bookings/<int:booking_id>/delete')
def booking_delete(booking_id):
    count, err = attempt(db.execute,
                         "DELETE FROM bookings WHERE booking_id = %s", (booking_id,))
    if not err and count == 0:
        err = 'Бронювання не знайдено'
    notify(err, 'Бронювання видалено')
    return redirect(url_for('bookings'))


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)