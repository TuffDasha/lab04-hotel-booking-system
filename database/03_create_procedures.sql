-- ==========================================================
-- Процедура 1: створення бронювання з повною перевіркою
-- Сума рахується тригером trg_booking_calc_total
-- ==========================================================
CREATE OR REPLACE FUNCTION create_booking(
    p_guest_id     INT,
    p_room_id      INT,
    p_check_in     DATE,
    p_check_out    DATE,
    p_guests_count INT DEFAULT 1
) RETURNS INT AS $$
DECLARE
    v_capacity    INT;
    v_room_status VARCHAR;
    v_booking_id  INT;
BEGIN
    IF p_check_out <= p_check_in THEN
        RAISE EXCEPTION 'Дата виїзду (%) має бути пізніше дати заїзду (%)', p_check_out, p_check_in;
    END IF;
    IF p_check_in < CURRENT_DATE THEN
        RAISE EXCEPTION 'Дата заїзду не може бути в минулому';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM guests WHERE guest_id = p_guest_id) THEN
        RAISE EXCEPTION 'Гостя з ID % не знайдено', p_guest_id;
    END IF;

    SELECT rt.capacity, r.status
    INTO v_capacity, v_room_status
    FROM rooms r
    INNER JOIN room_types rt ON rt.room_type_id = r.room_type_id
    WHERE r.room_id = p_room_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Номер з ID % не знайдено', p_room_id;
    END IF;
    IF v_room_status <> 'available' THEN
        RAISE EXCEPTION 'Номер % недоступний (статус: %)', p_room_id, v_room_status;
    END IF;
    IF p_guests_count > v_capacity THEN
        RAISE EXCEPTION 'Номер вміщує максимум % гостей, вказано %', v_capacity, p_guests_count;
    END IF;

    BEGIN
        INSERT INTO bookings (guest_id, room_id, check_in, check_out, guests_count)
        VALUES (p_guest_id, p_room_id, p_check_in, p_check_out, p_guests_count)
        RETURNING booking_id INTO v_booking_id;
    EXCEPTION
        WHEN exclusion_violation THEN
            RAISE EXCEPTION 'Номер % уже заброньовано на дати % - %',
                p_room_id, p_check_in, p_check_out;
    END;

    RETURN v_booking_id;
END;
$$ LANGUAGE plpgsql;


-- ==========================================================
-- Процедура 2: скасування бронювання з розрахунком повернення коштів
-- Політика: безкоштовно за 3 і більше днів до заїзду,
-- інакше утримується вартість першої ночі.
-- ==========================================================
CREATE OR REPLACE PROCEDURE cancel_booking(
    IN    p_booking_id INT,
    INOUT p_refund     DECIMAL
) LANGUAGE plpgsql AS $$
DECLARE
    v_b       bookings%ROWTYPE;
    v_paid    DECIMAL;
    v_penalty DECIMAL := 0;
BEGIN
    SELECT * INTO v_b FROM bookings WHERE booking_id = p_booking_id FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Бронювання % не знайдено', p_booking_id;
    END IF;
    IF v_b.status <> 'confirmed' THEN
        RAISE EXCEPTION 'Скасувати можна лише підтверджене бронювання (поточний статус: %)', v_b.status;
    END IF;

    SELECT COALESCE(SUM(p.amount), 0) INTO v_paid
    FROM payments p WHERE p.booking_id = p_booking_id;

    IF v_b.check_in - CURRENT_DATE < 3 THEN
        v_penalty := v_b.total_price / (v_b.check_out - v_b.check_in);  -- вартість однієї ночі
    END IF;

    p_refund := GREATEST(0, v_paid - v_penalty);

    UPDATE bookings SET status = 'cancelled' WHERE booking_id = p_booking_id;
END;
$$;


-- ==========================================================
-- Процедура 3: додавання послуги до бронювання (upsert кількості)
-- ==========================================================
CREATE OR REPLACE PROCEDURE add_service_to_booking(
    p_booking_id INT,
    p_service_id INT,
    p_quantity   INT DEFAULT 1
) LANGUAGE plpgsql AS $$
DECLARE
    v_status VARCHAR;
BEGIN
    IF p_quantity <= 0 THEN
        RAISE EXCEPTION 'Кількість має бути більше нуля';
    END IF;

    SELECT status INTO v_status FROM bookings WHERE booking_id = p_booking_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Бронювання % не знайдено', p_booking_id;
    END IF;
    IF v_status IN ('cancelled', 'checked_out') THEN
        RAISE EXCEPTION 'Не можна додавати послуги до бронювання зі статусом %', v_status;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM services WHERE service_id = p_service_id) THEN
        RAISE EXCEPTION 'Послугу з ID % не знайдено', p_service_id;
    END IF;

    INSERT INTO booking_services (booking_id, service_id, quantity)
    VALUES (p_booking_id, p_service_id, p_quantity)
    ON CONFLICT (booking_id, service_id)
    DO UPDATE SET quantity = booking_services.quantity + EXCLUDED.quantity;
END;
$$;


-- ==========================================================
-- Процедура 4: рахунок (інвойс) по бронюванню
-- ==========================================================
CREATE OR REPLACE FUNCTION get_booking_invoice(p_booking_id INT)
RETURNS TABLE(line_no INT, item TEXT, qty INT, unit_price DECIMAL, line_total DECIMAL) AS $$
DECLARE
    v_b        bookings%ROWTYPE;
    v_type     TEXT;
    v_night    DECIMAL;
    v_services DECIMAL;
    v_paid     DECIMAL;
BEGIN
    SELECT * INTO v_b FROM bookings WHERE booking_id = p_booking_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Бронювання % не знайдено', p_booking_id;
    END IF;

    SELECT rt.name, rt.base_price INTO v_type, v_night
    FROM rooms r
    INNER JOIN room_types rt ON rt.room_type_id = r.room_type_id
    WHERE r.room_id = v_b.room_id;

    SELECT COALESCE(SUM(bs.quantity * s.price), 0) INTO v_services
    FROM booking_services bs
    INNER JOIN services s ON s.service_id = bs.service_id
    WHERE bs.booking_id = p_booking_id;

    SELECT COALESCE(SUM(p.amount), 0) INTO v_paid
    FROM payments p WHERE p.booking_id = p_booking_id;

    RETURN QUERY
    SELECT 1, ('Проживання: ' || v_type)::TEXT, (v_b.check_out - v_b.check_in),
           v_night, v_b.total_price
    UNION ALL
    SELECT 2, s.name::TEXT, bs.quantity, s.price, bs.quantity * s.price
    FROM booking_services bs
    INNER JOIN services s ON s.service_id = bs.service_id
    WHERE bs.booking_id = p_booking_id
    UNION ALL
    SELECT 3, 'ВСЬОГО'::TEXT, NULL::INT, NULL::DECIMAL, v_b.total_price + v_services
    UNION ALL
    SELECT 4, 'Сплачено'::TEXT, NULL::INT, NULL::DECIMAL, v_paid
    UNION ALL
    SELECT 5, 'До сплати'::TEXT, NULL::INT, NULL::DECIMAL,
           v_b.total_price + v_services - v_paid
    ORDER BY 1, 2;
END;
$$ LANGUAGE plpgsql;