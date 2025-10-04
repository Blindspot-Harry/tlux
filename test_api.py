import requests

# Endpoint correto
url = "https://bulk.iremove.tools/api/dhru/api/index.php"

# Dados de teste
data = {
    "imei": "123456789012345",  # substitua pelo IMEI que quer testar
    "api_key": "I8QMHj1cZIqWWrdZ8tZDX2f2vnGDxttSpC0vHKbdxnbGs9nSlUOLESysHLyE"
}

try:
    response = requests.post(url, json=data)
    print("Status:", response.status_code)

    # Tenta decodificar JSON
    try:
        json_data = response.json()
        # Checa se retornou erro ou sucesso
        if 'ERROR' in json_data:
            print("Erro da API:", json_data['ERROR'][0]['MESSAGE'])
        elif 'SUCCESS' in json_data:
            print("Sucesso:", json_data['SUCCESS'][0]['MESSAGE'])
        else:
            print("Resposta inesperada:", json_data)
    except ValueError:
        # Se não for JSON, mostra texto
        print("Resposta (não JSON):", response.text)

except requests.exceptions.RequestException as e:
    print("Erro na requisição:", e)
