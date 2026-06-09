from werkzeug.security import generate_password_hash
for password in ["admin123", "consulta123", "12345678"]:
    print(generate_password_hash(password, method='pbkdf2:sha256'))
