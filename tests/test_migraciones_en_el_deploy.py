"""Que las dos cadenas de Alembic esten declaradas, y que la imagen las lleve.

🔴 **Tener el mecanismo no es tenerlo invocado.** Hasta el 2026-08-24 ningun
paso del deploy corria las migraciones de este producto: los `alembic upgrade`
del repo estaban en la suite y en los scripts de dev, y el esquema de las
instancias vivas lo armaba `Base.metadata.create_all()` al bootear. La linea de
`app/main.py` que dice *"demo only; deploy uses Alembic"* era, literalmente,
falsa.

Lo que se fija aca es lo que se rompe en silencio:

1. que **los dos** scripts declaren las migraciones —el `panel_admin.py` las
   corre al actualizar y el `nuevo_cliente.py` al dar de alta; que uno solo las
   tenga es peor que ninguno, porque el alta y el deploy dejarian la instancia
   en estados distintos—;
2. que la cadena de **LibraGenda vaya primero** —las revisiones de este producto
   tienen FK contra sus tablas—;
3. y que la imagen lleve con que correrlas.
"""
from __future__ import annotations

import contextlib
import importlib
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
#: Las CUATRO cadenas, en orden. `libraauth-migrar` entró el 2026-09-16 (la
#: adopción de la cadena de auth). `libracore-migrar` entró el 2026-08-25 y su cadena no la
#: corría nadie porque las migraciones del motor no viajaban en el wheel. Con una sola base
#: (ADR-035) la resuelve por `GESTIOLIBRA_DATABASE_URL`, porque `gestiolibra` figura en
#: `_UNA_SOLA_BASE` del motor; en la demo, que todavía tiene dos, por la variable del core.
ESPERADO = (
    ("libragenda-migrar", "upgrade"),
    ("libraauth-migrar", "upgrade", "--prefijo", "gestiolibra", "--base", "core"),
    ("libracore-migrar", "upgrade", "--prefijo", "gestiolibra"),
    ("alembic", "upgrade", "head"),
)


def _leer_de_la_config(script: str, expresion: str):
    """Evalua `expresion` sobre la `ProductConfig` (`config`) que deja el `configure()` de ese script al importarlo.

    Se importa en un proceso aparte: `configure()` escribe un global del motor y
    los dos scripts lo pisarian entre si, dando un verde que no dice de cual de
    los dos salio. Devuelve el resultado ya pasado por JSON.
    """
    import json

    codigo = (
        "import json, sys;"
        f"sys.path.insert(0, {str(RAIZ)!r});"
        f"sys.path.insert(0, {str(RAIZ / 'scripts')!r});"
        f"import importlib; importlib.import_module({script!r});"
        "from libracore.provisioning import get_config;"
        "config = get_config();"
        f"print(json.dumps({expresion}))"
    )
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True,
                       text=True, cwd=str(RAIZ))
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout)


def _config_de(script: str):
    return tuple(tuple(c) for c in _leer_de_la_config(script, "config.migraciones"))


@pytest.mark.parametrize("script", ["panel_admin", "nuevo_cliente"])
def test_los_dos_scripts_declaran_LAS_CUATRO_cadenas(script):
    assert _config_de(script) == ESPERADO


def test_el_orden_de_las_cadenas_es_el_que_importa():
    """Explicito ademas del `==` de arriba: si manana se agrega un comando, el
    `==` se cae por el motivo equivocado y esto dice cual era la afirmacion.

    El orden no es decorativo:

    - **LibraGenda primero** porque las revisiones de este producto tienen FK
      contra sus tablas.
    - **La propia al final**, por lo mismo.
    - **LibraCore en el medio**: corre contra otra base, asi que su posicion es
      libre, pero fijarla evita que el `==` de arriba sea la unica afirmacion.
    """
    comandos = _config_de("panel_admin")
    assert len(comandos) == 4, f"esperaba las cuatro cadenas, llegaron {comandos}"
    assert comandos[0][0] == "libragenda-migrar"
    assert comandos[1][0] == "libraauth-migrar"
    assert comandos[2][0] == "libracore-migrar"
    assert comandos[-1][:2] == ("alembic", "upgrade")

    # 🔑 El `--prefijo` es lo que hace que `libracore-migrar` NO tome
    # `DATABASE_URL` --- que en este contenedor apunta al dominio --- sino la
    # variable de la base del core. Sin el, migraria la base equivocada y
    # devolveria exito.
    assert "--prefijo" in comandos[2], (
        "sin `--prefijo`, `libracore-migrar` cae a DATABASE_URL, que aca es la "
        "base del DOMINIO y no la del core")


