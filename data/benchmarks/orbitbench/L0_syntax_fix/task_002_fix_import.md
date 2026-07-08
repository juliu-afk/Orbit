# L0-002: Fix missing import

## Task
Fix the NameError:
```python
result = math.sqrt(16)
print(result)
```

## Expected
```python
import math
result = math.sqrt(16)
print(result)
```

## Verify
Should output `4.0` with no errors.
