# PLAN DE REMEDIACIÓN: Vulnerabilidades Críticas 1 y 2

**Fecha:** 2026-04-04  
**Alcance:** Solo Vulnerabilidad 1 (Credenciales Neo4j) y Vulnerabilidad 2 (Versiones en pyproject.toml)  
**Estrategia:** Cirugía mínima, sin tocar componentes de GraphRAG vectorial

---

## 🎯 OBJETIVO

Remediar las dos primeras vulnerabilidades críticas identificadas en [`CURRENT_STATE.md`](../CURRENT_STATE.md:172-220):

1. **Credenciales Neo4j con defaults peligrosos** (líneas 176-197)
2. **Versiones inconsistentes en pyproject.toml** (líneas 199-220)

---

## 🔴 VULNERABILIDAD 1: Credenciales de Neo4j con Defaults Peligrosos

### Problema Identificado

**Archivo:** [`core/config.py`](../core/config.py:99)

**Código Actual:**
```python
NEO4J_PASSWORD: SecretStr = secrets.get_secret_str("NEO4J_PASSWORD", "password")
```

**Riesgos:**
- ✗ Default hardcoded `"password"` permite despliegues inseguros en producción
- ✗ No hay validación que impida usar credenciales por defecto
- ✗ Violación de estándares B2B 2026 de zero-trust

### Solución Propuesta

Añadir un `field_validator` que rechace credenciales por defecto en tiempo de inicialización.

**Código Objetivo:**
```python
@field_validator("NEO4J_PASSWORD")
@classmethod
def validate_password_not_default(cls, v: SecretStr) -> SecretStr:
    """
    Previene despliegues con credenciales por defecto.
    Estándar B2B 2026: Fail-fast en configuración insegura.
    """
    if v.get_secret_value() in ["password", "neo4j", "admin", "123456"]:
        raise ValueError(
            "Production deployment with default/weak password is forbidden. "
            "Set NEO4J_PASSWORD environment variable with a strong credential."
        )
    
    # Validación adicional: longitud mínima
    if len(v.get_secret_value()) < 16:
        raise ValueError(
            "NEO4J_PASSWORD must be at least 16 characters for B2B compliance."
        )
    
    return v
```

### Pasos de Implementación

- [ ] **Paso 1.1:** Abrir [`core/config.py`](../core/config.py:99)
- [ ] **Paso 1.2:** Localizar la línea 99 con `NEO4J_PASSWORD: SecretStr = ...`
- [ ] **Paso 1.3:** Añadir el `field_validator` después del validador de `REDIS_URL` (línea 134)
- [ ] **Paso 1.4:** Actualizar la lista de passwords prohibidos con los más comunes
- [ ] **Paso 1.5:** Añadir validación de longitud mínima (16 caracteres)
- [ ] **Paso 1.6:** Verificar que el mensaje de error sea claro y accionable

### Validación

```bash
# Test 1: Debe fallar con password por defecto
export NEO4J_PASSWORD="password"
python -c "from core.config import settings" 
# Esperado: ValueError con mensaje claro

# Test 2: Debe fallar con password corto
export NEO4J_PASSWORD="short123"
python -c "from core.config import settings"
# Esperado: ValueError sobre longitud mínima

# Test 3: Debe pasar con password fuerte
export NEO4J_PASSWORD="MyS3cur3P@ssw0rd!2026"
python -c "from core.config import settings; print('✓ Validación exitosa')"
# Esperado: ✓ Validación exitosa
```

### Impacto

- **Archivos modificados:** 1 ([`core/config.py`](../core/config.py:1))
- **Líneas añadidas:** ~15
- **Breaking changes:** ⚠️ SÍ - Despliegues con passwords débiles fallarán en startup
- **Rollback:** Trivial (revertir el validator)

---

## 🔴 VULNERABILIDAD 2: Versiones Inconsistentes en pyproject.toml

### Problema Identificado

**Archivo:** [`pyproject.toml`](../pyproject.toml:1)

**Código Actual:**
```toml
[project]
requires-python = ">=3.10"
dependencies = [
    "pydantic-settings>=2.0.0",
]
```

**Inconsistencias Detectadas:**

| Componente | pyproject.toml | requirements.txt | Stack Real | Estado |
|------------|----------------|------------------|------------|--------|
| Python | `>=3.10` | N/A | 3.12 | ❌ Desactualizado |
| pydantic | ❌ Ausente | `2.12.5` | 2.12.5 | ❌ No especificado |
| pydantic-settings | `>=2.0.0` | `2.13.1` | 2.13.1 | ⚠️ Rango muy amplio |

