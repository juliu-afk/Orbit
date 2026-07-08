# L1-003: Add pagination to list endpoint
## Task: Add offset/limit params to `def list_items(): return db.query(Item).all()`
## Expected: `def list_items(offset: int = 0, limit: int = 20) -> list[Item]:`
