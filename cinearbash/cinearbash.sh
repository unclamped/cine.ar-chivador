#!/usr/bin/env bash
clear
# ANSI escape code for green color
green="\e[32m"

# ANSI escape code for resetting color
reset="\e[0m"
#ASCII Art
echo -e "            █████
       ███████████████        █████████   ██████████         █████████   ██████████████████████
     ████████████████████     █████████   ████████████       █████████   ████████████████████
   ████████████████████████   █████████   █████████████      █████████   ██████████████████        ██████████
  █████████████████████████   █████████   ███████████████    █████████   █████████████████      ███████████████
 ██████████        █████      █████████   ████████████████   █████████   ██████████            ██████████████████
 ████████                     █████████   ██████████████████ █████████   ████████████████     ██████  ███    █████
█████████                     █████████   ████████████████████████████   ████████████████     █████    ██  █  ████
█████████                     █████████   ████████████████████████████   ████████████████     █████     █    █████
 ████████                     █████████   ██████████ █████████████████   ████████████████     ████  ██  █  █  ████
 ██████████        █████      █████████   ██████████  ████████████████   ██████████            ██████████████████
  █████████████████████████   █████████   ██████████    ██████████████   █████████████████      ████████████████
   ████████████████████████   █████████   ██████████     █████████████   ██████████████████       ████████████
    █████████████████████     █████████   ██████████       ███████████   ███████████████████
       ████████████████       █████████   ██████████        ██████████   ██████████████████████
           ████████
"
# Login
source cinear.cfg

login_url="https://id.cine.ar/v1.5/auth/login"
API_URI="https://play.cine.ar/api/v1.7"
production_info_url="${API_URI}/INCAA/prod/"
player_url="https://player.cine.ar/odeon/"

# Para logearse y obtener el token
login() {
    # Si ya tenemos un token.txt que funciona, podemos saltarnos el login
    if [ -f "token.txt" ]; then
        token=$(< token.txt)
        # Verificar si el token sigue siendo válido intentando obtener el perfil
        if curl -s -X GET "${API_URI}/user" -H "Authorization: Bearer $token" | jq -e '.perfiles' > /dev/null; then
            echo -e "${green}Usando token existente de token.txt${reset}"
            return 0
        fi
    fi

    echo -e "Iniciando sesión..."
    response=$(curl -s -X POST "$login_url" -H "Content-Type: application/json" -d "{\"email\": \"$email\", \"password\": \"$password\"}")
    token=$(echo "$response" | jq -r '.token // empty')
    
    if [ -z "$token" ] || [ "$token" = "null" ]; then
        echo "Error: Falló el inicio de sesión. Revisa tus credenciales en cinear.cfg"
        echo "Respuesta del servidor: $response"
        exit 1
    else
        echo "$token" > token.txt
        echo -e "${green}Logeado correctamente! Token guardado en token.txt${reset}"
    fi
}

# Obtener el perfil de usuario
get_user_pid() {
    local user_url="${API_URI}/user"
    perfil=$(curl -s -X GET "$user_url" -H "Authorization: Bearer $token" | jq -r '.perfiles[0].id // empty')
    if [ -z "$perfil" ] || [ "$perfil" = "null" ]; then
        echo "Error: No se pudo obtener el ID de perfil."
        exit 1
    fi
    echo "Perfil ID: $perfil"
}