def test_el_pin_de_libragenda_trae_el_comando_instalable():
    """`libragenda-migrar` es un `[project.scripts]` que aparecio en la v0.9.1.
    Con un pin anterior, el comando no existe en la imagen y el deploy se cae en
    el primer paso --- verificado en los contenedores vivos el 2026-08-24, donde
    con el pin v0.9.0 no estaba."""
    pins = _pins()
    assert _version(pins["libragenda"]) >= (0, 9, 1), pins["libragenda"]


def test_el_adaptador_de_turnos_acompana_el_pin_de_libragenda():
    """Desde `v0.10.0` el scheduler crea con `repository.reserve(...)` (la reserva
    atomica, ADR-013), no con `save`. El adaptador de hora local de este producto
    ---`_TurnosEnHoraLocal`--- tiene que ofrecer `reserve` o todos los altas de
    turno se caen con `AttributeError: ... has no attribute 'reserve'`.

    Reemplaza al guard que frenaba el pin en `< v0.10.0` hasta que estuviera
    implementado: se adapto el 2026-09-03 (el `reserve` traduce hora local <-> UTC
    envolviendo el validador). Este test lo sostiene desde el otro lado --- si el
    metodo se borra, o el pin sube sin el, el CI lo agarra --- y por eso mira el
    codigo real y no solo el numero del pin.
    """
    from app.services.appointments import _TurnosEnHoraLocal

    pins = _pins()
    if _version(pins["libragenda"]) >= (0, 10, 0):
        assert hasattr(_TurnosEnHoraLocal, "reserve"), (
            "el pin de libragenda esta en v0.10.0+, que exige `reserve()` en "
            "`_TurnosEnHoraLocal`; sin el, los altas de turno se caen en runtime")


def test_el_adaptador_de_turnos_implementa_TODO_el_puerto_de_libragenda():
    """El guard de arriba, pero sin una lista de metodos escrita a mano.

    El de arriba nombra `reserve`, asi que cubre el metodo que existia el dia
    que se escribio y **ninguno** de los que el motor agregue despues. Ya pasó
    una vez: LibraGenda sumo `relocate` --el `reserve` de reagendar, con el
    mismo lock-- y nada en este repo lo habria exigido al subir el pin; el
    sintoma habria sido un `AttributeError` en runtime, al mover un turno.

    Este mira el puerto **instalado** y pide que el adaptador ofrezca todo lo
    que declare. Cuando el pin sube, el guard se actualiza solo: no hay que
    acordarse de venir a agregar el nombre nuevo.
    """
    from libragenda.repositories import AppointmentRepository

    from app.services.appointments import _TurnosEnHoraLocal

    del_puerto = {n for n in dir(AppointmentRepository) if not n.startswith("_")}
    # Contraprueba: sobre un puerto vacio el `set()` de abajo da vacio y el test
    # pasaria sin mirar nada.
    assert "reserve" in del_puerto, del_puerto

    faltan = sorted(n for n in del_puerto if not hasattr(_TurnosEnHoraLocal, n))
    assert not faltan, (
        f"el puerto `AppointmentRepository` de la libragenda instalada declara "
        f"{sorted(del_puerto)}, y `_TurnosEnHoraLocal` no implementa {faltan}. "
        f"Sin esos metodos el motor se cae con AttributeError en runtime.")


