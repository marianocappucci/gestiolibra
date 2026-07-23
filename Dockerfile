# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends openssl git openssh-client && rm -rf /var/lib/apt/lists/*

# pyproject.toml referencia LibraGenda/LibraCore via git+https (asi
# funciona tambien el dev local en WSL, que no tiene identidad SSH contra
# GitHub -- ver wiki/entities/libracore.md). El build en el VPS reescribe
# esas URLs a git+ssh (--mount=type=ssh, agente con las dos deploy keys de
# solo lectura cargadas -- libracore ya tenia la suya, libragenda es
# nueva, GitHub no permite reusar una deploy key entre repos) y las
# descarta con la imagen: ninguna clave queda en ninguna capa.
RUN mkdir -p -m 0700 /root/.ssh && ssh-keyscan github.com >> /root/.ssh/known_hosts 2>/dev/null

COPY . .
RUN --mount=type=ssh \
    git config --global url."ssh://git@github.com/".insteadOf "https://github.com/" \
    && pip install --no-cache-dir . \
    && git config --global --unset url."ssh://git@github.com/".insteadOf

EXPOSE 8000

CMD ["uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
