// ===============================
// DAYS NAMES IN SPANISH
// ===============================

const SPANISH_MONTHS = [
    'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
];
const SPANISH_DAYS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];

// ===============================
// GLOBAL STATE
// ===============================

let currentDate = new Date();
let holidaysList = [];
let filteredHolidaysList = [];

// ===============================
// DATE UTILITIES
// ===============================

/**
 * Crea una fecha de forma segura sin problemas de zona horaria
 * @param {number} year - Año
 * @param {number} month - Mes (0-11)
 * @param {number} day - Día (1-31)
 * @returns {Date}
 */
function createDate(year, month, day) {
    // Usar UTC para evitar problemas de zona horaria
    return new Date(year, month, day, 12, 0, 0, 0);
}

/**
 * Formatea una fecha a string YYYY-MM-DD
 * @param {Date} date
 * @returns {string}
 */
function formatDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

/**
 * Convierte string YYYY-MM-DD a Date
 * @param {string} dateStr
 * @returns {Date}
 */
function parseDate(dateStr) {
    const [year, month, day] = dateStr.split('-').map(Number);
    return createDate(year, month - 1, day);
}

// ===============================
// RENDER CALENDAR
// ===============================

function renderCalendar() {
    const year = parseInt(document.getElementById('year-select').value);
    const month = parseInt(document.getElementById('month-select').value);
    
    currentDate = createDate(year, month, 1);

    // Actualizar título
    const monthYearEl = document.getElementById('current-month-year');
    monthYearEl.textContent = `${SPANISH_MONTHS[month]} ${year}`;

    // Limpiar calendario
    const calendarBody = document.getElementById('calendar-body');
    calendarBody.innerHTML = '';

    // Primer día del mes (0=Domingo, 1=Lunes, etc.)
    let firstDay = createDate(year, month, 1).getDay();
    firstDay = (firstDay === 0) ? 6 : firstDay - 1;
    // Última día del mes
    const lastDate = createDate(year, month + 1, 0).getDate();
    // Última día del mes anterior
    const lastDatePrevMonth = createDate(year, month, 0).getDate();

    // Obtener fecha actual (normalizada a mediodía para evitar problemas de zona horaria)
    const todayDate = new Date();
    const todayYear = todayDate.getFullYear();
    const todayMonth = todayDate.getMonth();
    const todayDay = todayDate.getDate();

    let date = 1;
    let prevDate = lastDatePrevMonth - firstDay + 1;

    for (let i = 0; i < 6; i++) {
        const row = document.createElement('tr');
        
        for (let j = 0; j < 7; j++) {
            const cell = document.createElement('td');

            if (i === 0 && j < firstDay) {
                // Días del mes anterior
                cell.textContent = prevDate;
                cell.classList.add('other-month');
                prevDate++;
            } else if (date > lastDate) {
                // Días del mes siguiente
                cell.textContent = date - lastDate;
                cell.classList.add('other-month');
                date++;
            } else {
                // Días del mes actual
                cell.textContent = date;
                
                const dateStr = formatDate(createDate(year, month, date));
                
                // Verificar si es un día inhabible
                if (holidaysList.includes(dateStr)) {
                    cell.classList.add('holiday');
                }

                // Verificar si es hoy (comparar año, mes y día)
                if (date === todayDay && 
                    month === todayMonth && 
                    year === todayYear) {
                    cell.classList.add('today');
                }

                // Agregar click para agregar/quitar días inhabitibles
                cell.addEventListener('click', () => toggleHoliday(dateStr, cell));
                
                date++;
            }

            row.appendChild(cell);
        }

        calendarBody.appendChild(row);
    }
}

// ===============================
// INITIALIZATION
// ===============================

async function init() {
    // Verificar sesión del usuario
    const session = await verificarSesion('ADMIN');
    if (!session) return;

    // Inicializar año en el select
    initYearSelect();

    // Cargar días inhabiles
    await loadHolidays();

    // Renderizar calendario
    renderCalendar();

    // Renderizar lista de días
    renderHolidaysList();

    // Agregar event listeners
    document.getElementById('btn-add-holiday').addEventListener('click', addHoliday);
    document.getElementById('date-input').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') addHoliday();
    });
    document.getElementById('prev-month').addEventListener('click', prevMonth);
    document.getElementById('next-month').addEventListener('click', nextMonth);
}

