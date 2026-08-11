-- Seeded automatically on first `docker compose up`.
--
-- Kept small but not trivial: primary keys, a foreign key, a nullable column,
-- a default, and a view. Schema introspection that only ever sees one flat
-- table will hide bugs you would rather find in Phase 1 than Phase 4.

CREATE TABLE customers (
    customer_id  SERIAL PRIMARY KEY,
    name         VARCHAR(120) NOT NULL,
    region       VARCHAR(10),
    tier         VARCHAR(20) NOT NULL DEFAULT 'standard',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE products (
    product_id   SERIAL PRIMARY KEY,
    sku          VARCHAR(40) NOT NULL UNIQUE,
    description  TEXT,
    unit_price   NUMERIC(10, 2) NOT NULL
);

CREATE TABLE orders (
    order_id     SERIAL PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES customers(customer_id),
    product_id   INTEGER NOT NULL REFERENCES products(product_id),
    quantity     INTEGER NOT NULL CHECK (quantity > 0),
    ordered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE VIEW order_summary AS
SELECT c.name          AS customer_name,
       c.region        AS region,
       p.sku           AS sku,
       o.quantity      AS quantity,
       o.quantity * p.unit_price AS line_total
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
JOIN products  p ON p.product_id  = o.product_id;

INSERT INTO customers (name, region, tier) VALUES
    ('Northwind Traders', 'APAC', 'gold'),
    ('Contoso Ltd',       'EMEA', 'standard'),
    ('Fabrikam Inc',      'APAC', 'gold'),
    ('Adventure Works',   'AMER', 'silver'),
    ('Wide World Imports', NULL,  'standard');

INSERT INTO products (sku, description, unit_price) VALUES
    ('SKU-1001', 'Industrial widget, 20mm',   12.50),
    ('SKU-1002', 'Industrial widget, 40mm',   19.95),
    ('SKU-2001', 'Calibration kit',          249.00),
    ('SKU-3001', 'Replacement gasket set',     8.75);

INSERT INTO orders (customer_id, product_id, quantity) VALUES
    (1, 1, 10), (1, 3,  1), (2, 2, 25),
    (3, 4, 100), (3, 1,  5), (4, 2, 12), (5, 3, 2);

-- A least-privilege read-only role. Generated connectors should use this, not
-- the owner. Worth demonstrating in the final presentation.
CREATE ROLE dsoa_reader WITH LOGIN PASSWORD 'dsoa_reader_local';
GRANT CONNECT ON DATABASE dsoa_source TO dsoa_reader;
GRANT USAGE ON SCHEMA public TO dsoa_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dsoa_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO dsoa_reader;
