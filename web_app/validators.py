import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
PHONE_RE = re.compile(r'^\+?[0-9\s\-()]{7,20}$')
PAYMENT_METHODS = ('card', 'cash', 'transfer')


def _date(value):
    try:
        return datetime.strptime((value or '').strip(), '%Y-%m-%d').date()
    except ValueError:
        return None


def _int(value):
    try:
        return int((value or '').strip())
    except (ValueError, AttributeError):
        return None


def validate_guest(f):
    d, e = {}, {}
    for key, label in (('first_name', "Ім’я"), ('last_name', 'Прізвище')):
        val = (f.get(key) or '').strip()
        if not val:
            e[key] = f'{label} обов’язкове'
        elif len(val) > 50:
            e[key] = 'Не більше 50 символів'
        d[key] = val

    email = (f.get('email') or '').strip().lower()
    if not email:
        e['email'] = 'Email обов’язковий'
    elif len(email) > 100 or not EMAIL_RE.match(email):
        e['email'] = 'Некоректний email'
    d['email'] = email

    phone = (f.get('phone') or '').strip()
    if phone and not PHONE_RE.match(phone):
        e['phone'] = 'Некоректний телефон (7-20 цифр, можна +, пробіли, дужки)'
    d['phone'] = phone or None

    birth = (f.get('birth_date') or '').strip()
    d['birth_date'] = None
    if birth:
        parsed = _date(birth)
        if parsed is None:
            e['birth_date'] = 'Некоректна дата'
        elif parsed >= date.today():
            e['birth_date'] = 'Дата народження має бути в минулому'
        else:
            d['birth_date'] = parsed
    return d, e


def validate_search(f):
    d, e = {}, {}
    d['check_in'], d['check_out'] = _date(f.get('check_in')), _date(f.get('check_out'))
    if d['check_in'] is None:
        e['check_in'] = 'Вкажіть коректну дату заїзду'
    if d['check_out'] is None:
        e['check_out'] = 'Вкажіть коректну дату виїзду'
    if not e and d['check_out'] <= d['check_in']:
        e['check_out'] = 'Виїзд має бути пізніше заїзду'
    d['guests_count'] = _int(f.get('guests_count')) or 1
    if not 1 <= d['guests_count'] <= 10:
        e['guests_count'] = 'Кількість гостей: від 1 до 10'
    return d, e


def validate_booking(f, creating=True):
    d, e = validate_search(f)
    if creating:
        d['guest_id'] = _int(f.get('guest_id'))
        if not d['guest_id']:
            e['guest_id'] = 'Оберіть гостя'
    d['room_id'] = _int(f.get('room_id'))
    if not d['room_id']:
        e['room_id'] = 'Оберіть номер'
    if creating and d['check_in'] and d['check_in'] < date.today():
        e['check_in'] = 'Дата заїзду не може бути в минулому'
    if not e and (d['check_out'] - d['check_in']).days > 365:
        e['check_out'] = 'Максимальний термін проживання: 365 ночей'
    return d, e


def validate_payment(f):
    d, e = {}, {}
    try:
        amount = Decimal((f.get('amount') or '').replace(',', '.').strip())
        if amount <= 0:
            e['amount'] = 'Сума має бути більше нуля'
        elif amount.as_tuple().exponent < -2 or amount >= Decimal('10000000'):
            e['amount'] = 'Не більше 2 знаків після коми і менше 10 000 000'
        d['amount'] = amount
    except InvalidOperation:
        e['amount'] = 'Введіть суму числом'
    d['method'] = f.get('method')
    if d['method'] not in PAYMENT_METHODS:
        e['method'] = 'Оберіть спосіб оплати'
    return d, e


def validate_service(f):
    d, e = {}, {}
    d['service_id'] = _int(f.get('service_id'))
    if not d['service_id']:
        e['service_id'] = 'Оберіть послугу'
    d['quantity'] = _int(f.get('quantity'))
    if d['quantity'] is None or not 1 <= d['quantity'] <= 100:
        e['quantity'] = 'Кількість: від 1 до 100'
    return d, e