// ===============================
// YEAR SELECT INITIALIZATION
// ===============================

function initYearSelect() {
    const yearSelect = document.getElementById('year-select');
    const monthSelect = document.getElementById('month-select');
    const today = new Date();
    const currentYear = today.getFullYear();
    const currentMonth = today.getMonth();
    
    // Agregar años: 5 años atrás y 5 años adelante
    for (let year = currentYear - 5; year <= currentYear + 5; year++) {
        const option = document.createElement('option');
        option.value = year;
        option.textContent = year;
        if (year === currentYear) option.selected = true;
        yearSelect.appendChild(option);
    }

    // Establecer mes y año actual
    monthSelect.value = currentMonth;
    yearSelect.value = currentYear;
}

// ===============================
// LOAD HOLIDAYS FROM SERVER
// ===============================

async function loadHolidays() {
    try {
        const res = await fetch('/api/diasinhabiles');
        if (!res.ok) throw new Error('Error al cargar días inhabiles');
        
        holidaysList = await res.json();
        filteredHolidaysList = [...holidaysList];
    } catch (error) {
        console.error('Error loading holidays:', error);
        showMessage('Error al cargar los días inhabiles', 'error');
    }
}

// ===============================
// TOGGLE HOLIDAY (CLICK ON CALENDAR)
// ===============================

async function toggleHoliday(dateStr, cellEl) {
    if (holidaysList.includes(dateStr)) {
        // Eliminar
        await deleteHoliday(dateStr);
    } else {
        // Agregar
        await addHolidayByDate(dateStr);
    }
}

// ===============================
// ADD HOLIDAY FROM DATE INPUT
// ===============================

async function addHoliday() {
    const dateInput = document.getElementById('date-input');
    const dateStr = dateInput.value.trim();

    if (!dateStr) {
        showMessage('Por favor selecciona una fecha', 'error');
        return;
    }

    await addHolidayByDate(dateStr);
    dateInput.value = '';
}

// ===============================
// ADD HOLIDAY (INTERNAL)
// ===============================

async function addHolidayByDate(dateStr) {
    try {
        const res = await fetch('/api/diasinhabiles', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': getCsrfToken(),
            },
            body: JSON.stringify({ fecha: dateStr }),
        });

        const data = await res.json();

        if (!res.ok) {
            showMessage(data.error || 'Error al agregar el día', 'error');
            return;
        }

        holidaysList = data.dias;
        filteredHolidaysList = [...holidaysList];
        
        // Resetear filtros
        document.getElementById('month-filter').value = '';
        document.getElementById('search-input').value = '';
        
        renderCalendar();
        renderHolidaysList();
        showMessage('Día inhabible agregado correctamente', 'success');
    } catch (error) {
        console.error('Error adding holiday:', error);
        showMessage('Error de conexión', 'error');
    }
}

// ===============================
// DELETE HOLIDAY
// ===============================

async function deleteHoliday(dateStr) {
    try {
        const res = await fetch(`/api/diasinhabiles/${dateStr}`, {
            method: 'DELETE',
            headers: {
                'X-CSRF-Token': getCsrfToken(),
            },
        });

        const data = await res.json();

        if (!res.ok) {
            showMessage(data.error || 'Error al eliminar el día', 'error');
            return;
        }

        holidaysList = data.dias;
        filteredHolidaysList = [...holidaysList];
        
        // Resetear filtros
        document.getElementById('month-filter').value = '';
        document.getElementById('search-input').value = '';
        
        renderCalendar();
        renderHolidaysList();
        showMessage('Día inhabible eliminado correctamente', 'success');
    } catch (error) {
        console.error('Error deleting holiday:', error);
        showMessage('Error de conexión', 'error');
    }
}

// ===============================
// RENDER HOLIDAYS LIST
// ===============================