def test_el_pin_de_libracore_trae_el_comando_que_se_declara():
    """El pin y la declaracion viajan juntos, y el minimo subio dos veces.

    La `v1.48.0` introdujo `migraciones` como UN comando; la `v1.51.0` acepta
    varios --- con un pin anterior, `configure()` no sabe que hacer con la tupla
    anidada ---. Y desde el 2026-08-25 se declara `libracore-migrar`, que es un
    `[project.scripts]` que **aparece en la v1.53.0**: con un pin anterior el
    comando no existe en la imagen y el primer paso del deploy se cae.

    Es el mismo control que `test_el_pin_de_libragenda_trae_el_comando_instalable`
    hace del otro lado.
    """
    pins = _pins()
    assert _version(pins["libracore"]) >= (1, 53, 0), pins["libracore"]


def _pins() -> dict:
    datos = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    salida = {}
    for dep in datos["project"]["dependencies"]:
        for motor in ("libracore", "libragenda"):
            if dep.startswith(motor + " @"):
                salida[motor] = dep.rsplit("@", 1)[-1]
    return salida


def _version(tag: str) -> tuple:
    return tuple(int(x) for x in tag.lstrip("v").split("."))


def test_la_imagen_lleva_con_que_correrlas():
    """El `alembic upgrade head` corre DENTRO del contenedor, contra
    `/app/alembic.ini`. Si el `.dockerignore` se llevara `migrations/`, el
    deploy fallaria recien en produccion y con un error de alembic que no nombra
    la causa."""
    assert (RAIZ / "alembic.ini").is_file()
    assert list((RAIZ / "migrations" / "versions").glob("*.py"))

    ignore = RAIZ / ".dockerignore"
    if ignore.is_file():
        lineas = [l.strip() for l in ignore.read_text(encoding="utf-8").splitlines()]
        for prohibido in ("migrations", "migrations/", "alembic.ini"):
            assert prohibido not in lineas, f".dockerignore excluye {prohibido}"


def test_libraauth_va_con_base_core_hasta_que_no_quede_una_instancia_de_dos_bases():
    """🔴 `--base core`, y no `--base dominio`: medido el 2026-10-25 sobre una instancia de dos bases.

    Con `--base core` el comando usa la base del core si la instancia todavía tiene la variable (la demo, hasta que
    se una) y, si no, cae a la del dominio (dev unida y todo alta nueva), porque `gestiolibra` figura en
    `_UNA_SOLA_BASE` del motor desde libracore v1.194.0. Con `--base dominio` migraría SIEMPRE la del dominio: en la demo
    crearía ahí las tablas de auth, vacías, al lado de las reales —sin fallar— y `libracore-unir-bases verificar`
    cortaría después con `auth_en_los_dos`. En una base única los dos valores van al mismo lugar, así que cambiarlo a
    `dominio` es un PR aparte, cuando no quede ninguna instancia de dos bases.
    """
    comando = next(c for c in _config_de("panel_admin") if c[0] == "libraauth-migrar")
    assert "--base" in comando, "sin --base, libraauth-migrar se niega a correr con --prefijo"
    assert comando[comando.index("--base") + 1] == "core", (
        f"mientras la demo tenga dos bases: --base core, no {comando[comando.index('--base') + 1]!r}")


def test_a_donde_va_libraauth_con_una_base_y_con_dos():
    """La resolución real de `libraauth-migrar` (`url_de_auth`), sin tocar ninguna base: el destino de cada `--base`."""
    from libraauth.migrar import url_de_auth

    dominio = "postgresql+psycopg://u:clave@servidor:5432/gestiolibra"
    core = "postgresql+psycopg://u:clave@servidor:5432/gestiolibra_core"

    # Una sola base (dev unida, alta nueva): sin variable del core, `core` y `dominio` son la misma.
    una = {"GESTIOLIBRA_DATABASE_URL": dominio}
    assert url_de_auth("gestiolibra", "core", entorno=una) == dominio
    assert url_de_auth("gestiolibra", "dominio", entorno=una) == dominio

    # Dos bases (la demo hasta que se una): `core` es la del core; `dominio` sería la equivocada.
    dos = {**una, "GESTIOLIBRA_LIBRACORE_DATABASE_URL": core}
    assert url_de_auth("gestiolibra", "core", entorno=dos) == core
    assert url_de_auth("gestiolibra", "dominio", entorno=dos) == dominio  # el peligro: migraría la base equivocada


