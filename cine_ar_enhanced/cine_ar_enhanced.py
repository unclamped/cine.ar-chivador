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
    # Replace non-alphanumeric with dots
    text = re.sub(r'[^a-zA-Z0-9]', '.', text)
    # Remove consecutive dots
    text = re.sub(r'\.+', '.', text)
    # Strip leading/trailing dots
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
    # Try to find SID in URL (e.g., /produccion/6111)
    match = re.search(r'/produccion/(\d+)', input_val)
    if match:
        return match.group(1)
    # Check if it's just the ID at the end of some other URL structure
    match = re.search(r'/(\d+)/?$', input_val)
    if match:
        return match.group(1)
    return None

def main():
    parser = argparse.ArgumentParser(description='Cine.ar Enhanced Downloader (PTP/HANDJOB Edition)')
    parser.add_argument('input', help='Cine.ar URL, movie SID, or direct manifest URL')
    parser.add_argument('-o', '--output', help='Custom output filename')
    parser.add_argument('-t', '--token', help='Custom auth token', default=TOKEN)
    parser.add_argument('-q', '--quality', help='Profile/Quality (default: MASTER)', default='MASTER')
    
    args = parser.parse_args()
    
    # Check if input is a direct manifest URL
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
    
    # 1. Fetch Metadata for Naming and Profile Filename
    meta = get_metadata(sid) if sid != "Unknown" else None
    title = "Unknown.Movie"
    year = "0000"
    profile_id = args.quality
    
    if meta:
        # Actual structure from info.json
        origin = meta.get('origin', {})
        raw_file_name = origin.get('file_name', 'Unknown Movie')
        
        # Clean up title: "6111 - MARTA SHOW - PLAY.mp4" -> "MARTA SHOW"
        # 1. Remove .mp4
        clean_title = raw_file_name.rsplit('.', 1)[0]
        # 2. Aggressively remove platform suffixes (PLAY, TVOD, AVOD)
        clean_title = re.sub(r'\s+-\s+(PLAY|TVOD|AVOD)$', '', clean_title, flags=re.IGNORECASE)
        # 3. Remove SID prefix: "6111 - "
        clean_title = re.sub(rf'^{sid}\s+-\s+', '', clean_title)
        
        # Try to find year in the cleaned title if not explicitly in JSON
        year = str(meta.get('year', meta.get('release_year', '0000')))
        if year == "0000":
            match = re.search(r'\((\d{4})\)', clean_title)
            if match:
                year = match.group(1)
                clean_title = clean_title.replace(f'({year})', '').strip()
        
        title = sanitize_ptp(clean_title)
        
        # Find correct profile filename from profiles object
        profiles = meta.get('profiles', {})
        target_profile = profiles.get(args.quality)
        if target_profile:
            filename = target_profile.get('file_name', '')
            if filename:
                profile_id = filename.replace('.mp4', '')

    # 2. Determine Filename
    if args.output:
        output_name = args.output
    else:
        # Format: Original.Title.YEAR.Resolution.Source-GROUP.mkv
        res_label = "1080p" if args.quality == "MASTER" else args.quality
        output_name = f'{title}.{year}.{res_label}.WEB-DL.x264-{GROUP_NAME}.mkv'

    # 3. Construct URL if not provided directly
    if not hq_url:
        # We need a session token
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

        # Use the secret URL pattern
        hq_url = f'https://{STREAM_DOMAIN}/odeon/_definst_/mp4:omc/INCAA/{sid}/{profile_id}.mp4/playlist.m3u8?t={session_token}'
    
    print(f'[*] Dynamic filename: {output_name}')
    print(f'[*] HQ URL: {hq_url}')

    # 4. Download with ffmpeg
    print(f'[*] Starting download -> {output_name}')
    ffmpeg_cmd = [
        'ffmpeg',
        '-y',
        '-protocol_whitelist', 'file,http,https,tcp,tls',
        '-i', hq_url,
        '-c', 'copy',
        output_name
    ]

    try:
        subprocess.run(ffmpeg_cmd, check=True)
        print(f'[+] Success! File saved as {output_name}')
    except subprocess.CalledProcessError:
        print(f'[!] ffmpeg failed. The stream might be offline or require a fresh token.')
    except FileNotFoundError:
        print('[!] Error: ffmpeg not found.')

if __name__ == '__main__':
    main()
