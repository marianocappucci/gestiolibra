# Guía de onboarding — Cliente nuevo en Gestiolibra

Esta guía es para vos, Mariano. Describe el proceso completo para dar de alta a un cliente
nuevo de Gestiolibra —barberías, peluquerías, lavaderos, estética, talleres— desde la
contratación hasta que está operando.

> **Qué es Gestiolibra y qué no.** Es un vertical de **turnos para negocios de servicios**:
> agenda, clientes, servicios, sucursales, recursos (sillón, box, puesto), recordatorios y
> señas. La facturación existe pero es un módulo **Premium**, no el centro del producto. Si
> el cliente lo que necesita es facturar, el producto es Contalibra; si es un consultorio o
> centro médico, es MedLibra.

---

## Resumen del proceso

1. Recopilar datos del cliente
2. Levantar la instancia
3. Primer acceso
4. Configurar el negocio, las sucursales y los horarios
5. Cargar servicios, precios y recursos
6. Aplicar el plan contratado
7. Configurar integraciones (recordatorios, ARCA) según el plan
8. Crear los usuarios
9. Handoff: primer ingreso con el cliente

---

## 1. Datos a recopilar antes de empezar

| Dato | Para qué sirve |
|------|----------------|
| Nombre comercial | Aparece en la app y en los recordatorios |
| Slug | Nombre corto sin espacios: define `clientes/<slug>/` y el subdominio |
| Plan contratado | Define qué módulos quedan habilitados |
| Sucursales | Nombre y dirección de cada una; una sola también es válido |
| Horarios de atención | Por sucursal y por día; es lo que habilita la grilla de turnos |
| Servicios que ofrece | Nombre y duración de cada uno — la duración define el largo del turno |
| Precios por servicio | Se pueden cargar distintos por sucursal |
| Recursos | Sillones, boxes, puestos: cuántos y cómo se llaman |
| ¿Cobra seña? | Módulo `senas`, desde el plan Estándar |
| ¿Quiere recordatorios? | Módulo `recordatorios`, desde el plan Estándar |
| ¿Necesita facturar? | Módulo `facturacion` + ARCA, sólo en Premium |
| Usuario y contraseña del admin | Para el primer acceso — comunicar por WhatsApp, no por email |

---

## 2. Levantar la instancia

Cada cliente corre en su propio contenedor, aislado en `clientes/<slug>/`, todos compartiendo
la imagen `gestiolibra:latest`. El código nunca se copia por cliente: sólo se crean datos y
configuración propios. El puerto base de este producto es **8076** (los va asignando el
provisioning, que mira los puertos realmente ocupados del host).

### Setup único del servidor

`nuevo_cliente.py` y `panel_admin.py` son wrappers finos sobre `libracore.provisioning`, y el
Python del sistema del VPS no tiene `pip` por política de Debian (PEP 668). Por eso corren con
un venv dedicado en `/root/gestiolibra/.venv-scripts`, **gitignored — no se versiona y no llega
por `git pull`**. Si hay que recrearlo:

```bash
apt-get install -y python3-venv
python3 -m venv /root/gestiolibra/.venv-scripts
/root/gestiolibra/.venv-scripts/bin/pip install \
  "libracore @ git+ssh://git@github-libracore/marianocappucci/libracore.git@<TAG>"
```

Dos cosas que no son obvias:

- **`<TAG>` es el pin que declara el `pyproject.toml` de *este* repo**, no un número común a
  la familia. Cada producto pinea su propia versión de LibraCore, y el venv del host tiene que
  espejar la suya: si queda atrás, el CLI opera con un motor distinto del que corre la
  instancia. Ya frenó un deploy de Contalibra por eso.
- **La URL va por SSH (`git+ssh://git@github-libracore/…`), no por HTTPS.** En este VPS el
  `https://` del `pyproject.toml` falla: la autenticación es por deploy key con alias en
  `~/.ssh/config`. `httpx` y el resto de las dependencias entran solas con LibraCore.

### Alta de un cliente nuevo

En el servidor, desde `/root/gestiolibra`:

```bash
./.venv-scripts/bin/python3 scripts/nuevo_cliente.py
```

El wizard pide nombre, slug, puerto, dominio, plan y credenciales de admin; crea
`clientes/<slug>/` (compose + `data/` con base, config y adjuntos aislados), buildea la imagen
si falta, levanta el contenedor y —si hay dominio— crea el proxy y el certificado en Nginx
Proxy Manager.

### Gestión del día a día

```bash
./.venv-scripts/bin/python3 scripts/panel_admin.py            # menú interactivo
./.venv-scripts/bin/python3 scripts/panel_admin.py listar     # instancias, puerto y estado
./.venv-scripts/bin/python3 scripts/panel_admin.py info <slug>
./.venv-scripts/bin/python3 scripts/panel_admin.py backup <slug>
./.venv-scripts/bin/python3 scripts/panel_admin.py actualizar [slug...]   # sin args = todas
./.venv-scripts/bin/python3 scripts/panel_admin.py pausar <slug>          # banner, sin cortar acceso
./.venv-scripts/bin/python3 scripts/panel_admin.py suspender <slug>       # corta el acceso
```

Lo mismo se hace por navegador desde el backoffice, en **https://admin.gestiolibra.com.ar**
(alta, baja, edición, plan, backup, SMTP y usuarios de cada instancia).

### DNS y dominio

- El wildcard `*.gestiolibra.com.ar` ya apunta al VPS: **no hay que tocar DNS** por cliente.
- El subdominio es `<slug>.gestiolibra.com.ar`, y el proxy + SSL los crea el alta.
- Para gestionarlos a mano: `panel_admin.py npm-crear | npm-eliminar | npm-listar`.

