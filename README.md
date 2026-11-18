# Niimbot B1 — Custom Firmware `3.08` (Third-Party Labels + Density Control)

> ## ⚠️ ADVERTENCIA IMPORTANTE / READ THIS FIRST
>
> - **Este firmware es EXCLUSIVAMENTE para la impresora Niimbot B1 con versión de firmware `3.08` (rama `3.x`).**
> - **NO flashees estos binarios en impresoras con firmware `4.x`, `5.x` o `6.x`.** Cruzar versiones mayores de firmware en impresoras Niimbot **dejará la impresora inservible (brick)** debido a diferencias de hardware/bootloader.
> - Proyecto con fines de investigación, interoperabilidad y derecho a reparar sobre hardware propio. Sin garantía; el uso es bajo tu propio riesgo.

---

## ¿Qué resuelve este parche en el firmware `3.08`?

En el firmware oficial `3.08`, cuando usas rollos de etiquetas genéricas (sin chip RFID), la impresora reduce drásticamente la energía del cabezal térmico (`[0x000204CE] = 3`), ignora el ajuste de densidad (`D1`–`D5`) y desactiva la alineación de etiquetas.

Este repositorio adapta y combina para el firmware **`3.08`** los parches de la comunidad:
- **Impresión negra intensa y velocidad normal en etiquetas genéricas (sin RFID):** desactiva el estrangulamiento de energía en `SetDensity` (`0x0101EA14`) y en las curvas térmicas (`0x01017130`, `0x0102384C`, `0x01023990`).
- **Control real de densidad (`D1` a `D5`):** conecta el byte de densidad (`0x0002072C`) directamente a los dos renderers térmicos (`0x010171F0` y `0x01017910`) mediante detours en código Thumb (`0x0102CDC8` y `0x0102CE24`).
- **Compatibilidad total con etiquetas originales (con RFID) y genéricas (`align7`):** mantiene los multiplicadores y rampa de motor originales cuando detecta un chip RFID (`tag_present == 1`) y aplica el multiplicador `400.0f` únicamente cuando no hay chip RFID (`tag_present == 0`).
- **Alineación automática de gap sin bucle infinito (`align3` + `Mode 3` fix):** corrige el hook de Pasada 2 (`0x01011ECC`) y la dirección de avance en `Mode 3` (`0x01018B26`) cuando no hay RFID, para que el gap quede posicionado en la barra de corte.

---

## Binarios incluidos en `firmware/`

| Archivo | MD5 | Descripción y cuándo usarlo |
|---|---|---|
| [`firmware/B1_3.08_density_align7.bin`](firmware/B1_3.08_density_align7.bin) | `ebdead6ae06dc73a4cc971d6b918f2c0` | **Recomendado (Completo con auto-seek):** Control de densidad `D1`–`D5` + `align7` (rápido con RFID, negro total sin RFID) + búsqueda y alineación automática de gap al encender o cerrar la tapa. |
| [`firmware/B1_3.08_density_align7_no_autoseek.bin`](firmware/B1_3.08_density_align7_no_autoseek.bin) | `489730b2c1e6dbaf525ebd96f1bce71b` | **Recomendado (Sin auto-seek al reiniciar):** Idéntico a `density_align7`, pero **no mueve el papel automáticamente al encender/reiniciar la impresora**. Ideal si dejas el rollo puesto entre reinicios y no quieres que busque el gap al encender (se alinea al presionar el botón físico o desde el primer trabajo). |
| [`firmware/B1_3.08_density_align3.bin`](firmware/B1_3.08_density_align3.bin) | `ccd9094c73129294adaa5bf31a145f62` | Control de densidad `D1`–`D5` + `align3` (auto-seek), con multiplicadores fijos `400.0f`. |
| [`firmware/B1_3.08_density_coeff.bin`](firmware/B1_3.08_density_coeff.bin) | `5c7e3aeab8a846fd658bb6b9e593f56b` | Control de densidad `D1`–`D5` + oscuridad total en genéricas, sin hooks de alineación. |
| [`firmware/B1_3.08_thirdparty_fullquality.bin`](firmware/B1_3.08_thirdparty_fullquality.bin) | `b50c4c774425b6fbd9f2cd6198cf6246` | Parche base: oscuridad máxima fija (`D5`) en etiquetas genéricas, sin escalado por densidad. |
| [`firmware/B1_3.08.bin`](firmware/B1_3.08.bin) | `455f420bb63b46469747c199d14497a4` | Firmware oficial **stock `3.08`** sin modificar (para restaurar de fábrica o reconstruir los parches). |

