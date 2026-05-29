// ── Estado global ──
let _data = null, _mes = '', _periodo = 'general', _maestro = '', _search = '', _barLimit = 20, _topPuntualLimit = 20;
let _sort = { col: null, dir: 1 };
let _pieChart = null, _barChart = null, _weekChart = null, _topPuntualChart = null;

const MESES_NOMBRES = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                       'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];

// ── Carga inicial: meses disponibles ──
async function inicializar() {
    // Leer parámetro ?mes= de la URL
    const urlMes = new URLSearchParams(window.location.search).get('mes');

    try {
        const res   = await fetch('/api/meses-maestria');
        if (res.status === 401) { window.location.href = 'login.html'; return; }
        const meses = await res.json();

        const sel = document.getElementById('mes-select');
        if (!meses.length) {
            sel.innerHTML = '<option value="">No hay meses disponibles</option>';
            document.getElementById('table-container').innerHTML =
                '<p class="no-results">No hay datos procesados. Ve al Panel de Administración para subir archivos de Maestría-Doctorado.</p>';
            return;
        }

        sel.innerHTML = meses.map(m => {
            const [anio, num] = m.split('_');
            const nombre = `${MESES_NOMBRES[parseInt(num) - 1]} ${anio}`;
            return `<option value="${m}">${nombre}</option>`;
        }).join('');

        // Seleccionar mes de URL o el más reciente
        _mes = (urlMes && meses.includes(urlMes)) ? urlMes : meses[0];
        sel.value = _mes;

        await cargarDatosMes();
    } catch(e) {
        document.getElementById('table-container').innerHTML =
            '<p class="no-results">Error al conectar con el servidor.</p>';
    }
}

async function cambiarMes(mes) {
    _mes = mes;
    _maestro = '';
    document.getElementById('teacher-select').value = '';
    document.getElementById('teacher-select').innerHTML = '<option value="">— Todos los docentes —</option>';
    await cargarDatosMes();
}

async function cargarDatosMes() {
    if (!_mes) return;
    document.getElementById('table-container').innerHTML = '<p class="no-results">Cargando...</p>';
    try {
        const res = await fetch(`/output/data_maestria_doctorado_${_mes}.json`);
        if (res.status === 401) { window.location.href = 'login.html'; return; }
        _data = await res.json();
        populateTeacherDropdown();
        render();
        renderComparativeChart();
        renderWeekChart();
        renderTopPuntualChart();
    } catch(e) {
        document.getElementById('table-container').innerHTML =
            '<p class="no-results">No se pudo cargar los datos del mes seleccionado.</p>';
    }
}

function populateTeacherDropdown() {
    const sel = document.getElementById('teacher-select');
    _data.por_profesor
        .slice()
        .sort((a,b) => a.PROFESOR.localeCompare(b.PROFESOR))
        .forEach(p => {
            const o = document.createElement('option');
            o.value = p.PROFESOR;
            o.textContent = p.PROFESOR;
            sel.appendChild(o);
        });
}