> ⚠️ **Al dar de baja una instancia, el proxy no se va solo.** `eliminar` baja el contenedor y
> borra el directorio, nada más. Correr **`npm-eliminar <slug>` antes**, porque después no
> queda `cliente.json` de donde leer el dominio — y ese comando depende de que el campo
> `domain` esté cargado ahí.

---

## 3. Primer acceso

```
URL: https://<slug>.gestiolibra.com.ar
Usuario: el que definiste en el alta
Contraseña: la que definiste — comunicarla por WhatsApp
```

Verificar que cargue la SPA y que el login funcione antes de seguir.

---

## 4. Configurar el negocio, sucursales y horarios

Este es el paso que más cambia respecto de los productos contables: **sin horarios cargados no
hay grilla de turnos**, y la agenda se ve vacía aunque todo lo demás esté bien.

- [ ] **Negocio**: nombre, contacto, zona horaria
- [ ] **Sucursales**: crear cada una con su nombre y dirección
- [ ] **Horarios por sucursal**: días y franjas de atención
- [ ] **Recursos**: sillones/boxes/puestos de cada sucursal

---

## 5. Servicios y precios

- [ ] Cargar cada **servicio** con su duración real — de ahí sale el largo del turno
- [ ] Cargar los **precios**, que pueden diferir por sucursal
- [ ] Verificar en la agenda que un turno de prueba tome la duración correcta

---

## 6. Plan y módulos

El plan se asigna en el alta y se puede cambiar después desde el backoffice. Lo que cambia es
qué módulos quedan habilitados:

| Plan | Precio | Qué habilita |
|------|--------|--------------|
| Básico | $15.000 | Agenda, turnos, clientes, servicios, sucursales y recursos |
| Estándar | $25.000 | Todo lo anterior + **recordatorios** y **señas** |
| Premium | $40.000 | Todo lo anterior + **facturación** y **dashboard** |

> **El core no se gatea.** Agenda, turnos y clientes están en todos los planes: un Gestiolibra
> sin turnos no es un plan más barato, es otra cosa. Lo que se vende por nivel es
> recordatorios/señas y facturación/dashboard. La fuente de verdad es `plans.py` de este repo.

---

## 7. Integraciones

### Recordatorios (plan Estándar en adelante)

Verificar con el cliente por qué canal quiere avisar y con cuánta anticipación, y **probar con
un turno real** antes del handoff: un recordatorio que no sale no avisa que no salió.

### Correo saliente (SMTP)

Se configura por instancia desde el backoffice (**Configuración → SMTP** en
`admin.gestiolibra.com.ar`), no dentro de la app. Para Gmail hay que usar una contraseña de
aplicación, no la del usuario.

### ARCA / facturación electrónica (sólo Premium)

Si el cliente contrató Premium y va a facturar, la configuración vive en `/config/arca` de la
instancia: certificado `.crt`, clave `.key`, CUIT y punto de venta. Probar primero en
**homologación** y recién después pasar a producción.

---

## 8. Usuarios

Los roles de Gestiolibra son dos (`Role` en `app/routers/users.py`):

| Rol | Puede hacer |
|-----|-------------|
| `admin` | Todo: configuración, usuarios, sucursales, servicios, facturación |
| `staff` | El día a día: agenda, turnos y clientes |

- [ ] Crear un `admin` para el dueño o encargado
- [ ] Crear un `staff` por cada persona que atienda
- [ ] Comunicar las credenciales de forma segura

---

## 9. Handoff con el cliente

Sesión de capacitación, en este orden:

1. **Ingresar** — URL, usuario, contraseña
2. **Cargar un turno** desde la agenda y ver cómo ocupa el recurso
3. **Reprogramar y cancelar** ese turno
4. **Dar de alta un cliente** y buscarlo en el historial
5. **Cobrar una seña** (si tiene el módulo)
6. **Ver el recordatorio** que salió por ese turno (si tiene el módulo)
7. **Dashboard** del día (si es Premium)

Al terminar:

- [ ] Cambiar la contraseña del admin por una que defina el cliente
- [ ] Confirmar que puede cargar un turno sin ayuda
- [ ] Dejar el número de soporte

---

## 10. Post-onboarding (primera semana)

- [ ] Contactarlo a los 2-3 días
- [ ] Verificar que los recordatorios estén saliendo
- [ ] Revisar que los horarios cargados coincidan con los reales (es el error más común)

---

## Checklist resumen

```
DATOS
[ ] Nombre, slug, plan, sucursales y horarios recopilados
[ ] Servicios con duración y precios definidos

INSTANCIA
[ ] Levantada y accesible por HTTPS
[ ] Login funciona

CONFIGURACIÓN
[ ] Negocio, sucursales y horarios cargados
[ ] Recursos cargados
[ ] Servicios y precios cargados
[ ] Plan aplicado y módulos correctos
[ ] Recordatorios probados con un turno real (si aplica)
[ ] SMTP configurado y probado (si aplica)
[ ] ARCA en homologación probada (si aplica)

USUARIOS
[ ] admin creado
[ ] staff creados

CAPACITACIÓN
[ ] Handoff hecho
[ ] El cliente carga un turno solo

POST-ONBOARDING
[ ] Seguimiento a los 3 días
[ ] Horarios y recordatorios verificados en uso real
```

---

## Contacto de soporte

- WhatsApp: +54 9 11 2775-2983
- Email: soporte@gestiolibra.com.ar
