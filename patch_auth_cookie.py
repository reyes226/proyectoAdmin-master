from pathlib import Path
path = Path('web/js/auth.js')
text = path.read_text(encoding='utf-8')
old = "async function login() {\n    const usuario  = document.getElementById('usuario').value.trim();\n    const password = document.getElementById('password').value;\n    const errorEl  = document.getElementById('error');\n    errorEl.textContent = '';\n\n    if (!usuario || !password) {\n        errorEl.textContent = 'Ingresa usuario y contraseña';\n        return;\n    }\n"
new = "async function login() {\n    const usuario  = document.getElementById('usuario').value.trim();\n    const password = document.getElementById('password').value;\n    const errorEl  = document.getElementById('error');\n    errorEl.textContent = '';\n\n    document.cookie = 'session=; path=/; max-age=0;';\n    document.cookie = 'proyecto_admin_session=; path=/; max-age=0;';\n\n    if (!usuario || !password) {\n        errorEl.textContent = 'Ingresa usuario y contraseña';\n        return;\n    }\n"
if old not in text:
    raise SystemExit('Pattern not found')
path.write_text(text.replace(old, new), encoding='utf-8')
print('patched')
