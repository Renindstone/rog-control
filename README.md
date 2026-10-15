# ROG Control

Reemplazo pequeño de Armoury Crate para Linux, para el **ROG Harpe Ace Mini**
(cable `0b05:1b63` o ROG Omni Receiver `0b05:1ace`). Hecho con Python, GTK4 y libadwaita.
No tiene dependencias extra.

## Instalación

```sh
./install-udev.sh   # una vez: permite usar el mouse sin sudo
./install.sh        # copia la app a ~/.local/share y la agrega al lanzador
```

O ejecútala directamente con `./rog-control.py`.

## Qué configura

Todos los cambios se guardan en la memoria del mouse, en el perfil activo (1–5).
Así que siguen funcionando aunque cierres la app o conectes el mouse a otra PC.

| Pestaña | Ajustes |
|---|---|
| Rendimiento | perfil, 4 niveles de DPI (100–42 000) con su color, nivel activo, tasa de sondeo, distancia de despegue, angle snapping, ajuste de ángulo |
| Botones | reasignar los 8 botones/acciones a funciones de mouse, multimedia o teclado (F13–F24 incluidas) |
| Iluminación | efecto, brillo y color del logo |
| Energía | batería, apagado automático, aviso de batería baja |
| Receptor | estado del Omni Receiver y del Polling Rate Booster |

## Qué no hace (a propósito)

- **Actualizar firmware** del mouse o del receptor: si sale mal, puede dejar el dispositivo inservible.
- **Emparejar** el receptor: ese protocolo no está documentado.
- **Cambiar la cantidad de niveles DPI**: el mouse acepta el comando pero no permite leer el valor, así que la app no podría mostrar el estado real.
- **Macros**.

## Protocolo

`probe.py` muestra lo que responde el mouse a cada comando de lectura. No escribe nada.
Los formatos de los paquetes se verificaron contra el mouse real. Se tomaron como referencia
el driver ASUS de [libratbag](https://github.com/libratbag/libratbag) y el modelo
Harpe Ace Mini de [G-Helper](https://github.com/seerge/g-helper).
