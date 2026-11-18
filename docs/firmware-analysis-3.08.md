# Ingeniería Inversa y Arquitectura de Parches — Niimbot B1 Firmware `3.08`

Documento técnico con el análisis completo del firmware oficial **`B1_3.08.bin`** (`125,016` bytes, MD5 `455f420bb63b46469747c199d14497a4`) para la impresora térmica **Niimbot B1** (MCU **Yichip YC3121-L**, ARM Cortex-M0 Thumb, base address `0x01010000`, SRAM `0x00020000`).

---

## 1. Mapa de Memoria y Direcciones Verificadas (`3.08` vs `5.22` vs `6.19`)

| Componente / Estructura | FW `3.08` | FW `5.22` | FW `6.19` | Descripción |
|---|---|---|---|---|
| `BASE_ADDR` | `0x01010000` | `0x01010000` | `0x01010000` | Dirección base en Flash (`offset = vaddr - 0x01010000`) |
| `__aeabi_fsub` | `0x0102638A` | `0x0102528A` | `0x01026146` | Resta IEEE-754 float en software (`r0 - r1`) |
| `__aeabi_fmul` | `0x0102639A` | `0x0102529A` | `0x01026156` | Multiplicación IEEE-754 float en software (`r0 * r1`) |
| `__aeabi_f2uiz` | `0x01026896` | `0x01025796` | `0x01026652` | Conversión float a entero sin signo (`\|r0\|`) |
| `CFG` struct base | `0x00020728` | `0x00020700` | `0x0002073C` | Estructura global de configuración en RAM |
| `density` (`CFG + 4`) | `0x0002072C` | `0x00020704` | `0x00020740` | Densidad configurada (`1..5`, comando `0x21`) |
| `paper_type` (`CFG + 6`) | `0x0002072E` | `0x00020706` | `0x00020742` | Tipo de etiqueta (`1`=gap, `2`=black mark, `3`=continuo, `5`=transparente) |
| `RFID` struct base | `0x0002087C` | `0x0002083C` | `0x0002E458` | Estado del lector RFID y datos del tag |
| `tag_present` | `0x00020888` (`+12`) | `0x00020848` (`+12`) | `0x0002E460` (`+8`) | `1` = tag RFID válido leído, `0` = sin tag (etiqueta genérica) |
| `heating_mode` | `0x000204CE` | `0x000204AC` | `0x000204CA` | `0` = energía/velocidad completa, `3` = atenuado sin RFID |
| `align_flag` | `0x00020623` | `0x000205FF` | `0x00020637` | `1` = ejecutar búsqueda de gap al cerrar tapa |
| `Renderer 1` | `0x010171F0` | `0x01016124` | `0x010161EC` | Cálculo de tiempo de calentamiento por línea (modo 1) |
| `Renderer 2` | `0x01017910` | `0x01016844` | `0x0101690C` | Cálculo de tiempo de calentamiento por línea (modo 2) |
| `Motor Ramp Table` | `0x0102D47C` | `0x0102BFE0` | `0x0102D21C` | Tabla de rampa de periodos del motor paso a paso |
| `Code Cave A` | `0x0102CDC8` | `0x0102BBEA` | — | Hueco de 68 bytes para función `scale(r0)` y `mtable[5]` |
| `Code Cave B` | `0x0102CE24` | `0x0102BC4A` | — | Hueco de 44 bytes para detours `det124` y `det844` |
| `Vector Cave` | `0x01010140` | `0x01010140` | `0x01010140` | Hueco tras la tabla de vectores para helpers `align3` y `align7` |

---

## 2. Cómo Bloquea o Degrada el Firmware Stock (`3.08`) las Etiquetas Genéricas

Cuando se coloca un rollo genérico (sin chip RFID), `[0x0002087C + 12]` (`tag_present`) permanece en `0`. En el firmware stock `3.08` ocurren cuatro problemas:

1. **Modo de calentamiento degradado (`[0x000204CE] = 3`)**:
   - Tres funciones comprueban `tag_present` (`0x01017130`, `0x0102384C`, `0x01023990`) y escriben `3` en `[0x000204CE]` cuando no hay RFID.
   - Además, en `3.08`, el handler del comando **`SetDensity` (`0x21`) en `0x0101EA04`** vuelve a comprobar `tag_present` y en **`0x0101EA14` (`strb r3, [r1, #0]`)** sobreescribe `[0x000204CE] = 3` justo al inicio de cada trabajo de impresión.
   - Cuando `[0x000204CE] == 3`, `Renderer 1` (`0x01017204`) y `Renderer 2` (`0x01017962`) saltan las ramas que multiplican el tiempo de calentamiento y el bucle de línea (`0x01015F10`) introduce retardos extra, produciendo impresiones **muy tenues/casi invisibles y lentas**.
2. **Multiplicadores de energía bajos sin chip**:
   - Las constantes flotantes en `0x01012E0C..0x01012E18`, `0x01017604..0x01017628` y `0x01017D50..0x01017D60` (`10.0` a `150.0`) limitan la energía entregada al cabezal térmico cuando no hay perfil RFID cargado.
3. **El ajuste de densidad (`D1`–`D5`) es ignorado por los renderers**:
   - El byte de densidad `[0x0002072C]` se guarda en RAM al recibir el comando `0x21`, pero nunca se conecta a `Renderer 1` ni `Renderer 2`.
