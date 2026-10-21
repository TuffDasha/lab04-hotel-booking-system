CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_types (
    room_type_id SERIAL PRIMARY KEY,
    name         VARCHAR(50) UNIQUE NOT NULL,
    description  TEXT,
    capacity     INT NOT NULL CHECK (capacity BETWEEN 1 AND 10),
    base_price   DECIMAL(10,2) NOT NULL CHECK (base_price > 0)
);

CREATE TABLE rooms (
    room_id      SERIAL PRIMARY KEY,
    room_number  VARCHAR(10) UNIQUE NOT NULL,
    floor        INT NOT NULL CHECK (floor BETWEEN 1 AND 50),
    room_type_id INT NOT NULL REFERENCES room_types(room_type_id),
    status       VARCHAR(20) NOT NULL DEFAULT 'available'
                 CHECK (status IN ('available', 'maintenance'))
);

CREATE TABLE guests (
    guest_id   SERIAL PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name  VARCHAR(50) NOT NULL,
    email      VARCHAR(100) UNIQUE NOT NULL
               CHECK (email LIKE '%_@_%._%'),
    phone      VARCHAR(20),
    birth_date DATE CHECK (birth_date < CURRENT_DATE),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE bookings (
    booking_id  SERIAL PRIMARY KEY,
    guest_id    INT NOT NULL REFERENCES guests(guest_id),
    room_id     INT NOT NULL REFERENCES rooms(room_id),
    check_in    DATE NOT NULL,
    check_out   DATE NOT NULL,
    guests_count INT NOT NULL DEFAULT 1 CHECK (guests_count > 0),
    status      VARCHAR(20) NOT NULL DEFAULT 'confirmed'
                CHECK (status IN ('confirmed', 'checked_in', 'checked_out', 'cancelled')),
    total_price DECIMAL(10,2) NOT NULL DEFAULT 0 CHECK (total_price >= 0),
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (check_out > check_in),
    EXCLUDE USING gist (
        room_id WITH =,
        daterange(check_in, check_out) WITH &&
    ) WHERE (status <> 'cancelled')
);

CREATE TABLE services (
    service_id SERIAL PRIMARY KEY,
    name       VARCHAR(100) UNIQUE NOT NULL,
    price      DECIMAL(10,2) NOT NULL CHECK (price >= 0)
);

CREATE TABLE booking_services (
    booking_id INT NOT NULL REFERENCES bookings(booking_id) ON DELETE CASCADE,
    service_id INT NOT NULL REFERENCES services(service_id),
    quantity   INT NOT NULL DEFAULT 1 CHECK (quantity > 0),
    PRIMARY KEY (booking_id, service_id)
);

CREATE TABLE payments (
    payment_id SERIAL PRIMARY KEY,
    booking_id INT NOT NULL REFERENCES bookings(booking_id) ON DELETE CASCADE,
    amount     DECIMAL(10,2) NOT NULL CHECK (amount > 0),
    method     VARCHAR(20) NOT NULL CHECK (method IN ('card', 'cash', 'transfer')),
    paid_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_rooms_type      ON rooms(room_type_id);
CREATE INDEX idx_bookings_guest  ON bookings(guest_id);
CREATE INDEX idx_bookings_room   ON bookings(room_id);
CREATE INDEX idx_bookings_dates  ON bookings(check_in, check_out);
CREATE INDEX idx_payments_booking ON payments(booking_id);