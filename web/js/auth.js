// ===============================
// AUTENTICACIÓN — SERVER-SIDE
// Las credenciales se validan en el servidor.
// Las sesiones usan cookies HTTP-only firmadas.
// ===============================

let _csrfToken = null;

// Expone el token para que otros módulos lo incluyan en sus peticiones.
function getCsrfToken() { return _csrfToken; }


// ===============================
// LOGIN
// ===============================

async function login() {
    const usuario  = document.getElementById('usuario').value.trim();
    const password = document.getElementById('password').value;
    const errorEl  = document.getElementById('error');
    errorEl.textContent = '';

    if (!usuario || !password) {
        errorEl.textContent = 'Ingresa usuario y contraseña';
        return;
    }

    try {
        const res  = await fetch('/api/login', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ usuario, password }),
        });
        const data = await res.json();

        if (!res.ok || !data.ok) {
            errorEl.textContent = data.error || 'Error al iniciar sesión';
            return;
        }

        _csrfToken = data.csrf_token;

        window.location.href = data.rol === 'ADMIN' ? 'admin.html' : 'dashboard.html';

    } catch {
        errorEl.textContent = 'No se pudo conectar al servidor';
    }
}


// ===============================
// VERIFICAR SESIÓN
// ===============================

/**
 * Verifica la sesión con el servidor.
 * - Si no está autenticado → redirige a login.html.
 * - Si el rol no coincide  → redirige a dashboard.html.
 * - Retorna los datos de sesión si todo es correcto.
 */
async function verificarSesion(rolRequerido = null) {
    try {
        const res = await fetch('/api/whoami');

        if (res.status === 401) {
            window.location.href = 'login.html';
            return null;
        }

        const data = await res.json();

        if (!data.authenticated) {
            window.location.href = 'login.html';
            return null;
        }

        _csrfToken = data.csrf_token;

        if (rolRequerido && data.rol !== rolRequerido) {
            alert('No tienes permisos para acceder a esta sección');
            window.location.href = 'dashboard.html';
            return null;
        }

        // Mostrar el enlace de administración si corresponde
        const adminContainer = document.getElementById('admin-link-container');
        if (adminContainer && data.rol === 'ADMIN') {
            adminContainer.innerHTML =
                '<a class="admin-link" href="admin.html">Panel Admin</a>';
        }

        return data;

    } catch {
        window.location.href = 'login.html';
        return null;
    }
}


// ===============================
// LOGOUT
// ===============================

async function logout() {
    try {
        await fetch('/api/logout', {
            method:  'POST',
            headers: { 'X-CSRF-Token': _csrfToken || '' },
        });
    } catch { /* ignorar errores de red al cerrar sesión */ }
    window.location.href = 'login.html';
}

function volverInicio() {
    window.location.href = 'index.html';
}


// ===============================
// UTILIDADES
// ===============================

function togglePassword() {
    const input = document.getElementById('password');
    input.type  = input.type === 'password' ? 'text' : 'password';
}

// Enter → login (solo activo en la página de login)
document.addEventListener('keypress', function (event) {
    if (event.key === 'Enter' && document.getElementById('usuario')) {
        login();
    }
});
