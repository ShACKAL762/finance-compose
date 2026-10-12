CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    type VARCHAR(10) NOT NULL CHECK (type IN ('income', 'expense')),
    category VARCHAR(100) NOT NULL CHECK (length(trim(category)) > 0),
    description VARCHAR(255) NOT NULL DEFAULT '',
    amount NUMERIC(12,2) NOT NULL CHECK (amount > 0)
);
-- Начальные записи создаются только при инициализации нового тома PostgreSQL.
INSERT INTO transactions (date, type, category, description, amount) VALUES
('2026-10-01', 'income', 'Работа', 'Зарплата — учебный пример', 60000.00),
('2026-10-02', 'expense', 'Еда', 'Продукты', 3500.50),
('2026-10-03', 'expense', 'Транспорт', 'Проезд', 1500.00);
