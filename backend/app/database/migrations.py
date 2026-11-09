"""Idempotent, data-preserving SQLite schema migrations."""
from sqlalchemy.engine import Engine

_TABLE_MIGRATIONS = {
    'transactions': {
        'create_sql': '''CREATE TABLE transactions__nullable_category (
            id INTEGER NOT NULL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            category_id INTEGER,
            description VARCHAR(120) NOT NULL,
            amount_paise INTEGER NOT NULL,
            type VARCHAR(8) NOT NULL,
            transaction_date DATE NOT NULL,
            payment_method VARCHAR(20) NOT NULL,
            notes TEXT,
            merchant VARCHAR(120),
            occurrence_key VARCHAR(100),
            created_at DATETIME NOT NULL,
            CHECK ((type = 'income' AND category_id IS NULL) OR (type = 'expense' AND category_id IS NOT NULL)),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY(category_id) REFERENCES categories (id) ON DELETE RESTRICT,
            UNIQUE (occurrence_key)
        )''',
        'indexes': (
            'CREATE INDEX IF NOT EXISTS ix_transactions_user_id ON transactions (user_id)',
            'CREATE INDEX IF NOT EXISTS ix_transactions_category_id ON transactions (category_id)',
            'CREATE INDEX IF NOT EXISTS ix_tx_user_date ON transactions (user_id, transaction_date)',
        ),
    },
    'recurring_transactions': {
        'create_sql': '''CREATE TABLE recurring_transactions__nullable_category (
            id INTEGER NOT NULL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            category_id INTEGER,
            description VARCHAR(120) NOT NULL,
            amount_paise INTEGER NOT NULL,
            type VARCHAR(8) NOT NULL,
            frequency VARCHAR(8) NOT NULL,
            start_date DATE NOT NULL,
            next_due_date DATE NOT NULL,
            end_date DATE,
            is_active BOOLEAN NOT NULL,
            CHECK ((type = 'income' AND category_id IS NULL) OR (type = 'expense' AND category_id IS NOT NULL)),
            FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY(category_id) REFERENCES categories (id) ON DELETE RESTRICT
        )''',
        'indexes': (
            'CREATE INDEX IF NOT EXISTS ix_recurring_transactions_user_id ON recurring_transactions (user_id)',
        ),
    },
}


def _category_column_is_required(connection, table_name: str) -> bool:
    rows = connection.exec_driver_sql(f'PRAGMA table_info("{table_name}")').mappings().all()
    category = next((row for row in rows if row['name'] == 'category_id'), None)
    return bool(category and category['notnull'])


def _migrate_table(engine: Engine, table_name: str, migration: dict) -> None:
    with engine.connect() as connection:
        if not _category_column_is_required(connection, table_name):
            connection.commit()
            return
        connection.commit()
        connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
        connection.commit()
        try:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
            connection.exec_driver_sql(migration['create_sql'])
            connection.exec_driver_sql(
                f'''INSERT INTO {table_name}__nullable_category (
                    id, user_id, category_id, description, amount_paise, type,
                    {'transaction_date, payment_method, notes, merchant, occurrence_key, created_at' if table_name == 'transactions' else 'frequency, start_date, next_due_date, end_date, is_active'}
                ) SELECT
                    id, user_id, CASE WHEN type = 'income' THEN NULL ELSE category_id END,
                    description, amount_paise, type,
                    {'transaction_date, payment_method, notes, merchant, occurrence_key, created_at' if table_name == 'transactions' else 'frequency, start_date, next_due_date, end_date, is_active'}
                FROM {table_name}'''
            )
            connection.exec_driver_sql(f'DROP TABLE {table_name}')
            connection.exec_driver_sql(f'ALTER TABLE {table_name}__nullable_category RENAME TO {table_name}')
            for index_sql in migration['indexes']:
                connection.exec_driver_sql(index_sql)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
            connection.commit()


def migrate_nullable_income_categories(engine: Engine) -> None:
    """Allow category-less income while retaining all rows and expense categories."""
    if engine.dialect.name != 'sqlite':
        return
    for table_name, migration in _TABLE_MIGRATIONS.items():
        _migrate_table(engine, table_name, migration)
