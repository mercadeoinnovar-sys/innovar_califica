# INNOVAR SERVICE – Sistema de Calificación y Ranking de Asesores
### Grupo Innovar Colombia (Ibagué, Girardot, Neiva)

Plataforma web empresarial desarrollada para **Grupo Innovar** destinada a evaluar el servicio al cliente en puntos de venta mediante códigos QR, calcular rankings ponderados en tiempo real y reconocer a los mejores asesores comerciales.

---

## 🎨 Identidad Visual Corporativa

- **Marca:** INNOVAR SERVICE &bull; Grupo Innovar.
- **Paleta de Colores Institucional:**
  - **Rojo Corporativo:** `#D90429` (Principal) y `#B50322` (Interacciones).
  - **Fondo y Contrastes:** Blanco puro `#FFFFFF`, Grafito oscuro `#111827`, Carbón `#1F2937` y Gris pizarra `#4B5563`.
  - **Acentos de Reconocimiento:** Dorado `#FFB703`, Plata `#94A3B8`, Bronce `#B45309`.
- **Tipografía:** Google Font **Montserrat** (pesos 400 a 800) para máxima legibilidad ejecutiva.
- **Iconografía:** Bootstrap Icons (v1.11.3) y gráficos interactivos con Chart.js.
- **Diseño Responsive:** Optimizado con Bootstrap 5.3 para smartphones (módulo QR), tablets y pantallas de escritorio.

---

## 🏛️ Módulos de la Plataforma

1. **Módulo de Clientes (Calificación QR):**
   - Acceso directo mediante escaneo de código QR en mostrador.
   - Identificación automática del asesor y la sede.
   - Encuesta interactiva con 5 preguntas clave con botones táctiles.
   - Selector interactivo de **5 Estrellas** con retroalimentación inmediata.
   - Protección contra calificaciones duplicadas el mismo día.
   - Cumplimiento de política de tratamiento de datos personales (Ley 1581).

2. **Módulo de Ranking ("Cuadro de Honor"):**
   - Podio destacado con medallas (🥇 1° Lugar, 🥈 2° Lugar, 🥉 3° Lugar).
   - Filtros dinámicos por ciudad (Ibagué, Girardot, Neiva), por sede específica y período (Mensual / Histórico).
   - Umbral de 5 evaluaciones mínimas para aparecer en el ranking oficial y sección para asesores en proceso.

3. **Módulo de Asesor (Perfil Motivacional):**
   - Frases motivacionales dinámicas según el nivel de desempeño.
   - Indicadores individuales: promedio, evaluaciones totales, posición nacional y porcentaje de satisfacción.
   - Desglose gráfico de calificaciones (1 a 5 estrellas).
   - Insignias de reconocimiento obtenidas (Asesor 5 Estrellas, Excelente Atención, Líder de Satisfacción, etc.).
   - Muro de comentarios y sugerencias verificadas de clientes.
   - Visualización y descarga del código QR personal.

4. **Módulo Administrativo (Dashboard Ejecutivo):**
   - Tarjetas KPI: total de asesores, activos, evaluaciones acumuladas, promedio general y satisfacción %.
   - Gráfico de dona (Chart.js) de distribución de calificaciones.
   - Gráfico de barras (Chart.js) con volumen de evaluaciones por ciudad.
   - Tabla con filtros combinados y paginación rápida.
   - **Exportación directa a Excel (formato CSV con codificación UTF-8 BOM)**.

5. **Gestión de Códigos QR:**
   - Catálogo de QR individuales por asesor y códigos generales por sede.
   - Generación automática de imágenes PNG de alta resolución.
   - Botón de descarga de imagen y botón de copiado de URL directa al portapapeles.

---

## 🚀 Puesta en Marcha en tu Máquina

### 1. Activar el Entorno Virtual
Abre tu PowerShell en la carpeta del proyecto (`C:\innovar_califica`):
```powershell
.\.venv\Scripts\activate
```

### 2. Iniciar el Servidor de Desarrollo
```powershell
python manage.py runserver 0.0.0.0:8000
```

### 3. Navegar por los Módulos
- **Inicio / Landing Institucional:** [http://localhost:8000/](http://localhost:8000/)
- **Módulo de Clientes (Formulario QR):** [http://localhost:8000/evaluate/](http://localhost:8000/evaluate/)
- **Ranking Oficial y Podio:** [http://localhost:8000/ranking/](http://localhost:8000/ranking/)
- **Dashboard Administrativo:** [http://localhost:8000/admin-dashboard/](http://localhost:8000/admin-dashboard/)
- **Gestión de Códigos QR:** [http://localhost:8000/qr-management/](http://localhost:8000/qr-management/)
- **Perfil de Asesor de Ejemplo:** [http://localhost:8000/advisor/1/](http://localhost:8000/advisor/1/)
- **Panel Django Admin:** [http://localhost:8000/admin/](http://localhost:8000/admin/)