// ── Filtros ──
function setPeriodo(p, btn) {
    _periodo = p;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const label = p === 'general' ? 'General' : p === 'quincena_1' ? 'Quincena 1' : 'Quincena 2';
    document.getElementById('comp-periodo-label').textContent    = label;
    document.getElementById('puntual-periodo-label').textContent = label;
    render();
    renderComparativeChart();
    renderTopPuntualChart();
}
function setMaestro(v) { _maestro = v; render(); }
function setSearch(v)  { _search = v.toUpperCase(); renderTable(); }
function setBarLimit(n, btn) {
    _barLimit = n;
    document.querySelectorAll('.bar-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    renderComparativeChart();
}
function toggleSort(col) {
    _sort.dir = (_sort.col === col) ? _sort.dir * -1 : 1;
    _sort.col = col;
    renderTable();
}

// ── Helpers ──
function getD(p) {
    return _periodo === 'general' ? p.general
         : _periodo === 'quincena_1' ? p.quincena_1
         : p.quincena_2;
}
function pct(v, t) { return t ? ((v/t)*100).toFixed(1)+'%' : '0%'; }
function pctNum(v, t) { return t ? (v/t)*100 : 0; }

function semaforo(p, t, total) {
    const a = total ? ((p+t)/total)*100 : 0;
    const cls = a >= 80 ? 'sem-green' : a >= 60 ? 'sem-yellow' : 'sem-red';
    const tip = a >= 80 ? 'Asistencia buena' : a >= 60 ? 'Asistencia regular' : 'Asistencia baja';
    return `<span class="sem ${cls}" title="${tip}"></span>`;
}

function sortIcon(col) {
    if (_sort.col !== col) return '<span class="sort-icon">⇅</span>';
    return _sort.dir === 1 ? '<span class="sort-icon">▲</span>' : '<span class="sort-icon">▼</span>';
}

function getStats() {
    if (_maestro) {
        const prof = _data.por_profesor.find(p => p.PROFESOR === _maestro);
        if (!prof) return null;
        const d = getD(prof);
        return { puntual: d.PUNTUAL, tolerancia: d.TOLERANCIA, falta: d.FALTA, total: d.TOTAL };
    }
    let puntual=0, tolerancia=0, falta=0, total=0;
    _data.por_profesor.forEach(p => {
        const d = getD(p);
        puntual += d.PUNTUAL; tolerancia += d.TOLERANCIA; falta += d.FALTA; total += d.TOTAL;
    });
    return { puntual, tolerancia, falta, total };
}

function getFilteredSorted() {
    let list = _maestro
        ? _data.por_profesor.filter(p => p.PROFESOR === _maestro)
        : _data.por_profesor;

    if (_search) list = list.filter(p => p.PROFESOR.includes(_search));

    if (_sort.col) {
        list = [...list].sort((a, b) => {
            const da = getD(a), db = getD(b);
            if (_sort.col === 'PROFESOR') return _sort.dir * a.PROFESOR.localeCompare(b.PROFESOR);
            if (_sort.col === 'ASIST') {
                const va = da.TOTAL ? (da.PUNTUAL+da.TOLERANCIA)/da.TOTAL : 0;
                const vb = db.TOTAL ? (db.PUNTUAL+db.TOLERANCIA)/db.TOTAL : 0;
                return _sort.dir * (va - vb);
            }
            return _sort.dir * ((da[_sort.col]??0) - (db[_sort.col]??0));
        });
    }
    return list;
}

// ── Render principal ──
function render() {
    if (!_data) return;
    const s = getStats();
    renderCards(s);
    renderChart(s);
    renderTable();
}

// ── Tarjetas ──
function renderCards(s) {
    const asistPct = pct(s.puntual + s.tolerancia, s.total);
    document.getElementById('stats-grid').innerHTML = `
        <div class="stat-card">
            <h4>Total Clases</h4>
            <div class="stat-val">${s.total.toLocaleString()}</div>
            <div class="stat-sub">${_periodo === 'general' ? 'Mes completo' : _periodo === 'quincena_1' ? 'Quincena 1' : 'Quincena 2'}</div>
        </div>
        <div class="stat-card puntual">
            <h4>Puntual</h4>
            <div class="stat-val">${pct(s.puntual, s.total)}</div>
            <div class="stat-sub">${s.puntual.toLocaleString()} clases</div>
        </div>
        <div class="stat-card tolerancia">
            <h4>Tolerancia</h4>
            <div class="stat-val">${pct(s.tolerancia, s.total)}</div>
            <div class="stat-sub">${s.tolerancia.toLocaleString()} clases</div>
        </div>
        <div class="stat-card falta">
            <h4>Falta</h4>
            <div class="stat-val">${pct(s.falta, s.total)}</div>
            <div class="stat-sub">${s.falta.toLocaleString()} clases</div>
        </div>`;
}

// ── Dona ──
function renderChart(s) {
    const label = (_maestro || 'Todos') + ' · ' +
        (_periodo === 'general' ? 'General' : _periodo === 'quincena_1' ? 'Quincena 1' : 'Quincena 2');
    document.getElementById('chart-title').textContent =
        _maestro ? _maestro.split(' ').slice(0,3).join(' ') : 'Todos los docentes';
    document.getElementById('chart-subtitle').textContent =
        _periodo === 'general' ? 'Mes completo' : _periodo === 'quincena_1' ? 'Quincena 1 (días 1–15)' : 'Quincena 2 (días 16–fin)';

    const ctx = document.getElementById('pie-chart').getContext('2d');
    if (_pieChart) _pieChart.destroy();
    _pieChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Puntual','Tolerancia','Falta'],
            datasets: [{
                data: [s.puntual, s.tolerancia, s.falta],
                backgroundColor: ['#28a745','#C5A300','#dc3545'],
                borderWidth: 2,
                borderColor: '#fff'
            }]
        },
        options: {
            cutout: '62%',
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: c => {
                    const v = c.parsed, tot = c.dataset.data.reduce((a,b)=>a+b,0);
                    return ` ${v.toLocaleString()} (${tot?((v/tot)*100).toFixed(1):0}%)`;
                }}}
            }
        }
    });

    const tot = s.total || 1;
    document.getElementById('pie-legend').innerHTML = `
        <div class="legend-item">
            <div class="legend-left"><div class="legend-dot" style="background:#28a745"></div>Puntual</div>
            <span class="legend-val">${pct(s.puntual,tot)} &nbsp; <small style="color:#999">${s.puntual.toLocaleString()}</small></span>
        </div>
        <div class="legend-item">
            <div class="legend-left"><div class="legend-dot" style="background:#C5A300"></div>Tolerancia</div>
            <span class="legend-val">${pct(s.tolerancia,tot)} &nbsp; <small style="color:#999">${s.tolerancia.toLocaleString()}</small></span>
        </div>
        <div class="legend-item">
            <div class="legend-left"><div class="legend-dot" style="background:#dc3545"></div>Falta</div>
            <span class="legend-val">${pct(s.falta,tot)} &nbsp; <small style="color:#999">${s.falta.toLocaleString()}</small></span>
        </div>`;
}

