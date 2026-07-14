# Informe individual SCP vs ML — 10699_SIGMA

**Fecha del analisis:** 14/07/2026
**Cliente:** ID_CLIENT=10699 | Fichero: `TA_FOV_SCP_ML_10699_SIGMA.csv`
**Batch/Run:** ID_BATCH=[63] | ID_RUN_STAGING=[58] | SOURCE_RUN_ID=[1]
**Estado global del cliente:** SUCCESS_WITH_WARNINGS

---

## 1. Resumen ejecutivo

Este cliente tiene **1.108 series candidatas**, pero **ninguna es comparable** en ningun periodo analizado. No es un error del pipeline: es un caso valido de cobertura que requiere diagnostico (ver seccion 2). No se reportan metricas de performance porque no existen series validas sobre las que calcularlas.

---

## 2. Cobertura

Series candidatas (universo de cobertura, `HAS_BASE_CANDIDATE=1`): **1.108**.

Distribucion original de `COMPARISON_STATUS` (categorias del CSV, sin modificar):

| COMPARISON_STATUS | N | % sobre candidatas |
|---|---|---|
| NOT_COMPARABLE_MISSING_VALIDATION | 1.108 | 100.0% |

Exclusiones ML reales (`HAS_ML_EXCLUDED=1`, no varia por periodo): **334** (30.1% sobre candidatas).

Motivos de exclusion ML:

| Motivo | N |
|---|---|
| MissingHistory | 170 |
| ShortSeries | 164 |

Cobertura por periodo:

| Periodo | Candidatas | Comparables | % comparable |
|---|---|---|---|
| M1 | 1.108 | 0 | 0.0% |
| M2 | 1.108 | 0 | 0.0% |
| M3 | 1.108 | 0 | 0.0% |
| M4 | 1.108 | 0 | 0.0% |
| M5 | 1.108 | 0 | 0.0% |
| M6 | 1.108 | 0 | 0.0% |
| RECENT_3M | 1.108 | 0 | 0.0% |
| OLDER_3M | 1.108 | 0 | 0.0% |
| 6M | 1.108 | 0 | 0.0% |

---

## 3. Semestre completo (6M)

Sin series comparables en Semestre completo (M1-M6): no hay metricas de performance que mostrar (caso valido de cobertura, no se inventan datos).

Frecuencia de victoria: Sin series comparables en Semestre completo (M1-M6): no hay metricas de performance que mostrar (caso valido de cobertura, no se inventan datos).

---

## 4. Primer trimestre del semestre (M1-M3)

Sin series comparables en Primer trimestre del semestre (M1-M3): no hay metricas de performance que mostrar (caso valido de cobertura, no se inventan datos).

Frecuencia de victoria: Sin series comparables en Primer trimestre del semestre (M1-M3): no hay metricas de performance que mostrar (caso valido de cobertura, no se inventan datos).

---

## 5. Segundo trimestre del semestre (M4-M6)

Sin series comparables en Segundo trimestre del semestre (M4-M6): no hay metricas de performance que mostrar (caso valido de cobertura, no se inventan datos).

Frecuencia de victoria: Sin series comparables en Segundo trimestre del semestre (M4-M6): no hay metricas de performance que mostrar (caso valido de cobertura, no se inventan datos).

---

## 6. Comparacion entre trimestres

No hay datos suficientes en ambos trimestres para compararlos (alguno sin series comparables).

---

## 7. Evolucion mensual

Sin series comparables en ningun mes.

---

## 8. Frecuencia de victoria

Semestre completo: Sin series comparables en Semestre completo (M1-M6): no hay metricas de performance que mostrar (caso valido de cobertura, no se inventan datos).

La frecuencia de victoria (cuantas series gana cada metodo) es una perspectiva distinta del impacto ponderado por volumen (seccion 3): una mejora del WAPE global no implica automaticamente que ML gane en la mayoria de series, ni al reves.

---

## 9. Impacto absoluto

Sin series comparables en Semestre completo (M1-M6): no hay metricas de performance que mostrar (caso valido de cobertura, no se inventan datos).

---

## 10. Modelos ML

Sin series comparables en Semestre completo (M1-M6): no hay metricas de performance que mostrar (caso valido de cobertura, no se inventan datos).

---

## 11. Modelos SCP

Sin series comparables en Semestre completo (M1-M6): no hay metricas de performance que mostrar (caso valido de cobertura, no se inventan datos).

---

## 12. Clasificaciones

Sin series comparables en Semestre completo (M1-M6): no hay metricas de performance que mostrar (caso valido de cobertura, no se inventan datos).

---

## 13. Exclusiones

`COMPARISON_STATUS='NOT_COMPARABLE_ML_EXCLUDED'`: 0 filas. `HAS_ML_EXCLUDED=1` (recuento real): 334 filas. La diferencia (334) corresponde a exclusiones ML "tapadas" por otro `COMPARISON_STATUS` de mayor precedencia (p.ej. falta tambien SCP).

---

## 14. Casos de mayor mejora

Sin series comparables en Semestre completo (M1-M6): no hay metricas de performance que mostrar (caso valido de cobertura, no se inventan datos).

---

## 15. Casos de mayor deterioro

Sin series comparables en Semestre completo (M1-M6): no hay metricas de performance que mostrar (caso valido de cobertura, no se inventan datos).

---

## 16. Riesgos

- El CSV de origen requirio normalizacion en memoria (comillas dobladas envolventes).
- Los clientes del batch cargado no proceden todos del mismo ID_BATCH.

---

## 17. Limitaciones

- El winner (`WINNER_METHOD_*`) se usa como fuente de verdad; el criterio exacto de empate relativo (relativeDiff < 0.0001) no esta documentado en el repositorio y no se reconstruye.
- Modelos y clasificaciones se muestran unicamente para el semestre completo (6M), no para cada periodo.
- Los valores extremos de WAPE o de mejora relativa (series con historico muy pequeno) no se recortan silenciosamente: se conservan en las estadisticas y se senalan en los chequeos de calidad.
- Este informe es retrospectivo (backtesting) y no garantiza comportamiento futuro.
- Este cliente no tiene ninguna serie comparable: las secciones de performance quedan vacias por diseno, no se ha inventado ningun dato para rellenarlas.

---

## 18. Conclusion

No es posible concluir sobre la mejora de ML frente a SCP para este cliente: ninguna de sus 1.108 series candidatas es comparable (ver seccion 2 para el motivo). Esto es un resultado de cobertura, no de performance.
