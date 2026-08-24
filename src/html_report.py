"""
Orquestacion del informe HTML estatico y offline (Fase 5B).

Genera, dentro de run_config.run_dir_temp: index.html (pagina global),
clients/<CLIENTE>/index.html (una por cada ClientAnalysisResult, valido o
invalido) y assets/styles.css. Se apoya exclusivamente en resultados ya
calculados (ClientAnalysisResult, GlobalAnalysisResult, ExecutionRecord) y
en las rutas relativas ya producidas por _generate_client_outputs /
_generate_global_outputs (all_outputs, global_outputs): nunca relee Excel,
Markdown, logs ni manifest.json de disco, y nunca recalcula metricas.

`generate_html_report` NO valida enlaces por si misma: index.html enlaza a
manifest.json y execution.log, ninguno de los cuales existe todavia en el
momento en que se genera el HTML (se escriben despues, en la fase
MANIFEST). El llamador (run_pipeline() en analysis_fov_scp_ml.py) debe
invocar `validate_run_links()` DESPUES de escribir manifest.json y
execution.log, y ANTES de publish_run(): en ese punto todos los destinos
declarados ya existen en disco. Un fallo de validacion debe propagarse tal
cual (por ejemplo, relanzado como RuntimeError por el llamador) para que la
ejecucion no se publique y el directorio temporal se conserve para
diagnostico, igual que para cualquier otra fase obligatoria del pipeline.
"""

from __future__ import annotations

import posixpath
import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit

import jinja2

from src import html_view_models as vm
from src.client_analysis import ClientAnalysisResult
from src.global_analysis import GlobalAnalysisResult
from src.html_formatters import encode_url_path, to_posix
from src.run_config import RunConfig

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
ASSETS_SRC_DIR = Path(__file__).resolve().parent.parent / "report_assets"

CHART_SECTION_LABELS: dict[str, str] = {
    "coverage": "Cobertura",
    "semester": "Semestre completo",
    "quarters": "Trimestres",
    "monthly": "Evolución mensual",
    "models": "Modelos",
    "classifications": "Clasificaciones",
    "impact_and_risk": "Impacto y riesgos",
    "clients": "Clientes",
}


def _jinja_env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["encode_url_path"] = encode_url_path
    return env


def _rel_url(from_page: str, to_target: str) -> str:
    """
    Ruta relativa (POSIX, SIN codificar) de `from_page` a `to_target`, ambas
    expresadas como rutas relativas a la raiz de la ejecucion. La
    codificacion por segmento se aplica solo en el template, al renderizar
    el atributo href/src (filtro encode_url_path).
    """
    from_dir = posixpath.dirname(from_page)
    return posixpath.relpath(to_target, start=from_dir) if from_dir else to_target


def _find_first(paths: list[str], suffix: str) -> str | None:
    for p in paths:
        if p.endswith(suffix):
            return p
    return None


def _alt_text(posix_path: str) -> str:
    stem = Path(posix_path).stem
    return f"Gráfico: {stem.replace('_', ' ')}"


def _group_charts_for_page(paths: list[str], page_path: str) -> list[dict]:
    """Agrupa PNG por la subcarpeta charts/<seccion>/ y calcula ya la URL relativa a page_path."""
    by_section: dict[str, list[str]] = {}
    for p in paths:
        if not p.endswith(".png"):
            continue
        parts = p.split("/")
        if "charts" not in parts:
            continue
        idx = parts.index("charts")
        section = parts[idx + 1] if idx + 1 < len(parts) else "otros"
        by_section.setdefault(section, []).append(p)

    def _charts_payload(paths_in_section: list[str]) -> list[dict]:
        return [{"url": _rel_url(page_path, c), "alt": _alt_text(c)} for c in sorted(paths_in_section)]

    groups: list[dict] = []
    seen: set[str] = set()
    for section, label in CHART_SECTION_LABELS.items():
        if section in by_section:
            groups.append({"section": section, "label": label, "charts": _charts_payload(by_section[section])})
            seen.add(section)
    for section, paths_in_section in by_section.items():
        if section not in seen:
            groups.append({"section": section, "label": section, "charts": _charts_payload(paths_in_section)})
    return groups


