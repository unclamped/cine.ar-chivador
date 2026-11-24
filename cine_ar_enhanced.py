# -*- coding: utf-8 -*-
import hashlib
import base64
import requests
import re
import subprocess
import os
import argparse
import sys
from urllib.parse import urlparse
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from pymediainfo import MediaInfo
except ImportError:
    MediaInfo = None

# Load configuration from .env
GROUP_NAME = os.getenv('GROUP_NAME', 'HANDJOB')

# Default Configuration
TOKEN = os.getenv('CINEAR_TOKEN', '')
PERFIL = os.getenv('CINEAR_PERFIL', '')
SOURCE = 'INCAA'
STREAM_DOMAIN = '63665c4aa186c.streamlock.net'

def sanitize_ptp(text):
    """Sanitizes text according to PTP/HANDJOB conventions: 
    Replace all non-alphanumeric characters with dots, remove duplicates."""
    text = re.sub(r'[^a-zA-Z0-9]', '.', text)
    text = re.sub(r'\.+', '.', text)
    return text.strip('.')

def get_metadata(sid):
    """Fetches movie metadata from the info.json endpoint."""
    url = f'https://player.cine.ar/odeon/extras/{SOURCE}/{sid}/info.json'
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f'[!] Warning: Could not fetch metadata for SID {sid}: {e}')
        return None

def extract_sid(input_val):
    """Extracts SID from a URL or returns the SID if numeric."""
    if input_val.isdigit():
        return input_val
    match = re.search(r'/produccion/(\d+)', input_val)
    if match:
        return match.group(1)
    match = re.search(r'/(\d+)/?$', input_val)
    if match:
        return match.group(1)
    return None

def get_actual_resolution(file_path):
    """Uses MediaInfo to get the actual height of the video."""
    if not MediaInfo:
        print("[!] Warning: pymediainfo not installed. Skipping resolution verification.")
        return None
    try:
        media_info = MediaInfo.parse(file_path)
        for track in media_info.tracks:
            if track.track_type == 'Video':
                return track.height
    except Exception as e:
        print(f"[!] Error parsing MediaInfo: {e}")
    return None

def main():
    parser = argparse.ArgumentParser(description='Cine.ar Enhanced Downloader (PTP/HANDJOB Edition)')
    parser.add_argument('input', help='Cine.ar URL, movie SID, or direct manifest URL')
    parser.add_argument('-o', '--output', help='Custom output filename')
    parser.add_argument('-t', '--token', help='Custom auth token', default=TOKEN)
    parser.add_argument('-q', '--quality', help='Profile/Quality (default: MASTER)', default='MASTER')
    
    args = parser.parse_args()
    
    if args.input.startswith('http') and ('.m3u8' in args.input or '.mpd' in args.input):
        hq_url = args.input
        sid = extract_sid(args.input) or "Unknown"
        print(f'[*] Using direct manifest URL: {hq_url}')
    else:
        sid = extract_sid(args.input)
        if not sid:
            print(f'[!] Error: Could not determine SID from input: {args.input}')
            sys.exit(1)
        hq_url = None

    print(f'[*] Processing SID: {sid}')
    
    # 1. Fetch Metadata for Naming
    meta = get_metadata(sid) if sid != "Unknown" else None
    title = "Unknown.Movie"
    year = "0000"
    profile_id = args.quality
    
    if meta:
        origin = meta.get('origin', {})
        raw_file_name = origin.get('file_name', 'Unknown Movie')
        clean_title = raw_file_name.rsplit('.', 1)[0]
        # Remove SID prefix, - PLAY, - TVOD, etc.
        clean_title = re.sub(r'\s+-\s+(PLAY|TVOD|AVOD|SVOD)$', '', clean_title, flags=re.IGNORECASE)
        clean_title = re.sub(rf'^{sid}\s+-\s+', '', clean_title)
        
        # info.json doesn't have 'year', so we rely on regex
        match = re.search(r'\((\d{4})\)', clean_title)
        if match:
            year = match.group(1)
            clean_title = clean_title.replace(f'({year})', '').strip()
        
        title = sanitize_ptp(clean_title)
        
        profiles = meta.get('profiles', {})
        target_profile = profiles.get(args.quality)
        if target_profile:
            filename = target_profile.get('file_name', '')
            if filename:
                profile_id = filename.replace('.mp4', '')

    # 2. Determine Temp Filename for initial download
    temp_output = f"temp_{sid}_{args.quality}.mp4"

    # 3. Construct URL if not provided directly
    if not hq_url:
        session_token = args.token
        try:
            clave = f'{SOURCE}{sid}{PERFIL}{args.token}ARSAT'
            digest = hashlib.md5(clave.encode()).digest()
            x_auth_key = base64.b64encode(digest).decode()
            api_url = f'https://player.cine.ar/odeon/?s={SOURCE}&i={sid}&p={PERFIL}&t={args.token}'
            headers = {
                'Authorization': f'Bearer {args.token}',
                'X-Auth-Key': x_auth_key,
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36'
            }
            r = requests.get(api_url, headers=headers, timeout=5)
            if r.status_code == 200:
                m_url = r.json().get('url', '')
                if '?t=' in m_url:
                    session_token = m_url.split('?t=')[1]
        except:
            pass
        hq_url = f'https://{STREAM_DOMAIN}/odeon/_definst_/mp4:omc/INCAA/{sid}/{profile_id}.mp4/playlist.m3u8?t={session_token}'
    
    print(f'[*] HQ URL: {hq_url}')

    # 4. Download with ffmpeg to temporary file
    print(f'[*] Starting download to temporary file: {temp_output}')
    ffmpeg_cmd = [
        'ffmpeg', '-y',
        '-protocol_whitelist', 'file,http,https,tcp,tls',
        '-i', hq_url,
        '-c', 'copy',
        temp_output
    ]

    try:
        subprocess.run(ffmpeg_cmd, check=True)
        print(f'[+] Download complete.')
        
        # 5. Verify Resolution with MediaInfo
        actual_height = get_actual_resolution(temp_output)
        if actual_height:
            print(f"[*] Verified resolution height: {actual_height}p")
            res_label = f"{actual_height}p"
        else:
            res_label = "1080p" if args.quality == "MASTER" else args.quality
            print(f"[*] Could not verify resolution. Falling back to quality label: {res_label}")

        # 6. Final Renaming
        if args.output:
            final_name = args.output
        else:
            final_name = f'{title}.{year}.{res_label}.WEB-DL.x264-{GROUP_NAME}.mkv'

        if os.path.exists(final_name):
            print(f"[!] Warning: {final_name} already exists. Overwriting.")
        
        os.rename(temp_output, final_name)
        print(f'[+] Success! Final file saved as: {final_name}')

    except subprocess.CalledProcessError:
        print(f'[!] ffmpeg failed. The stream might be offline or require a fresh token.')
        if os.path.exists(temp_output): os.remove(temp_output)
    except FileNotFoundError:
        print('[!] Error: ffmpeg not found.')
    except Exception as e:
        print(f'[!] An error occurred during post-processing: {e}')
        if os.path.exists(temp_output): os.remove(temp_output)

if __name__ == '__main__':
    main()
