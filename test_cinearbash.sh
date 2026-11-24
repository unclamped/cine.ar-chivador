#!/usr/bin/env bash
TOKEN="${CINEAR_TOKEN:?set CINEAR_TOKEN}"
PERFIL="${CINEAR_PERFIL:?set CINEAR_PERFIL}"
SID="8327"
SOURCE="INCAA"
URL="https://player.cine.ar/odeon/?s=${SOURCE}&i=${SID}&p=${PERFIL}&t=${TOKEN}"
CLAVE="${SOURCE}${SID}${PERFIL}${TOKEN}ARSAT"
DIGEST=$(echo -n "$CLAVE" | md5sum | cut -d ' ' -f1)
DIGEST_CLAVE=$(echo -n "$DIGEST" | xxd -r -p | base64)

echo "URL: $URL"
echo "Digest Clave: $DIGEST_CLAVE"

curl -s -H "Authorization: Bearer ${TOKEN}" -H "X-Auth-Key: ${DIGEST_CLAVE}" "${URL}" | jq .