function renderHolidaysList() {
    const holidaysList_el = document.getElementById('holidays-list');

    if (filteredHolidaysList.length === 0) {
        if (holidaysList.length === 0) {
            holidaysList_el.innerHTML = '<p class="empty-message">No hay días inhabibles registrados</p>';
        } else {
            holidaysList_el.innerHTML = '<p class="empty-message">No se encontraron resultados</p>';
        }
        return;
    }

    // Ordenar días inhabiles por fecha
    const sortedHolidays = [...filteredHolidaysList].sort();

    let currentMonth = null;
    let html = '';

    sortedHolidays.forEach(dateStr => {
        const date = parseDate(dateStr);
        const month = date.getMonth();
        let dayIndex = date.getDay();
        dayIndex = (dayIndex === 0) ? 6 : dayIndex - 1;
        const dayName = SPANISH_DAYS[dayIndex];
        const formattedDate = formatDateForDisplay(dateStr);

        // Mostrar encabezado de mes si cambió
        if (month !== currentMonth) {
            if (currentMonth !== null) {
                html += '</div>';
            }
            currentMonth = month;
            html += `<div class="month-group"><div class="month-title">${SPANISH_MONTHS[month]}</div>`;
        }

        html += `
            <div class="holiday-item">
                <div class="holiday-date">
                    <span class="date">${formattedDate}</span>
                    <span class="day-name">${dayName}</span>
                </div>
                <button class="btn-delete-holiday" onclick="deleteHoliday('${dateStr}')">
                    Eliminar
                </button>
            </div>
        `;
    });

    if (currentMonth !== null) {
        html += '</div>';
    }

    holidaysList_el.innerHTML = html;
}

// ===============================
// FILTER HOLIDAYS
// ===============================

function filterHolidays() {
    const monthFilter = document.getElementById('month-filter').value;
    const searchInput = document.getElementById('search-input').value.toLowerCase();

    filteredHolidaysList = holidaysList.filter(dateStr => {
        const date = parseDate(dateStr);
        const month = date.getMonth();
        const dayName = SPANISH_DAYS[date.getDay()].toLowerCase();
        const displayDate = formatDateForDisplay(dateStr).toLowerCase();

        // Filtrar por mes
        if (monthFilter !== '' && month !== parseInt(monthFilter)) {
            return false;
        }

        // Filtrar por búsqueda
        if (searchInput && !displayDate.includes(searchInput) && !dayName.includes(searchInput)) {
            return false;
        }

        return true;
    });

    renderHolidaysList();
}

// ===============================
// FORMAT DATE FOR DISPLAY
// ===============================

function formatDateForDisplay(dateStr) {
    const [year, month, day] = dateStr.split('-');
    const monthIndex = parseInt(month) - 1;
    return `${day} de ${SPANISH_MONTHS[monthIndex]} de ${year}`;
}

// ===============================
// MONTH NAVIGATION
// ===============================

function changeMonth() {
    renderCalendar();
}

function prevMonth() {
    const monthSelect = document.getElementById('month-select');
    const yearSelect = document.getElementById('year-select');
    
    let month = parseInt(monthSelect.value);
    let year = parseInt(yearSelect.value);

    month--;
    if (month < 0) {
        month = 11;
        year--;
    }

    monthSelect.value = month;
    yearSelect.value = year;
    renderCalendar();
}

function nextMonth() {
    const monthSelect = document.getElementById('month-select');
    const yearSelect = document.getElementById('year-select');
    
    let month = parseInt(monthSelect.value);
    let year = parseInt(yearSelect.value);

    month++;
    if (month > 11) {
        month = 0;
        year++;
    }

    monthSelect.value = month;
    yearSelect.value = year;
    renderCalendar();
}

// ===============================
// SHOW MESSAGE
// ===============================

function showMessage(text, type) {
    const messageEl = document.getElementById('add-holiday-message');
    messageEl.textContent = text;
    messageEl.className = `message ${type}`;

    setTimeout(() => {
        messageEl.className = 'message';
    }, 3000);
}

// ===============================
// LOGOUT
// ===============================

async function logout() {
    try {
        await fetch('/api/logout', { method: 'POST' });
        window.location.href = 'login.html';
    } catch {
        window.location.href = 'login.html';
    }
}

// ===============================
// DOCUMENT READY
// ===============================

document.addEventListener('DOMContentLoaded', init);