// ── Tabla ──
function renderTable() {
    if (!_data) return;
    const container = document.getElementById('table-container');
    const hasExtra = _data.por_profesor.length > 0 && (
        'SEMESTRE' in _data.por_profesor[0] || 'GENERACION' in _data.por_profesor[0] || 'ID' in _data.por_profesor[0]
    );
    const showSemester = hasExtra && 'SEMESTRE' in _data.por_profesor[0];
    const showGeneration = hasExtra && 'GENERACION' in _data.por_profesor[0];
    const showId = hasExtra && 'ID' in _data.por_profesor[0];

    // Vista de docente individual: muestra los 3 periodos
    if (_maestro) {
        const prof = _data.por_profesor.find(p => p.PROFESOR === _maestro);
        if (!prof) return;
        const meta = [];
        if (showId && prof.ID) meta.push(`ID: ${prof.ID}`);
        if (showSemester && prof.SEMESTRE) meta.push(`Semestre: ${prof.SEMESTRE}`);
        if (showGeneration && prof.GENERACION) meta.push(`Generación: ${prof.GENERACION}`);
        document.getElementById('table-title').textContent = prof.PROFESOR.split(' ').slice(0,4).join(' ');
        if (meta.length) {
            document.getElementById('table-title').textContent += ` — ${meta.join(' · ')}`;
        }

        const rows = [
            { label:'Mes completo',  d: prof.general },
            { label:'Quincena 1',    d: prof.quincena_1 },
            { label:'Quincena 2',    d: prof.quincena_2 },
        ].map(({ label, d }) => {
            const asist = d.TOTAL ? (((d.PUNTUAL+d.TOLERANCIA)/d.TOTAL)*100).toFixed(1)+'%' : '—';
            const sem   = semaforo(d.PUNTUAL, d.TOLERANCIA, d.TOTAL);
            return `<tr>
                <td>${sem}<strong>${label}</strong></td>
                <td><span class="badge badge-p">${d.PUNTUAL}</span></td>
                <td><span class="badge badge-t">${d.TOLERANCIA}</span></td>
                <td><span class="badge badge-f">${d.FALTA}</span></td>
                <td><strong>${d.TOTAL}</strong></td>
                <td class="pct-cell">${asist}</td>
            </tr>`;
        }).join('');
        container.innerHTML = `
            <table>
                <thead><tr>
                    <th>Periodo</th>
                    <th>Puntual</th>
                    <th>Tolerancia</th>
                    <th>Falta</th>
                    <th>Total</th>
                    <th>Asistencia</th>
                </tr></thead>
                <tbody>${rows}</tbody>
            </table>`;
        return;
    }

    // Vista general
    const list = getFilteredSorted();
    document.getElementById('table-title').textContent = `Docentes (${list.length} mostrados)`;

    if (list.length === 0) {
        container.innerHTML = '<p class="no-results">No se encontraron docentes con ese nombre.</p>';
        return;
    }

    const rows = list.map(p => {
        const d   = getD(p);
        const a   = d.TOTAL ? (((d.PUNTUAL+d.TOLERANCIA)/d.TOTAL)*100).toFixed(1) : '0';
        const sem = semaforo(d.PUNTUAL, d.TOLERANCIA, d.TOTAL);
        return `<tr>
            <td class="cell-name">${sem}${p.PROFESOR}${showId && p.ID ? ` <span class="meta">(${p.ID})</span>` : ''}</td>
            ${showSemester ? `<td>${p.SEMESTRE || '–'}</td>` : ''}
            ${showGeneration ? `<td>${p.GENERACION || '–'}</td>` : ''}
            <td><span class="badge badge-p">${d.PUNTUAL}</span></td>
            <td><span class="badge badge-t">${d.TOLERANCIA}</span></td>
            <td><span class="badge badge-f">${d.FALTA}</span></td>
            <td>${d.TOTAL}</td>
            <td class="pct-cell">${a}%</td>
        </tr>`;
    }).join('');

    container.innerHTML = `
        <table>
            <thead><tr>
                <th class="sortable" onclick="toggleSort('PROFESOR')">Docente ${sortIcon('PROFESOR')}</th>
                ${showSemester ? '<th>Semestre</th>' : ''}
                ${showGeneration ? '<th>Generación</th>' : ''}
                <th class="sortable" onclick="toggleSort('PUNTUAL')">Puntual ${sortIcon('PUNTUAL')}</th>
                <th class="sortable" onclick="toggleSort('TOLERANCIA')">Tolerancia ${sortIcon('TOLERANCIA')}</th>
                <th class="sortable" onclick="toggleSort('FALTA')">Falta ${sortIcon('FALTA')}</th>
                <th class="sortable" onclick="toggleSort('TOTAL')">Total ${sortIcon('TOTAL')}</th>
                <th class="sortable" onclick="toggleSort('ASIST')">Asistencia % ${sortIcon('ASIST')}</th>
            </tr></thead>
            <tbody>${rows}</tbody>
        </table>`;
}

