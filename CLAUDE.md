# FOV SCP Classic Auto vs SCP Classic Optimizer Analysis

## Propósito

Este repositorio contiene un análisis exploratorio retrospectivo para comparar
la precisión y cobertura de dos flujos de forecast:

- SCP Classic Auto (Auto): flujo automático de forecast actual.
- SCP Classic Optimizer (Optimizer): pipeline de clasificación, selección y
  routing de modelos. Los identificadores técnicos `SCP_*`/`ML_*` permanecen
  inalterados; `ML` mantiene su significado cuando nombra la familia de
  aprendizaje automático.

El objetivo es producir evidencia clara, auditable e interpretable sobre dónde
Optimizer mejora frente a Auto y dónde Auto continúa siendo superior.

## Especificación funcional

La especificación completa está en:

`docs/analysis_requirements.md`

Antes de planificar o modificar el pipeline, los cálculos, los informes, los
Excel o los gráficos, lee el documento completo y úsalo como fuente funcional
de verdad.

No es necesario leerlo para operaciones Git simples o consultas que no
modifiquen el análisis.

## Punto de entrada

La ejecución completa debe mantenerse en:

`python analysis_fov_scp_ml.py`

## Convención temporal

Los identificadores técnicos son:

- `M1`, `M2`, `M3`, `M4`, `M5` y `M6`
- `RECENT_3M`
- `OLDER_3M`
- `6M`

Interpretación:

- `RECENT_3M` = M1 + M2 + M3
- `OLDER_3M` = M4 + M5 + M6
- `6M` = M1 + M2 + M3 + M4 + M5 + M6

Etiquetas visibles:

- `RECENT_3M`: 3 meses recientes (M3–M1)
- `OLDER_3M`: 3 meses anteriores (M6–M4)
- `6M`: Semestre completo (M1–M6)

No uses “trimestre reciente”, “trimestre anterior”, Q1 ni Q2 en los informes.

## Principios metodológicos

Distingue siempre:

- cobertura;
- performance;
- WAPE global ponderado;
- mejora media y mediana por cliente;
- mejora media y mediana por serie;
- frecuencia de victoria;
- reducción absoluta de error.

No calcules WAPE agregado como promedio simple de WAPE por serie.

No afirmes que Optimizer mejora de forma generalizada frente a Auto basándote únicamente en el
WAPE global.

## Inputs y outputs

- Descubre automáticamente todos los CSV de `data/`.
- No modifiques los CSV originales.
- Procesa un cliente por CSV.
- Aísla errores para que un CSV inválido no bloquee los demás.
- Escribe cada resultado individual en `outputs/<CLIENTE>/`.
- Escribe la comparativa agregada en `outputs/global/`.
- Mantén los resúmenes de ejecución en la raíz de `outputs/`.

## Restricciones

- No conectarse a bases de datos.
- No usar APIs o servicios externos.
- No usar rutas absolutas dentro del código.
- Usar `pathlib`.
- Mantener compatibilidad con Windows y PowerShell.
- Evitar bucles fila a fila cuando pandas permita vectorización.
- Cerrar todas las figuras de matplotlib.
- No modificar archivos fuera de este repositorio.

## Git

Antes de modificar código, muestra:

```text
git status
git branch --show-current
git diff --stat
```

No cambies de rama automáticamente.

No hagas commit ni push salvo petición explícita del usuario.

## Forma de trabajo

Para desarrollos amplios:

1. Inspecciona.
2. Propón el diseño.
3. Espera aprobación.
4. Implementa el núcleo y los tests.
5. Espera revisión.
6. Implementa outputs por cliente.
7. Espera revisión.
8. Implementa la comparativa global.
9. Ejecuta tests y pipeline completo.

No implementes todas las fases de una vez cuando el usuario haya solicitado
puntos de control.

## Validación

Antes de dar por terminada una fase:

- ejecuta los tests relevantes;
- ejecuta el pipeline cuando corresponda;
- informa de errores y warnings;
- muestra los archivos modificados;
- muestra `git diff --stat`;
- no ocultes limitaciones o datos no analizables.
