# YTramer

Pega un link de YouTube, elige carpeta, formato, nombre y si quieres recortar. Sin anuncios, sin esperas, sin registro.

Las páginas de "convertir YouTube a MP3" están llenas de publicidad, ventanas emergentes y descargas forzadas. **YTramer** es un programa de escritorio que hace lo mismo en una ventana limpia.

## Pensado para desarrollo de juegos

Cuando estás armando un prototipo o un prototipo de sonido, necesitas efectos y música rápido, sin salir del flujo de trabajo ni pelearte con un sitio lleno de anuncios. Copias el link, pegas, descargas.

## Formatos

**Audio:** MP3 · WAV · M4A · OPUS · FLAC
**Video:** MP4 · WEBM

Los formatos con pérdida (MP3, M4A, OPUS) traen selector de calidad. WAV y FLAC se guardan tal cual, sin comprimir.

## Recortar

Un botón **Recortar** junto al link abre los controles del corte:

- La app lee la duración del video y muestra **Desde** y **Hasta**.
- Puedes mover los deslizadores o escribir el tiempo exacto (`1:30`, `90`, `1:02:03`).
- Los botones **-5s / +5s** ajustan cada punto sin escribir nada.
- **Aplicar y descargar** baja solo ese tramo: no se descarga el video completo y luego se corta.

El recorte mínimo es de 1 segundo. Si un video no permite descarga parcial, la app lo baja completo y lo recorta al final, así que siempre terminas con el fragmento.

## Nombre

El campo **Nombre (opcional)** decide cómo se guarda el archivo. Si lo dejas vacío se usa el título del video. Los caracteres inválidos de Windows se cambian por `_` y, si el nombre ya existe, se agrega `(2)`, `(3)`, etc.

## Uso

```
python main.py
```

Pega el link y presiona Enter. La descarga corre en segundo plano con barra de progreso, velocidad y tiempo restante.

## Compilar

```
python build.py
```

Genera `programa/YTramer.exe` (un solo archivo, sin instalar nada). El script descarga ffmpeg y deno automáticamente; no hace falta tenerlos instalados.

## Requisitos

Python 3.10 o superior. `build.py` instala las dependencias solo (`yt-dlp` y `pyinstaller`).

---

Uso personal y educativo. Respeta los derechos de autor del material que descargas.