-- Представлення 1: повна інформація про бронювання з фінансами
CREATE OR REPLACE VIEW v_booking_details AS
SELECT
    b.booking_id,
    g.guest_id,
    g.first_name || ' ' || g.last_name AS guest_name,
    g.email,
    r.room_number,
    rt.name                            AS room_type,
    b.check_in,
    b.check_out,
    (b.check_out - b.check_in)         AS nights,
    b.guests_count,
    b.status,
    b.total_price                      AS room_total,
    COALESCE(s.services_total, 0)      AS services_total,
    b.total_price + COALESCE(s.services_total, 0) AS grand_total,
    COALESCE(p.paid_total, 0)          AS paid_total,
    CASE WHEN b.status = 'cancelled' THEN 0
         ELSE b.total_price + COALESCE(s.services_total, 0) - COALESCE(p.paid_total, 0)
    END                                AS balance_due
FROM bookings b
INNER JOIN guests g      ON g.guest_id = b.guest_id
INNER JOIN rooms r       ON r.room_id = b.room_id
INNER JOIN room_types rt ON rt.room_type_id = r.room_type_id
LEFT JOIN (
    SELECT bs.booking_id, SUM(bs.quantity * sv.price) AS services_total
    FROM booking_services bs
    INNER JOIN services sv ON sv.service_id = bs.service_id
    GROUP BY bs.booking_id
) s ON s.booking_id = b.booking_id
LEFT JOIN (
    SELECT booking_id, SUM(amount) AS paid_total
    FROM payments
    GROUP BY booking_id
) p ON p.booking_id = b.booking_id;

-- Представлення 2: стан номерів на сьогодні
CREATE OR REPLACE VIEW v_room_status_today AS
SELECT
    r.room_id,
    r.room_number,
    r.floor,
    rt.name       AS room_type,
    rt.capacity,
    rt.base_price,
    CASE WHEN r.status = 'maintenance' THEN 'maintenance'
         WHEN cur.booking_id IS NOT NULL THEN 'occupied'
         ELSE 'free'
    END           AS current_state,
    cur.guest_name,
    cur.check_out AS busy_until
FROM rooms r
INNER JOIN room_types rt ON rt.room_type_id = r.room_type_id
LEFT JOIN LATERAL (
    SELECT b.booking_id, b.check_out,
           g.first_name || ' ' || g.last_name AS guest_name
    FROM bookings b
    INNER JOIN guests g ON g.guest_id = b.guest_id
    WHERE b.room_id = r.room_id
      AND b.status <> 'cancelled'
      AND CURRENT_DATE >= b.check_in
      AND CURRENT_DATE <  b.check_out
    LIMIT 1
) cur ON TRUE;

-- Представлення 3: зведення по гостях
CREATE OR REPLACE VIEW v_guest_summary AS
SELECT
    g.guest_id,
    g.first_name || ' ' || g.last_name AS guest_name,
    g.email,
    g.phone,
    COUNT(b.booking_id)                AS bookings_count,
    COALESCE(SUM(b.total_price), 0)    AS total_spent,
    MAX(b.check_out)                   AS last_departure
FROM guests g
LEFT JOIN bookings b ON b.guest_id = g.guest_id AND b.status <> 'cancelled'
GROUP BY g.guest_id, g.first_name, g.last_name, g.email, g.phone;