---

## Cómo flashear la impresora

### Opción 1: Desde el navegador (Web Serial / Web Bluetooth)
1. Conecta la **Niimbot B1** por cable USB a tu computadora y enciéndela.
2. Abre [https://printers.niim.blue/firmware/flashing-firmware/](https://printers.niim.blue/firmware/flashing-firmware/) en Chrome o Edge.
3. Conecta la impresora y verifica que tu versión actual sea **`3.08`**.
4. Selecciona el archivo [`firmware/B1_3.08_density_align7.bin`](firmware/B1_3.08_density_align7.bin) (o [`firmware/B1_3.08_density_align7_no_autoseek.bin`](firmware/B1_3.08_density_align7_no_autoseek.bin)) e introduce **`3.08`** como versión destino.
5. Al finalizar el flasheo, la impresora se apagará sola (es normal). Presiona el botón de encendido para volver a prenderla.

### Opción 2: Desde terminal con `niimblue-node`
```bash
# En macOS (reemplaza el puerto por el tuyo, ej. /dev/cu.usbmodem*):
npx @mmote/niimblue-node flash -t serial -a /dev/cu.usbmodem* -n 3.08 \
  -f firmware/B1_3.08_density_align7.bin

# En Linux:
npx @mmote/niimblue-node flash -t serial -a /dev/ttyACM0 -n 3.08 \
  -f firmware/B1_3.08_density_align7.bin
```

---

## Reconstruir los binarios desde el código fuente

El script [`firmware/build_b1_308_patched.py`](firmware/build_b1_308_patched.py) utiliza únicamente la librería estándar de Python 3, verifica el MD5 del binario stock `B1_3.08.bin` y genera de forma reproducible las 5 variantes:

```bash
python3 firmware/build_b1_308_patched.py
```

---

## Estructura del repositorio

| Ruta | Descripción |
|---|---|
| [`firmware/build_b1_308_patched.py`](firmware/build_b1_308_patched.py) | Script generador reproducible de todos los parches sobre `B1_3.08.bin`. |
| [`firmware/*.bin`](firmware/) | Imagen stock `3.08` y las 5 variantes parcheadas listas para flashear. |
| [`docs/firmware-analysis-3.08.md`](docs/firmware-analysis-3.08.md) | Documentación técnica completa de ingeniería inversa, mapa de memoria RAM/Flash y detalle de cada parche en `3.08`. |
| [`src/B1_3.08_density_hooks.s`](src/B1_3.08_density_hooks.s) | Código ensamblador ARM Cortex-M0 (Thumb) de los code caves (`scale`, `det124`, `det844`, `align3`, `mode3_dir`, `align7`). |
| [`src/B1_3.08_density_hooks.ld`](src/B1_3.08_density_hooks.ld) | Linker script con las direcciones exactas en Flash para `3.08`. |
| [`test-labels/`](test-labels/) | Etiquetas de prueba (`384 px`, `50x30 mm`) para validar los niveles de densidad `D1`–`D5`. |

---

## Créditos y Referencias

- [ThreeDaPrint/niimbot](https://github.com/ThreeDaPrint/niimbot) — Ingeniería inversa del modelo de energía/densidad y detours Cortex-M0 en firmware `5.22`.
- [vkolarik/niimbot-b1](https://github.com/vkolarik/niimbot-b1) — Análisis y diseño de los parches `align3` y `align7` en firmware `6.19`.
- [lotabout/niimbot](https://github.com/lotabout/niimbot) — Parche comunitario original "variant B".
- [fw.niim.blue](https://fw.niim.blue/) y [printers.niim.blue](https://printers.niim.blue/firmware/flashing-firmware/) — Repositorio de firmwares y herramientas de flasheo de MultiMote.