@pytest.mark.parametrize("script", ["panel_admin", "nuevo_cliente"])
def test_los_dos_scripts_declaran_una_sola_base_y_la_tabla_de_modulos(script):
    """El alta nace con UNA base y escribe los módulos en la tabla del producto (ADR-035, libracore ADR-083).

    Va en los dos scripts: `configure()` pisa un global y el que corre último gana, así que uno solo no alcanza. Sin
    `tabla_modulos` el alta esperaría `modulos` (la del motor) y terminaría en `AltaIncompleta`, o peor, prendería los
    adicionales en la tabla que este producto no lee."""
    leido = _leer_de_la_config(script, (
        "{'tabla': config.tabla_modulos, 'core_separado': config.core_separado,"
        " 'bases': list(config.bases_postgres), 'urls': [list(p) for p in config.db_urls]}"
    ))
    assert leido["tabla"] == "gestiolibra_modulos"
    assert leido["core_separado"] is False
    assert leido["bases"] == ["gestiolibra"], "el alta no debe crear `gestiolibra_core`"
    assert [base for _variable, base in leido["urls"]] == ["gestiolibra", "gestiolibra"]
    assert not any("gestiolibra_core" in base for _v, base in leido["urls"])


def test_los_scripts_no_piden_la_base_del_core_aparte():
    """`base_core_separada=True` ya no decide nada (el motor lo ignora) y dejarlo sugiere lo contrario."""
    for script in ("panel_admin.py", "nuevo_cliente.py"):
        codigo = (RAIZ / "scripts" / script).read_text(encoding="utf-8")
        sin_comentarios = "\n".join(l for l in codigo.splitlines() if not l.lstrip().startswith("#"))
        assert "base_core_separada" not in sin_comentarios, script


@contextlib.contextmanager
def _base_temporal(etiqueta: str):
    """Una base vacía y propia en el servidor de la suite (nombre único); devuelve `(url psycopg, url SQLAlchemy)`."""
    import uuid
    from urllib.parse import urlsplit, urlunsplit

    import psycopg
    from motor_de_test import TEST_DATABASE_URL
    from psycopg import sql

    cruda = TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    nombre = f"gestiolibra_{etiqueta}_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(cruda, autocommit=True) as c:
        c.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nombre)))
    url = urlunsplit(urlsplit(cruda)._replace(path=f"/{nombre}"))
    try:
        yield url, url.replace("postgresql://", "postgresql+psycopg://", 1)
    finally:
        with psycopg.connect(cruda, autocommit=True) as c:
            c.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nombre)))


def _correr_cadena(dominio: str, core: str | None = None, *, solo: tuple[str, ...] | None = None,
                   base_de_auth: str | None = None) -> None:
    """Las cadenas que declara `panel_admin.py`, como subprocesos y en su orden, contra bases propias.

    Sin `core`, **sin ninguna `GESTIOLIBRA_LIBRACORE_*` en el entorno** (el alta nueva y dev unida). Con `core`, la
    variable del core apuntada a esa base (la demo, hasta que se una). `base_de_auth` cambia el `--base` de
    `libraauth-migrar`; sin él, el del deploy."""
    import os

    entorno = {k: v for k, v in os.environ.items() if not k.startswith("GESTIOLIBRA_LIBRACORE_")}
    entorno.update(DATABASE_URL=dominio, GESTIOLIBRA_DATABASE_URL=dominio)
    if core:
        entorno["GESTIOLIBRA_LIBRACORE_DATABASE_URL"] = core
    bin_ = Path(sys.executable).parent
    for comando in _config_de("panel_admin"):
        if solo is not None and comando[0] not in solo:
            continue
        comando = list(comando)
        if base_de_auth and comando[0] == "libraauth-migrar":
            comando[comando.index("--base") + 1] = base_de_auth
        r = subprocess.run([str(bin_ / comando[0]), *comando[1:]], env=entorno, cwd=str(RAIZ),
                           capture_output=True, text=True, timeout=300)
        assert r.returncode == 0, f"{' '.join(comando)}: {(r.stderr or r.stdout)[-2000:]}"