def _render_to_file(env: jinja2.Environment, template_name: str, context: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html = env.get_template(template_name).render(**context)
    out_path.write_text(html, encoding="utf-8")


def generate_html_report(
    *,
    run_config: RunConfig,
    results: list[ClientAnalysisResult],
    global_result: GlobalAnalysisResult,
    all_outputs: dict[int, list[str]],
    global_outputs: list[str],
    execution_records: list,
    started_at, finished_at,
    status: str,
    git_commit: str | None,
    git_worktree_dirty: bool | None,
) -> list[str]:
    """
    Devuelve la lista de rutas (relativas a run_dir_temp, POSIX) de todo el
    HTML y los assets generados, lista para anadir a outputs_generated.
    """
    env = _jinja_env()
    run_dir = run_config.run_dir_temp

    posix_all_outputs = {k: [to_posix(p) for p in v] for k, v in all_outputs.items()}
    posix_global_outputs = [to_posix(p) for p in global_outputs]

    ordered_results = sorted(results, key=lambda r: r.source.file_name)
    n_clients_valid = sum(1 for r in results if r.file_valid)
    batches_detected = sorted({b for r in results for b in r.source.id_batch})
    # No todo ExecutionRecord representa un cliente: un CSV con read_error
    # (o que nunca llego a parsearse) genera un ExecutionRecord fisico con
    # id_client=None y estado=INPUT_NOT_ANALYZED. Solo cuentan como cliente
    # los registros con id_client asignado.
    n_clients_processed = sum(1 for rec in execution_records if rec.id_client is not None)

    header = vm.build_header_vm(
        run_config, git_commit, git_worktree_dirty, status, started_at, finished_at,
        n_clients_processed, n_clients_valid, batches_detected,
    )
    resumen = vm.build_executive_summary_vm(global_result)
    perspectives = vm.build_perspectives_vm(global_result)
    monthly = vm.build_monthly_evolution_vm(global_result)

    client_rows = vm.build_client_table_vm(ordered_results)
    for row, result in zip(client_rows, ordered_results):
        row["url"] = _rel_url("index.html", f"clients/{result.source.folder_name}/index.html")

    inventory_rows = vm.build_inventory_table_vm(execution_records)
    for row, record in zip(inventory_rows, execution_records):
        row["client_url"] = (
            _rel_url("index.html", f"clients/{row['folder_name']}/index.html")
            if row["has_client_page"] and row["folder_name"] else None
        )
        own_paths = posix_all_outputs.get(record.id_client, [])
        log_path = _find_first(own_paths, ".txt")
        row["log_url"] = _rel_url("index.html", log_path) if log_path else None

    global_chart_groups = _group_charts_for_page(posix_global_outputs, "index.html")
    global_excel_url = _find_first(posix_global_outputs, ".xlsx")
    global_md_url = _find_first(posix_global_outputs, ".md")

    # Lista declarativa, no una comprobacion de existencia en disco: estos 5
    # ficheros los escribe siempre el propio run_pipeline() antes de
    # publicar (run_config.json y execution_summary.* ya existen en el
    # momento en que se genera este HTML; manifest.json y execution.log se
    # escriben justo despues, antes de validate_run_links()). Enlazarlos
    # aqui de forma incondicional es lo que permite que index.html incluya
    # manifest.json sin tener que regenerarse tras escribirlo.
    exec_files = [
        {"label": "Configuración de la ejecución", "url": "run_config.json"},
        {"label": "Resumen de ejecución (Markdown)", "url": "execution_summary.md"},
        {"label": "Resumen de ejecución (Excel)", "url": "execution_summary.xlsx"},
        {"label": "Manifiesto de la ejecución", "url": "manifest.json"},
        {"label": "Log de ejecución", "url": "execution.log"},
    ]

    phase8_global = vm.build_phase8_global_vm(global_result.periods["6M"].phase8)

    global_context = {
        "run_name": run_config.run_name_effective,
        "css_url": _rel_url("index.html", "assets/styles.css"),
        "global_url": None,
        "header": header, "resumen": resumen, "perspectives": perspectives, "monthly": monthly,
        "clients": client_rows, "inventory": inventory_rows,
        "methodology": vm.METHODOLOGY_NOTES,
        "chart_groups": global_chart_groups,
        "phase8_global": phase8_global,
        "global_excel_url": global_excel_url, "global_md_url": global_md_url,
        "exec_files": exec_files,
    }
    _render_to_file(env, "global_report.html", global_context, run_dir / "index.html")
    generated: list[str] = ["index.html"]

    for i, result in enumerate(ordered_results):
        page_path = f"clients/{result.source.folder_name}/index.html"
        prev_result = ordered_results[i - 1] if i > 0 else None
        next_result = ordered_results[i + 1] if i < len(ordered_results) - 1 else None
        prev_dict = (
            {"etiqueta": prev_result.source.file_label, "display_name": prev_result.source.display_name,
             "id_client": prev_result.source.id_client,
             "url": _rel_url(page_path, f"clients/{prev_result.source.folder_name}/index.html")}
            if prev_result is not None else None
        )
        next_dict = (
            {"etiqueta": next_result.source.file_label, "display_name": next_result.source.display_name,
             "id_client": next_result.source.id_client,
             "url": _rel_url(page_path, f"clients/{next_result.source.folder_name}/index.html")}
            if next_result is not None else None
        )
        page = vm.build_client_page_vm(result, prev_client=prev_dict, next_client=next_dict)

        own_paths = posix_all_outputs.get(result.source.id_client, [])
        own_excel = _find_first(own_paths, ".xlsx")
        own_md = _find_first(own_paths, ".md")
        own_log = _find_first(own_paths, ".txt")
        page["own_excel_url"] = _rel_url(page_path, own_excel) if own_excel else None
        page["own_md_url"] = _rel_url(page_path, own_md) if own_md else None
        page["own_log_url"] = _rel_url(page_path, own_log) if own_log else None
        page["chart_groups"] = _group_charts_for_page(own_paths, page_path)

        client_context = {
            "run_name": run_config.run_name_effective,
            "css_url": _rel_url(page_path, "assets/styles.css"),
            "global_url": _rel_url(page_path, "index.html"),
            "page": page,
        }
        _render_to_file(env, "client_report.html", client_context, run_dir / "clients" / result.source.folder_name / "index.html")
        generated.append(page_path)

    assets_dir = run_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ASSETS_SRC_DIR / "styles.css", assets_dir / "styles.css")
    generated.append("assets/styles.css")

    return generated


