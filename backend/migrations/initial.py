from sqlalchemy import text, inspect
from src.config.database import Base, engine
from src import models
def migrate():
    Base.metadata.create_all(engine)
    # create_all does not alter existing tables; add the retirement/invalidation columns in place.
    additions = {
        'datasets': [('retired_at', 'DOUBLE NULL'), ('retired_by', 'VARCHAR(150) NULL'), ('retire_reason', 'VARCHAR(1000) NULL')],
        'jobs': [('invalidated_at', 'DOUBLE NULL'), ('invalidated_by', 'VARCHAR(150) NULL'), ('invalidated_reason', 'VARCHAR(1000) NULL')],
        'reports': [('invalidated_at', 'DOUBLE NULL'), ('invalidated_reason', 'VARCHAR(1000) NULL')],
    }
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in additions.items():
            existing = {c['name'] for c in inspector.get_columns(table)}
            for name, ddl in columns:
                if name not in existing:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}'))
if __name__=='__main__':migrate()