// ── Gráfica comparativa horizontal ──
function renderComparativeChart() {
    if (!_data) return;
    const ctx = document.getElementById('bar-chart').getContext('2d');
    if (_barChart) _barChart.destroy();

    let sorted = [..._data.por_profesor]
        .filter(p => getD(p).TOTAL > 0)
        .sort((a,b) => {
            const da = getD(a), db = getD(b);
            return (db.FALTA/db.TOTAL) - (da.FALTA/da.TOTAL);
        });

    if (_barLimit > 0) sorted = sorted.slice(0, _barLimit);

    document.getElementById('bar-container').style.height =
        Math.max(420, sorted.length * 30) + 'px';

    const labels = sorted.map(p => {
        const parts = p.PROFESOR.split(/[\s-]+/);
        return parts.slice(0,2).join(' ');
    });

    _barChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label:'Puntual',    data: sorted.map(p=>getD(p).PUNTUAL),    backgroundColor:'#28a745' },
                { label:'Tolerancia', data: sorted.map(p=>getD(p).TOLERANCIA), backgroundColor:'#C5A300' },
                { label:'Falta',      data: sorted.map(p=>getD(p).FALTA),      backgroundColor:'#dc3545' },
            ]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top' },
                tooltip: { mode: 'index', intersect: false }
            },
            scales: { x: { stacked: true }, y: { stacked: true } }
        }
    });
}

// ── Tendencia semanal ──
function renderWeekChart() {
    if (!_data || !_data.por_dia_semana || _data.por_dia_semana.length === 0) return;
    document.getElementById('week-section').style.display = 'block';

    const ctx = document.getElementById('week-chart').getContext('2d');
    if (_weekChart) _weekChart.destroy();
    const dias = _data.por_dia_semana;

    _weekChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: dias.map(d => d.dia),
            datasets: [
                { label:'Puntual',    data: dias.map(d=>d.PUNTUAL),    backgroundColor:'#28a745' },
                { label:'Tolerancia', data: dias.map(d=>d.TOLERANCIA), backgroundColor:'#C5A300' },
                { label:'Falta',      data: dias.map(d=>d.FALTA),      backgroundColor:'#dc3545' },
            ]
        },
        options: {
            responsive: true,
            plugins: { legend: { position: 'top' }, tooltip: { mode: 'index', intersect: false } },
            scales: { x: { stacked: true }, y: { stacked: true } }
        }
    });
}