# --------------------------------------------------------------------------
# Validacion de enlaces (seccion 15 de la especificacion)
# --------------------------------------------------------------------------

_HREF_SRC_RE = re.compile(r'\b(?:href|src)\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)


def extract_local_links(html_text: str) -> list[str]:
    """Extrae los valores de href/src que no son anclas internas puras (#...)."""
    links = []
    for m in _HREF_SRC_RE.finditer(html_text):
        raw = m.group(1)
        if not raw or raw.startswith("#"):
            continue
        links.append(raw)
    return links


def validate_html_links(
    html_paths: list[Path], root_dir: Path, pending_targets: set[Path] | None = None,
) -> list[str]:
    """
    Validador generico: analiza EXACTAMENTE los ficheros HTML de
    `html_paths` (nunca escanea un directorio por su cuenta), extrae
    href/src, rechaza URLs externas o esquemas peligrosos (http, https, //,
    javascript:, data:, mailto:, etc.), resuelve cada ruta local relativa
    al HTML que la contiene y verifica que el destino existe en disco y que
    no escapa de `root_dir`. Devuelve la lista de problemas encontrados
    (vacia si todo valida); no lanza por si mismo.

    `pending_targets`: rutas absolutas de destinos que TODAVIA no existen
    con su nombre definitivo pero que forman parte de la MISMA transaccion
    atomica que este HTML (p.ej. un log temporal que se sustituira junto al
    HTML si la validacion pasa). Un enlace hacia una de estas rutas se
    considera valido si, en su lugar, existe el fichero temporal
    correspondiente (`<destino>.tmp`): esto permite validar un HTML que
    enlaza a un fichero preparado pero aun no publicado, sin invertir el
    orden de la transaccion (generar -> validar -> publicar) ni relajar la
    comprobacion de existencia para cualquier otro enlace.

    Reutilizado tanto por la validacion de un run completo (Fase 5B, ver
    `validate_run_links`) como por el catalogo historico de ejecuciones
    (Fase 5C, `src/run_catalog.py`): el catalogo pasa aqui UNICAMENTE su
    propio index.html (nunca los HTML de cada run historico, que ya se
    validaron cuando ESE run se publico), asi que solo se comprueba que el
    enlace a `<run>/index.html` resuelva a un fichero existente, sin volver
    a recorrer ni revalidar el contenido de cada run.
    """
    problems: list[str] = []
    root_dir = root_dir.resolve()
    pending_targets = {p.resolve() for p in (pending_targets or set())}
    for html_path in sorted(html_paths):
        html_path = html_path.resolve()
        text = html_path.read_text(encoding="utf-8")
        for raw in extract_local_links(text):
            split = urlsplit(raw)
            if split.scheme or raw.startswith("//"):
                problems.append(f"{html_path}: enlace externo o de protocolo no permitido: {raw!r}")
                continue
            target_rel = unquote(raw.split("#", 1)[0])
            if not target_rel:
                continue
            target = (html_path.parent / target_rel).resolve()
            try:
                target.relative_to(root_dir)
            except ValueError:
                problems.append(f"{html_path}: el enlace escapa del directorio raiz: {raw!r}")
                continue
            if target.exists():
                continue
            if target in pending_targets and target.with_name(target.name + ".tmp").exists():
                continue
            problems.append(f"{html_path}: destino inexistente: {raw!r} -> {target}")
    return problems


def validate_run_links(run_dir: Path) -> list[str]:
    """
    Valida todos los .html de UN run completo (Fase 5B): rglob acotado a
    `run_dir` (nunca a un output-root que pueda contener otros runs).
    Delgado sobre `validate_html_links`.
    """
    run_dir = run_dir.resolve()
    return validate_html_links(sorted(run_dir.rglob("*.html")), run_dir)
