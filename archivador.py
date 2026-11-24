# -*- coding: utf-8 -*-
import argparse
import base64
import json
import logging
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests
from playwright.sync_api import sync_playwright, Error

# --- Configuración de Logging ---
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

# --- Funciones Auxiliares ---

def get_ffmpeg_version():
    """Verifica si ffmpeg está instalado y devuelve su versión."""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, check=True)
        version_line = result.stdout.splitlines()[0]
        return version_line
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

def sanitize_filename(name):
    """Elimina caracteres no válidos para nombres de archivo."""
    return re.sub(r'[\/*?:"<>|]',"", name)

# --- Lógica Principal ---

def fetch_convert_url(page_url: str, token: str | None) -> tuple[str | None, str | None, str | None]:
    """
    Navega a la página de la película usando Playwright para capturar la URL de 'convert'
    y el título de la película, inyectando un token de autenticación si se proporciona.
    """
    logging.info("Iniciando navegador para encontrar la URL del manifiesto...")
    convert_url = None
    convert_content = None
    title = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Interceptar respuestas para encontrar la de 'convert' y su contenido
        def handle_response(response):
            nonlocal convert_url, convert_content
            if "odeon/convert/" in response.url and response.status == 200:
                logging.info(f"URL del manifiesto encontrada: {response.url}")
                convert_url = response.url
                try:
                    convert_content = response.text()
                    logging.info("Contenido del manifiesto capturado exitosamente.")
                except Exception as e:
                    logging.warning(f"No se pudo obtener el contenido del manifiesto: {e}")
        
        page.on("response", handle_response)

        try:
            # Si hay token, navegar primero al dominio para establecer el localStorage
            if token:
                logging.info("Inyectando token de autenticación en Local Storage...")
                # Ir a la página base para tener el contexto del dominio
                page.goto("https://play.cine.ar", wait_until="domcontentloaded")
                page.evaluate('''
                    token => {
                        localStorage.setItem('odeon_token', token);
                    }
                ''', token)
                logging.info("Token inyectado.")

            logging.info(f"Navegando a: {page_url}")
            page.goto(page_url, wait_until="networkidle", timeout=60000)
            title = page.title()
            logging.info(f"Título de la página encontrado: {title}")
            
            # Intentar hacer clic en el botón de reproducir si no se capturó la URL
            if not convert_url:
                logging.info("Intentando encontrar y hacer clic en el botón de reproducción...")
                # Locators para el botón de play
                locators = [
                    'a[href*="/reproducir"]',
                    'a[description="Click para reproducir"]',
                    'button:has-text("Reproducir")',
                    'image[description="Reproducir"]'
                ]
                for selector in locators:
                    try:
                        play_button = page.locator(selector).first
                        if play_button.is_visible():
                            play_button.click()
                            logging.info(f"Botón de reproducción pulsado (selector: {selector}).")
                            break
                    except:
                        continue
                
                # Si sigue sin encontrarse y es una URL de producción, intentar navegar a /reproducir
                if not convert_url and "/produccion/" in page.url and not "/reproducir" in page.url:
                    logging.info("Navegando directamente a la URL de reproducción...")
                    try:
                        page.goto(page.url + "/reproducir", wait_until="networkidle", timeout=30000)
                    except:
                        pass

            # Esperar un poco más si la URL no se ha encontrado todavía
            if not convert_url:
                logging.info("Esperando a que se genere la petición del manifiesto...")
                for _ in range(15):  # Esperar hasta 15 segundos
                    if convert_url:
                        break
                    page.wait_for_timeout(1000)

        except Error as e:
            logging.error(f"Error de Playwright: {e}")
            return None, None, None
        finally:
            browser.close()
            logging.info("Navegador cerrado.")

    return convert_url, convert_content, title