// ── Top docentes puntuales ──
function setTopPuntualLimit(n, btn) {
    _topPuntualLimit = n;
    document.querySelectorAll('.puntual-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    renderTopPuntualChart();
}

function renderTopPuntualChart() {
    if (!_data) return;
    const ctx = document.getElementById('top-puntual-chart').getContext('2d');
    if (_topPuntualChart) _topPuntualChart.destroy();

    let sorted = [..._data.por_profesor]
        .filter(p => getD(p).TOTAL > 0)
        .sort((a, b) => {
            const da = getD(a), db = getD(b);
            const pctA = (da.PUNTUAL + da.TOLERANCIA) / da.TOTAL;
            const pctB = (db.PUNTUAL + db.TOLERANCIA) / db.TOTAL;
            return pctB - pctA;
        });

    if (_topPuntualLimit > 0) sorted = sorted.slice(0, _topPuntualLimit);

    document.getElementById('puntual-container').style.height =
        Math.max(420, sorted.length * 30) + 'px';

    const labels = sorted.map(p => {
        const parts = p.PROFESOR.split(/[\s-]+/);
        return parts.slice(0, 2).join(' ');
    });

    _topPuntualChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label: 'Puntual',    data: sorted.map(p => getD(p).PUNTUAL),    backgroundColor: '#28a745' },
                { label: 'Tolerancia', data: sorted.map(p => getD(p).TOLERANCIA), backgroundColor: '#C5A300' },
                { label: 'Falta',      data: sorted.map(p => getD(p).FALTA),      backgroundColor: '#dc3545' },
            ]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top' },
                tooltip: { mode: 'index', intersect: false }
            },
            scales: { x: { stacked: true }, y: { stacked: true } }
        }
    });
}

// ── Exportar PDF (simplificado para maestría) ──
async function exportarPDF() {
    if (!_data) return;
    alert('Función de exportar PDF disponible próximamente');
}

// ── Días inhabiles (gestión básica) ──
async function abrirModalDiasInhabiles() {
    document.getElementById('modal-dias-inhabiles').style.display = 'block';
    await cargarListaDiasInhabiles();
}

function cerrarModalDiasInhabiles() {
    document.getElementById('modal-dias-inhabiles').style.display = 'none';
}

async function cargarListaDiasInhabiles() {
    try {
        const res = await fetch('/api/diasinhabiles');
        if (res.status === 401) return;
        const dias = await res.json();
        const lista = document.getElementById('dias-list');
        
        if (!dias.length) {
            lista.innerHTML = '<p style="color:#999; text-align:center;">No hay días inhabiles registrados</p>';
            return;
        }
        
        lista.innerHTML = dias.map(fecha => {
            const d = new Date(fecha + 'T12:00:00');
            const nombreDia = ['Domingo','Lunes','Martes','Miércoles','Jueves','Viernes','Sábado'][d.getDay()];
            const display = `${nombreDia} ${d.getDate()} de ${['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'][d.getMonth()]} de ${d.getFullYear()}`;
            return `<div style="display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid #eee;">
                <span>${display} (${fecha})</span>
                <button class="btn-del" onclick="eliminarDiaInhabible('${fecha}')">✕</button>
            </div>`;
        }).join('');
    } catch(e) {
        document.getElementById('dias-list').innerHTML = '<p style="color:#999;">Error al cargar días</p>';
    }
}

async function agregarDiaInhabible() {
    const fecha = document.getElementById('fecha-input').value;
    if (!fecha) {
        alert('Selecciona una fecha');
        return;
    }
    
    try {
        const res = await fetch('/api/diasinhabiles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
            body: JSON.stringify({ fecha })
        });
        const data = await res.json();
        
        const msgDiv = document.getElementById('resultado-mensaje');
        if (res.ok) {
            msgDiv.style.backgroundColor = '#d4edda';
            msgDiv.style.color = '#155724';
            msgDiv.textContent = '✓ Día inhabible agregado';
            document.getElementById('fecha-input').value = '';
        } else {
            msgDiv.style.backgroundColor = '#f8d7da';
            msgDiv.style.color = '#721c24';
            msgDiv.textContent = '✗ ' + (data.error || 'Error');
        }
        msgDiv.style.display = 'block';
        setTimeout(() => { msgDiv.style.display = 'none'; }, 3000);
        await cargarListaDiasInhabiles();
    } catch(e) {
        alert('Error: ' + e.message);
    }
}

async function eliminarDiaInhabible(fecha) {
    if (!confirm('¿Eliminar este día inhabible?')) return;
    
    try {
        const res = await fetch(`/api/diasinhabiles/${fecha}`, {
            method: 'DELETE',
            headers: { 'X-CSRF-Token': getCsrfToken() }
        });
        if (res.ok) await cargarListaDiasInhabiles();
    } catch(e) {
        alert('Error: ' + e.message);
    }
}

async function logout() {
    await fetch('/api/logout', { method: 'POST' });
    window.location.href = 'login.html';
}

// ── Inicializar al cargar ──
document.addEventListener('DOMContentLoaded', async () => {
    if (!ensureServerMode()) return;
    const sesion = await verificarSesion();
    if (sesion) inicializar();
});
