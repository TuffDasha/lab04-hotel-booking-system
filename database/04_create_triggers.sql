-- Таблиця аудиту змін статусу бронювань
-- (без FOREIGN KEY: історія має зберігатися, навіть якщо бронювання видалять)
CREATE TABLE booking_audit (
    audit_id   SERIAL PRIMARY KEY,
    booking_id INT NOT NULL,
    old_status VARCHAR(20),
    new_status VARCHAR(20),
    changed_by VARCHAR(50) NOT NULL DEFAULT current_user,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ==========================================================
-- Тригер 1: автоматичний розрахунок вартості проживання
-- ==========================================================
CREATE OR REPLACE FUNCTION calc_booking_total() RETURNS TRIGGER AS $$
DECLARE
    v_price DECIMAL;
BEGIN
    SELECT rt.base_price INTO v_price
    FROM rooms r
    INNER JOIN room_types rt ON rt.room_type_id = r.room_type_id
    WHERE r.room_id = NEW.room_id;

    NEW.total_price := v_price * (NEW.check_out - NEW.check_in);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_booking_calc_total
BEFORE INSERT OR UPDATE OF room_id, check_in, check_out ON bookings
FOR EACH ROW
EXECUTE FUNCTION calc_booking_total();

-- ==========================================================
-- Тригер 2: аудит змін статусу бронювання
-- ==========================================================
CREATE OR REPLACE FUNCTION log_booking_status_change() RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO booking_audit (booking_id, old_status, new_status)
    VALUES (NEW.booking_id, OLD.status, NEW.status);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_booking_status_audit
AFTER UPDATE OF status ON bookings
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION log_booking_status_change();

-- ==========================================================
-- Тригер 3: бізнес-валідація бронювання (запобіжник на рівні БД)
-- ==========================================================
CREATE OR REPLACE FUNCTION validate_booking() RETURNS TRIGGER AS $$
DECLARE
    v_room_status VARCHAR;
    v_capacity    INT;
BEGIN
    IF NEW.status = 'cancelled' THEN
        RETURN NEW;
    END IF;

    SELECT r.status, rt.capacity INTO v_room_status, v_capacity
    FROM rooms r
    INNER JOIN room_types rt ON rt.room_type_id = r.room_type_id
    WHERE r.room_id = NEW.room_id;

    IF v_room_status <> 'available'
       AND (TG_OP = 'INSERT' OR NEW.room_id IS DISTINCT FROM OLD.room_id) THEN
        RAISE EXCEPTION 'Номер недоступний для бронювання (статус: %)', v_room_status;
    END IF;

    IF NEW.guests_count > v_capacity THEN
        RAISE EXCEPTION 'Кількість гостей (%) перевищує місткість номера (%)',
            NEW.guests_count, v_capacity;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_booking_validate
BEFORE INSERT OR UPDATE OF room_id, guests_count, status ON bookings
FOR EACH ROW
EXECUTE FUNCTION validate_booking();

-- ==========================================================
-- Тригер 4: контроль оплат (не більше вартості, не для скасованих)
-- ==========================================================
CREATE OR REPLACE FUNCTION check_payment() RETURNS TRIGGER AS $$
DECLARE
    v_status VARCHAR;
    v_total  DECIMAL;
    v_paid   DECIMAL;
BEGIN
    SELECT b.status,
           b.total_price + COALESCE((
               SELECT SUM(bs.quantity * s.price)
               FROM booking_services bs
               INNER JOIN services s ON s.service_id = bs.service_id
               WHERE bs.booking_id = b.booking_id), 0)
    INTO v_status, v_total
    FROM bookings b
    WHERE b.booking_id = NEW.booking_id;

    IF NOT FOUND THEN
        RETURN NEW;   -- помилку видасть зовнішній ключ
    END IF;

    IF v_status = 'cancelled' THEN
        RAISE EXCEPTION 'Не можна приймати оплату за скасоване бронювання';
    END IF;

    SELECT COALESCE(SUM(p.amount), 0) INTO v_paid
    FROM payments p WHERE p.booking_id = NEW.booking_id;

    IF v_paid + NEW.amount > v_total THEN
        RAISE EXCEPTION 'Сума оплат (%) перевищує вартість бронювання (%)',
            v_paid + NEW.amount, v_total;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_payment_check
BEFORE INSERT ON payments
FOR EACH ROW
EXECUTE FUNCTION check_payment();