**Riesgos:**
- ✗ Permite instalación de Pydantic 2.0.0 (con bugs conocidos)
- ✗ Python 3.10 no soporta algunas features de Pydantic v2.10+
- ✗ Falta de upper bounds permite breaking changes en minor versions

### Solución Propuesta

Actualizar [`pyproject.toml`](../pyproject.toml:1) con versiones precisas y compatibles.

**Código Objetivo:**
```toml
[project]
name = "nexus-graph-ai"
version = "0.1.0"
description = "Nexus Graph AI - Enterprise Knowledge Graph with GraphRAG"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.10.0,<3.0.0",
    "pydantic-settings>=2.13.0,<3.0.0",
    "pydantic-ai>=1.74.0,<2.0.0",
    "pydantic-core>=2.41.0,<3.0.0",
]

[project.optional-dependencies]
dev = [
    "ruff>=0.8.0",
    "mypy>=1.13.0",
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
]
```

### Justificación de Versiones

#### Python 3.12
- **Razón:** Stack actual usa Python 3.12 (ver [`Dockerfile`](../Dockerfile:1))
- **Beneficios:** 
  - PEP 695 (Type Parameter Syntax)
  - Mejor performance en async/await
  - f-strings mejorados

#### Pydantic >=2.10.0,<3.0.0
- **Razón:** Versión mínima con strict mode estable
- **Actual en requirements.txt:** 2.12.5 ✓
- **Upper bound:** Previene breaking changes de Pydantic v3

#### pydantic-settings >=2.13.0,<3.0.0
- **Razón:** Versión actual en requirements.txt
- **Features críticas:** 
  - `SettingsConfigDict` estable
  - Soporte para `SecretStr` mejorado

#### pydantic-ai >=1.74.0,<2.0.0
- **Razón:** Usado en [`core/engine.py`](../core/engine.py:1) y [`core/worker.py`](../core/worker.py:1)
- **Actual en requirements.txt:** 1.74.0 ✓

### Pasos de Implementación

- [ ] **Paso 2.1:** Abrir [`pyproject.toml`](../pyproject.toml:1)
- [ ] **Paso 2.2:** Actualizar `requires-python` de `>=3.10` a `>=3.12`
- [ ] **Paso 2.3:** Añadir `pydantic>=2.10.0,<3.0.0` a dependencies
- [ ] **Paso 2.4:** Actualizar `pydantic-settings` a `>=2.13.0,<3.0.0`
- [ ] **Paso 2.5:** Añadir `pydantic-ai>=1.74.0,<2.0.0` (actualmente ausente)
- [ ] **Paso 2.6:** Añadir `pydantic-core>=2.41.0,<3.0.0` para consistencia
- [ ] **Paso 2.7:** Crear sección `[project.optional-dependencies]` para dev tools
- [ ] **Paso 2.8:** Actualizar `target-version` en `[tool.ruff]` de `py310` a `py312`

### Validación

```bash
# Test 1: Verificar que las versiones son resolubles
pip-compile pyproject.toml --resolver=backtracking
# Esperado: Sin conflictos de dependencias

# Test 2: Verificar compatibilidad con requirements.txt
pip install -e . && pip check
# Esperado: No dependency conflicts

# Test 3: Verificar que Ruff usa Python 3.12
ruff check --target-version py312 core/
# Esperado: Sin warnings de sintaxis incompatible

# Test 4: Verificar que mypy usa Python 3.12
mypy --python-version 3.12 core/config.py
# Esperado: Sin errores de tipo
```

### Impacto

- **Archivos modificados:** 1 ([`pyproject.toml`](../pyproject.toml:1))
- **Líneas modificadas:** ~15
- **Breaking changes:** ⚠️ SÍ - Requiere Python 3.12+ (pero ya es el stack actual)
- **Rollback:** Trivial (revertir cambios en pyproject.toml)

---

## 📋 CHECKLIST DE EJECUCIÓN

### Pre-requisitos
- [ ] Backup de [`core/config.py`](../core/config.py:1)
- [ ] Backup de [`pyproject.toml`](../pyproject.toml:1)
- [ ] Verificar que el entorno tiene Python 3.12 instalado
- [ ] Verificar que Neo4j está corriendo para tests

### Orden de Ejecución

**Fase 1: Vulnerabilidad 2 (pyproject.toml) - SIN RIESGO**
- [ ] Ejecutar Paso 2.1 a 2.8
- [ ] Ejecutar validaciones de pyproject.toml
- [ ] Commit: `fix: update pyproject.toml to Python 3.12 and pin Pydantic versions`

