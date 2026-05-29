#!/usr/bin/env python3
"""
Gestiona el archivo de usuarios con contraseñas hasheadas.

Uso:
    python setup_users.py           # Muestra usuarios actuales
    python setup_users.py --reset   # Recrea el archivo con contraseñas por defecto
    python setup_users.py --passwd  # Cambia la contraseña de un usuario
"""
import os
import sys
import json

CONFIG_DIR = os.path.join(os.path.dirname(__file__), 'config')
USERS_FILE = os.path.join(CONFIG_DIR, 'users.json')


def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, encoding='utf-8') as f:
        return json.load(f)


def save_users(users):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def hash_password(password):
    from werkzeug.security import generate_password_hash
    return generate_password_hash(password, method='pbkdf2:sha256')


def cmd_list():
    users = load_users()
    if not users:
        print("No hay usuarios configurados.")
        return
    print(f"\nUsuarios en {USERS_FILE}:\n")
    for nombre, datos in users.items():
        print(f"  {nombre:15s}  rol={datos['rol']}")
    print()


def cmd_reset():
    print("⚠️  Esto recrea el archivo con contraseñas por defecto.")
    print("   admin → admin123")
    print("   consulta → consulta123")
    confirm = input("¿Continuar? (s/N): ").strip().lower()
    if confirm != 's':
        print("Cancelado.")
        return

    users = {
        "admin":    {"password_hash": hash_password("admin123"),    "rol": "ADMIN"},
        "consulta": {"password_hash": hash_password("consulta123"), "rol": "CONSULTA"},
    }
    save_users(users)
    print(f"✅ Usuarios creados en: {USERS_FILE}")
    print("\n⚠️  Cambia las contraseñas antes de usar en producción:")
    print("   python setup_users.py --passwd")


def cmd_passwd():
    users = load_users()
    if not users:
        print("No hay usuarios. Ejecuta primero: python setup_users.py --reset")
        return

    print("Usuarios disponibles:", ", ".join(users))
    nombre = input("Usuario a modificar: ").strip()
    if nombre not in users:
        print(f"Usuario '{nombre}' no existe.")
        return

    import getpass
    password = getpass.getpass("Nueva contraseña: ")
    if len(password) < 8:
        print("La contraseña debe tener al menos 8 caracteres.")
        return
    confirmar = getpass.getpass("Confirmar contraseña: ")
    if password != confirmar:
        print("Las contraseñas no coinciden.")
        return

    users[nombre]['password_hash'] = hash_password(password)
    save_users(users)
    print(f"✅ Contraseña actualizada para '{nombre}'.")


if __name__ == '__main__':
    args = sys.argv[1:]
    if '--reset' in args:
        cmd_reset()
    elif '--passwd' in args:
        cmd_passwd()
    else:
        cmd_list()