# Obtener informacion a partir del SID
get_production_info() {
    local sid="$1"
    formatted_sid=$(printf "%04d" $sid)
    
    response=$(curl -s -X GET "${production_info_url}/${sid}?perfil=${perfil}" -H "Authorization: Bearer $token" -H "Content-Type: application/json")
    
    # Check if the response contains an error
    errorMsg=$(echo "$response" | jq -r '.message // empty')
    if [ "$errorMsg" = "producción no encontrada o incompatible con las características del perfil" ]; then
        echo -e "\e[0;31mSID $sid no encontrado o incompatible${reset}"
        return 1
    fi

    # Ver si es pelicula o serie
    tipo_text=$(echo "$response" | jq -r '.tipos[0].text // empty')
    titulo=$(echo "$response" | jq -r '.tit // "Pelicula_$sid"')
    anio=$(echo "$response" | jq -r '.an // ""')

    safe_folder_name=$(echo "$tipo_text" | sed 's/[^a-zA-Z0-9]/_/g')
    [ -z "$safe_folder_name" ] && safe_folder_name="Descargas"

    # Bajar Pelis
    if [ "$tipo_text" = "Películas" ] || [ "$tipo_text" = "Cortos" ]; then
        # Crea la carpeta si no existe
        mkdir -p "./$safe_folder_name"
        # Guardar metadatos
        echo "$response" | jq . > "./$safe_folder_name/${formatted_sid}.json"
        echo "$response" | jq '{Titulo: .tit, Anio: .an, Duracion: .dura, Sinopsis: .sino, Genero: .gens}' > "./$safe_folder_name/${formatted_sid}.txt"

        # Conseguir el poster
        echo -e "${green}Descargando Cartel...${reset}"
        poster=$(echo "$response" | jq -r '.afis[0] // empty')
        if [ -n "$poster" ]; then
            poster_url="https://img.cine.ar/image/${poster}/context/odeon_afiche_prod"
            curl -s -o "./$safe_folder_name/${formatted_sid}.jpg" "$poster_url"
        fi

        # OBTENER VIDEO
        source_id="INCAA"
        url="${player_url}?s=${source_id}&i=${sid}&p=${perfil}&t=${token}"
        
        # Generating the digest (X-Auth-Key)
        clave="${source_id}${sid}${perfil}${token}ARSAT"
        digest=$(echo -n "$clave" | md5sum | cut -d ' ' -f1)
        digest_clave=$(echo -n "$digest" | xxd -r -p | base64)
        
        video_resp=$(curl -s -H "Authorization: Bearer ${token}" -H "X-Auth-Key: ${digest_clave}" "${url}")
        video=$(echo "$video_resp" | jq -r '.url // empty')

        if [ -z "$video" ] || [ "$video" = "null" ]; then
            echo "Error: No se pudo obtener la URL del video para el SID $sid"
            echo "Respuesta: $video_resp"
            return 1
        fi

        echo -e "${green}Descargando Video: $titulo ($anio)${reset}"
        hlsdl -f -b "$video" -o "./$safe_folder_name/${formatted_sid} - ${titulo} (${anio}).ts"
    
    elif [ "$tipo_text" = "Series" ]; then
        # ... logic for series ...
        mkdir -p "./$safe_folder_name/$formatted_sid"
        echo "$response" | jq . > "./$safe_folder_name/$formatted_sid/${formatted_sid}.json"
        
        items=$(echo "$response" | jq '.items // []')
        length=$(echo "$items" | jq 'length')

        for (( i=0; i<length; i++ ))
        do
            episode_title=$(echo "$items" | jq -r ".[$i].tit")
            season_number=$(echo "$items" | jq -r ".[$i].tempo")
            episode_number=$(echo "$items" | jq -r ".[$i].capi")
            episode_sid=$(echo "$items" | jq -r ".[$i].sid")
            formatted_season=$(printf "%02d" $season_number)
            formatted_episode=$(printf "%02d" $episode_number)

            echo -e "${green}Descargando Episodio: S${formatted_season}E${formatted_episode} - $episode_title${reset}"

            # OBTENER VIDEO EPISODIO
            source_id="INCAA"
            url="${player_url}?s=${source_id}&i=${episode_sid}&p=${perfil}&t=${token}"
            clave="${source_id}${episode_sid}${perfil}${token}ARSAT"
            digest=$(echo -n "$clave" | md5sum | cut -d ' ' -f1)
            digest_clave=$(echo -n "$digest" | xxd -r -p | base64)
            
            video=$(curl -s -H "Authorization: Bearer ${token}" -H "X-Auth-Key: ${digest_clave}" "${url}" | jq -r '.url // empty')
            
            if [ -n "$video" ] && [ "$video" != "null" ]; then
                hlsdl -f -b "$video" -o "./$safe_folder_name/${formatted_sid}/${formatted_sid} - ${titulo} S${formatted_season}E${formatted_episode}.ts"
            fi
        done
    fi
}

# Arranca la fiesta
login
get_user_pid

read -p "SID inicial: " start_number
read -p "SID final: " end_number
read -p "Ingresar el maximo de peliculas para descargar al mismo tiempo: " concurrent_limit

current_jobs=0

for ((sid = start_number; sid <= end_number; sid++)); do
echo -e "Comenzando la descarga de SID:${sid}"
get_production_info "$sid"  &  # Send the job to the background

    ((current_jobs++))
    if ((current_jobs >= concurrent_limit)); then
        wait -n  # Wait for at least one job to finish before continuing
        ((current_jobs--))
    fi
done
wait  # Wait for all background jobs to finish
echo "terminado"
