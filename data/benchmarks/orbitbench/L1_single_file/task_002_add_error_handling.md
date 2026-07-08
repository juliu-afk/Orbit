# L1-002: Add error handling to file reader

## Task
Add try/except for FileNotFoundError:
```python
def read_config(path):
    with open(path) as f:
        return f.read()
```

## Expected
```python
def read_config(path: str) -> str:
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return ""
```

## Verify
`read_config("/nonexistent/path")` should return `""` without crashing.