def download_movie(manifest_url: str, manifest_content: str | None, output_filename: str):
    """
    Descarga y procesa el manifiesto para finalmente descargar el video con ffmpeg.
    """
    master_playlist = None
    
    # 1. Obtener manifiesto principal
    if manifest_content:
        master_playlist = manifest_content
    else:
        logging.info("Descargando manifiesto principal con requests...")
        try:
            res = requests.get(manifest_url)
            res.raise_for_status()
            master_playlist = res.text
        except requests.RequestException as e:
            logging.error(f"No se pudo descargar el manifiesto principal: {e}")
            return

    # 2. Parsear manifiesto y elegir la mejor calidad
    # (Esta es una implementación simple, se puede mejorar para elegir calidad)
    lines = master_playlist.strip().split('\n')
    best_stream_info = None
    max_bandwidth = 0

    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            bandwidth_match = re.search(r'BANDWIDTH=(\d+)', line)
            if bandwidth_match:
                bandwidth = int(bandwidth_match.group(1))
                if bandwidth > max_bandwidth:
                    max_bandwidth = bandwidth
                    # La URL del stream está en la siguiente línea
                    if i + 1 < len(lines):
                        best_stream_info = lines[i+1]

    if not best_stream_info:
        logging.error("No se pudo encontrar ninguna pista de video en el manifiesto.")
        return

    # 3. Extraer y decodificar el manifiesto de la pista de video
    base64_data_match = re.search(r'base64,(.*)', best_stream_info)
    if not base64_data_match:
        logging.error("No se encontró el contenido base64 en el manifiesto de la pista.")
        return
    
    base64_data = base64_data_match.group(1)
    try:
        # Añadir padding si es necesario
        missing_padding = len(base64_data) % 4
        if missing_padding:
            base64_data += '='* (4 - missing_padding)
        segment_playlist = base64.b64decode(base64_data).decode('utf-8')
    except (base64.binascii.Error, UnicodeDecodeError) as e:
        logging.error(f"Error al decodificar el manifiesto de la pista: {e}")
        return

    # 4. Guardar manifiesto en un archivo temporal y descargar con ffmpeg
    temp_playlist_path = Path("temp_playlist.m3u8")
    with open(temp_playlist_path, 'w', encoding='utf-8') as f:
        f.write(segment_playlist)

    logging.info(f"Manifiesto de segmentos guardado en '{temp_playlist_path}'")
    logging.info("Iniciando descarga con ffmpeg... Esto puede tardar varios minutos.")
    
    ffmpeg_command = [
        'ffmpeg',
        '-y',  # Sobrescribir sin preguntar
        '-protocol_whitelist', 'file,http,https,tcp,tls',
        '-i', str(temp_playlist_path),
        '-bsf:a', 'aac_adtstoasc',
        '-vcodec', 'copy',
        '-c', 'copy',
        '-crf', '5',
        str(output_filename)
    ]

    try:
        subprocess.run(ffmpeg_command, check=True)
        logging.info(f"¡Éxito! Película guardada como '{output_filename}'")
    except subprocess.CalledProcessError as e:
        logging.error(f"ffmpeg falló con el código de salida {e.returncode}")
    except FileNotFoundError:
        logging.error("Error: ffmpeg no está instalado o no se encuentra en el PATH.")
    finally:
        # 5. Limpieza
        logging.info(f"Eliminando archivo temporal '{temp_playlist_path}'")
        temp_playlist_path.unlink()


def main():
    """Función principal que orquesta todo el proceso."""
    parser = argparse.ArgumentParser(
        description="Descargador de películas de cine.ar.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Ejemplos de uso:
  # Descarga básica
  python archivador.py "https://play.cine.ar/INCAA/produccion/1234"

  # Especificando un nombre de archivo de salida
  python archivador.py "https://play.cine.ar/INCAA/produccion/1234" -o "Mi Pelicula.mp4"

  # Usando un token para una sesión autenticada
  python archivador.py "https://play.cine.ar/INCAA/produccion/1234" --token "valor_del_token_aqui"
"""
    )
    parser.add_argument("url", help="La URL completa de la película en cine.ar play.")
    parser.add_argument("-o", "--output", help="Ruta del archivo de video de salida. Ej: 'pelicula.mp4'")
    parser.add_argument("--token", help="El token de 'odeon_token' del Local Storage para la autenticación.")
    
    args = parser.parse_args()

    # --- Verificaciones Iniciales ---
    ffmpeg_version = get_ffmpeg_version()
    if not ffmpeg_version:
        logging.error("ffmpeg no parece estar instalado o no está en el PATH del sistema.")
        logging.error("Por favor, instálalo y asegúrate de que sea accesible desde la terminal.")
        sys.exit(1)
    logging.info(f"ffmpeg encontrado: {ffmpeg_version}")

    # --- Flujo Principal ---
    convert_url, convert_content, title = fetch_convert_url(args.url, args.token)

    if not convert_url:
        logging.error("No se pudo obtener la URL del manifiesto. No se puede continuar.")
        sys.exit(1)
    
    if not title:
        logging.warning("No se pudo obtener el título de la película, se usará un nombre genérico.")
        title = "pelicula_archivada"

    output_file = args.output if args.output else f"{sanitize_filename(title)}.mp4"

    download_movie(convert_url, convert_content, output_file)


if __name__ == "__main__":
    main()