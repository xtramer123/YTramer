# YTramer

Pega un link de YouTube, elige carpeta y formato, y listo. Sin anuncios, sin esperas, sin registro.

Las páginas de "convertir YouTube a MP3" están llenas de publicidad, ventanas emergentes y descargas forzadas. **YTramer** es un programa de escritorio que hace lo mismo en una ventana limpia.

## Pensado para desarrollo de juegos

Cuando estás armando un prototipo o un prototipo de sonido, necesitas efectos y música rápido, sin salir del flujo de trabajo ni pelearte con un sitio lleno de anuncios. Copias el link, pegas, descargas.

## Formatos

**Audio:** MP3 · WAV · M4A · OPUS · FLAC
**Video:** MP4 · WEBM

Los formatos con pérdida (MP3, M4A, OPUS) traen selector de calidad. WAV y FLAC se guardan tal cual, sin comprimir.

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