"""Fix linter-reverted files + add orbit.spec hiddenimports."""
import os, re

def fix(path, old, new):
    with open(path, 'r', encoding='utf-8', newline='') as f:
        c = f.read()
    if old in c:
        c = c.replace(old, new)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(c)
        return 'FIXED'
    elif new in c:
        return 'OK'
    return 'MISS'

# ── P1-5: 4 prebuilders shallow copy ──
old_p15 = 'l2 = raw_context.get("l2", {})'
new_p15 = 'l2 = dict(raw_context.get("l2", {}))  # PR#201 P1-5: shallow copy'
for f in ['architect', 'developer', 'reviewer', 'qa']:
    r = fix(f'src/orbit/context/prebuilders/{f}.py', old_p15, new_p15)
    print(f'  {f}: {r}')

# ── P2-4: schema_change multi-migration ──
sc_path = 'src/orbit/context/scanners/schema_change.py'
with open(sc_path, 'r', encoding='utf-8', newline='') as f:
    sc = f.read()

# Check if already fixed
if 'py_files[:10]' in sc:
    print('  schema_change: OK (already fixed)')
else:
    # Replace the single-migration block
    old_block = '''            result["has_migration"] = True
            latest = py_files[0]
            content = latest.read_text(encoding="utf-8", errors="replace")

            # 简单正则提取 create_table / alter_table 操作
            import re
            create_tables = re.findall(r"create_table\s*\(\s*['\"]'''
    if old_block in sc:
        # Find the full block end
        idx = sc.index(old_block)
        # Find the return statement after this block
        end_marker = '            return result'
        end_idx = sc.index(end_marker, idx)

        new_block = '''            result["has_migration"] = True
            # PR#201 P2-4: read all migration files, not just latest
            import re
            create_tables: list[str] = []
            alter_tables: list[str] = []
            add_columns: list[dict[str, str]] = []
            for mf in py_files[:10]:
                c = mf.read_text(encoding="utf-8", errors="replace")
                create_tables.extend(re.findall(r"create_table\\s*\\(\\s*'([^']+)'", c, re.IGNORECASE))
                alter_tables.extend(re.findall(r"alter_table\\s*\\(\\s*'([^']+)'", c, re.IGNORECASE))
                add_columns.extend(
                    {"table": t, "column": col}
                    for t, col in re.findall(r"add_column\\s*\\(\\s*'([^']+)'\\s*,\\s*sa\\.Column\\s*\\(\\s*'([^']+)'", c, re.IGNORECASE)
                )
            result["tables_added"] = create_tables
            result["tables_modified"] = alter_tables
            result["columns_added"] = add_columns

'''
        sc = sc[:idx] + new_block + sc[end_idx:]
        with open(sc_path, 'w', encoding='utf-8', newline='') as f:
            f.write(sc)
        print('  schema_change: FIXED')
    else:
        print('  schema_change: MISS (block not found)')

# ── P2-1: prebuilder cache (check) ──
pb_path = 'src/orbit/context/prebuilder.py'
with open(pb_path, 'r', encoding='utf-8', newline='') as f:
    pb = f.read()
if '_instances' in pb:
    print('  prebuilder cache: OK')
else:
    print('  prebuilder cache: MISS')

# ── P2-2: chatter→clarifier ──
if 'chatter": ClarifierContextPrebuilder()' in pb:
    print('  chatter→clarifier: OK')
else:
    print('  chatter→clarifier: MISS')

print('Done')
