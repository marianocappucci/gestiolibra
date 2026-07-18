# Convenciones de Gestiolibra

- `app/` contiene la API y los casos de uso propios del negocio; no duplicar reglas de LibraGenda.
- LibraGenda se configura al arranque mediante `LIBRAGENDA_DATABASE_URL`.
- Migraciones de LibraGenda se ejecutan antes de iniciar la API; el `create_all()` del demo no se usa en producción.
- Routers HTTP traducen errores de dominio a códigos 404/409/422; no exponen tracebacks.
- Modelos clínicos no entran aquí; gastronomía pertenece a Restolibra.
- Tests unitarios para negocio y smoke tests HTTP para cada flujo principal.
- Secretos en `.env` fuera de Git; dependencias internas pineadas a tags exactos.
