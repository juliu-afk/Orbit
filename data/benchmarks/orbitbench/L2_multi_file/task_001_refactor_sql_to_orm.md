# L2-001: Refactor raw SQL to SQLAlchemy ORM

## Task
Convert this raw SQL query function to use SQLAlchemy ORM session:
```python
def get_users_by_age(conn, min_age: int):
    cursor = conn.execute("SELECT name, age FROM users WHERE age >= ?", (min_age,))
    return [{"name": row[0], "age": row[1]} for row in cursor.fetchall()]
```

## Expected
```python
from sqlalchemy import select
from sqlalchemy.orm import Session

def get_users_by_age(session: Session, min_age: int) -> list[dict]:
    stmt = select(User).where(User.age >= min_age)
    return [{"name": u.name, "age": u.age} for u in session.execute(stmt).scalars()]
```

## Verify
Function uses ORM session, no raw SQL string.
