# Convenciones de Gestiolibra

- `app/` contiene la API y los casos de uso propios del negocio; no duplicar reglas de LibraGenda.
- LibraGenda se configura al arranque mediante `LIBRAGENDA_DATABASE_URL`.
- Migraciones de LibraGenda se ejecutan antes de iniciar la API; el `create_all()` del demo no se usa en producción.
- Routers HTTP traducen errores de dominio a códigos 404/409/422; no exponen tracebacks.
- Modelos clínicos no entran aquí; gastronomía pertenece a Restolibra.
- Tests unitarios para negocio y smoke tests HTTP para cada flujo principal.
- Secretos en `.env` fuera de Git; dependencias internas pineadas a tags exactos.

## Dónde se arregla (regla de la familia, 2026-10-03)

**El arreglo de fondo vive siempre en el motor** (`libracore`; `libracommerce` y `libra-ui` para
lo suyo), **nunca en este repo.** Lo que otro producto comparte o podría compartir —el protocolo
con ARCA, las reglas fiscales y sus validaciones, las guardas contra duplicados, la numeración, la
cuenta corriente, los componentes de pantalla compartidos— se escribe y se arregla en el motor.
Este repo sólo aporta **costuras** (los hooks que el motor ya expone) y lo suyo: pantallas,
textos y su modelo de datos propio. Si falta la costura, se agrega al motor; si el arreglo hace
falta antes, igual se hace en el motor (PR y tag) y acá se sube el pin: nada «provisorio» en este
repo. Un hueco que se encuentra acá se busca en los demás productos antes de darlo por acotado.
Detalle y motivo: `reglas/producto.md` del wiki.
