# -*- coding: utf-8 -*-
import base64
import re
import subprocess
from pathlib import Path

def download_movie(manifest_content: str, output_filename: str):
    lines = manifest_content.strip().split('\n')
    best_stream_info = None
    max_bandwidth = 0

    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            bandwidth_match = re.search(r'BANDWIDTH=(\d+)', line)
            if bandwidth_match:
                bandwidth = int(bandwidth_match.group(1))
                if bandwidth > max_bandwidth:
                    max_bandwidth = bandwidth
                    if i + 1 < len(lines):
                        best_stream_info = lines[i+1]

    if not best_stream_info:
        print("Error: No se pudo encontrar ninguna pista de video en el manifiesto.")
        return

    base64_data_match = re.search(r'base64,(.*)', best_stream_info)
    if not base64_data_match:
        print("Error: No se encontró el contenido base64 en el manifiesto de la pista.")
        return
    
    base64_data = base64_data_match.group(1)
    try:
        missing_padding = len(base64_data) % 4
        if missing_padding:
            base64_data += '='* (4 - missing_padding)
        segment_playlist = base64.b64decode(base64_data).decode('utf-8')
    except (base64.binascii.Error, UnicodeDecodeError) as e:
        print(f"Error al decodificar el manifiesto de la pista: {e}")
        return

    temp_playlist_path = Path("temp_playlist.m3u8")
    with open(temp_playlist_path, 'w', encoding='utf-8') as f:
        f.write(segment_playlist)

    print(f"Manifiesto de segmentos guardado en '{temp_playlist_path}'")
    print("Iniciando descarga con ffmpeg...")
    
    ffmpeg_command = [
        'ffmpeg',
        '-y',
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
        print(f"¡Éxito! Película guardada como '{output_filename}'")
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg falló con el código de salida {e.returncode}")
    finally:
        if temp_playlist_path.exists():
            temp_playlist_path.unlink()

if __name__ == "__main__":
    import sys
    with open("manifest_body.txt", "r") as f:
        content = f.read()
    download_movie(content, "Marta Show.mp4")