4. **Alineación automática del gap (`align3` y `Mode 3`)**:
   - En el camino sin chip (`0x01011E5E`), el firmware pone `[0x00020623] = 0` (`0x01011ECE`) y además el bloque de alineación (`0x010128C6`) aborta si `tag_present != 1`.
   - Más importante aún: en `3.08`, `0x01011E5E` es una máquina de estados de **2 pasadas**:
     - **Pasada 1 (`0x01011EBA`)**: activa `[0x00020034 + 4] = 1` y avanza el motor `60` pasos (`7.5 mm`).
     - **Pasada 2 (`0x01011ECA`)**: limpia `[0x00020034 + 4] = 0` y retrocede `60` pasos (`7.5 mm`).
     - Como `0x0101288A` en `3.08` no ignora `0x010128B0` mientras `[0x00020034 + 4] == 1`, activar `[0x00020623] = 1` en la Pasada 1 provoca un **bucle infinito** de avance y retroceso. Por ello, el hook `align3` debe colocarse **exclusivamente en `0x01011ECC` (Pasada 2)**.
   - Finalmente, cuando `Mode 3` (`0x0101875E`) detecta el gap en el sensor óptico (`12.7 mm` detrás del cabezal), calcula en `case 7` (`0x01018A32..0x01018A90`) los pasos hasta el cabezal como `(label_len_mm - 12.7) * 64`. Sin RFID, `label_len_mm = 0`, dando `-812.8f`, que `__aeabi_f2uiz` (`0x01026896`) convierte en `+812` microsteps (`12.7 mm`) al descartar el bit de signo. En `case 8` (`0x01018B24`), el firmware stock mueve el motor en **reversa (`r0 = 1`)** en vez de **adelante (`r0 = 0`)** cuando no hay RFID, dejando la etiqueta desfasada `25.4 mm`. Nuestro helper `MODE3_DIR_HELPER` (`0x01010148`) pasa `r0 = tag_present` (`1` = reversa con RFID, `0` = avance sin RFID) en `0x01018B26`, alineando el gap exactamente en la barra de corte (`+7.5 mm`).

---

## 3. Detalle de los Parches Aplicados por `build_b1_308_patched.py`

### 3.1. Base `fullquality` (`apply_fullquality_base`)
- **`0x01017130`, `0x0102384C`, `0x01023990`**: `03 21` (`movs r1, #3`) $\rightarrow$ `00 21` (`movs r1, #0`).
- **`0x0101EA14` (`SetDensity`)**: `0b 70` (`strb r3, [r1, #0]`) $\rightarrow$ `00 bf` (`nop`), evitando que el comando `SetDensity` reactive el modo lento/tenue `3` al imprimir sin RFID.
- **15 constantes float**: reemplazadas por `400.0f` (`0x43C80000`) en `0x01012E0C..0x01012E18`, `0x01017604`, `0x01017618..0x01017628`, `0x01017D50..0x01017D60`.
- **Tabla de rampa de motor (`0x0102D47C`, 64 entradas `uint16`)**: escalada $\times 1.5$.

### 3.2. Control de Densidad `D1`–`D5` (`apply_density_coeff_hooks`)
- **Cave A (`0x0102CDC8`, 68 bytes)**: lee `density` en `0x0002072C`, aplica máscara `0x7F`, limita al rango `[1..5]` y multiplica el float de entrada `r0` por `mtable[d - 1] = {0.675, 0.75625, 0.8375, 0.91875, 1.0}` usando `__aeabi_fmul` (`0x0102639A`).
- **Cave B (`0x0102CE24`, 44 bytes)**:
  - `det124` (`0x0102CE24`): escala el argumento float en `[sp, #0x38]` de `Renderer 1` y ejecuta las instrucciones desplazadas (`mov r6, r2; adds r6, #0xff`).
  - `det844` (`0x0102CE38`): escala los argumentos float en `[sp, #0x3C]` y `[sp, #0x40]` de `Renderer 2` y ejecuta las instrucciones desplazadas (`mov r4, r2; mov r6, r0`).
- **Hooks BL (4 bytes c/u)**:
  - `0x010171F2`: `bl 0x0102CE24`
  - `0x01017912`: `bl 0x0102CE38`

### 3.3. Búsqueda de Gap sin Chip (`apply_align3_patch`)
- **`0x010128C6`**: `1f d1` (`bne 0x01012908`) $\rightarrow$ `00 bf` (`nop`).
- **`ALIGN3_HELPER` (`0x01010140`, 8 bytes)**: invocado desde `0x01011ECC` (Pasada 2 de `0x01011E5E`), escribe `1` en `[0x00020623]`.
- **`MODE3_DIR_HELPER` (`0x01010148`, 16 bytes)**: invocado desde `0x01018B26` (`Mode 3` `case 8`), carga `r0 = [0x0002087C + 12]` (`tag_present`) antes de llamar a `0x010180F8`, de modo que sin RFID avanza `+12.7 mm` desde el sensor óptico hasta el cabezal antes de los `+7.5 mm` finales hacia la barra de corte.

### 3.4. Multiplicador Condicional por Tag (`apply_align7_patch`)
- Restaura los 4 pools de constantes float originales y la rampa de motor (`0x0102D47C`, 200 bytes) desde `B1_3.08.bin` stock (preservando intacto el puntero `0x000208C8` en `0x01017614`).
- **`ALIGN7_HELPER` (`0x01010160`, 28 bytes)**: comprueba `tag_present` (`[0x0002087C + 12]`). Si es `1` (etiqueta original con RFID), multiplica por la constante original en `r1`; si es `0` (etiqueta genérica sin RFID), sustituye `r1 = 400.0f` y llama a `__aeabi_fmul` (`0x0102639A`).
- Redirige los **18 sitios `bl __aeabi_fmul`** de calentamiento a `0x01010160`.