def test_las_cuatro_cadenas_del_deploy_migran_una_base_nueva_sin_variable_del_core():
    """El alta nueva: las cuatro cadenas de `panel_admin.py`, como subprocesos y en su orden, contra UNA base vacía.

    Sin `GESTIOLIBRA_LIBRACORE_*` en el entorno. Es el comando del compose de dev con la variable ya retirada: si
    `libracore-migrar` o `libraauth-migrar --base core` no cayeran a la base del dominio (o si alguna cadena chocara con
    otra por un nombre de tabla repetido), el deploy de una instancia unida y todo alta nueva morirían acá."""
    import psycopg

    with _base_temporal("cadena") as (url, sqla):
        _correr_cadena(sqla)

        with psycopg.connect(url) as c:
            tablas = {f[0] for f in c.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'").fetchall()}
            versiones = {t for t in tablas if t.startswith("alembic_version")}
            segunda = c.execute("SELECT 1 FROM pg_database WHERE datname = current_database() || '_core'").fetchone()
        # Todo en la misma base: la agenda, la de LibraCore, la de auth y la tabla de módulos propia.
        assert {"agenda_clients", "clients", "cajas", "modulos", "gestiolibra_modulos", "usuarios",
                "auth_log"} <= tablas
        assert versiones == {"alembic_version", "alembic_version_libragenda",
                             "alembic_version_libraauth", "alembic_version_gestiolibra"}
        assert segunda is None, "el alta no debe crear `<base>_core`"


def _unir_bases_verificar(dominio: str, core: str):
    """`libracore-unir-bases verificar` sobre dos bases: (código de salida, texto)."""
    r = subprocess.run(
        [str(Path(sys.executable).parent / "libracore-unir-bases"), "--prefijo", "gestiolibra",
         "--core", core, "--dominio", dominio, "verificar"],
        capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr


def test_libraauth_con_base_dominio_en_una_instancia_de_dos_bases_deja_la_union_imposible():
    """🔴 Lo medido el 2026-10-25, de punta a punta: por qué el deploy sigue con `--base core`.

    En una instancia que todavía tiene dos bases (la demo) `--base dominio` termina bien y crea en el dominio las
    tablas de auth, vacías, al lado de las reales del core; desde ahí `libracore-unir-bases` corta con `auth_en_los_dos`
    y la unión de esa demo no se puede hacer sin retirar a mano el juego de tablas sobrante."""
    import psycopg

    def tiene_usuarios(url: str) -> bool:
        with psycopg.connect(url) as c:
            return c.execute("SELECT count(*) FROM information_schema.tables "
                             "WHERE table_schema = 'public' AND table_name = 'usuarios'").fetchone()[0] == 1

    with _base_temporal("dom") as (dominio, dominio_sqla), _base_temporal("core") as (core, core_sqla):
        _correr_cadena(dominio_sqla, core_sqla)
        assert tiene_usuarios(core) and not tiene_usuarios(dominio)  # los usuarios de la demo están en el core
        antes, texto = _unir_bases_verificar(dominio_sqla, core_sqla)
        assert antes == 0, texto  # control: con el deploy tal cual, se puede unir

        _correr_cadena(dominio_sqla, core_sqla, solo=("libraauth-migrar",), base_de_auth="dominio")

        assert tiene_usuarios(dominio)  # migró la base equivocada, sin fallar
        despues, texto = _unir_bases_verificar(dominio_sqla, core_sqla)
        assert despues != 0 and "auth_en_los_dos" in texto, texto
