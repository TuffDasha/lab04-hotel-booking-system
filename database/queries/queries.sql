-- ==========================================================
-- РІВЕНЬ 1
-- ==========================================================

-- Запит 1 (простий, фільтрація + сортування):
-- Підтверджені бронювання, що починаються з 20 жовтня 2026
SELECT booking_id, guest_id, room_id, check_in, check_out, total_price
FROM bookings
WHERE status = 'confirmed'
  AND check_in >= '2026-10-20'
ORDER BY check_in;

-- Запит 2 (JOIN): бронювання з ПІБ гостя, номером кімнати та типом номера
SELECT
    b.booking_id,
    g.first_name || ' ' || g.last_name AS guest,
    r.room_number,
    rt.name AS room_type,
    b.check_in,
    b.check_out,
    (b.check_out - b.check_in) AS nights,
    b.status
FROM bookings b
INNER JOIN guests g      ON g.guest_id = b.guest_id
INNER JOIN rooms r       ON r.room_id = b.room_id
INNER JOIN room_types rt ON rt.room_type_id = r.room_type_id
ORDER BY b.check_in;

-- Запит 3 (агрегатний): виручка та кількість ночей за типами номерів
SELECT
    rt.name AS room_type,
    COUNT(b.booking_id)           AS bookings_count,
    SUM(b.check_out - b.check_in) AS total_nights,
    SUM(b.total_price)            AS revenue,
    ROUND(AVG(b.total_price), 2)  AS avg_booking_price
FROM room_types rt
INNER JOIN rooms r    ON r.room_type_id = rt.room_type_id
INNER JOIN bookings b ON b.room_id = r.room_id
WHERE b.status <> 'cancelled'
GROUP BY rt.room_type_id, rt.name
HAVING COUNT(b.booking_id) > 0
ORDER BY revenue DESC;

-- Запит 4а (підзапит у WHERE): бронювання дорожчі за середню вартість
SELECT booking_id, room_id, total_price
FROM bookings
WHERE status <> 'cancelled'
  AND total_price > (SELECT AVG(total_price) FROM bookings WHERE status <> 'cancelled')
ORDER BY total_price DESC;

-- Запит 4б (корельований підзапит NOT EXISTS): номери, які жодного разу не бронювали
SELECT r.room_number, rt.name AS room_type, r.status
FROM rooms r
INNER JOIN room_types rt ON rt.room_type_id = r.room_type_id
WHERE NOT EXISTS (
    SELECT 1 FROM bookings b WHERE b.room_id = r.room_id
);

-- Запит 5 (кілька JOIN + STRING_AGG): повна картка бронювання з переліком послуг
SELECT
    b.booking_id,
    g.last_name || ' ' || g.first_name AS guest,
    r.room_number,
    b.check_in,
    b.check_out,
    b.status,
    COALESCE(STRING_AGG(s.name || ' x' || bs.quantity, ', ' ORDER BY s.name), '—') AS services
FROM bookings b
INNER JOIN guests g ON g.guest_id = b.guest_id
INNER JOIN rooms r  ON r.room_id = b.room_id
LEFT JOIN booking_services bs ON bs.booking_id = b.booking_id
LEFT JOIN services s          ON s.service_id = bs.service_id
GROUP BY b.booking_id, g.last_name, g.first_name, r.room_number
ORDER BY b.booking_id;

-- ==========================================================
-- РІВЕНЬ 2: складні аналітичні запити
-- ==========================================================

-- Аналітика 1: фінансовий стан кожного бронювання (нараховано, сплачено, борг)
-- Послуги та оплати агрегуємо в окремих CTE, інакше JOIN двох "багато"
-- помножить рядки і суми будуть завищені.
WITH svc AS (
    SELECT bs.booking_id, SUM(bs.quantity * s.price) AS services_total
    FROM booking_services bs
    INNER JOIN services s ON s.service_id = bs.service_id
    GROUP BY bs.booking_id
),
paid AS (
    SELECT booking_id, SUM(amount) AS paid_total
    FROM payments
    GROUP BY booking_id
)
SELECT
    b.booking_id,
    g.last_name,
    b.status,
    b.total_price                                    AS room_total,
    COALESCE(svc.services_total, 0)                  AS services_total,
    b.total_price + COALESCE(svc.services_total, 0)  AS grand_total,
    COALESCE(paid.paid_total, 0)                     AS paid_total,
    b.total_price + COALESCE(svc.services_total, 0)
        - COALESCE(paid.paid_total, 0)               AS balance_due
FROM bookings b
INNER JOIN guests g ON g.guest_id = b.guest_id
LEFT JOIN svc  ON svc.booking_id = b.booking_id
LEFT JOIN paid ON paid.booking_id = b.booking_id
WHERE b.status <> 'cancelled'
ORDER BY balance_due DESC;

-- Аналітика 2: завантаженість типів номерів за жовтень 2026
-- Ночі, що потрапляють у місяць, рахуємо через GREATEST/LEAST.
-- Номери на ремонті не враховуємо в доступній місткості.
SELECT
    rt.name AS room_type,
    COUNT(DISTINCT r.room_id) AS rooms_available,
    COALESCE(SUM(
        GREATEST(0,
            LEAST(b.check_out, DATE '2026-11-01') - GREATEST(b.check_in, DATE '2026-10-01'))
    ), 0) AS nights_booked,
    ROUND(
        100.0 * COALESCE(SUM(
            GREATEST(0,
                LEAST(b.check_out, DATE '2026-11-01') - GREATEST(b.check_in, DATE '2026-10-01'))
        ), 0) / NULLIF(COUNT(DISTINCT r.room_id) * 31, 0),
    1) AS occupancy_pct
FROM room_types rt
LEFT JOIN rooms r ON r.room_type_id = rt.room_type_id AND r.status = 'available'
LEFT JOIN bookings b ON b.room_id = r.room_id AND b.status <> 'cancelled'
GROUP BY rt.room_type_id, rt.name
HAVING COUNT(DISTINCT r.room_id) > 0
ORDER BY occupancy_pct DESC;

-- Аналітика 3: рейтинг гостей за витратами (віконні функції)
WITH guest_totals AS (
    SELECT
        g.guest_id,
        g.first_name || ' ' || g.last_name AS guest,
        COUNT(b.booking_id)                AS bookings_cnt,
        COALESCE(SUM(b.total_price), 0)    AS total_spent
    FROM guests g
    LEFT JOIN bookings b ON b.guest_id = g.guest_id AND b.status <> 'cancelled'
    GROUP BY g.guest_id, g.first_name, g.last_name
)
SELECT
    guest,
    bookings_cnt,
    total_spent,
    RANK() OVER (ORDER BY total_spent DESC)                  AS spending_rank,
    ROUND(100.0 * total_spent / SUM(total_spent) OVER (), 1) AS share_pct,
    SUM(total_spent) OVER (ORDER BY total_spent DESC, guest_id) AS running_total
FROM guest_totals
ORDER BY spending_rank, guest;