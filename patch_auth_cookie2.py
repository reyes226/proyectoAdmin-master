from pathlib import Path
import re
path = Path('web/js/auth.js')
text = path.read_text(encoding='utf-8')
pattern = re.compile(r'(async function login\(\) \{\n\s*const usuario\s*=.*\n\s*const password\s*=.*\n\s*const errorEl\s*=.*\n\s*errorEl\.textContent\s*=\s*[\'\"]\'[\'\"]\;\n\n)')
match = pattern.search(text)
if not match:
    raise SystemExit('Pattern not found')
insert = "    document.cookie = 'session=; path=/; max-age=0;';\n    document.cookie = 'proyecto_admin_session=; path=/; max-age=0;';\n\n"
text = text[:match.end(1)] + insert + text[match.end(1):]
path.write_text(text, encoding='utf-8')
print('patched')
