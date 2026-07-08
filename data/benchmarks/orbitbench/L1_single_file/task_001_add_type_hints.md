# L1-001: Add type hints to function

## Task
Add type annotations to this function:
```python
def calculate_total(items, tax_rate):
    subtotal = sum(items)
    tax = subtotal * tax_rate
    return subtotal + tax
```

## Expected
```python
from decimal import Decimal
from typing import List

def calculate_total(items: List[Decimal], tax_rate: Decimal) -> Decimal:
    subtotal = sum(items)
    tax = subtotal * tax_rate
    return subtotal + tax
```

## Verify
Function should accept `List[Decimal]` and `Decimal`, return `Decimal`.