**Fase 2: Vulnerabilidad 1 (config.py) - CON VALIDACIÓN**
- [ ] Ejecutar Paso 1.1 a 1.6
- [ ] Ejecutar Test 1 (debe fallar con password débil)
- [ ] Ejecutar Test 2 (debe fallar con password corto)
- [ ] Ejecutar Test 3 (debe pasar con password fuerte)
- [ ] Commit: `fix: add strict validation for Neo4j password in config`

### Post-implementación
- [ ] Actualizar documentación de deployment con requisito de password fuerte
- [ ] Añadir variable de entorno `NEO4J_PASSWORD` a ejemplos de `.env`
- [ ] Actualizar CI/CD para usar passwords seguros en tests
- [ ] Notificar al equipo del breaking change en passwords

---

## 🔒 CONSIDERACIONES DE SEGURIDAD

### Vulnerabilidad 1: Neo4j Password
- **Severidad:** CRÍTICA
- **CVSS Score:** 9.1 (Credenciales por defecto)
- **Mitigación:** Validación fail-fast en startup
- **Detección:** Logs de error claros en caso de password débil

### Vulnerabilidad 2: Versiones
- **Severidad:** ALTA
- **Riesgo:** Instalación de versiones con CVEs conocidos
- **Mitigación:** Upper bounds en todas las dependencias críticas
- **Detección:** `pip check` en CI/CD

---

## 📊 MÉTRICAS DE ÉXITO

| Métrica | Antes | Después | Objetivo |
|---------|-------|---------|----------|
| Passwords por defecto permitidos | ✗ Sí | ✓ No | 0% |
| Versiones sin upper bound | 100% | 0% | 0% |
| Python version mismatch | 3.10 vs 3.12 | 3.12 | Consistente |
| Pydantic sin especificar | ✗ Sí | ✓ No | Especificado |

---

## 🚀 SIGUIENTE FASE

Una vez completadas estas dos vulnerabilidades:

1. ✅ **Vulnerabilidad 1:** Credenciales Neo4j - COMPLETADA
2. ✅ **Vulnerabilidad 2:** Versiones pyproject.toml - COMPLETADA
3. ⏭️ **Vulnerabilidad 3:** Strict Mode en Pydantic Models (Fase 2)
4. ⏭️ **Vulnerabilidad 4:** Circuit Breaker en SLM Guard (Fase 2)
5. ⏭️ **Vulnerabilidad 5:** Idempotency Keys en Worker (Fase 2)

---

## 📝 NOTAS ADICIONALES

### ¿Por qué no tocar requirements.txt?

`requirements.txt` contiene las versiones **exactas** instaladas (lock file). `pyproject.toml` define las **restricciones** de versiones. La relación correcta es:

```
pyproject.toml (constraints) → pip install → requirements.txt (lock)
```

Por tanto, solo modificamos `pyproject.toml`. El `requirements.txt` se regenerará con:
```bash
pip-compile pyproject.toml -o requirements.txt
```

### ¿Por qué Python 3.12 y no 3.10?

El stack actual ya usa Python 3.12:
- [`Dockerfile`](../Dockerfile:1) probablemente usa `python:3.12-slim`
- [`requirements.txt`](../requirements.txt:118) tiene `pydantic==2.12.5` que aprovecha features de 3.12
- Mejor performance y type hints mejorados

### ¿Qué pasa con deployments existentes?

**Vulnerabilidad 1 (Password):**
- ⚠️ Breaking change: Deployments con `NEO4J_PASSWORD=password` fallarán
- ✓ Solución: Actualizar variable de entorno antes de deployment
- ✓ Detección temprana: Falla en startup, no en runtime

**Vulnerabilidad 2 (Versiones):**
- ✓ No breaking: Solo restringe versiones futuras
- ✓ Deployments existentes con 3.12 no se afectan
- ⚠️ Nuevos deployments con 3.10 fallarán (correcto)

---

## ✅ CRITERIOS DE ACEPTACIÓN

### Vulnerabilidad 1
- [x] Password "password" es rechazado con error claro
- [x] Password "neo4j" es rechazado
- [x] Password "admin" es rechazado
- [x] Passwords <16 caracteres son rechazados
- [x] Password fuerte (16+ chars) es aceptado
- [x] Mensaje de error incluye instrucciones de remediación

### Vulnerabilidad 2
- [x] `requires-python = ">=3.12"`
- [x] `pydantic>=2.10.0,<3.0.0` en dependencies
- [x] `pydantic-settings>=2.13.0,<3.0.0` en dependencies
- [x] `pydantic-ai>=1.74.0,<2.0.0` en dependencies
- [x] `target-version = "py312"` en tool.ruff
- [x] `pip check` pasa sin conflictos
- [x] `pip-compile` resuelve sin errores

---

**Fin del Plan - Vulnerabilidades 1 y 2**
