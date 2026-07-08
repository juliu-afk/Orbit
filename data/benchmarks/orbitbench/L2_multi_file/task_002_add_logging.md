# L2-002: Add structured logging to service
## Task: Replace print() with structlog in this service function
```python
def process_order(order_id):
    print(f"Processing order {order_id}")
    result = db.execute(...)
    print(f"Done: {result}")
    return result
```
## Expected: Use `logger.info()` with key-value pairs
