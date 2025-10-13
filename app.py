# app.py — T-Lux (Stripe integrado + iRemoval)
import os
import sqlite3
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from flask_babel import Babel, gettext as _
import smtplib
from email.message import EmailMessage
import bcrypt
from dotenv import load_dotenv
import stripe
from functools import wraps
import requests

# =======================================
# T-LUX Flask App — inicialização principal (única)
# =======================================
app = Flask(__name__)
app.secret_key = os.getenv("APP_SECRET", "chave-super-secreta")

# ⚠️ DEV ONLY: empurra um contexto global para evitar o erro enquanto limpamos o arquivo
app.app_context().push()

# Configuração de idiomas (Babel)
app.config["BABEL_DEFAULT_LOCALE"] = "en"
app.config["BABEL_DEFAULT_TIMEZONE"] = "UTC"
app.config["LANGUAGES"] = {"en": "English", "pt": "Português"}
babel = Babel(app)

# -----------------------
# Carrega variáveis do .env
# -----------------------
load_dotenv()

# -----------------------
# Configurações do Sistema T-Lux
# -----------------------
APP_SECRET = os.getenv("APP_SECRET", secrets.token_hex(16))
BASE_DIR = os.path.dirname(__file__)
# caminho do DB padrão (usa T-LUX.db / t-lux.db conforme preferir)
DB_FILE = os.getenv("DB_FILE", os.path.join(BASE_DIR, "t-lux.db"))

# -----------------------
# Stripe — agora usando .env
# -----------------------
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY
    print("✅ Stripe carregado com sucesso!")
else:
    print("⚠️ Stripe não configurado (STRIPE_SECRET_KEY ausente).")

# -----------------------
# Mapeamento de modelos para SERVICEID reais
# -----------------------
def obter_service_id(modelo: str) -> int | None:
    mapping = {
        "iPhone 5S": 1,
        "iPhone 6/6+": 2,
        "iPhone SE/6S/6S+": 3,
        "iPhone 7/7+": 4,
        "iPhone 8/8+": 5,
        "iPhone X": 6,
        "iPhone XR": 74,
        "iPhone XS": 74,
        "iPhone XS Max": 74,
        "iPhone 11": 75,
        "iPhone 11 Pro": 76,
        "iPhone 11 Pro Max": 77,
        "iPhone 12 Mini": 78,
        "iPhone 12": 79,
        "iPhone 12 Pro": 80,
        "iPhone 12 Pro Max": 81,
        "iPhone 13 Mini": 82,
        "iPhone 13": 83,
        "iPhone 13 Pro": 84,
        "iPhone 13 Pro Max": 85,
        "iPhone SE (2ND GEN)": 99,
        "iPhone SE (3RD GEN)": 100,
        "iPhone 14": 101,
        "iPhone 14 Plus": 102,
        "iPhone 14 Pro": 103,
        "iPhone 14 Pro Max": 104,
        "iPhone 15": 105,
        "iPhone 15 Plus": 106,
        "iPhone 15 Pro": 107,
        "iPhone 15 Pro Max": 108,
        "iPhone 16": 230,
        "iPhone 16 Plus": 231,
        "iPhone 16 Pro": 229,
        "iPhone 16 Pro Max": 228,
        "iPhone 16e": 232,
    }
    return mapping.get(modelo)


# -----------------------
# Funções principais de integração
# -----------------------
def criar_ordem(service_id: int, imei: str):
    """
    Cria uma ordem real na API iRemoval.
    Retorna dict com status, order_id e resposta completa.
    """
    payload = {
        "username": USERNAME,
        "apiaccesskey": API_KEY,
        "action": "placeimeiorder",
        "service": service_id,
        "imei": imei
    }

    try:
        resp = requests.post(API_URL, data=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if "SUCCESS" in data:
            order_id = data["SUCCESS"][0].get("ORDERID")
            return {
                "status": "success",
                "order_id": order_id,
                "raw": data
            }
        else:
            return {
                "status": "error",
                "raw": data
            }

    except Exception as e:
        return {"status": "error", "message": str(e)}


def consultar_ordem(order_id: int):
    """
    Consulta o status de uma ordem existente na API iRemoval.
    Retorna a resposta crua da API.
    """
    payload = {
        "username": USERNAME,
        "apiaccesskey": API_KEY,
        "action": "getimeiorder",
        "orderid": order_id
    }

    try:
        resp = requests.post(API_URL, data=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


def processar_pedido(modelo: str, imei: str):
    """
    Integração direta no coração do T-Lux:
    - Pega o service_id pelo modelo
    - Cria ordem na API
    - Retorna resultado
    """
    service_id = obter_service_id(modelo)
    if not service_id:
        return {"status": "error", "message": "Modelo não encontrado no mapeamento."}

    resultado = criar_ordem(service_id, imei)
    if resultado["status"] == "success":
        order_id = resultado["order_id"]
        print(f"✅ Ordem criada com sucesso! ORDERID={order_id}")
        return {"status": "success", "order_id": order_id}
    else:
        print("❌ Erro ao criar ordem:", resultado)
        return resultado

def atualizar_servicos():
    payload = {
        "username": USERNAME,
        "apiaccesskey": API_KEY,
        "action": "services"
    }
    try:
        resp = requests.post(API_URL, data=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        conn = get_db()
        c = conn.cursor()

        for grupo in data.get("SERVICES", []):
            group_name = grupo.get("GROUPNAME", "Outros")
            for servico in grupo.get("SERVICES", []):
                c.execute("""
                    INSERT OR REPLACE INTO services (id, nome, credit, group_name)
                    VALUES (?, ?, ?, ?)
                """, (servico["ID"], servico["NAME"], servico["CREDIT"], group_name))

        conn.commit()
        # conn.close() — fechado pelo teardown
        return True
    except Exception as e:
        print("Erro ao atualizar serviços:", e)
        return False

def consultar_status(order_ref):
    payload = {
        "username": "T-Lux",
        "apiaccesskey": API_KEY,
        "action": "order",
        "id": order_ref
    }
    try:
        resp = requests.post(API_URL, data=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}

# -----------------------
# Decorator: login_required
# -----------------------
from functools import wraps
from flask import session, redirect, url_for, flash

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Você precisa estar logado para acessar esta página.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function
# -----------------------
# Decorator for admin-only routes
# -----------------------
from functools import wraps
from flask import session, redirect, url_for, flash

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is logged in
        if not session.get("user_id"):
            flash("⚠️ You need to log in first.", "warning")
            return redirect(url_for("login"))

        # Check if user is admin
        if not session.get("is_admin"):
            flash("⛔ Access restricted to administrators only.", "danger")
            return redirect(url_for("dashboard"))

        return f(*args, **kwargs)
    return decorated_function

# -----------------------
# Funções auxiliares iRemoval
# -----------------------
import requests
import sqlite3
from datetime import datetime

from datetime import datetime, timezone

from datetime import datetime, timedelta, timezone
UTC = timezone.utc

def _now_iso() -> str:
    """Retorna timestamp ISO com fuso UTC."""
    return datetime.now(UTC).isoformat()

def init_db():
    """Garante que a tabela transactions tenha todas as colunas necessárias."""
    conn = get_db()
    c = conn.cursor()

    c.execute("PRAGMA table_info(transactions)")
    colunas = [info[1] for info in c.fetchall()]

    def add_coluna(nome, tipo):
        if nome not in colunas:
            c.execute(f"ALTER TABLE transactions ADD COLUMN {nome} {tipo}")
            print(f"✅ Coluna '{nome}' adicionada à tabela transactions.")

    add_coluna("imei", "TEXT")
    add_coluna("order_id", "TEXT")
    add_coluna("preco_fornecedor", "REAL DEFAULT 0.0")
    add_coluna("lucro", "REAL DEFAULT 0.0")
    add_coluna("processed", "INTEGER DEFAULT 0")

    conn.commit()
    # conn.close() — fechado pelo teardown


def validar_transacao(tx_id: int) -> bool:
    """Verifica se a transação existe, está paga e ainda não foi processada."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT status, processed FROM transactions WHERE id=?", (tx_id,))
    tx = c.fetchone()
    # conn.close() — fechado pelo teardown
    if not tx:
        return False
    status, processed = tx
    return status == "paid" and processed == 0


def obter_dados_imei(tx_id: int):
    """Busca o IMEI e o modelo do iPhone associado à transação."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT imei, modelo FROM transactions WHERE id=?", (tx_id,))
    row = c.fetchone()
    # conn.close() — fechado pelo teardown
    if row:
        return row["imei"], row["modelo"]
    return None


def registrar_log_desbloqueio(tx_id, user_email, imei, modelo, status):
    """Registra logs de desbloqueio vinculados a uma transação."""
    conn = get_db()
    c = conn.cursor()
    data_hora = datetime.now(timezone.utc).isoformat()
    c.execute("""
        INSERT INTO logs_desbloqueio (tx_id, user_email, imei, modelo, status, data_hora)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (tx_id, user_email, imei, modelo, status, data_hora))
    conn.commit()
    # conn.close() — fechado pelo teardown

# -----------------------
# Funções de comunicação com iRemoval
# -----------------------
def enviar_para_iremoval(imei, modelo):
    """
    Envia a ordem de desbloqueio para a API iRemoval/DHRU.
    Retorna o JSON da API ou {"error": "..."} em caso de falha.
    """
    service_id = obter_service_id(modelo)  # mapeia modelo -> service_id real no iRemoval
    if not service_id:
        return {"error": f"Service ID não encontrado para modelo {modelo}"}

# -----------------------
# Função para criar ordem real via API iRemoval
# -----------------------
def criar_ordem(service_id, imei):
    payload_order = {
        "apiaccesskey": API_KEY,  # tua chave da API
        "action": "placeimeiorder",
        "service": service_id,
        "imei": imei
    }

    try:
        resp = requests.post(API_URL, data=payload_order, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if "SUCCESS" in data:
            order_id = data["SUCCESS"][0].get("ORDERID")
            return {"status": "success", "order_id": order_id}
        else:
            return {"status": "error", "message": data}

    except Exception as e:
        return {"status": "error", "message": str(e)}

def consultar_status(order_id: str) -> dict:
    """
    Consulta o status de uma ordem no iRemoval (Bulk API).
    Retorna dict com resultado ou {"error": "..."} em caso de falha.
    """
    payload = {
        "key": DHRU_API_KEY,
        "action": "order_status",
        "order_id": order_id
    }

    try:
        response = requests.post(DHRU_API_URL, data=payload, timeout=30)
        response.raise_for_status()
        result = response.json()

        if "ERROR" in result:
            return {"error": result["ERROR"][0]}
        return result

    except Exception as e:
        return {"error": f"Erro ao consultar status: {str(e)}"}

def consultar_status_unlock(tx_id):
    """
    Consulta o status real do desbloqueio no iRemoval usando o order_id salvo em transactions.
    Retorna dicionário: {'status': 'success/failed/pending', 'message': ...}
    """
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT order_id FROM transactions WHERE id=?", (tx_id,))
    row = c.fetchone()
    # conn.close() — fechado pelo teardown

    if not row or not row["order_id"]:
        return {"status": "pending", "message": "Order ID não encontrado"}

    order_id = row["order_id"]
    result = consultar_status(order_id)

    if "error" in result:
        return {"status": "failed", "message": result["error"]}
    else:
        api_status = result.get("status", "pending").lower()
        return {
            "status": api_status,
            "message": result.get("message", "")
        }


# -----------------------
# Função integrada de processamento automático
# -----------------------

def processar_desbloqueio(modelo, imei, metodo_pagamento, email):
    """
    Processa o pedido de desbloqueio real via API iRemoval.
    - Pega o service_id correto
    - Cria ordem na API
    - Registra transação no banco com order_id
    """
    conn = get_db()
    cursor = conn.cursor()

    # procurar o ID do serviço para o modelo
    service_id = obter_service_id(modelo)
    if not service_id:
        # conn.close() — fechado pelo teardown
        return {"status": "error", "message": f"Modelo {modelo} não encontrado no mapeamento."}

    # criar ordem real na API
    resultado = criar_ordem(service_id, imei)

    if resultado["status"] == "success":
        order_id = resultado["order_id"]

        # salvar transação no banco com order_id
        cursor.execute("""
            INSERT INTO transactions (modelo, imei, metodo_pagamento, email, order_id, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (modelo, imei, metodo_pagamento, email, order_id, "Pendente"))
        conn.commit()
        # conn.close() — fechado pelo teardown

        return {"status": "success", "order_id": order_id}

    else:
        # conn.close() — fechado pelo teardown
        return {"status": "error", "message": resultado}

#------------------------
#Maddleware protecao
#------------------------
@app.before_request
def verificar_email_global():
    """
    Middleware: antes de cada requisição, verifica se o usuário está logado
    e se o e-mail foi verificado.
    Exceções: login, registro, verificação de e-mail e páginas públicas.
    """
    rotas_publicas = {
        "login", "register", "logout",
        "verify_email_route", "resend_verification",
        "check_email", "static"
    }

    if "user_id" in session:
        # Se usuário existe mas ainda não confirmou o e-mail
        if not session.get("email_verified", False):
            # Pega rota atual
            rota_atual = request.endpoint

            # Se tentar acessar rota protegida → redireciona
            if rota_atual not in rotas_publicas:
                flash("⚠️ Você precisa verificar seu e-mail para continuar.", "warning")
                return redirect(url_for("check_email"))

# ------------------------------
# Página pública (Landing Page)
# ------------------------------
@app.route("/")
def home():
    # Se o usuário já estiver logado, envia direto para o painel
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_template("home.html")
    
from datetime import datetime, UTC

# ======================================
# 🌍 SUPORTE MULTILÍNGUE (Flask-Babel 3.x)
# ======================================
from flask_babel import Babel
from flask import request, session

# -----------------------
# 🌍 Babel Configuration
# -----------------------
app.config["BABEL_DEFAULT_LOCALE"] = "en"
app.config["BABEL_DEFAULT_TIMEZONE"] = "UTC"
app.config["LANGUAGES"] = ["en", "pt"]

# ======================================
# 🌍 SUPORTE MULTILÍNGUE — Flask-Babel (corrigido)
# ======================================
from flask import request, session, redirect, url_for
from flask_babel import Babel

# -----------------------
# Configuração do Babel
# -----------------------
app.config["BABEL_DEFAULT_LOCALE"] = "en"
app.config["BABEL_DEFAULT_TIMEZONE"] = "UTC"
app.config["LANGUAGES"] = {
    "en": "English",
    "pt": "Português"
}

# -----------------------
# Selecionador de idioma
# -----------------------
from flask import request, session, redirect, url_for
from flask_babel import Babel

def get_locale():
    """
    Determina o idioma ativo da sessão.
    Prioridade:
      1️⃣ Idioma manual definido pelo usuário (/set_language/<lang>)
      2️⃣ Idioma do navegador (Accept-Language)
      3️⃣ Idioma padrão ('en')
    """
    # 1️⃣ Preferência manual na sessão
    lang = session.get("lang")
    if lang in app.config["LANGUAGES"]:
        return lang

    # 2️⃣ Idioma aceito pelo navegador
    best_match = request.accept_languages.best_match(app.config["LANGUAGES"])
    if best_match:
        return best_match

    # 3️⃣ Padrão
    return app.config["BABEL_DEFAULT_LOCALE"]
# Disponibiliza a função no Jinja (para usar em templates)
app.jinja_env.globals["get_locale"] = get_locale

# (Re)inicializa o Babel usando o seletor de locale
babel = Babel(app, locale_selector=get_locale)   # substitui a versão antiga "Babel(app)"

# -----------------------
# Rota para mudar idioma
# -----------------------
@app.route("/set_language/<lang>")
def set_language(lang):
    """Altera o idioma da sessão e redireciona de volta."""
    if lang in app.config["LANGUAGES"]:
        session["lang"] = lang
        print(f"🌍 Idioma alterado para: {lang}")
    return redirect(request.referrer or url_for("home"))

LANGUAGES={
 "pt":"Portugues",
 "en":"Engles"
 }
# -----------------------
# Países (195) -> name + currency code
# Note: lista completa incluída. Currency is ISO code (e.g., MZN, USD, BRL)
# -----------------------
COUNTRIES = {
    "AF": {"name": "Afghanistan", "currency": "AFN"},
    "AL": {"name": "Albania", "currency": "ALL"},
    "DZ": {"name": "Algeria", "currency": "DZD"},
    "AS": {"name": "American Samoa", "currency": "USD"},
    "AD": {"name": "Andorra", "currency": "EUR"},
    "AO": {"name": "Angola", "currency": "AOA"},
    "AI": {"name": "Anguilla", "currency": "XCD"},
    "AQ": {"name": "Antarctica", "currency": "USD"},
    "AG": {"name": "Antigua and Barbuda", "currency": "XCD"},
    "AR": {"name": "Argentina", "currency": "ARS"},
    "AM": {"name": "Armenia", "currency": "AMD"},
    "AW": {"name": "Aruba", "currency": "AWG"},
    "AU": {"name": "Australia", "currency": "AUD"},
    "AT": {"name": "Austria", "currency": "EUR"},
    "AZ": {"name": "Azerbaijan", "currency": "AZN"},
    "BS": {"name": "Bahamas", "currency": "BSD"},
    "BH": {"name": "Bahrain", "currency": "BHD"},
    "BD": {"name": "Bangladesh", "currency": "BDT"},
    "BB": {"name": "Barbados", "currency": "BBD"},
    "BY": {"name": "Belarus", "currency": "BYN"},
    "BE": {"name": "Belgium", "currency": "EUR"},
    "BZ": {"name": "Belize", "currency": "BZD"},
    "BJ": {"name": "Benin", "currency": "XOF"},
    "BM": {"name": "Bermuda", "currency": "BMD"},
    "BT": {"name": "Bhutan", "currency": "BTN"},
    "BO": {"name": "Bolivia", "currency": "BOB"},
    "BQ": {"name": "Bonaire, Sint Eustatius and Saba", "currency": "USD"},
    "BA": {"name": "Bosnia and Herzegovina", "currency": "BAM"},
    "BW": {"name": "Botswana", "currency": "BWP"},
    "BV": {"name": "Bouvet Island", "currency": "NOK"},
    "BR": {"name": "Brasil", "currency": "BRL"},
    "IO": {"name": "British Indian Ocean Territory", "currency": "USD"},
    "BN": {"name": "Brunei Darussalam", "currency": "BND"},
    "BG": {"name": "Bulgaria", "currency": "BGN"},
    "BF": {"name": "Burkina Faso", "currency": "XOF"},
    "BI": {"name": "Burundi", "currency": "BIF"},
    "CV": {"name": "Cabo Verde", "currency": "CVE"},
    "KH": {"name": "Cambodia", "currency": "KHR"},
    "CM": {"name": "Cameroon", "currency": "XAF"},
    "CA": {"name": "Canada", "currency": "CAD"},
    "KY": {"name": "Cayman Islands", "currency": "KYD"},
    "CF": {"name": "Central African Republic", "currency": "XAF"},
    "TD": {"name": "Chad", "currency": "XAF"},
    "CL": {"name": "Chile", "currency": "CLP"},
    "CN": {"name": "China", "currency": "CNY"},
    "CX": {"name": "Christmas Island", "currency": "AUD"},
    "CC": {"name": "Cocos (Keeling) Islands", "currency": "AUD"},
    "CO": {"name": "Colombia", "currency": "COP"},
    "KM": {"name": "Comoros", "currency": "KMF"},
    "CG": {"name": "Congo - Brazzaville", "currency": "XAF"},
    "CD": {"name": "Congo - Kinshasa", "currency": "CDF"},
    "CK": {"name": "Cook Islands", "currency": "NZD"},
    "CR": {"name": "Costa Rica", "currency": "CRC"},
    "CI": {"name": "Côte d’Ivoire", "currency": "XOF"},
    "HR": {"name": "Croatia", "currency": "HRK"},
    "CU": {"name": "Cuba", "currency": "CUP"},
    "CW": {"name": "Curaçao", "currency": "ANG"},
    "CY": {"name": "Cyprus", "currency": "EUR"},
    "CZ": {"name": "Czechia", "currency": "CZK"},
    "DK": {"name": "Denmark", "currency": "DKK"},
    "DJ": {"name": "Djibouti", "currency": "DJF"},
    "DM": {"name": "Dominica", "currency": "XCD"},
    "DO": {"name": "Dominican Republic", "currency": "DOP"},
    "EC": {"name": "Ecuador", "currency": "USD"},
    "EG": {"name": "Egypt", "currency": "EGP"},
    "SV": {"name": "El Salvador", "currency": "USD"},
    "GQ": {"name": "Equatorial Guinea", "currency": "XAF"},
    "ER": {"name": "Eritrea", "currency": "ERN"},
    "EE": {"name": "Estonia", "currency": "EUR"},
    "SZ": {"name": "Eswatini", "currency": "SZL"},
    "ET": {"name": "Ethiopia", "currency": "ETB"},
    "FK": {"name": "Falkland Islands", "currency": "FKP"},
    "FO": {"name": "Faroe Islands", "currency": "DKK"},
    "FJ": {"name": "Fiji", "currency": "FJD"},
    "FI": {"name": "Finland", "currency": "EUR"},
    "FR": {"name": "France", "currency": "EUR"},
    "GF": {"name": "French Guiana", "currency": "EUR"},
    "PF": {"name": "French Polynesia", "currency": "XPF"},
    "TF": {"name": "French Southern Territories", "currency": "EUR"},
    "GA": {"name": "Gabon", "currency": "XAF"},
    "GM": {"name": "Gambia", "currency": "GMD"},
    "GE": {"name": "Georgia", "currency": "GEL"},
    "DE": {"name": "Germany", "currency": "EUR"},
    "GH": {"name": "Ghana", "currency": "GHS"},
    "GI": {"name": "Gibraltar", "currency": "GIP"},
    "GR": {"name": "Greece", "currency": "EUR"},
    "GL": {"name": "Greenland", "currency": "DKK"},
    "GD": {"name": "Grenada", "currency": "XCD"},
    "GP": {"name": "Guadeloupe", "currency": "EUR"},
    "GU": {"name": "Guam", "currency": "USD"},
    "GT": {"name": "Guatemala", "currency": "GTQ"},
    "GG": {"name": "Guernsey", "currency": "GBP"},
    "GN": {"name": "Guinea", "currency": "GNF"},
    "GW": {"name": "Guinea-Bissau", "currency": "XOF"},
    "GY": {"name": "Guyana", "currency": "GYD"},
    "HT": {"name": "Haiti", "currency": "HTG"},
    "HM": {"name": "Heard Island and McDonald Islands", "currency": "AUD"},
    "VA": {"name": "Holy See", "currency": "EUR"},
    "HN": {"name": "Honduras", "currency": "HNL"},
    "HK": {"name": "Hong Kong SAR China", "currency": "HKD"},
    "HU": {"name": "Hungary", "currency": "HUF"},
    "IS": {"name": "Iceland", "currency": "ISK"},
    "IN": {"name": "India", "currency": "INR"},
    "ID": {"name": "Indonesia", "currency": "IDR"},
    "IR": {"name": "Iran", "currency": "IRR"},
    "IQ": {"name": "Iraq", "currency": "IQD"},
    "IE": {"name": "Ireland", "currency": "EUR"},
    "IM": {"name": "Isle of Man", "currency": "GBP"},
    "IL": {"name": "Israel", "currency": "ILS"},
    "IT": {"name": "Italy", "currency": "EUR"},
    "JM": {"name": "Jamaica", "currency": "JMD"},
    "JP": {"name": "Japan", "currency": "JPY"},
    "JE": {"name": "Jersey", "currency": "GBP"},
    "JO": {"name": "Jordan", "currency": "JOD"},
    "KZ": {"name": "Kazakhstan", "currency": "KZT"},
    "KE": {"name": "Kenya", "currency": "KES"},
    "KI": {"name": "Kiribati", "currency": "AUD"},
    "KP": {"name": "Korea (North)", "currency": "KPW"},
    "KR": {"name": "Korea (South)", "currency": "KRW"},
    "KW": {"name": "Kuwait", "currency": "KWD"},
    "KG": {"name": "Kyrgyzstan", "currency": "KGS"},
    "LA": {"name": "Laos", "currency": "LAK"},
    "LV": {"name": "Latvia", "currency": "EUR"},
    "LB": {"name": "Lebanon", "currency": "LBP"},
    "LS": {"name": "Lesotho", "currency": "LSL"},
    "LR": {"name": "Liberia", "currency": "LRD"},
    "LY": {"name": "Libya", "currency": "LYD"},
    "LI": {"name": "Liechtenstein", "currency": "CHF"},
    "LT": {"name": "Lithuania", "currency": "EUR"},
    "LU": {"name": "Luxembourg", "currency": "EUR"},
    "MO": {"name": "Macao SAR China", "currency": "MOP"},
    "MG": {"name": "Madagascar", "currency": "MGA"},
    "MW": {"name": "Malawi", "currency": "MWK"},
    "MY": {"name": "Malaysia", "currency": "MYR"},
    "MV": {"name": "Maldives", "currency": "MVR"},
    "ML": {"name": "Mali", "currency": "XOF"},
    "MT": {"name": "Malta", "currency": "EUR"},
    "MH": {"name": "Marshall Islands", "currency": "USD"},
    "MQ": {"name": "Martinique", "currency": "EUR"},
    "MR": {"name": "Mauritania", "currency": "MRU"},
    "MU": {"name": "Mauritius", "currency": "MUR"},
    "YT": {"name": "Mayotte", "currency": "EUR"},
    "MX": {"name": "Mexico", "currency": "MXN"},
    "FM": {"name": "Micronesia", "currency": "USD"},
    "MD": {"name": "Moldova", "currency": "MDL"},
    "MC": {"name": "Monaco", "currency": "EUR"},
    "MN": {"name": "Mongolia", "currency": "MNT"},
    "ME": {"name": "Montenegro", "currency": "EUR"},
    "MS": {"name": "Montserrat", "currency": "XCD"},
    "MA": {"name": "Morocco", "currency": "MAD"},
    "MZ": {"name": "Moçambique", "currency": "MZN"},
    "MM": {"name": "Myanmar (Burma)", "currency": "MMK"},
    "NA": {"name": "Namibia", "currency": "NAD"},
    "NR": {"name": "Nauru", "currency": "AUD"},
    "NP": {"name": "Nepal", "currency": "NPR"},
    "NL": {"name": "Netherlands", "currency": "EUR"},
    "NC": {"name": "New Caledonia", "currency": "XPF"},
    "NZ": {"name": "New Zealand", "currency": "NZD"},
    "NI": {"name": "Nicaragua", "currency": "NIO"},
    "NE": {"name": "Niger", "currency": "XOF"},
    "NG": {"name": "Nigeria", "currency": "NGN"},
    "NU": {"name": "Niue", "currency": "NZD"},
    "NF": {"name": "Norfolk Island", "currency": "AUD"},
    "MP": {"name": "Northern Mariana Islands", "currency": "USD"},
    "NO": {"name": "Norway", "currency": "NOK"},
    "OM": {"name": "Oman", "currency": "OMR"},
    "PK": {"name": "Pakistan", "currency": "PKR"},
    "PW": {"name": "Palau", "currency": "USD"},
    "PS": {"name": "Palestinian Territories", "currency": "ILS"},
    "PA": {"name": "Panama", "currency": "PAB"},
    "PG": {"name": "Papua New Guinea", "currency": "PGK"},
    "PY": {"name": "Paraguay", "currency": "PYG"},
    "PE": {"name": "Peru", "currency": "PEN"},
    "PH": {"name": "Philippines", "currency": "PHP"},
    "PN": {"name": "Pitcairn Islands", "currency": "NZD"},
    "PL": {"name": "Poland", "currency": "PLN"},
    "PT": {"name": "Portugal", "currency": "EUR"},
    "PR": {"name": "Puerto Rico", "currency": "USD"},
    "QA": {"name": "Qatar", "currency": "QAR"},
    "MK": {"name": "North Macedonia", "currency": "MKD"},
    "RO": {"name": "Romania", "currency": "RON"},
    "RU": {"name": "Russia", "currency": "RUB"},
    "RW": {"name": "Rwanda", "currency": "RWF"},
    "RE": {"name": "Réunion", "currency": "EUR"},
    "BL": {"name": "Saint Barthélemy", "currency": "EUR"},
    "SH": {"name": "Saint Helena", "currency": "SHP"},
    "KN": {"name": "Saint Kitts and Nevis", "currency": "XCD"},
    "LC": {"name": "Saint Lucia", "currency": "XCD"},
    "MF": {"name": "Saint Martin", "currency": "EUR"},
    "PM": {"name": "Saint Pierre and Miquelon", "currency": "EUR"},
    "VC": {"name": "Saint Vincent and the Grenadines", "currency": "XCD"},
    "WS": {"name": "Samoa", "currency": "WST"},
    "SM": {"name": "San Marino", "currency": "EUR"},
    "ST": {"name": "Sao Tome and Principe", "currency": "STN"},
    "SA": {"name": "Saudi Arabia", "currency": "SAR"},
    "SN": {"name": "Senegal", "currency": "XOF"},
    "RS": {"name": "Serbia", "currency": "RSD"},
    "SC": {"name": "Seychelles", "currency": "SCR"},
    "SL": {"name": "Sierra Leone", "currency": "SLL"},
    "SG": {"name": "Singapore", "currency": "SGD"},
    "SX": {"name": "Sint Maarten", "currency": "ANG"},
    "SK": {"name": "Slovakia", "currency": "EUR"},
    "SI": {"name": "Slovenia", "currency": "EUR"},
    "SB": {"name": "Solomon Islands", "currency": "SBD"},
    "SO": {"name": "Somalia", "currency": "SOS"},
    "ZA": {"name": "South Africa", "currency": "ZAR"},
    "GS": {"name": "South Georgia & South Sandwich Islands", "currency": "GBP"},
    "SS": {"name": "South Sudan", "currency": "SSP"},
    "ES": {"name": "Spain", "currency": "EUR"},
    "LK": {"name": "Sri Lanka", "currency": "LKR"},
    "SD": {"name": "Sudan", "currency": "SDG"},
    "SR": {"name": "Suriname", "currency": "SRD"},
    "SJ": {"name": "Svalbard and Jan Mayen", "currency": "NOK"},
    "SE": {"name": "Sweden", "currency": "SEK"},
    "CH": {"name": "Switzerland", "currency": "CHF"},
    "SY": {"name": "Syria", "currency": "SYP"},
    "TW": {"name": "Taiwan", "currency": "TWD"},
    "TJ": {"name": "Tajikistan", "currency": "TJS"},
    "TZ": {"name": "Tanzania", "currency": "TZS"},
    "TH": {"name": "Thailand", "currency": "THB"},
    "TL": {"name": "Timor-Leste", "currency": "USD"},
    "TG": {"name": "Togo", "currency": "XOF"},
    "TK": {"name": "Tokelau", "currency": "NZD"},
    "TO": {"name": "Tonga", "currency": "TOP"},
    "TT": {"name": "Trinidad and Tobago", "currency": "TTD"},
    "TN": {"name": "Tunisia", "currency": "TND"},
    "TR": {"name": "Turkey", "currency": "TRY"},
    "TM": {"name": "Turkmenistan", "currency": "TMT"},
    "TC": {"name": "Turks and Caicos Islands", "currency": "USD"},
    "TV": {"name": "Tuvalu", "currency": "AUD"},
    "UG": {"name": "Uganda", "currency": "UGX"},
    "UA": {"name": "Ukraine", "currency": "UAH"},
    "AE": {"name": "United Arab Emirates", "currency": "AED"},
    "GB": {"name": "United Kingdom", "currency": "GBP"},
    "US": {"name": "United States", "currency": "USD"},
    "UM": {"name": "U.S. Minor Outlying Islands", "currency": "USD"},
    "UY": {"name": "Uruguay", "currency": "UYU"},
    "UZ": {"name": "Uzbekistan", "currency": "UZS"},
    "VU": {"name": "Vanuatu", "currency": "VUV"},
    "VE": {"name": "Venezuela", "currency": "VES"},
    "VN": {"name": "Vietnam", "currency": "VND"},
    "VG": {"name": "British Virgin Islands", "currency": "USD"},
    "VI": {"name": "U.S. Virgin Islands", "currency": "USD"},
    "WF": {"name": "Wallis and Futuna", "currency": "XPF"},
    "EH": {"name": "Western Sahara", "currency": "MAD"},
    "YE": {"name": "Yemen", "currency": "YER"},
    "ZM": {"name": "Zambia", "currency": "ZMW"},
    "ZW": {"name": "Zimbabwe", "currency": "ZWL"}
}

# -----------------------
# Exchange rates (placeholder)
# EXCHANGE_RATES[currency] = number of local units per 1 USD
# i.e. 1 USD = EXCHANGE_RATES['MZN'] MZN
# Use these to convert local_amount -> usd_amount: usd = local_amount / EXCHANGE_RATES[currency]
# -----------------------
EXCHANGE_RATES = {
    "USD": 1.0,
    "MZN": 63.0,
    "BRL": 5.3,
    "ZAR": 18.2,
    "EUR": 0.92,
    "GBP": 0.78,
    "CAD": 1.34,
    "AUD": 1.48,
    "NGN": 1190.0,
    "KES": 155.0,
    "GHS": 11.0,
    "TZS": 2320.0,
    "XOF": 610.0,
    "XAF": 610.0,
    "CNY": 7.1,
    "INR": 83.0,
    "JPY": 150.0,
    "EGP": 30.0,
    "RUB": 95.0,
    "MXN": 18.0,
}

# -----------------------
# Pacotes e modelos (preços fixos em USD)
# -----------------------
# -----------------------
# Planos / Pacotes de acesso (em USD)
# -----------------------
# -----------------------
# Planos / Pacotes de acesso (em USD)
# -----------------------

PACOTES = [
    {
        "nome": "Starter",
        "dias": 7,
        "preco_usd": 8.00,
        "descricao": "Ideal para novos usuários — acesso completo por 7 dias."
    },
    {
        "nome": "Bronze",
        "dias": 30,
        "preco_usd": 39.00,  # atualizado ✅
        "descricao": "Pacote mensal com desbloqueios ilimitados e suporte padrão."
    },
    {
        "nome": "Prata",
        "dias": 60,
        "preco_usd": 87.30,
        "descricao": "Plano de 2 meses — ideal para técnicos ativos."
    },
    {
        "nome": "Gold",
        "dias": 180,  # 6 meses
        "preco_usd": 190.47,
        "descricao": "Acesso profissional de 6 meses — prioridade no suporte."
    },
    {
        "nome": "Premium",
        "dias": 365,  # 1 ano
        "preco_usd": 400.00,
        "descricao": "Licença anual — desbloqueios ilimitados e suporte VIP."
    },
]

# -----------------------
# Preço de venda no T-Lux (com lucro ajustado, SEM SINAL)
# -----------------------
# Fornecedor (iRemoval) — SEM SINAL
PRECO_IREMOVAL_SEM_SINAL_USD = {
    "iPhone 11": 55.00, "iPhone 11 Pro": 60.00, "iPhone 11 Pro Max": 65.00,
    "iPhone 12": 60.00, "iPhone 12 Mini": 55.00, "iPhone 12 Pro": 65.00, "iPhone 12 Pro Max": 70.00,
    "iPhone 13": 70.00, "iPhone 13 Mini": 55.00, "iPhone 13 Pro": 75.00, "iPhone 13 Pro Max": 85.00,
    "iPhone 14": 80.00, "iPhone 14 Plus": 85.00, "iPhone 14 Pro": 90.00, "iPhone 14 Pro Max": 95.00,
    "iPhone 15": 85.00, "iPhone 15 Plus": 90.00, "iPhone 15 Pro": 105.00, "iPhone 15 Pro Max": 110.00,
    "iPhone SE (2ª Geração)": 55.00, "iPhone SE (3ª Geração)": 55.00,
    "iPhone XR": 50.00, "iPhone XS": 50.00, "iPhone XS Max": 50.00,
}

# -----------------------
# Tabelas de Preços T-Lux (ajustadas com margem)
# -----------------------

# iPhone com SINAL — serviços premium (Signal Bypass)
MODELOS_IPHONE_USD_SINAL = {
    "iPhone 6s": 31.75, "iPhone 6s Plus": 34.92,
    "iPhone 7": 39.68, "iPhone 7 Plus": 42.86,
    "iPhone 8": 47.62, "iPhone 8 Plus": 50.79,
    "iPhone SE (1st Gen)": 44.44, "iPhone SE (2nd Gen)": 47.62, "iPhone SE (3rd Gen)": 57.14,
    "iPhone X": 71.43, "iPhone Xr": 79.37, "iPhone Xs": 82.54, "iPhone Xs Max": 87.30,
    "iPhone 11": 95.24, "iPhone 11 Pro": 103.17, "iPhone 11 Pro Max": 107.94,
    "iPhone 12 Mini": 111.11, "iPhone 12": 119.05, "iPhone 12 Pro": 126.98, "iPhone 12 Pro Max": 134.92,
    "iPhone 13 Mini": 134.92, "iPhone 13": 142.86, "iPhone 13 Pro": 150.79, "iPhone 13 Pro Max": 158.73,
    "iPhone 14": 158.73, "iPhone 14 Plus": 166.67, "iPhone 14 Pro": 174.60, "iPhone 14 Pro Max": 182.54,
    "iPhone 15": 253.97, "iPhone 15 Plus": 261.90, "iPhone 15 Pro": 269.84, "iPhone 15 Pro Max": 277.78,
    "iPhone 16": 253.97, "iPhone 16 Plus": 269.84, "iPhone 16 Pro": 285.71, "iPhone 16 Pro Max": 317.46
}

# iPhone SEM SINAL — preços otimizados (No Signal Bypass)
MODELOS_IPHONE_SEM_SINAL_USD = {
    "iPhone 5S": 10.00,
    "iPhone 6": 12.50, "iPhone 6 Plus": 12.50,
    "iPhone 6s": 14.00, "iPhone 6s Plus": 14.00,
    "iPhone 7": 18.00, "iPhone 7 Plus": 18.00,
    "iPhone 8": 22.00, "iPhone 8 Plus": 24.00,
    "iPhone X": 28.00,
    "iPhone XR": 55.00, "iPhone XS": 60.00, "iPhone XS Max": 65.00,
    "iPhone 11": 66.00, "iPhone 11 Pro": 72.00, "iPhone 11 Pro Max": 78.00,
    "iPhone 12 Mini": 66.00, "iPhone 12": 72.00, "iPhone 12 Pro": 78.00, "iPhone 12 Pro Max": 84.00,
    "iPhone 13 Mini": 66.00, "iPhone 13": 90.00, "iPhone 13 Pro": 90.00, "iPhone 13 Pro Max": 108.00,
    "iPhone 14": 96.00, "iPhone 14 Plus": 102.00, "iPhone 14 Pro": 108.00, "iPhone 14 Pro Max": 114.00,
    "iPhone 15": 102.00, "iPhone 15 Plus": 108.00, "iPhone 15 Pro": 126.00, "iPhone 15 Pro Max": 132.00,
    "iPhone 16": 95.00, "iPhone 16 Plus": 100.00, "iPhone 16 Pro": 115.00, "iPhone 16 Pro Max": 120.00,
    "iPhone SE (2nd Gen)": 60.00, "iPhone SE (3rd Gen)": 60.00,
}

# Alias de compatibilidade
MODELOS_IPHONE_USD_NO_SIGNAL = MODELOS_IPHONE_SEM_SINAL_USD

# Combinação geral
MODELOS_IPHONE_USD = {**MODELOS_IPHONE_USD_SINAL, **MODELOS_IPHONE_SEM_SINAL_USD}

# Ordenar alfabeticamente
MODELOS_IPHONE_USD = dict(sorted(MODELOS_IPHONE_USD.items()))

# -----------------------
# Preços do fornecedor (iRemoval) em USD
# -----------------------
PRECO_IREMOVAL_USD = {
    "iPhone 6s": 19.99,
    "iPhone 6s Plus": 24.99,
    "iPhone 7": 24.99,
    "iPhone 7 Plus": 24.99,
    "iPhone 8": 34.99,
    "iPhone 8 Plus": 34.99,
    "iPhone SE (2nd gen)": 95.00,
    "iPhone SE (3rd gen)": 95.00,
    "iPhone X": 39.99,
    "iPhone Xr": 90.00,
    "iPhone Xs": 90.00,
    "iPhone Xs Max": 90.00,
    "iPhone 11": 95.00,
    "iPhone 11 Pro": 100.00,
    "iPhone 11 Pro Max": 105.00,
    "iPhone 12 Mini": 95.00,
    "iPhone 12": 100.00,
    "iPhone 12 Pro": 105.00,
    "iPhone 12 Pro Max": 110.00,
    "iPhone 13 Mini": 95.00,
    "iPhone 13": 110.00,
    "iPhone 13 Pro": 115.00,
    "iPhone 13 Pro Max": 125.00,
    "iPhone 14": 120.00,
    "iPhone 14 Plus": 125.00,
    "iPhone 14 Pro": 130.00,
    "iPhone 14 Pro Max": 135.00,
    "iPhone 15": 125.00,
    "iPhone 15 Plus": 130.00,
    "iPhone 15 Pro": 145.00,
    "iPhone 15 Pro Max": 150.00,
    "iPhone 16": 100.00,
    "iPhone 16 Plus": 105.00,
    "iPhone 16 Pro": 120.00,
    "iPhone 16 Pro Max": 125.00
}

# -----------------------
# Modelos Full Signal direto (A12+ e acima)
# -----------------------
MODELOS_FULL_SIGNAL = [
    "iPhone Xs", "iPhone Xs Max", "iPhone Xr",
    "iPhone 11", "iPhone 11 Pro", "iPhone 11 Pro Max",
    "iPhone 12", "iPhone 12 Mini", "iPhone 12 Pro", "iPhone 12 Pro Max",
    "iPhone 13", "iPhone 13 Mini", "iPhone 13 Pro", "iPhone 13 Pro Max",
    "iPhone 14", "iPhone 14 Plus", "iPhone 14 Pro", "iPhone 14 Pro Max",
    "iPhone 15", "iPhone 15 Plus", "iPhone 15 Pro", "iPhone 15 Pro Max",
    "iPhone 16", "iPhone 16 Plus", "iPhone 16 Pro", "iPhone 16 Pro Max"
]
#------------------------
# Rota desbloqueio Unlock
#------------------------
@app.route("/unlock", methods=["GET", "POST"])
@login_required
def unlock_page():
    """
    Solicita desbloqueio de iPhones via iRemoval/DHRU.
    Salva transação com custo e lucro, envia ordem, atualiza status e registra order_id.
    """
    user = current_user()

    if request.method == "POST":
        modelo = request.form.get("modelo")
        imei = request.form.get("imei")
        sem_sinal_flag = int(request.form.get("sem_sinal", "1"))  # 1 = SEM SINAL por padrão
        user_email = user["email"]

        # -----------------------
        # Verifica preços do modelo
        # -----------------------
        try:
            preco_venda, preco_fornecedor, lucro = get_preco(modelo, sem_sinal=bool(sem_sinal_flag))
        except KeyError:
            flash("Modelo não encontrado na tabela de preços.", "danger")
            return redirect(url_for("unlock_page"))

        # -----------------------
        # Grava transação inicial no banco
        # -----------------------
        tx_id = gravar_transacao_unlock(
            session["user_id"], modelo, imei, sem_sinal_flag,
            preco_venda, preco_fornecedor, lucro
        )

        # -----------------------
        # Cria ordem via API (iRemoval/DHRU)
        # -----------------------
        resultado = processar_desbloqueio(modelo, imei, "credit", user_email)

        if isinstance(resultado, dict) and resultado.get("status") == "success":
            status = "success"
            message = "Ordem enviada com sucesso! Verifique o painel para status."
            order_id = resultado.get("order_id")

            # Atualiza transação com order_id
            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE transactions SET order_id=?, updated_at=? WHERE id=?",
                      (order_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), tx_id))
            conn.commit()
            # conn.close() — fechado pelo teardown

            # Feedback
            flash(f"✅ {message}", "success")
            log("INFO", f"Desbloqueio {modelo} IMEI {imei} solicitado por {user_email}")

            # Email de confirmação (não obrigatório)
            try:
                send_email(
                    user_email,
                    "T-Lux - Desbloqueio solicitado",
                    f"Modelo: {modelo}\nIMEI: {imei}\nStatus: {status}\nOrder ID: {order_id}"
                )
            except Exception:
                pass

        else:
            status = "failed"
            message = f"Falha ao criar ordem: {resultado}"
            order_id = None
            flash(f"❌ {message}", "danger")
            log("ERROR", f"Falha no desbloqueio {modelo} IMEI {imei}: {resultado}")

        # -----------------------
        # Renderiza resultado
        # -----------------------
        return render_template(
            "unlock_result.html",
            modelo=modelo,
            imei=imei,
            preco=preco_venda,
            preco_fornecedor=preco_fornecedor,
            lucro=lucro,
            sem_sinal=bool(sem_sinal_flag),
            status=status,
            message=message,
            order_id=order_id
        )

    # -----------------------
    # GET: exibe formulário
    # -----------------------
    return render_template("unlock.html", modelos=MODELOS_IPHONE)

import os
from flask import Flask, request, session, redirect, url_for, render_template, flash
from datetime import datetime, timedelta, timezone
import sqlite3
import bcrypt
import re
from typing import Tuple
from flask import g

# -----------------------
# Configurações de banco
# -----------------------
BASE_DIR = os.path.dirname(__file__)
DB_FILE = os.getenv("DB_FILE", os.path.join(BASE_DIR, "t-lux.db"))

# -----------------------
# Credenciais administrativas (mova para .env se possível!)
# -----------------------
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "arrymauai3@gmail.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "404315")
TECH_EMAIL = os.getenv("TECH_EMAIL", "tluxblindspot@gmail.com")
TECH_PASSWORD = os.getenv("TECH_PASSWORD", "404315")

# -----------------------
# API Keys externas (placeholders se não definidos no .env)
# -----------------------
DHRU_API_KEY = os.getenv("DHRU_API_KEY", "")
DHRU_API_URL = os.getenv("DHRU_API_URL", "https://bulk.iremove.tools/api/dhru/api/index.php")

IMEI_API_KEY = os.getenv("IMEI_API_KEY", "")
IMEI_BASE_URL = os.getenv("IMEI_BASE_URL", "https://api.imei.info")

# -----------------------
# Defaults de preços (preencha conforme necessário)
# -----------------------
UNLOCK_PRECOS = {}

# -----------------------
# Banco de Dados (SQLite) + Inicialização
# -----------------------
from datetime import timezone
UTC = timezone.utc

def get_db():
    """Abre conexão SQLite com suporte a múltiplas threads e WAL ativo"""
    if "db" not in g:
        g.db = sqlite3.connect(DB_FILE, timeout=30, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exception):
    """Fecha conexão ativa ao encerrar contexto Flask"""
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    """Cria todas as tabelas necessárias se não existirem"""
    conn = get_db()
    c = conn.cursor()
    # Exemplo simples: tabela de eventos
    c.execute("""
    CREATE TABLE IF NOT EXISTS eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        descricao TEXT,
        data TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)
    conn.commit()
# -----------------------
# Limpeza automática de códigos expirados
# -----------------------
def clean_expired_codes():
    db = get_db()
    db.execute("DELETE FROM verification_codes WHERE expires_at < datetime('now')")
    db.commit()

def registrar_evento(user_id, descricao):
    import sqlite3
    try:
        # 🔒 Abre conexão nova, totalmente independente do Flask
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO eventos (user_id, descricao, data)
            VALUES (?, ?, datetime('now', 'localtime'))
        """, (user_id, descricao))
        conn.commit()
        # conn.close() — fechado pelo teardown
        print(f"[OK] Evento registrado para o usuário {user_id}: {descricao}")
    except Exception as e:
        print(f"[ERRO] Falha ao registrar evento: {e}")

        # -----------------------
        # USERS
        # -----------------------
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            language TEXT,
            access_key TEXT,
            access_expiry TEXT,
            is_admin INTEGER DEFAULT 0,
            region TEXT DEFAULT 'USD',
            email_verified INTEGER DEFAULT 1,  -- verificado por padrão
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # -----------------------
        # TRANSACTIONS
        # -----------------------
        c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            purpose TEXT,               -- 'package' | 'unlock'
            pacote TEXT,
            modelo TEXT,
            imei TEXT,
            sem_sinal INTEGER DEFAULT 0,
            amount REAL,
            status TEXT,
            processed INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            order_id TEXT,
            preco_fornecedor REAL DEFAULT 0.0,
            lucro REAL DEFAULT 0.0,
            tx_ref TEXT UNIQUE,
            stripe_id TEXT,
            updated_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        # -----------------------
        # LICENSES
        # -----------------------
        c.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            license_key TEXT,
            pacote TEXT,
            modelo TEXT,
            issued_at TEXT,
            expires_at TEXT,
            status TEXT DEFAULT 'active',
            tx_id INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(tx_id) REFERENCES transactions(id) ON DELETE SET NULL
        )
        """)

        # -----------------------
        # LOGS (auditoria geral)
        # -----------------------
        c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        # -----------------------
        # LOGS DE DESBLOQUEIO
        # -----------------------
        c.execute("""
        CREATE TABLE IF NOT EXISTS logs_desbloqueio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_id INTEGER,
            user_email TEXT,
            imei TEXT,
            modelo TEXT,
            status TEXT,
            data_hora TEXT,
            FOREIGN KEY(tx_id) REFERENCES transactions(id) ON DELETE CASCADE
        )
        """)

        # -----------------------
        # TECH REQUESTS (suporte)
        # -----------------------
        c.execute("""
        CREATE TABLE IF NOT EXISTS tech_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
            mensagem TEXT,
            status TEXT DEFAULT 'open',
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # -----------------------
        # LOGIN ATTEMPTS
        # -----------------------
        c.execute("""
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            ip_address TEXT,
            status TEXT,  -- 'success' | 'failed'
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # -----------------------
        # BLOCKED USERS
        # -----------------------
        c.execute("""
        CREATE TABLE IF NOT EXISTS blocked_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT,
            ip_address TEXT,
            blocked_until TEXT,
            UNIQUE(email, ip_address)
        )
        """)

        # -----------------------
        # LOGS DE EVENTOS
        # -----------------------
        c.execute("""
        CREATE TABLE IF NOT EXISTS logs_eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            mensagem TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        # -----------------------
        # SERVICES (catálogo iRemoval)
        # -----------------------
        c.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY,
            nome TEXT NOT NULL,
            credit REAL NOT NULL,
            group_name TEXT NOT NULL
        )
        """)

        # -----------------------
        # ORDERS (pedidos enviados)
        # -----------------------
        c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            service_id INTEGER NOT NULL,
            service_name TEXT NOT NULL,
            order_ref TEXT UNIQUE,
            imei TEXT,
            status TEXT DEFAULT 'PENDING',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # -----------------------
        # EMAIL VERIFICATIONS
        # -----------------------
        c.execute("""
        CREATE TABLE IF NOT EXISTS email_verifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            token TEXT,
            created_at TEXT,
            expires_at TEXT,
            used INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        # -----------------------
        # Índices para performance
        # -----------------------
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_licenses_user ON licenses(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_logs_user ON logs(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts_email ON login_attempts(email)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_blocked_users_email ON blocked_users(email)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_orders_email ON orders(user_email)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_orders_ref ON orders(order_ref)")

        # -----------------------
        # Criar usuários iniciais (admin / tech)
        # -----------------------
        usuarios_iniciais = [
            (ADMIN_EMAIL, ADMIN_PASSWORD, 1),  # Admin
            (TECH_EMAIL, TECH_PASSWORD, 0),    # Técnico
        ]
        for email, password, is_admin in usuarios_iniciais:
            c.execute("SELECT id FROM users WHERE email = ?", (email,))
            if c.fetchone() is None:
                pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                c.execute("""
                    INSERT INTO users (email, password_hash, is_admin, region, email_verified, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    email, pw_hash, is_admin,
                    "USD", 1, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))

        conn.commit()

        
# -----------------------
# Funções de preços e transações
# -----------------------
def get_preco(modelo: str, sem_sinal: bool) -> tuple[float, float, float]:
    """
    Retorna (preco_venda, preco_fornecedor, lucro) para o modelo.
    Levanta KeyError se não existir.
    """
    if sem_sinal:
        pv = MODELOS_IPHONE_SEM_SINAL_USD[modelo]
        pf = PRECO_IREMOVAL_SEM_SINAL_USD[modelo]
    else:
        pv = MODELOS_IPHONE_USD[modelo]
        pf = PRECO_IREMOVAL_USD.get(modelo, 0.0)
    return pv, pf, round(pv - pf, 2)


def gravar_transacao_unlock(user_id: int, modelo: str, imei: str, sem_sinal: int, preco_venda: float, preco_fornecedor: float, lucro: float) -> int:
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO transactions (user_id, purpose, modelo, imei, sem_sinal, amount, preco_fornecedor, lucro, status, processed, created_at)
        VALUES (?, 'unlock', ?, ?, ?, ?, ?, ?, 'paid', 0, ?)
    """, (user_id, modelo, imei, sem_sinal, preco_venda, preco_fornecedor, lucro, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    tx_id = c.lastrowid
    conn.commit()
    # conn.close() — fechado pelo teardown
    return tx_id

# -----------------------
# Utilidades
# -----------------------
def generate_license_key():
    return uuid.uuid4().hex.upper()

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def current_user():
    """Retorna o usuário logado como dicionário ou None"""
    if "user_id" not in session:
        return None
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (session["user_id"],))
    row = c.fetchone()
    if not row:
        return None
    # Converte sqlite3.Row para dict
    return {k: row[k] for k in row.keys()}

def _issue_license_from_tx(tx_id):
    """
    Emite uma licença a partir de uma transação paga.
    Atualiza o usuário e cria histórico em licenses.
    """
    conn = get_db()
    c = conn.cursor()

    # Busca transação
    c.execute("SELECT * FROM transactions WHERE id=?", (tx_id,))
    tx = c.fetchone()
    if not tx:
        # conn.close() — fechado pelo teardown
        app.logger.error(f"Transação {tx_id} não encontrada.")
        return False

    user_id = tx["user_id"]
    pacote = tx["pacote"]
    if not user_id or not pacote:
        # conn.close() — fechado pelo teardown
        app.logger.error(f"Transação {tx_id} inválida (sem user_id/pacote).")
        return False

    # Recupera info do pacote
    pacote_info = PACOTES_USD.get(pacote)
    if not pacote_info:
        # conn.close() — fechado pelo teardown
        app.logger.error(f"Pacote {pacote} não existe.")
        return False

    # Calcula validade da licença
    dias = pacote_info.get("duration_days", 7)
    expiry_date = datetime.now() + timedelta(days=dias)
    access_key = secrets.token_hex(16)

    # Atualiza usuário
    try:
        c.execute("""
            UPDATE users
            SET access_key=?, access_expiry=?
            WHERE id=?
        """, (access_key, expiry_date.strftime("%Y-%m-%d %H:%M:%S"), user_id))
    except Exception as e:
        app.logger.warning(f"Possível falta da coluna updated_at em users: {e}")

    # Cria registro em licenses (histórico)
    c.execute("""
        INSERT INTO licenses (user_id, license_key, pacote, issued_at, expires_at, tx_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        access_key,
        pacote,
        now_str(),
        expiry_date.strftime("%Y-%m-%d %H:%M:%S"),
        tx_id
    ))

    # Atualiza transação
    c.execute("""
        UPDATE transactions
        SET status=?, updated_at=?
        WHERE id=?
    """, ("license_issued", now_str(), tx_id))

    conn.commit()
    # conn.close() — fechado pelo teardown

    app.logger.info(f"✅ Licença emitida para user {user_id} (pacote {pacote}, expira em {expiry_date}).")
    return True

# -----------------------
# Função de envio de e-mail
# -----------------------
from flask_mail import Mail, Message
import os

# Configuração do Outlook SMTP
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.office365.com")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", 587))
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "1") == "1"
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD", "")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER", app.config["MAIL_USERNAME"])

mail = Mail(app)

def send_email(to_email: str, subject: str, body_text: str = None, body_html: str = None, bcc: list[str] = None):
    try:
        # --- Desativado temporariamente ---
        print("📧 [DEBUG - EMAIL DESATIVADO]")
        print(f"Para: {to_email}")
        print(f"Assunto: {subject}")
        if body_text:
            print("Texto:", body_text)
        if body_html:
            print("HTML:", body_html)
        return True
    except Exception as e:
        print(f"❌ [EMAIL] ERRO simulado ao enviar para {to_email}: {e}")
        return False

# 🔹 Rota de teste de envio (apenas admin)
@app.route("/_debug_email")
def _debug_email():
    if not session.get("is_admin"):
        return "Unauthorized", 401

    destino = request.args.get("to", "arrymauai3@gmail.com")
    body_text = "Teste T-Lux via Outlook SMTP."
    body_html = """
    <html><body style="font-family:Arial">
      <h3 style="color:#0057b8">Teste de Envio T-Lux</h3>
      <p>Se você está vendo este e-mail, o SMTP Outlook está configurado com sucesso ✅</p>
    </body></html>
    """
    ok = send_email(
        destino,
        "Teste T-Lux (SMTP Outlook)",
        body_text=body_text,
        body_html=body_html,
        bcc=[app.config["MAIL_DEFAULT_SENDER"]]  # cópia oculta para tua caixa
    )
    return ("OK" if ok else "FAIL"), (200 if ok else 500)

# -----------------------
# Função de envio de e-mail (T-Lux via Zoho)
# -----------------------
from email.message import EmailMessage
import smtplib, ssl

def send_email(to_email, subject, body_text=None, body_html=None):
    """
    Envia e-mails usando Zoho SMTP com suporte a HTML.
    As credenciais são carregadas do .env.
    """
    smtp_host = os.getenv("ZOHO_SMTP_HOST", "smtp.zoho.com")
    smtp_port = int(os.getenv("ZOHO_SMTP_PORT", 587))
    smtp_user = os.getenv("ZOHO_SMTP_USER")
    smtp_pass = os.getenv("ZOHO_SMTP_PASS")

    msg = EmailMessage()
    msg["From"] = f"T-Lux Systems <{smtp_user}>"
    msg["To"] = to_email
    msg["Subject"] = subject

    # HTML ou texto simples
    if body_html:
        msg.add_alternative(body_html, subtype="html")
    else:
        msg.set_content(body_text or "")

    # Conexão segura
    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls(context=context)
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)

    print(f"✅ [E-MAIL] Enviado com sucesso para {to_email}")

#---------------------------
# Bloqueio de tentativas
#---------------------------    
from datetime import datetime, timedelta, timezone
UTC = timezone.utc

LOGIN_MAX_ATTEMPTS = 5
LOGIN_BLOCK_MINUTES = 10
MAX_FAILED_ATTEMPTS = LOGIN_MAX_ATTEMPTS
BLOCK_TIME_MINUTES = LOGIN_BLOCK_MINUTES

def _now_iso():
    return datetime.now(UTC).isoformat()

def is_blocked(email: str, ip: str) -> bool:
    """Verifica se email OU IP está bloqueado neste momento."""
    conn = get_db()
    c = conn.cursor()
    now = _now_iso()
    c.execute(
        """
        SELECT 1
        FROM blocked_users
        WHERE (email = ? OR ip_address = ?)
          AND blocked_until > ?
        LIMIT 1
        """,
        (email, ip, now),
    )
    return c.fetchone() is not None

def failed_attempts(email: str, ip: str) -> int:
    """
    Conta tentativas falhadas recentes para este email+IP dentro da janela BLOCK_TIME_MINUTES.
    Considera status='failed'.
    """
    conn = get_db()
    c = conn.cursor()
    time_limit = (datetime.now(UTC) - timedelta(minutes=BLOCK_TIME_MINUTES)).isoformat()
    c.execute(
        """
        SELECT COUNT(*) AS total
        FROM login_attempts
        WHERE (email = ? OR ip_address = ?)
          AND status = 'failed'
          AND created_at >= ?
        """,
        (email, ip, time_limit),
    )
    row = c.fetchone()
    # row pode ser tupla (0) ou dict-like; normaliza pra int
    try:
        return int(row[0] if row is not None else 0)
    except Exception:
        return int((row["total"] if row and "total" in row.keys() else 0))

def register_login_attempt(email: str, ip: str, status: str, conn=None) -> None:
    """
    Registra tentativa (success/failed) e aplica bloqueio se exceder o limite.
    Usa a conexão passada ou get_db(); NÃO fecha aqui (teardown fecha no fim da request).
    """
    close_after = False
    if conn is None:
        conn = get_db()
        close_after = True

    c = conn.cursor()
    try:
        # 1) Registra a tentativa
        c.execute(
            """
            INSERT INTO login_attempts (email, ip_address, status, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (email, ip, status, _now_iso()),
        )
        conn.commit()

        # 2) Se falhou, checa se deve bloquear
        if status == "failed":
            total = failed_attempts(email, ip)
            if total >= MAX_FAILED_ATTEMPTS:
                blocked_until = (datetime.now(UTC) + timedelta(minutes=BLOCK_TIME_MINUTES)).isoformat()

                # Atualiza ou insere novo bloqueio
                c.execute(
                    """
                    UPDATE blocked_users
                       SET blocked_until = ?
                     WHERE email = ? OR ip_address = ?
                    """,
                    (blocked_until, email, ip),
                )
                if c.rowcount == 0:
                    c.execute(
                        """
                        INSERT INTO blocked_users (email, ip_address, blocked_until)
                        VALUES (?, ?, ?)
                        """,
                        (email, ip, blocked_until),
                    )
                conn.commit()

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        app.logger.error(f"[DB ERROR] register_login_attempt failed: {e}")

    finally:
        # opcional: fecha se foi aberta internamente
        if close_after:
            try:
                conn.close()
            except Exception:
                pass

# -----------------------
# Password Reset (Forgot Password)
# -----------------------
@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    """
    Step 1: User enters email
    Step 2: System sends 6-digit verification code via email
    Step 3: Redirects user to code confirmation and password reset
    """
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not email:
            flash("Please enter your email address.", "warning")
            return redirect(url_for("forgot_password"))

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE email=?", (email,))
        user = c.fetchone()

        if not user:
            # conn.close() — fechado pelo teardown
            flash("No account found with that email address.", "danger")
            return redirect(url_for("forgot_password"))

        # Generate and send a verification code
        create_verification_code(email, user["id"])
        flash("A 6-digit verification code has been sent to your email.", "info")

        # conn.close() — fechado pelo teardown
        return redirect(url_for("reset_password", email=email))

    return render_template("forgot_password.html")

# --------------------------
# 🔑 Reset Password (after code)
# --------------------------
@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    """
    Tela para redefinir senha com código de verificação.
    """
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        code = request.form.get("code", "").strip()
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not email or not code or not new_password or not confirm_password:
            flash(_("Please fill in all fields."), "warning")
            return redirect(url_for("reset_password"))

        if new_password != confirm_password:
            flash(_("Passwords do not match."), "danger")
            return redirect(url_for("reset_password"))

        conn = get_db()
        c = conn.cursor()

        # valida código
        c.execute("""
            SELECT id, user_id, expires_at, used FROM verification_codes
            WHERE email=? AND code=? ORDER BY id DESC LIMIT 1
        """, (email, code))
        row = c.fetchone()

        if not row:
            flash(_("Invalid verification code."), "danger")
            return redirect(url_for("reset_password"))

        exp = datetime.fromisoformat(row["expires_at"])
        if datetime.now() > exp:
            flash(_("Code expired. Please request a new one."), "warning")
            return redirect(url_for("forgot_password"))

        # atualiza senha
        hashed = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt())
        c.execute("UPDATE users SET password=?, email_verified=1 WHERE id=?", (hashed, row["user_id"]))
        c.execute("UPDATE verification_codes SET used=1 WHERE id=?", (row["id"],))
        conn.commit()

        registrar_evento(row["user_id"], "Password reset successfully")
        flash(_("✅ Password reset successful. You can now log in."), "success")
        return redirect(url_for("login"))

    # GET → exibe formulário de redefinição
    return render_template("reset_password.html")

# -----------------------
# Login attempts (anti-bruteforce)
# -----------------------

def registrar_tentativa_login(email: str, sucesso: bool):
    """Registra tentativa de login no banco."""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO login_attempts (email, attempt_time, success) VALUES (?, ?, ?)",
        (email.lower(), now_str(), 1 if sucesso else 0)
    )
    conn.commit()
    # conn.close() — fechado pelo teardown

def is_login_blocked(email: str) -> Tuple[bool, int]:
    """
    Verifica se o usuário ainda está bloqueado por excesso de tentativas de login.
    Retorna (True, segundos_restantes) ou (False, 0).
    """
    conn = get_db()
    c = conn.cursor()

    window_start = (datetime.now(UTC) - timedelta(minutes=LOGIN_BLOCK_MINUTES)).isoformat()

    # Conta falhas recentes
    c.execute("""
        SELECT COUNT(*) as fails FROM login_attempts
        WHERE email=? AND success=0 AND attempt_time >= ?
    """, (email, window_start))
    row = c.fetchone()
    fails = row["fails"] if row else 0

    if fails < LOGIN_MAX_ATTEMPTS:
        # conn.close() — fechado pelo teardown
        return False, 0

    # Última falha registrada
    c.execute("""
        SELECT MAX(attempt_time) as last_fail FROM login_attempts
        WHERE email=? AND success=0
    """, (email,))
    last = c.fetchone()
    # conn.close() — fechado pelo teardown

    if not last or not last["last_fail"]:
        return False, 0

    last_fail_time = datetime.fromisoformat(last["last_fail"])
    unblock_time = last_fail_time + timedelta(minutes=LOGIN_BLOCK_MINUTES)
    remaining = (unblock_time - datetime.now(UTC)).total_seconds()

    if remaining > 0:
        return True, int(remaining)
    return False, 0

# -----------------------
# Email Verification & OTP (Secure T-Lux System)
# -----------------------

import hmac, hashlib, secrets
from datetime import datetime, timedelta, timezone
from typing import Tuple

UTC = timezone.utc

# ------------------------------------
# 🔹 TOKEN VERIFICATION (LINK METHOD)
# ------------------------------------

def gerar_token_verificacao(user_id: int, validade_horas: int = 48) -> str:
    """
    Gera token seguro para verificação de e-mail via link.
    Salva em email_verifications e retorna o token.
    """
    token = secrets.token_urlsafe(32)
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    expires = (datetime.now(UTC) + timedelta(hours=validade_horas)).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO email_verifications (user_id, token, created_at, expires_at, used)
        VALUES (?, ?, ?, ?, 0)
    """, (user_id, token, now, expires))
    conn.commit()
    # conn.close() — fechado pelo teardown
    return token


def marcar_token_usado(token: str):
    """Marca token de verificação como utilizado."""
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE email_verifications SET used=1 WHERE token=?", (token,))
    conn.commit()
    # conn.close() — fechado pelo teardown

def verify_email_token(token: str) -> Tuple[bool, str]:
    """
    Verifica a validade de um token de verificação de e-mail.
    Se for válido:
      ✅ Marca o usuário como verificado
      ✅ Marca o token como usado
    Retorna:
      (True, "mensagem de sucesso") ou (False, "mensagem de erro")
    """
    conn = get_db()
    c = conn.cursor()

    try:
        # 1️⃣ Busca o token na base
        c.execute("""
            SELECT id, user_id, used, expires_at
            FROM email_verifications
            WHERE token = ?
        """, (token,))
        row = c.fetchone()

        # 2️⃣ Token não existe
        if not row:
            return False, "❌ Invalid or unknown verification token."

        # 3️⃣ Token já usado
        if row["used"]:
            return False, "⚠️ This verification link has already been used."

        # 4️⃣ Valida expiração
        try:
            expira_em = datetime.fromisoformat(row["expires_at"]).replace(tzinfo=UTC)
        except Exception:
            return False, "⚠️ Invalid expiration date format."

        if datetime.now(UTC) > expira_em:
            return False, "⌛ Verification link expired. Please request a new one."

        # 5️⃣ Marca como verificado
        user_id = row["user_id"]
        c.execute("UPDATE users SET email_verified = 1 WHERE id = ?", (user_id,))
        c.execute("UPDATE email_verifications SET used = 1 WHERE id = ?", (row["id"],))
        conn.commit()

        return True, "✅ Email verified successfully!"

    except Exception as e:
        # Rollback de segurança em caso de erro
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"[DB ERROR] verify_email_token failed: {e}")
        return False, "❌ An unexpected error occurred during verification."

    # ❌ NÃO fecha a conexão aqui — o teardown faz isso automaticamente

# ------------------------------------
# 🔹 OTP VERIFICATION (CODE METHOD)
# ------------------------------------
import hmac, hashlib, secrets, string, random
from datetime import datetime, timedelta, timezone
from flask import current_app as app
from typing import Optional

UTC = timezone.utc


# -----------------------
# Funções utilitárias OTP
# -----------------------

def generate_code(length: int = 6) -> str:
    """Gera código numérico aleatório (OTP)."""
    length = max(length, 4)  # mínimo de segurança
    return ''.join(random.choices(string.digits, k=length))


def hash_code(code: str) -> str:
    """Hash HMAC-SHA256 do código OTP usando a secret_key do app."""
    key = app.secret_key.encode()
    return hmac.new(key, code.encode(), hashlib.sha256).hexdigest()


# ============================================================
# 🔐 T-LUX EMAIL & OTP VERIFICATION MODULE
# ============================================================

import hmac, hashlib, random
from datetime import datetime, timedelta, timezone
from typing import Optional

UTC = timezone.utc

# ============================================================
# 🔧 Funções auxiliares
# ============================================================

def _now_iso() -> str:
    """Retorna timestamp ISO no fuso UTC."""
    return datetime.now(UTC).isoformat()

def generate_code(length: int = 6) -> str:
    """Gera um código numérico aleatório."""
    return ''.join(random.choices('0123456789', k=length))

def hash_code(code: str) -> str:
    """Retorna hash SHA256 do código (armazenado no DB)."""
    return hashlib.sha256(code.encode()).hexdigest()

# ============================================================
# 🧮 Criação e envio de código OTP (WhatsApp-style)
# ============================================================

def create_verification_code(email: str, user_id: Optional[int] = None, length: int = 6, minutes_valid: int = 10) -> bool:
    """
    Cria e salva um código OTP, envia via e-mail com design moderno.
    """
    code = generate_code(length)
    code_hash = hash_code(code)
    now_iso = _now_iso()
    expires_at = (datetime.now(UTC) + timedelta(minutes=minutes_valid)).isoformat()

    conn = None
    try:
        conn = get_db()
        c = conn.cursor()

        # Invalida códigos antigos
        c.execute("UPDATE verification_codes SET used=1 WHERE email=? AND used=0", (email,))

        # Insere novo
        c.execute("""
            INSERT INTO verification_codes (user_id, email, code_hash, created_at, expires_at, used)
            VALUES (?, ?, ?, ?, ?, 0)
        """, (user_id, email, code_hash, now_iso, expires_at))
        conn.commit()

    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        app.logger.error(f"[VERIFICATION_CODE][DB] Failed for {email}: {e}")
        return False

    # =====================================================
    # 💌 Monta o e-mail de verificação OTP
    # =====================================================
    subject = "🔐 Your T-Lux Verification Code"
    minutes_lbl = f"{minutes_valid} minute{'s' if minutes_valid != 1 else ''}"

    body_text = (
        f"T-Lux Verification\n\n"
        f"Your verification code is: {code}\n"
        f"This code will expire in {minutes_lbl}.\n\n"
        f"If you did not request this, just ignore this email.\n"
        f"— T-Lux Unlock Systems"
    )

    body_html = f"""
    <div style="font-family:Arial,sans-serif;background:#f7f7f7;padding:20px;">
      <div style="max-width:600px;margin:auto;background:#ffffff;padding:28px;border-radius:12px;
                  box-shadow:0 6px 18px rgba(0,0,0,0.08);text-align:center;">
        <h2 style="color:#d4af37;margin-bottom:6px;">🔐 T-Lux Verification</h2>
        <p style="color:#555;">Use the code below to continue your verification:</p>
        <div style="margin:20px 0;">
          <span style="display:inline-block;font-size:30px;letter-spacing:8px;color:#0d6efd;
                       font-weight:800;border:2px dashed #0d6efd;border-radius:10px;padding:12px 20px;">
            {code}
          </span>
        </div>
        <p style="color:#555;">This code will expire in <strong>{minutes_lbl}</strong>.</p>
        <hr style="border:none;border-top:1px solid #eee;margin:25px 0;">
        <p style="font-size:12px;color:#777;">
          © 2025 T-Lux Unlock Systems — Secure Global Platform
        </p>
      </div>
    </div>
    """

    try:
        send_email(email, subject, body_text=body_text, body_html=body_html)
        app.logger.info(f"✅ Verification code sent to {email}")
        return True
    except Exception as e:
        app.logger.error(f"[VERIFICATION_CODE][MAIL] Failed to send code to {email}: {e}")
        return False

# ============================================================
# 🔍 Verificação de código OTP (versão atualizada — 30 segundos)
# ============================================================

def verify_code(email: str, code: str) -> bool:
    """
    Valida o código OTP de um usuário (expira em 30 segundos).
    Retorna True se o código é válido e marca como usado.
    """
    try:
        db = get_db()
        c = db.cursor()

        # Busca o código mais recente e ainda não usado
        c.execute("""
            SELECT id, code_hash, expires_at, used
            FROM verification_codes
            WHERE email=? AND used=0
            ORDER BY id DESC
            LIMIT 1
        """, (email,))
        row = c.fetchone()

        # Nenhum código ativo encontrado
        if not row:
            app.logger.warning(f"[VERIFY_CODE] Nenhum código ativo encontrado para {email}")
            return False

        # Verifica expiração
        try:
            expires = datetime.fromisoformat(row["expires_at"])
        except Exception:
            app.logger.error(f"[VERIFY_CODE] Erro ao converter expires_at para {email}")
            return False

        now_utc = datetime.now(UTC)
        if now_utc > expires:
            app.logger.info(f"[VERIFY_CODE] Código expirado para {email}")
            # Marca como usado/expirado para não reutilizar
            try:
                c.execute("UPDATE verification_codes SET used=1 WHERE id=?", (row["id"],))
                db.commit()
            except Exception:
                pass
            return False

        # Compara hashes de forma segura (protege contra timing attacks)
        if not hmac.compare_digest(row["code_hash"], hash_code(code)):
            app.logger.info(f"[VERIFY_CODE] Código incorreto para {email}")
            return False

        # Marca como usado (para impedir reuso)
        try:
            c.execute("UPDATE verification_codes SET used=1 WHERE id=?", (row["id"],))
            db.commit()
            app.logger.info(f"✅ Código verificado com sucesso para {email}")
        except Exception as e:
            app.logger.error(f"[VERIFY_CODE][DB] Erro ao marcar código como usado: {e}")
            return False

        return True

    except Exception as e:
        app.logger.error(f"[VERIFY_CODE][EXCEPTION] {e}")
        return False

# ============================================================
# 💌 Envio de link alternativo (token)
# ============================================================

def enviar_email_verificacao(user_id: int, user_email: str) -> bool:
    """
    Envia e-mail de verificação com link (caso o usuário prefira clicar).
    """
    try:
        token = gerar_token_verificacao(user_id)
        verify_url = url_for("verify_email_route", token=token, _external=True)

        subject = "🔐 Verify your email — T-Lux Unlock Systems"

        body_html = f"""
        <div style='font-family:Arial,sans-serif;background:#f5f5f5;padding:30px;'>
          <div style='max-width:600px;margin:auto;background:#fff;padding:35px;border-radius:12px;
                      box-shadow:0 6px 20px rgba(0,0,0,0.1);'>
            <h2 style='color:#d4af37;text-align:center;margin-bottom:20px;'>
              ✨ Welcome to <span style="color:#0d6efd;">T-Lux</span>
            </h2>
            <p>Hello,</p>
            <p>Thank you for registering with <strong>T-Lux Unlock Systems</strong>!</p>
            <p>To activate your account, click the button below:</p>
            <div style='text-align:center;margin:30px 0;'>
              <a href='{verify_url}' 
                 style='background:#d4af37;color:#fff;text-decoration:none;padding:14px 28px;
                        border-radius:8px;font-weight:bold;'>
                 ✅ Verify Email
              </a>
            </div>
            <p>If the button above doesn’t work, copy and paste this link:</p>
            <p style='word-break:break-all;color:#0d6efd;'>{verify_url}</p>
            <hr style='margin:30px 0;border:none;border-top:1px solid #eee;'>
            <p style='font-size:13px;color:#777;text-align:center;'>
              This link expires in 48 hours.<br>
              If you did not create a T-Lux account, please ignore this message.
            </p>
            <p style='font-size:12px;text-align:center;color:#999;margin-top:10px;'>
              © 2025 T-Lux — Secure Unlock Platform<br>
              <em>Developed by Blindspot</em>
            </p>
          </div>
        </div>
        """

        send_email(user_email, subject, body_html=body_html)
        app.logger.info(f"✅ Verification link sent to {user_email}")
        return True

    except Exception as e:
        app.logger.error(f"❌ Error sending verification email: {e}")
        return False

# ============================================================
# 🧱 AUTO-MIGRATION: Ensure database structure consistency
# ============================================================

def ensure_database_schema():
    """
    Garante que as tabelas 'users' e 'verification_codes' têm as colunas certas.
    Corrige automaticamente se estiver faltando algo.
    """
    conn = get_db()
    c = conn.cursor()

    # ---------------------------
    # USERS TABLE CHECK
    # ---------------------------
    try:
        c.execute("PRAGMA table_info(users);")
        columns = [col[1] for col in c.fetchall()]

        if "email_verified" not in columns:
            app.logger.warning("🛠 Adding 'email_verified' column to 'users' table...")
            c.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0;")
            conn.commit()
            app.logger.info("✅ Column 'email_verified' added successfully.")
    except Exception as e:
        app.logger.error(f"[MIGRATION][USERS] Error: {e}")

    # ---------------------------
    # VERIFICATION_CODES TABLE CHECK
    # ---------------------------
    try:
        c.execute("PRAGMA table_info(verification_codes);")
        columns = [col[1] for col in c.fetchall()]

        if "user_id" not in columns:
            app.logger.warning("🛠 Adding 'user_id' column to 'verification_codes'...")
            c.execute("ALTER TABLE verification_codes ADD COLUMN user_id INTEGER;")
            conn.commit()

        if "expires_at" not in columns:
            app.logger.warning("🛠 Adding 'expires_at' column to 'verification_codes'...")
            c.execute("ALTER TABLE verification_codes ADD COLUMN expires_at TIMESTAMP;")
            conn.commit()

        if "used" not in columns:
            app.logger.warning("🛠 Adding 'used' column to 'verification_codes'...")
            c.execute("ALTER TABLE verification_codes ADD COLUMN used INTEGER DEFAULT 0;")
            conn.commit()

        app.logger.info("✅ verification_codes structure verified and up-to-date.")
    except Exception as e:
        app.logger.error(f"[MIGRATION][VERIFICATION_CODES] Error: {e}")

# -----------------------
# Licença a partir de transação
# -----------------------
def _issue_license_from_tx(tx_id: int):
    conn = get_db()
    c = conn.cursor()

    # Recupera a transação
    c.execute("SELECT * FROM transactions WHERE id=?", (tx_id,))
    tx = c.fetchone()
    if not tx:
        # conn.close() — fechado pelo teardown
        return False, "Transação não encontrada."

    # Evita duplicidade
    c.execute("SELECT id FROM licenses WHERE tx_id=?", (tx_id,))
    if c.fetchone():
        # conn.close() — fechado pelo teardown
        return True, "Licença já emitida."

    # Só PACOTE gera licença
    if (tx["purpose"] or "").lower() != "package":
        # conn.close() — fechado pelo teardown
        return True, "Transação não é de pacote (nenhuma licença emitida)."

    pacote = tx["pacote"]
    duration_days = PACOTES.get(pacote, {}).get("duration_days", 30)
    expires_at = (datetime.now() + timedelta(days=duration_days)).strftime("%Y-%m-%d %H:%M:%S")
    license_key = generate_license_key()

    # Inserir licença e atualizar usuário
    c.execute("""
        INSERT INTO licenses (user_id, license_key, pacote, modelo, issued_at, expires_at, tx_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (tx["user_id"], license_key, pacote, None, now_str(), expires_at, tx_id))
    c.execute("UPDATE users SET access_key=?, access_expiry=? WHERE id=?",
              (license_key, expires_at, tx["user_id"]))
    conn.commit()

    # Notifica usuário
    c.execute("SELECT email, language FROM users WHERE id=?", (tx["user_id"],))
    row = c.fetchone()
    # conn.close() — fechado pelo teardown
    if row:
        user_email = row["email"]
        user_lang = (row["language"] or "pt").lower()
        subject = "Chave de Acesso T-Lux"
        body_pt = f"Obrigado pelo pagamento.\n\nChave de acesso: {license_key}\nPacote: {pacote}\nValidade: {expires_at}"
        body_en = f"Thank you for your payment.\n\nAccess key: {license_key}\nPackage: {pacote}\nExpires: {expires_at}"
        try:
            send_email(user_email, subject, body_pt if user_lang.startswith("pt") else body_en)
            send_email(
                TECH_EMAIL,
                f"[T-Lux] Licença emitida (Package) TX {tx_id}",
                f"User: {user_email}\nPackage: {pacote}\nTX_ID: {tx_id}"
            )
        except Exception:
            pass

    return True, "Licença emitida."


# -----------------------
# Conversão de moeda
# -----------------------
def get_currency_for_region(region_code):
    if not region_code:
        return "USD"
    info = COUNTRIES.get(region_code.upper())
    return info["currency"] if info else "USD"


def convert_local_to_usd(local_amount, currency_code):
    """
    Converte um valor local (ex: MZN) para USD usando EXCHANGE_RATES.
    """
    rate = EXCHANGE_RATES.get(currency_code or "USD", 1.0)
    try:
        rate = float(rate) if rate else 1.0
    except Exception:
        rate = 1.0
    return round(float(local_amount) / rate, 2)

# -----------------------
# Rotas principais
# -----------------------
#--------------------
# Rota Registacao
#--------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # 1️⃣ Collect form data
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()
        language = request.form.get("language", "en")[:2].lower()
        region = request.form.get("region", "").strip() or "MZ"
        currency = request.form.get("currency", "").strip() or "USD"
        terms_ok = request.form.get("terms") == "on"
        ip = request.remote_addr

        # 2️⃣ Check blocking
        if is_blocked(email, ip):
            flash("Registration temporarily blocked due to multiple failed attempts.", "danger")
            return redirect(url_for("register"))

        # 3️⃣ Validation
        if not all([first_name, last_name, username, email, password]):
            register_login_attempt(email, ip, "failed")
            flash("Please fill in all required fields.", "danger")
            return redirect(url_for("register"))
        if not terms_ok:
            register_login_attempt(email, ip, "failed")
            flash("You must accept the Terms and Conditions.", "warning")
            return redirect(url_for("register"))

        # 4️⃣ Hash password
        hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        conn = get_db()
        c = conn.cursor()

        try:
            # 5️⃣ Check duplicates
            c.execute("SELECT id FROM users WHERE email=? OR username=?", (email, username))
            if c.fetchone():
                conn.rollback()
                register_login_attempt(email, ip, "failed", conn=conn)
                flash("Email or username already exists.", "danger")

                if failed_attempts(email, ip) >= MAX_FAILED_ATTEMPTS:
                    block_user(email, ip)
                    flash(f"Too many failed attempts. Registration blocked for {BLOCK_TIME_MINUTES} minutes.", "danger")

                return redirect(url_for("register"))

            # 6️⃣ Insert user (not verified yet)
            c.execute("""
                INSERT INTO users (
                    first_name, last_name, username, email, password_hash,
                    language, region, currency, email_verified, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """, (
                first_name, last_name, username, email, hashed_pw,
                language, region, currency,
                datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()

            # 7️⃣ Get new user
            c.execute("SELECT id, is_admin FROM users WHERE email=?", (email,))
            user = c.fetchone()

            # 8️⃣ Generate verification token + OTP (dual system)
            token = gerar_token_verificacao(user["id"])
            verify_link = url_for("verify_email_route", token=token, _external=True)
            create_verification_code(email, user_id=user["id"], length=8, minutes_valid=10)

            # 9️⃣ Send verification email
            try:
                html_body = render_template(
                    "email_verificacao.html",
                    first_name=first_name,
                    link_verificacao=verify_link
                )

                text_body = f"""
                Hello {first_name},

                Thank you for registering with T-Lux Unlock Systems!
                To activate your account, please click the link below:

                {verify_link}

                Or enter the 8-digit code we sent to your email in the verification page.

                This link and code expire in 10 minutes.

                — T-Lux Systems Team
                """

                send_email(
                    to_email=email,
                    subject="🔐 Verify your email — T-Lux Unlock Systems",
                    body_text=text_body,
                    body_html=html_body
                )

            except Exception as e:
                flash("Account created, but failed to send verification email.", "warning")
                app.logger.error(f"[EMAIL ERROR] Verification failed: {e}")

            # 🔟 Register success
            register_login_attempt(email, ip, "success", conn=conn)
            registrar_evento(user["id"], "Account created (pending verification)")

            # 1️⃣1️⃣ Create unverified session
            session.clear()
            session["user_id"] = user["id"]
            session["email"] = email
            session["is_admin"] = bool(user["is_admin"])
            session["email_verified"] = False

            # 1️⃣2️⃣ Redirect to check-email page
            flash("✅ Account created! Please check your inbox for the verification link or code.", "info")
            return redirect(url_for("check_email"))

        except sqlite3.IntegrityError as e:
            conn.rollback()
            register_login_attempt(email, ip, "failed", conn=conn)

            if "users.username" in str(e).lower():
                flash("Username already taken.", "danger")
            elif "users.email" in str(e).lower():
                flash("Email already registered.", "danger")
            else:
                flash("Registration error. Please try again.", "danger")

            if failed_attempts(email, ip) >= MAX_FAILED_ATTEMPTS:
                block_user(email, ip)
                flash(f"Too many failed attempts. Registration blocked for {BLOCK_TIME_MINUTES} minutes.", "danger")

        finally:
            if conn:
                try:
                    # conn.close() — fechado automaticamente pelo teardown
                    pass
                except Exception:
                    pass

    # GET request
    return render_template("register.html", countries=COUNTRIES, languages=LANGUAGES)

# --------------------------
# 💌 Email Verification (Link + OTP)
# --------------------------
@app.route("/email_verificacao/<token>", methods=["GET", "POST"])
@app.route("/verify_email", methods=["GET", "POST"])
def verify_email_route(token=None):
    """
    Verifica o email do usuário — aceita tanto link (com token) quanto código OTP manual.
    """
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()

        # -------------------------------------------
        # 1️⃣ Verificação via LINK (token)
        # -------------------------------------------
        if token and token != "none":
            c.execute("SELECT user_id, expires_at, used FROM email_tokens WHERE token=?", (token,))
            token_row = c.fetchone()

            if not token_row:
                flash(_("Invalid or expired verification link."), "danger")
                return redirect(url_for("verify_step1"))

            if token_row["used"]:
                flash(_("This link has already been used."), "warning")
                return redirect(url_for("login"))

            # Verifica validade
            expires_at = datetime.fromisoformat(token_row["expires_at"])
            if datetime.now() > expires_at:
                flash(_("This verification link has expired. Please request a new one."), "danger")
                return redirect(url_for("verify_step1"))

            # Marca como verificado
            user_id = token_row["user_id"]
            c.execute("UPDATE users SET email_verified=1 WHERE id=?", (user_id,))
            c.execute("UPDATE email_tokens SET used=1 WHERE token=?", (token,))
            conn.commit()

            registrar_evento(user_id, "Email verified via link")
            flash(_("✅ Your email has been verified successfully!"), "success")
            return redirect(url_for("login"))

        # -------------------------------------------
        # 2️⃣ Verificação via CÓDIGO (OTP manual)
        # -------------------------------------------
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            code = request.form.get("code", "").strip()

            if not email or not code:
                flash(_("Please enter both email and code."), "warning")
                return redirect(url_for("verify_step2"))

            c.execute("""
                SELECT vc.id, vc.user_id, vc.code, vc.expires_at, vc.used, u.email_verified
                FROM verification_codes vc
                JOIN users u ON u.id = vc.user_id
                WHERE vc.email=? AND vc.code=?
                ORDER BY vc.id DESC LIMIT 1
            """, (email, code))
            vc = c.fetchone()

            if not vc:
                flash(_("Invalid verification code."), "danger")
                return redirect(url_for("verify_step2"))

            if vc["used"]:
                flash(_("This code has already been used."), "warning")
                return redirect(url_for("login"))

            expires_at = datetime.fromisoformat(vc["expires_at"])
            if datetime.now() > expires_at:
                flash(_("This code has expired. Please request a new one."), "danger")
                return redirect(url_for("verify_step2"))

            # Marca como verificado
            user_id = vc["user_id"]
            c.execute("UPDATE users SET email_verified=1 WHERE id=?", (user_id,))
            c.execute("UPDATE verification_codes SET used=1 WHERE id=?", (vc["id"],))
            conn.commit()

            registrar_evento(user_id, "Email verified via OTP")

            # ✅ Redireciona dependendo do status de licença
            c.execute("SELECT license_expiry FROM users WHERE id=?", (user_id,))
            user = c.fetchone()
            if user and user["license_expiry"]:
                exp = datetime.fromisoformat(user["license_expiry"])
                if exp > datetime.now():
                    flash(_("✅ Email verified — License active! Redirecting to dashboard..."), "success")
                    return redirect(url_for("dashboard"))

            flash(_("✅ Email verified! Please activate your access to continue."), "success")
            return redirect(url_for("choose_package"))

        # -------------------------------------------
        # 3️⃣ GET padrão — mostra a tela nova
        # -------------------------------------------
        # Aqui decide se o usuário está no passo 1 (inserir email) ou passo 2 (inserir código)
        step = request.args.get("step", "1")
        if step == "1":
            return render_template("verify_step1.html")
        else:
            return render_template("verify_step2.html")

    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.error(f"[VERIFY_EMAIL_ERROR] {e}")
        flash(_("⚠️ Verification failed. Please try again later."), "danger")
        return redirect(url_for("login"))

    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

# ---------------------------
# STEP 1: Usuário introduz o e-mail
# ---------------------------
@app.route("/verify_step1", methods=["GET", "POST"])
def verify_step1():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not email:
            flash(_("Please enter your email."), "warning")
            return redirect(url_for("verify_step1"))

        # Cria e envia o código de verificação — válido por 30 segundos
        if create_verification_code(email=email, length=6, minutes_valid=0.5):
            flash(_("A 6-digit verification code has been sent to your email."), "info")
            masked = mask_email(email)
            return render_template("verify_email_step2.html", email=email, masked_email=masked)
        else:
            flash(_("Failed to send verification code. Please try again."), "danger")
            return redirect(url_for("verify_step1"))

    return render_template("verify_email_step1.html")

# ---------------------------
# STEP 2: Usuário introduz o código
# ---------------------------
@app.route("/verify_step2", methods=["POST"])
def verify_step2():
    email = request.form.get("email", "").strip().lower()
    code = "".join([request.form.get(f"digit{i}", "") for i in range(6)]).strip()

    # Verifica se o código é válido
    if verify_code(email, code):
        conn = get_db()
        c = conn.cursor()

        # Busca o ID do usuário antes de registrar o evento
        c.execute("SELECT id FROM users WHERE email=?", (email,))
        user = c.fetchone()

        if not user:
            flash(_("⚠️ User not found."), "danger")
            return redirect(url_for("verify_step1"))

        user_id = user["id"]

        # Marca o e-mail como verificado
        c.execute("UPDATE users SET email_verified=1 WHERE id=?", (user_id,))
        conn.commit()

        registrar_evento(user_id, "Email verified via OTP (2-step)")

        flash(_("✅ Email verified successfully!"), "success")
        return redirect(url_for("choose_package"))

    # Se falhar a verificação do código
    else:
        flash(_("❌ Invalid or expired code."), "danger")
        masked = mask_email(email)
        return render_template("verify_email_step2.html", email=email, masked_email=masked)

# ---------------------------
# Utilitário para mascarar e-mail
# ---------------------------
def mask_email(email: str) -> str:
    try:
        name, domain = email.split("@")
        return f"{name[0]}***@{domain[0]}***.{domain.split('.')[-1]}"
    except Exception:
        return email

# ----------------------
# 🔐 LOGIN — T-LUX
# ----------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").encode("utf-8")
        ip = request.remote_addr

        # 1️⃣ Check temporary block
        if is_blocked(email, ip):
            flash("🚫 Login temporarily blocked due to multiple failed attempts.", "danger")
            return render_template("login.html")

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email=?", (email,))
        user = c.fetchone()

        if not user:
            register_login_attempt(email, ip, "failed")
            flash("❌ Invalid credentials.", "danger")
            # conn.close() — fechado pelo teardown
            return render_template("login.html")

        stored_pw = user["password_hash"]
        valid = bcrypt.checkpw(password, stored_pw.encode("utf-8"))

        if valid:
            # ✅ Auto-verify admin
            if email == ADMIN_EMAIL:
                try:
                    c.execute("UPDATE users SET email_verified=1 WHERE email=?", (email,))
                    conn.commit()
                except Exception as e:
                    app.logger.warning(f"[ADMIN VERIFY] Failed: {e}")

            # ⚠️ User must verify email first
            if not user["email_verified"] and email != ADMIN_EMAIL:
                flash("⚠️ Please verify your email before accessing your account.", "warning")
                token = gerar_token_verificacao(user["id"])  # new token
                verify_url = url_for("verify_email_route", token=token, _external=True)
                create_verification_code(email, user_id=user["id"], length=8, minutes_valid=10)

                # Send verification email again
                try:
                    html_body = render_template(
                        "email_verificacao.html",
                        first_name=user["first_name"],
                        link_verificacao=verify_url
                    )
                    send_email(
                        to_email=email,
                        subject="🔐 Verify your email — T-Lux Unlock Systems",
                        body_html=html_body
                    )
                    flash("📩 A new verification link and code were sent to your email.", "info")
                except Exception as e:
                    app.logger.error(f"[EMAIL ERROR] Re-send verification failed: {e}")
                    flash("⚠️ Account not verified. Failed to send new email. Try again later.", "danger")

                # conn.close() — fechado pelo teardown
                return redirect(url_for("verify_email_route", token=token))

            # ✅ Success: log in user
            register_login_attempt(email, ip, "success", conn=conn)

            session.clear()
            session["user_id"] = user["id"]
            session["email"] = user["email"]
            session["is_admin"] = bool(user["is_admin"])
            session["email_verified"] = True

            registrar_evento(user["id"], "User successfully logged in")

            # 🧠 Admin redirect
            if session["is_admin"]:
                flash("👑 Logged in with privileged access!", "success")
                # conn.close() — fechado pelo teardown
                return redirect(url_for("dashboard"))

            # 💳 Check access package
            if not has_active_access(user):
                flash("⚠️ Your account doesn’t have an active Access Key yet.", "warning")
                # conn.close() — fechado pelo teardown
                return redirect(url_for("choose_package"))

            flash("✅ Login successful!", "success")
            # conn.close() — fechado pelo teardown
            return redirect(url_for("dashboard"))

        # ❌ Wrong password
        register_login_attempt(email, ip, "failed", conn=conn)
        if failed_attempts(email, ip) >= MAX_FAILED_ATTEMPTS:
            block_user(email, ip)
            flash(f"🚫 Too many failed attempts. Login blocked for {BLOCK_TIME_MINUTES} minutes.", "danger")
        else:
            flash("❌ Invalid email or password.", "danger")

        # conn.close() — fechado pelo teardown

    return render_template("login.html")

# ----------------------
# 🔁 RESEND VERIFICATION (link + OTP)
# ----------------------
@app.route("/resend_verification_code", methods=["GET", "POST"])
def resend_verification_code_route():
    """Reenvia o link e o código de verificação (token + OTP)."""
    token = "none"  # garante valor padrão em caso de erro
    email = request.form.get("email", "").strip().lower() if request.method == "POST" else request.args.get("email", "").strip().lower()

    if not email:
        flash(_("Please enter your email address."), "warning")
        return redirect(url_for("verify_email_route", token="none"))

    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, first_name, email_verified FROM users WHERE email=?", (email,))
        user = c.fetchone()

        if not user:
            flash(_("No account found with that email."), "danger")
            return redirect(url_for("verify_email_route", token="none"))

        if user["email_verified"]:
            flash(_("Your email is already verified. You can log in directly."), "info")
            return redirect(url_for("login"))

        user_id = user["id"]

        # 🔹 Invalida códigos antigos antes de gerar novos
        c.execute("UPDATE verification_codes SET used=1 WHERE email=? AND used=0", (email,))
        conn.commit()

        # 🔹 Gera novo token de link
        token = gerar_token_verificacao(user_id)
        verify_link = url_for("verify_email_route", token=token, _external=True)

        # 🔹 Gera novo código numérico (OTP)
        create_verification_code(email, user_id=user_id, length=8, minutes_valid=10)

        # 🔹 Monta o corpo do e-mail
        html_body = render_template(
            "email_verificacao.html",
            first_name=user["first_name"],
            link_verificacao=verify_link
        )

        text_body = (
            f"Hello {user['first_name']},\n\n"
            f"A new verification link and code were generated for your T-Lux account.\n\n"
            f"Link: {verify_link}\n\n"
            f"This link and code expire in 10 minutes.\n\n"
            f"— T-Lux Unlock Systems"
        )

        # 🔹 Envia o e-mail
        send_email(
            to_email=email,
            subject="🔁 New Verification Code — T-Lux Unlock Systems",
            body_text=text_body,
            body_html=html_body
        )

        flash(_("📩 A new verification link and code were sent to your email."), "info")
        registrar_evento(user_id, "Resent email verification code")

    except Exception as e:
        if conn:
            conn.rollback()
        app.logger.error(f"[EMAIL ERROR][Resend] {e}")
        flash(_("⚠️ Failed to send a new verification email. Try again later."), "danger")

    finally:
        if conn:
            # o teardown já fecha automaticamente
            pass

    return redirect(url_for("verify_email_route", token=token))

#-----------------------------------
# logou route
#-----------------------------------
@app.route("/logout", methods=["GET", "POST"])
def logout():
    user_id = session.get("user_id")

    # registra evento se houver usuário logado
    if user_id:
        try:
            registrar_evento(user_id, "Logout efetuado")
        except Exception:
            pass  # não deixa erro de log quebrar logout

    # limpa sessão por completo
    session.clear()

    # feedback ao usuário
    flash("Sessão terminada com sucesso.", "info")

    # redireciona para login
    return redirect(url_for("login"))

# ----------------------
# 📩 CHECK EMAIL PAGE — After Registration
# ----------------------
@app.route("/check_email")
def check_email():
    """
    Informs the user that a verification email has been sent,
    showing options to resend it if needed.
    """
    # 1️⃣ Security: ensure there is a valid session
    if not session.get("user_id") or not session.get("email"):
        flash("Please log in first.", "warning")
        return redirect(url_for("login"))

    email = session.get("email")

    # 2️⃣ Optional: check if already verified
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT email_verified FROM users WHERE email=?", (email,))
    user = c.fetchone()
    # conn.close() — fechado pelo teardown

    if user and user["email_verified"]:
        flash("✅ Your email is already verified. You can now log in.", "success")
        return redirect(url_for("login"))

    # 3️⃣ Render info page
    return render_template("check_email.html", email=email)

# -----------------------
# Verifica se usuário tem licença ativa
# -----------------------
def has_active_access(user):
    """
    Verifica se o usuário tem uma licença ativa / acesso ativo.
    """
    if not user:
        return False

    try:
        exp = user["access_expiry"]  # <-- CORRIGIDO
        if not exp:
            return False

        if isinstance(exp, str):
            exp = datetime.fromisoformat(exp)

        return exp > datetime.now()
    except Exception as e:
        app.logger.error(f"[ACCESS_CHECK_ERROR] {e}")
        return False

#----------------------
# Dashboard
#----------------------
@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()

    if not has_active_access(user):
        flash("Sua licença expirou ou não está ativa. Escolha um pacote para continuar.", "warning")
        return redirect(url_for("choose_package"))

    conn = get_db()
    c = conn.cursor()

    try:
        c.execute("SELECT * FROM licenses WHERE user_id=? ORDER BY issued_at DESC", (user["id"],))
        licenses = c.fetchall()
    except Exception:
        licenses = []

    c.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY created_at DESC", (user["id"],))
    transacoes = c.fetchall()

    try:
        c.execute("SELECT * FROM logs_desbloqueio WHERE user_id=? ORDER BY created_at DESC", (user["id"],))
        desbloqueios = c.fetchall()
    except Exception:
        desbloqueios = []

    # conn.close() — fechado pelo teardown

    # ✅ Registra o evento após fechar o banco principal
    registrar_evento(user["id"], "Acessou o painel/dashboard")

    saldo = user.get("saldo", 0)
    licenca_ativa = bool(user.get("access_expiry") and user["access_expiry"] > now_str())

    return render_template(
        "dashboard.html",
        user=user,
        saldo=saldo,
        desbloqueios=desbloqueios,
        transacoes=transacoes,
        licenses=licenses,
        modelos=MODELOS_IPHONE_USD_SINAL,
        licenca_ativa=licenca_ativa
    )

# -----------------------
# Fluxo de Pacotes / Chaves de Acesso (Planos T-Lux)
# -----------------------

@app.route("/choose-package")
@login_required
def choose_package():
    """
    Exibe os pacotes de acesso disponíveis (Starter, Bronze, Silver, Gold, Premium)
    para o usuário ativar a conta.
    """
    user = current_user()

    return render_template(
        "choose_package.html",
        user=user,
        pacotes=PACOTES,  # lista de dicionários
        publishable_key=os.getenv("STRIPE_PUBLISHABLE_KEY")
    )

# ---------------------------
# Fluxo pagamento de pacotes
# ---------------------------
@app.route("/pagar_pacote", methods=["POST"])
@login_required
def pagar_pacote():
    """
    Inicia o pagamento Stripe de um pacote de licença (em USD).
    A ativação é confirmada automaticamente via webhook Stripe.
    """
    user = current_user()
    pacote_nome = request.form.get("pacote", "").strip()

    # 🔒 Procurar o pacote pelo nome
    pacote = next((p for p in PACOTES if p["nome"] == pacote_nome), None)
    if not pacote:
        flash("❌ Invalid package selection.", "danger")
        app.logger.warning(f"Tentativa de pacote inválido: {pacote_nome}")
        return redirect(url_for("choose_package"))

    # 💵 Valor em dólares
    amount_usd = float(pacote["preco_usd"])

    # 🔹 Referência única da transação
    tx_ref = f"TLUXPKG-{user['id']}-{secrets.token_hex(6)}-{int(datetime.now().timestamp())}"

    # 🔹 URLs de retorno
    success_url = url_for("dashboard", _external=True) + "?success=1"
    cancel_url = url_for("choose_package", _external=True) + "?canceled=1"

    try:
        # ✅ Criar sessão Stripe Checkout
        session_stripe = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"T-Lux — {pacote['nome']}"},
                    "unit_amount": int(amount_usd * 100),  # Stripe usa centavos
                },
                "quantity": 1,
            }],
            mode="payment",
            client_reference_id=tx_ref,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "user_id": user["id"],
                "pacote": pacote["nome"],
                "dias": pacote["dias"],
                "tx_ref": tx_ref
            }
        )

        # 💾 Registrar transação no banco
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO transactions 
            (user_id, purpose, pacote, modelo, amount, tx_ref, status, stripe_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user["id"], "package", pacote["nome"], None, amount_usd,
            tx_ref, "pending", session_stripe.id, now_str()
        ))
        conn.commit()
        # conn.close() — fechado pelo teardown

        print(f"✅ Stripe session created: {session_stripe.id}")
        print(f"🔗 Checkout link: {session_stripe.url}")

        return redirect(session_stripe.url, code=303)

    except Exception as e:
        app.logger.error(f"[ERRO STRIPE - PACOTE] {e}")
        flash("⚠️ Unable to start payment at the moment. Please try again shortly.", "danger")
        return redirect(url_for("choose_package"))
# -----------------------
# Detectar modelo a partir da serial/IMEI (simplificado)
# -----------------------
def detect_model_from_serial(serial: str):
    """
    Detecta modelo do iPhone a partir da serial/IMEI.
    ⚠️ Exemplo básico, ideal é integrar com API oficial (ex: IMEI.info).
    """
    s = (serial or "").strip().upper()
    if not s:
        return None

    # Map simples (apenas exemplos básicos)
    if s.startswith("A") or "6S" in s:
        return "iPhone 6s"
    if "6SPLUS" in s:
        return "iPhone 6s Plus"
    if "7PLUS" in s:
        return "iPhone 7 Plus"
    if "7" in s:
        return "iPhone 7"
    if "8PLUS" in s:
        return "iPhone 8 Plus"
    if "8" in s:
        return "iPhone 8"
    if "SE" in s:
        return "iPhone SE"
    if "XSMAX" in s:
        return "iPhone Xs Max"
    if "XS" in s:
        return "iPhone Xs"
    if "XR" in s:
        return "iPhone Xr"
    if "X" in s:
        return "iPhone X"

    if "11PROMAX" in s:
        return "iPhone 11 Pro Max"
    if "11PRO" in s:
        return "iPhone 11 Pro"
    if "11" in s:
        return "iPhone 11"

    if "12PROMAX" in s:
        return "iPhone 12 Pro Max"
    if "12PRO" in s:
        return "iPhone 12 Pro"
    if "12MINI" in s:
        return "iPhone 12 Mini"
    if "12" in s:
        return "iPhone 12"

    if "13PROMAX" in s:
        return "iPhone 13 Pro Max"
    if "13PRO" in s:
        return "iPhone 13 Pro"
    if "13" in s:
        return "iPhone 13"

    if "14PROMAX" in s:
        return "iPhone 14 Pro Max"
    if "14PRO" in s:
        return "iPhone 14 Pro"
    if "14" in s:
        return "iPhone 14"

    if "15PROMAX" in s:
        return "iPhone 15 Pro Max"
    if "15PRO" in s:
        return "iPhone 15 Pro"
    if "15" in s:
        return "iPhone 15"

    if "16PROMAX" in s:
        return "iPhone 16 Pro Max"
    if "16PRO" in s:
        return "iPhone 16 Pro"
    if "16" in s:
        return "iPhone 16"

    return None  # fallback


# -----------------------
# Enviar ordem para iRemoval/DHRU
# -----------------------
def iremoval_unlock(modelo: str, imei: str, user_email: str):
    """
    Envia ordem de desbloqueio para a API iRemoval/DHRU.
    Retorna (success, message, data).
    """
    payload = {
        "key": DHRU_API_KEY,
        "action": "place_order",
        "service_id": obter_service_id(modelo),
        "imei": imei
    }

    try:
        r = requests.post(DHRU_API_URL, data=payload, timeout=30)

        if r.status_code != 200:
            app.logger.error(f"[iRemoval] HTTP {r.status_code} → {r.text}")
            return False, f"Erro HTTP {r.status_code}", {"raw": r.text}

        data = r.json()

        if "error" in data:
            msg = data.get("error", "Erro desconhecido no iRemoval")
            app.logger.error(f"[iRemoval] Falha no pedido: {msg}")
            return False, msg, data

        # Pedido aceito → captura ID
        order_id = data.get("id") or data.get("order_id")
        status = data.get("status", "pending")

        msg = data.get("message", f"Pedido criado (status={status})")

        app.logger.info(f"[iRemoval] Pedido criado → order_id={order_id}, modelo={modelo}, imei={imei}")

        return True, msg, {
            "order_id": order_id,
            "status": status,
            "raw": data
        }

    except Exception as e:
        app.logger.error(f"[iRemoval] Exceção ao enviar pedido: {e}")
        return False, str(e), {}

# -----------------------
# Função auxiliar: detectar modelo a partir de serial/IMEI
# -----------------------
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization")
        if not token:
            return jsonify({"error": "Token ausente"}), 401

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT expires_at FROM tokens WHERE token = ?", (token,))
        result = c.fetchone()
        # conn.close() — fechado pelo teardown

        if not result:
            return jsonify({"error": "Token inválido"}), 401

        expires_at = datetime.strptime(result[0], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > expires_at:
            return jsonify({"error": "Token expirado"}), 401

        return f(*args, **kwargs)
    return decorated

# -----------------------
# Consulta IMEI.info
# -----------------------
def consulta_imei(numero):
    """
    Consulta informações de um IMEI/Serial usando a API IMEI.info.
    Retorna o modelo se encontrado, senão None.
    """
    try:
        url = f"{IMEI_BASE_URL}/check/apple-basic/"
        headers = {"Authorization": f"Token {IMEI_API_KEY}"}
        params = {"imei": numero}

        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            app.logger.warning(f"IMEI.info status {resp.status_code}: {resp.text}")
            return None

        dados = resp.json()
        dados_json = dados.get("data") or dados
        modelo = dados_json.get("model") or dados_json.get("deviceName")
        return modelo
    except Exception as e:
        app.logger.error(f"Erro ao consultar IMEI.info: {e}")
        return None

# -----------------------
# Verificação de Serial / Envio para iRemoval
# -----------------------
@app.route("/verificar_serial", methods=["GET", "POST"])
@login_required
def verificar_serial():
    """
    Fluxo de verificação de desbloqueio:
    - Usuário escolhe modelo do iPhone
    - Digita a serial/IMEI
    - Sistema calcula preço e lucro
    - Exibe tela de confirmação para pagamento
    """
    user = current_user()

    # 1️⃣ Verifica se o usuário tem acesso ativo
    if not has_active_access(user):
        flash("Ative sua conta adquirindo um pacote.", "warning")
        return redirect(url_for("choose_package"))

    # 🧠 Dicionário unificado (Signal + No-Signal)
    MODELOS_IPHONE = {**MODELOS_IPHONE_USD_SINAL, **MODELOS_IPHONE_USD_NO_SIGNAL}

    if request.method == "POST":
        modelo = request.form.get("modelo", "").strip()
        serial = request.form.get("serial", "").strip().upper()  # normalizado

        if not modelo or not serial:
            flash("Escolha um modelo e digite a serial/IMEI.", "danger")
            return redirect(url_for("verificar_serial"))

        # 💰 Busca preços
        preco_cliente = MODELOS_IPHONE.get(modelo)
        preco_fornecedor = PRECO_IREMOVAL_USD.get(modelo, 0.0)

        if not preco_cliente:
            flash(f"Modelo {modelo} não está disponível para desbloqueio.", "warning")
            app.logger.warning(f"Tentativa inválida: modelo {modelo} não listado")
            return redirect(url_for("verificar_serial"))

        lucro = preco_cliente - preco_fornecedor

        return render_template(
            "confirmar_desbloqueio.html",
            user=user,
            serial=serial,
            modelo=modelo,
            preco_cliente=preco_cliente,
            preco_fornecedor=preco_fornecedor,
            lucro=lucro,
            currency="USD"
        )

    # GET → renderiza formulário inicial
    return render_template(
    "verificar_serial.html",
    user=user,
    MODELOS_IPHONE_USD_SINAL=MODELOS_IPHONE_USD_SINAL,
    MODELOS_IPHONE_SEM_SINAL_USD=MODELOS_IPHONE_SEM_SINAL_USD
)

#-----------------------
# Pagar Desbloqueio
#-----------------------
@app.route("/pagar_desbloqueio", methods=["POST"])
@login_required
def pagar_desbloqueio():
    """
    Inicia o fluxo de pagamento e desbloqueio via iRemoval (pós-pago).
    - Cria sessão Stripe
    - Registra transação vinculada
    - Após pagamento, webhook/process_unlock cuidam do desbloqueio
    """
    user = current_user()
    if not has_active_access(user):
        flash("Ative sua conta adquirindo um pacote.", "warning")
        return redirect(url_for("choose_package"))

    modelo = request.form.get("modelo", "").strip()
    serial = request.form.get("serial", "").strip().upper()  # 🔧 normalizado

    if not modelo or not serial:
        flash("Escolha um modelo e insira a serial/IMEI.", "danger")
        return redirect(url_for("verificar_serial"))

    if modelo not in MODELOS_IPHONE_USD:
        flash("Modelo inválido.", "danger")
        app.logger.warning(f"Tentativa de desbloqueio com modelo inválido: {modelo}")
        return redirect(url_for("verificar_serial"))

    preco_cliente = MODELOS_IPHONE_USD[modelo]
    preco_fornecedor = PRECO_IREMOVAL_USD.get(modelo, 0.0)
    lucro = preco_cliente - preco_fornecedor

    tx_ref = f"TLUXULK-{user['id']}-{secrets.token_hex(6)}-{int(datetime.now().timestamp())}"
    success_url = url_for("process_unlock", tx_ref=tx_ref, _external=True)
    cancel_url = url_for("dashboard", _external=True)

    try:
        # 🔹 Criar sessão de pagamento no Stripe
        session_stripe = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"Desbloqueio {modelo} - T-Lux"},
                    "unit_amount": int(preco_cliente * 100),
                },
                "quantity": 1,
            }],
            mode="payment",
            client_reference_id=tx_ref,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "user_id": user["id"],
                "modelo": modelo,
                "imei": serial,
                "tx_ref": tx_ref
            }
        )

        # 🔹 Registrar transação no banco
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO transactions 
            (user_id, purpose, modelo, imei, amount, preco_fornecedor, lucro, tx_ref, status, stripe_id, created_at, processed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            user["id"], "unlock", modelo, serial,
            preco_cliente, preco_fornecedor, lucro,
            tx_ref, "pending", session_stripe.id, now_str()
        ))
        conn.commit()
        # conn.close() — fechado pelo teardown

        print(f"✅ Sessão Stripe criada: {session_stripe.id}")
        print(f"🔗 Link de checkout: {session_stripe.url}")

        return redirect(session_stripe.url, code=303)

    except Exception as e:
        app.logger.error(f"[ERRO STRIPE - UNLOCK] {e}")
        flash("Não foi possível iniciar o pagamento no momento. Tente novamente em instantes.", "danger")
        return redirect(url_for("verificar_serial"))

# -----------------------
# Sucesso de Pagamento
# -----------------------
@app.route("/payment/success")
def payment_success():
    tx_ref = request.args.get("tx_ref")
    # Este endpoint é apenas informativo: a confirmação real vem pelo webhook
    flash("Pagamento realizado. Aguarde confirmação (pode demorar alguns segundos).", "success")
    return redirect(url_for("dashboard"))
    
# -----------------------
# Webhook do Stripe (seguro e automatizado)
# -----------------------
from flask import Response, abort

@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature")

    try:
        # 🔒 Verificação de assinatura Stripe
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        app.logger.error("[WEBHOOK] ❌ Payload inválido recebido")
        return abort(400)
    except stripe.error.SignatureVerificationError:
        app.logger.error("[WEBHOOK] 🚫 Assinatura Stripe inválida")
        return abort(400)
    except Exception as e:
        app.logger.error(f"[WEBHOOK] ⚠️ Erro inesperado na verificação: {e}")
        return abort(400)

    # 🎯 Processa apenas evento de pagamento concluído
    if event["type"] == "checkout.session.completed":
        session_obj = event["data"]["object"]

        # Recupera referência única
        tx_ref = (
            session_obj.get("metadata", {}).get("tx_ref")
            or session_obj.get("client_reference_id")
        )

        if not tx_ref:
            app.logger.error("[WEBHOOK] Sessão Stripe sem tx_ref detectada")
            return abort(400)

        conn = get_db()
        try:
            c = conn.cursor()
            c.execute("SELECT * FROM transactions WHERE tx_ref=?", (tx_ref,))
            tx = c.fetchone()

            if not tx:
                app.logger.error(f"[WEBHOOK] Transação não encontrada (tx_ref={tx_ref})")
                return abort(404)

            # ✅ Atualiza status da transação
            c.execute("""
                UPDATE transactions
                SET status=?, stripe_id=?, updated_at=?
                WHERE id=?
            """, ("successful", session_obj.get("id"), now_str(), tx["id"]))
            conn.commit()

            purpose = (tx["purpose"] or "").lower()

            # --------------------------
            # 🟢 Ativação de Pacote (Licença)
            # --------------------------
            if purpose == "package":
                pacote_nome = tx["pacote"]
                pacote = next((p for p in PACOTES if p["nome"] == pacote_nome), None)

                if not pacote:
                    app.logger.warning(f"[WEBHOOK] Pacote '{pacote_nome}' não encontrado na lista.")
                else:
                    dias = pacote["dias"]

                    try:
                        # Calcula validade
                        data_inicio = datetime.now()
                        data_expira = (
                            data_inicio + timedelta(days=dias)
                            if dias < 9999 else None  # permanente
                        )

                        # Atualiza acesso do usuário
                        c.execute("""
                            UPDATE users
                            SET access_key=?, access_expiry=?
                            WHERE id=?
                        """, (
                            f"KEY-{secrets.token_hex(12)}",
                            data_expira.isoformat() if data_expira else None,
                            tx["user_id"]
                        ))
                        conn.commit()

                        app.logger.info(f"[WEBHOOK] ✅ Licença '{pacote_nome}' ativada por {dias} dias (tx_ref={tx_ref})")

                    except Exception as e:
                        app.logger.error(f"[WEBHOOK] Erro ao emitir licença (tx_ref={tx_ref}) → {e}")

            # --------------------------
            # 🔓 Pedido de desbloqueio automático
            # --------------------------
            elif purpose == "unlock":
                try:
                    c.execute("SELECT email FROM users WHERE id=?", (tx["user_id"],))
                    row = c.fetchone()
                    user_email = row["email"] if row else None

                    ok = _submit_unlock_order(user_email, tx["modelo"], tx["id"])
                    if ok:
                        app.logger.info(f"[WEBHOOK] 🔓 Pedido de desbloqueio submetido (tx_ref={tx_ref})")
                    else:
                        app.logger.warning(f"[WEBHOOK] Falha ao submeter desbloqueio (tx_ref={tx_ref})")
                except Exception as e:
                    app.logger.error(f"[WEBHOOK] Erro ao processar desbloqueio (tx_ref={tx_ref}) → {e}")

            else:
                app.logger.warning(f"[WEBHOOK] Propósito desconhecido: {purpose} (tx_ref={tx_ref})")

        except Exception as e:
            app.logger.error(f"[WEBHOOK] Falha geral ao processar tx_ref={tx_ref} → {e}")
            return abort(500)
        finally:
            try:
                # conn.close() — fechado pelo teardown automaticamente
                pass
            except Exception:
                pass

    return Response(status=200)

@app.route("/receipt_package/<tx_ref>")
@login_required
def receipt_package(tx_ref):
    """Exibe o recibo de pagamento do pacote de acesso."""
    user = current_user()
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM transactions WHERE tx_ref=?", (tx_ref,))
    tx = c.fetchone()

    if not tx:
        flash("Receipt not found.", "warning")
        return redirect(url_for("dashboard"))

    dias = 0
    if tx["pacote"]:
        pacote = next((p for p in PACOTES if p["nome"] == tx["pacote"]), None)
        if pacote:
            dias = pacote["dias"]

    # Busca chave de acesso atual
    c.execute("SELECT access_key FROM users WHERE id=?", (user["id"],))
    user_key = c.fetchone()

    return render_template(
        "receipt_package.html",
        user=user,
        tx_ref=tx_ref,
        pacote_nome=tx["pacote"],
        dias=dias,
        preco_cliente=tx["preco_cliente"],
        currency=tx["currency"],
        access_key=user_key["access_key"] if user_key else None,
        payment_date=tx["created_at"],
        now=datetime.now()
    )

# -----------------------
# Acesso Técnico (solicitação)
# -----------------------
@app.route("/obter_tecnico", methods=["GET", "POST"])
@login_required
def obter_tecnico():
    user = current_user()  # pega usuário logado
    
    if request.method == "POST":
        # -----------------------
        # Flash de confirmação
        # -----------------------
        flash("Solicitação para Acesso Técnico recebida. Entraremos em contato.", "info")

        # -----------------------
        # Log no Flask
        # -----------------------
        app.logger.info(f"Usuário {user['email']} solicitou Acesso Técnico.")

        # -----------------------
        # Salva no banco (tech_requests)
        # -----------------------
        try:
            conn = get_db()
            c = conn.cursor()
            c.execute(
                "INSERT INTO tech_requests (user_email, mensagem) VALUES (?, ?)",
                (user['email'], "Solicitação de Acesso Técnico")
            )
            conn.commit()
            # conn.close() — fechado pelo teardown
        except Exception as e:
            app.logger.error(f"Erro ao salvar solicitação técnica: {e}")

        # -----------------------
        # Notificação por email ao técnico
        # -----------------------
        try:
            send_email(TECH_EMAIL, "[T-Lux] Solicitação de Acesso Técnico", f"Usuário: {user['email']}")
        except Exception as e:
            app.logger.warning(f"Falha ao enviar email de notificação: {e}")

        return redirect(url_for("dashboard"))

    # GET: mostra a página de requisitos / formulário
    return render_template("obter_tecnico.html", user=user)

# -----------------------
# Painel de Solicitações Técnicas (para o técnico)
# -----------------------
@app.route("/painel/tech_requests", methods=["GET", "POST"])
@login_required
def painel_tech_requests():
    user = current_user()

    # Verifica se o usuário é técnico/admin
    if not user.get("is_admin", 0):
        flash("Acesso negado.", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db()
    c = conn.cursor()

    # Se o técnico atualizar o status de uma solicitação
    if request.method == "POST":
        request_id = request.form.get("request_id")
        novo_status = request.form.get("status")
        if request_id and novo_status:
            try:
                c.execute(
                    "UPDATE tech_requests SET status = ? WHERE id = ?",
                    (novo_status, request_id)
                )
                conn.commit()
                flash(f"Solicitação {request_id} atualizada para '{novo_status}'.", "success")
            except Exception as e:
                flash(f"Erro ao atualizar solicitação: {e}", "danger")

    # Busca todas as solicitações
    c.execute("SELECT * FROM tech_requests ORDER BY criado_em DESC")
    requests_list = c.fetchall()
    # conn.close() — fechado pelo teardown

    return render_template("painel_tech_requests.html", requests=requests_list, user=user)


# -----------------------
# Desbloquear (rota antiga mantida para compatibilidade — agora não usada diretamente)
# -----------------------
@app.route("/desbloquear", methods=["POST"])
@login_required
def desbloquear():
    # Mantida como compat: preferir fluxo verificar_serial -> pagar_desbloqueio
    user = current_user()
    modelo = request.form.get("modelo")
    if not modelo or modelo not in MODELOS_IPHONE:
        flash("Modelo inválido para desbloqueio.", "danger")
        return redirect(url_for("dashboard"))
    flash(f"Solicitação de desbloqueio para {modelo} recebida (fluxo antigo). Use o fluxo novo com serial.", "info")
    log("INFO", f"Usuário {user['email']} solicitou desbloqueio (legacy) do modelo {modelo}")
    return redirect(url_for("dashboard"))

# -----------------------
# Admin + Ações
# -----------------------
@app.route("/admin")
@login_required
def admin():
    u = current_user()
    if not u or not u["is_admin"]:
        flash("Acesso negado.", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = c.fetchall()
    c.execute("SELECT * FROM transactions ORDER BY created_at DESC")
    transactions = c.fetchall()
    c.execute("SELECT * FROM licenses ORDER BY issued_at DESC")
    licenses = c.fetchall()
    # conn.close() — fechado pelo teardown

    return render_template("admin.html", users=users, transactions=transactions, licenses=licenses)

@app.route("/admin/tx/<int:tx_id>/approve", methods=["POST"])
@login_required
def admin_tx_approve(tx_id):
    u = current_user()
    if not u or not u["is_admin"]:
        flash("Acesso negado.", "danger")
        return redirect(url_for("admin"))
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE transactions SET status=?, updated_at=? WHERE id=?",
              ("successful", now_str(), tx_id))
    conn.commit()
    # conn.close() — fechado pelo teardown

    # Se for pacote, emite licença; se for desbloqueio, apenas loga
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM transactions WHERE id=?", (tx_id,))
    tx = c.fetchone()
    # conn.close() — fechado pelo teardown
    if tx and (tx["purpose"] or "").lower() == "package":
        _issue_license_from_tx(tx_id)
        flash("Transação (pacote) aprovada e licença emitida.", "success")
    else:
        flash("Transação aprovada.", "success")
    return redirect(url_for("admin"))

@app.route("/admin/tx/<int:tx_id>/fail", methods=["POST"])
@login_required
def admin_tx_fail(tx_id):
    u = current_user()
    if not u or not u["is_admin"]:
        flash("Acesso negado.", "danger")
        return redirect(url_for("admin"))
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE transactions SET status=?, updated_at=? WHERE id=?",
              ("failed", now_str(), tx_id))
    conn.commit()
    # conn.close() — fechado pelo teardown
    flash("Transação marcada como falhada.", "warning")
    return redirect(url_for("admin"))

@app.route("/admin/license/<int:lic_id>/revoke", methods=["POST"])
@login_required
def admin_license_revoke(lic_id):
    u = current_user()
    if not u or not u["is_admin"]:
        flash("Acesso negado.", "danger")
        return redirect(url_for("admin"))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id, license_key FROM licenses WHERE id=?", (lic_id,))
    row = c.fetchone()
    if not row:
        # conn.close() — fechado pelo teardown
        flash("Licença não encontrada.", "danger")
        return redirect(url_for("admin"))
    user_id = row["user_id"]
    lic_key = row["license_key"]
    c.execute("DELETE FROM licenses WHERE id=?", (lic_id,))
    c.execute("UPDATE users SET access_key=NULL, access_expiry=NULL WHERE id=? AND access_key=?", (user_id, lic_key))
    conn.commit()
    # conn.close() — fechado pelo teardown
    flash("Licença revogada.", "info")
    return redirect(url_for("admin"))

# -----------------------
# Logs e Overview
# -----------------------
@app.route("/admin/logs")
@login_required
def admin_logs():
    u = current_user()
    if not u or not u["is_admin"]:
        flash("Acesso negado.", "danger")
        return redirect(url_for("dashboard"))
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM logs ORDER BY created_at DESC LIMIT 100")
    logs = c.fetchall()
    # conn.close() — fechado pelo teardown
    return render_template("admin_logs.html", logs=logs)

@app.route("/admin/overview")
@login_required
def admin_overview():
    u = current_user()
    if not u or not u["is_admin"]:
        flash("Acesso negado.", "danger")
        return redirect(url_for("dashboard"))
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as total_users FROM users")
    total_users = c.fetchone()["total_users"]
    c.execute("SELECT COUNT(*) as total_tx FROM transactions")
    total_tx = c.fetchone()["total_tx"]
    c.execute("SELECT COUNT(*) as pending_tx FROM transactions WHERE status='pending'")
    pending_tx = c.fetchone()["pending_tx"]
    c.execute("SELECT COUNT(*) as successful_tx FROM transactions WHERE status='successful'")
    successful_tx = c.fetchone()["successful_tx"]
    c.execute("SELECT COUNT(*) as failed_tx FROM transactions WHERE status='failed'")
    failed_tx = c.fetchone()["failed_tx"]
    c.execute("SELECT COUNT(*) as total_licenses FROM licenses")
    total_licenses = c.fetchone()["total_licenses"]
    c.execute("SELECT COUNT(*) as expired_licenses FROM licenses WHERE expires_at < ?", (now_str(),))
    expired_licenses = c.fetchone()["expired_licenses"]
    # conn.close() — fechado pelo teardown
    
    overview = {
        "total_users": total_users,
        "total_tx": total_tx,
        "pending_tx": pending_tx,
        "successful_tx": successful_tx,
        "failed_tx": failed_tx,
        "total_licenses": total_licenses,
        "expired_licenses": expired_licenses
    }
    return render_template("admin_overview.html", overview=overview)

@app.route("/admin/update_services")
@login_required
def update_services():
    user = current_user()
    if not user["is_admin"]:
        flash("Acesso negado!", "danger")
        return redirect(url_for("dashboard"))

    if atualizar_servicos():
        flash("✅ Lista de serviços atualizada com sucesso!", "success")
    else:
        flash("❌ Falha ao atualizar serviços.", "danger")
    return redirect(url_for("services"))

@app.route("/admin/transactions")
@login_required
def admin_transactions():
    # Garante que só admin acessa
    if not session.get("is_admin"):
        flash("Acesso negado. Apenas administradores podem visualizar transações.", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT t.id, u.email, t.modelo, t.imei, t.sem_sinal, 
               t.amount AS preco_venda, t.preco_fornecedor, t.lucro, 
               t.status, t.order_id, t.created_at
        FROM transactions t
        LEFT JOIN users u ON t.user_id = u.id
        ORDER BY t.created_at DESC
    """)
    rows = c.fetchall()
    # conn.close() — fechado pelo teardown

    return render_template("admin_transactions.html", transactions=rows)

# -----------------------
# Painel: Lista de desbloqueios com status
# -----------------------
@app.route("/painel/unlocks")
@login_required
def painel_unlocks():
    """
    Exibe todos os desbloqueios do usuário logado,
    mostrando status em tempo real usando order_id da iRemoval.
    """
    user_id = session["user_id"]
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM transactions WHERE user_id=? AND purpose='unlock' ORDER BY created_at DESC",
        (user_id,)
    )
    rows = c.fetchall()
    # conn.close() — fechado pelo teardown

    desbloqueios = []
    for tx in rows:
        status_info = consultar_status_unlock(tx["id"])
        desbloqueios.append({
            "tx_id": tx["id"],
            "modelo": tx["modelo"],
            "imei": tx.get("modelo", ""),  # ou a coluna correta do IMEI
            "preco": tx["amount"],
            "created_at": tx["created_at"],
            "status": status_info["status"],
            "message": status_info["message"],
            "order_id": tx.get("order_id")
        })

    return render_template("painel_unlocks.html", desbloqueios=desbloqueios)

# -----------------------
# Painel: fornece status de desbloqueios em JSON (AJAX)
# -----------------------
@app.route("/painel/unlocks/status")
@login_required
def painel_unlocks_status():
    """
    Retorna o status de todos os desbloqueios do usuário logado em JSON.
    Inclui informações de Full Signal e mensagens personalizadas.
    """
    user_id = session.get("user_id")
    if not user_id:
        return {"desbloqueios": []}, 401  # Usuário não autenticado

    try:
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM transactions WHERE user_id=? AND purpose='unlock' ORDER BY created_at DESC",
            (user_id,)
        )
        rows = c.fetchall()
        # conn.close() — fechado pelo teardown
    except Exception as e:
        log("ERROR", f"Erro ao buscar desbloqueios do usuário {user_id}: {e}")
        return {"desbloqueios": []}, 500

    desbloqueios = []
    for tx in rows:
        status_info = consultar_status_unlock(tx["id"])

        modelo = tx.get("modelo", "Desconhecido")
        imei = tx.get("imei") or tx.get("modelo", "")

        # Full Signal direto ou precisa restaurar
        if modelo in MODELOS_FULL_SIGNAL:
            full_signal = "Sim"
            full_signal_message = "🔓 Full Signal desbloqueado com sucesso!"
        else:
            full_signal = "Restauração necessária"
            full_signal_message = "🔧 Para ativar Full Signal, restaure o iPhone via iTunes/Finder."

        desbloqueios.append({
            "tx_id": tx.get("id"),
            "modelo": modelo,
            "imei": imei,
            "preco": tx.get("amount", 0),
            "created_at": tx.get("created_at"),
            "status": status_info.get("status", "pendente"),
            "message": status_info.get("message", ""),
            "order_id": tx.get("order_id"),
            "full_signal": full_signal,
            "full_signal_message": full_signal_message
        })

    return {"desbloqueios": desbloqueios}
    
# -----------------------------
# 🔍 Função para obter transação pelo tx_ref
# -----------------------------
def obter_transacao(tx_ref: str):
    """
    Retorna os detalhes de uma transação a partir do tx_ref.
    Usado no painel e no processamento do desbloqueio.
    """
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT * FROM transactions WHERE tx_ref = ?
        """, (tx_ref,))
        row = c.fetchone()
        return dict(row) if row else None
    except Exception as e:
        app.logger.error(f"[DB] Erro ao buscar transação {tx_ref}: {e}")
        return None

# -----------------------
# Processar unlock após pagamento
# -----------------------
@app.route("/process_unlock/<tx_ref>")
@login_required
def process_unlock(tx_ref):
    """
    Processa o desbloqueio após o pagamento:
    - Busca transação no banco
    - Envia ordem ao iRemoval
    - Salva order_id, status e marca processed=1
    - Renderiza resultado final
    """
    user = current_user()

    unlock_info = obter_transacao(tx_ref)
    if not unlock_info:
        flash("Transação não encontrada.", "danger")
        return redirect(url_for("painel_unlocks"))

    imei = unlock_info.get("serial") or unlock_info.get("imei")
    modelo = unlock_info["modelo"]
    preco_fornecedor = unlock_info.get("preco_fornecedor", 0.0)
    lucro = unlock_info.get("lucro", 0.0)

    # 🔹 Enviar requisição real para iRemoval
    try:
        resposta = enviar_para_iremoval(imei, modelo, preco_fornecedor)
    except Exception as e:
        resposta = {"error": str(e)}

    if "error" in resposta:
        status = "failed"
        order_id = None
        msg = resposta["error"]
    else:
        order_id = resposta.get("id") or resposta.get("order_id")
        status = resposta.get("status", "pending").lower()
        msg = resposta.get("msg", "Ordem enviada com sucesso.")

    # 🔹 Atualizar transação no BD
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        UPDATE transactions
        SET order_id=?, status=?, processed=1, updated_at=?
        WHERE tx_ref=?
    """, (order_id, status, now_str(), tx_ref))
    conn.commit()
    # conn.close() — fechado pelo teardown

    return render_template(
        "resultado_desbloqueio.html",
        user=user,
        serial=imei,
        modelo=modelo,
        preco_fornecedor=preco_fornecedor,
        lucro=lucro,
        status=status,
        message=msg,
        order_id=order_id
    )

# -----------------------
# Consultar status de um unlock
# -----------------------
@app.route("/status_unlock/<tx_ref>")
@login_required
def status_unlock(tx_ref):
    """
    Consulta o status atualizado de um desbloqueio no iRemoval:
    - Busca transação pelo tx_ref
    - Consulta API iRemoval pelo order_id
    - Atualiza status no banco
    - Renderiza resultado para o usuário
    """
    user = current_user()

    # 🔹 Buscar transação
    unlock_info = obter_transacao(tx_ref)
    if not unlock_info:
        flash("Transação não encontrada.", "danger")
        return redirect(url_for("painel_unlocks"))

    order_id = unlock_info.get("order_id")
    if not order_id:
        flash("Order ID não encontrado para esta transação.", "warning")
        return redirect(url_for("painel_unlocks"))

    # 🔹 Consultar status no iRemoval
    try:
        resposta = consultar_status(order_id)
    except Exception as e:
        app.logger.error(f"[UNLOCK STATUS] Falha ao consultar iRemoval (order_id={order_id}) → {e}")
        resposta = {"error": str(e)}

    if "error" in resposta:
        status = "failed"
        msg = resposta["error"]
    else:
        status = resposta.get("status", "pending").lower()
        msg = resposta.get("msg", "Consulta realizada com sucesso.")

    # 🔹 Atualizar status no banco
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("""
            UPDATE transactions
            SET status=?, updated_at=?
            WHERE tx_ref=?
        """, (status, now_str(), tx_ref))
        conn.commit()
    except Exception as e:
        app.logger.error(f"[UNLOCK STATUS] Erro ao atualizar transação no BD (tx_ref={tx_ref}) → {e}")
        flash("Erro interno ao atualizar status no banco.", "danger")
    finally:
        try:
            # conn.close() — fechado automaticamente pelo teardown
            pass
        except Exception:
            pass

    # 🔹 Renderizar resultado
    return render_template(
        "status_desbloqueio.html",
        user=user,
        tx_ref=tx_ref,
        order_id=order_id,
        modelo=unlock_info["modelo"],
        imei=unlock_info["serial"],   # ⚡ trocado para imei no template
        status=status,
        message=msg
    )

# -----------------------
# Listagem AJAX de desbloqueios do usuário
# -----------------------
@app.route("/painel/unlocks/status")
@login_required
def painel_unlocks_status_v2():
    """
    Retorna JSON com todos os desbloqueios do usuário logado.
    Usado para preencher tabela no painel via AJAX.
    """
    user = current_user()

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, modelo, imei, amount AS preco_cliente,
               preco_fornecedor, lucro, order_id, status,
               created_at, updated_at
        FROM transactions
        WHERE user_id=? AND purpose='unlock'
        ORDER BY created_at DESC
    """, (user["id"],))
    rows = c.fetchall()
    # conn.close() — fechado pelo teardown

    desbloqueios = []
    for row in rows:
        desbloqueios.append({
            "tx_id": row["id"],
            "modelo": row["modelo"],
            "imei": row["imei"],
            "preco_cliente": row["preco_cliente"] or 0.0,
            "preco_fornecedor": row["preco_fornecedor"] or 0.0,
            "lucro": row["lucro"] or 0.0,
            "order_id": row["order_id"],
            "status": row["status"] or "pending",
            "message": "",
            "full_signal": "Sim" if "Pro" in (row["modelo"] or "") else "Instruções",
            "full_signal_message": "Para restaurar o Full Signal, siga as instruções no suporte T-LUX.",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        })

    return jsonify({"desbloqueios": desbloqueios})

# -----------------------
# Painel Admin - Unlocks
# -----------------------
@app.route("/admin/unlocks")
@login_required
def admin_unlocks():
    user = current_user()
    if not user.get("is_admin"):
        flash("Acesso negado. Apenas administradores.", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db()
    c = conn.cursor()

    # 🔹 Estatísticas gerais de desbloqueios
    c.execute("""
        SELECT 
            COALESCE(SUM(amount), 0) AS total_receita,
            COALESCE(SUM(preco_fornecedor), 0) AS total_fornecedor,
            COALESCE(SUM(lucro), 0) AS total_lucro
        FROM transactions 
        WHERE purpose = 'unlock'
    """)
    stats_row = c.fetchone()
    stats = {
        "total_receita": round(stats_row["total_receita"], 2) if stats_row else 0.0,
        "total_fornecedor": round(stats_row["total_fornecedor"], 2) if stats_row else 0.0,
        "total_lucro": round(stats_row["total_lucro"], 2) if stats_row else 0.0,
    }

    # 🔹 Pedidos pendentes
    c.execute("""
        SELECT 
            t.id, 
            u.email AS user_email, 
            t.modelo, 
            t.imei, 
            t.amount, 
            t.preco_fornecedor, 
            t.lucro, 
            t.status,
            t.created_at
        FROM transactions t
        JOIN users u ON u.id = t.user_id
        WHERE t.purpose = 'unlock' 
          AND t.status IN ('pending','processing')
        ORDER BY t.created_at DESC
    """)
    pendentes = [dict(r) for r in c.fetchall()]

    # 🔹 Histórico de desbloqueios
    c.execute("""
        SELECT 
            t.id, 
            u.email AS user_email, 
            t.modelo, 
            t.imei, 
            t.amount, 
            t.preco_fornecedor, 
            t.lucro, 
            t.status,
            t.created_at
        FROM transactions t
        JOIN users u ON u.id = t.user_id
        WHERE t.purpose = 'unlock' 
          AND t.status NOT IN ('pending','processing')
        ORDER BY t.created_at DESC
        LIMIT 50
    """)
    historico = [dict(r) for r in c.fetchall()]

    # conn.close() — fechado pelo teardown

    return render_template(
        "admin_unlocks.html",
        user=user,
        stats=stats,
        pendentes=pendentes,
        historico=historico
    )


@app.route("/admin/unlocks/status")
@login_required
def admin_unlocks_status():
    """
    Retorna em JSON todos os desbloqueios (admin).
    Inclui informações do usuário, valores e status.
    """
    user = current_user()
    if not user.get("is_admin"):
        flash("Acesso negado. Apenas administradores podem visualizar.", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT t.id, t.user_id, u.email, u.username, t.modelo, t.imei,
               t.amount AS preco_cliente, t.preco_fornecedor, t.lucro,
               t.order_id, t.status, t.created_at, t.updated_at
        FROM transactions t
        LEFT JOIN users u ON u.id = t.user_id
        WHERE t.purpose='unlock'
        ORDER BY t.created_at DESC
    """)
    rows = c.fetchall()
    # conn.close() — fechado pelo teardown

    desbloqueios = []
    for row in rows:
        desbloqueios.append({
            "tx_id": row["id"],
            "user_id": row["user_id"],
            "email": row["email"],
            "username": row["username"],
            "modelo": row["modelo"],
            "imei": row["imei"],
            "preco_cliente": row["preco_cliente"] or 0.0,
            "preco_fornecedor": row["preco_fornecedor"] or 0.0,
            "lucro": row["lucro"] or 0.0,
            "order_id": row["order_id"],
            "status": row["status"] or "pending",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"]
        })

    return jsonify({"desbloqueios": desbloqueios})

# -----------------------
# Admin - Forçar atualização de status (forçar consulta ao iRemoval)
# -----------------------
@app.route("/admin/forcar_status/<int:tx_id>", endpoint="admin_forcar_status_route")
@login_required
def admin_forcar_status(tx_id):
    """
    Rota que o admin usa para forçar a atualização do status de um unlock.
    Faz:
      - Verifica permissões de admin
      - Lê a transação pelo tx_id
      - Chama consultar_status(order_id)
      - Atualiza status no DB e informa o admin (flash)
    """
    user = current_user()
    if not user.get("is_admin"):
        flash("Acesso negado. Apenas administradores.", "danger")
        return redirect(url_for("dashboard"))

    # Busca transação
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, order_id, tx_ref, modelo, imei FROM transactions WHERE id=?", (tx_id,))
    row = c.fetchone()
    if not row:
        # conn.close() — fechado pelo teardown
        flash("Transação não encontrada.", "danger")
        return redirect(url_for("admin_unlocks"))

    order_id = row["order_id"]

    if not order_id:
        # conn.close() — fechado pelo teardown
        flash("Order ID não encontrado. Verifique se o processamento (/process_unlock) já foi executado.", "warning")
        return redirect(url_for("admin_unlocks"))

    # Consulta status real no iRemoval
    try:
        result = consultar_status(order_id)
    except Exception as e:
        # conn.close() — fechado pelo teardown
        flash(f"Erro ao contactar iRemoval: {e}", "danger")
        return redirect(url_for("admin_unlocks"))

    # Normaliza resposta
    if "error" in result:
        new_status = "failed"
        message = result.get("error")
    else:
        new_status = result.get("status", result.get("state", "pending")).lower()
        message = result.get("message") or result.get("msg") or ""

    # Atualiza DB
    c.execute(
        "UPDATE transactions SET status=?, updated_at=? WHERE id=?",
        (new_status, now_str(), tx_id)
    )
    conn.commit()
    # conn.close() — fechado pelo teardown

    flash(f"Status atualizado para '{new_status}'. {message}", "info")
    return redirect(url_for("admin_unlocks"))

@app.route("/admin/dashboard")
@login_required
def admin_dashboard():
    # Permitir só admin
    if not session.get("is_admin"):
        abort(403)

    conn = get_db()
    c = conn.cursor()

    # Total de usuários
    c.execute("SELECT COUNT(*) as total_users FROM users")
    row = c.fetchone()
    total_users = row["total_users"] or 0

    # Transações totais e receita
    c.execute("SELECT COUNT(*) as total_tx, COALESCE(SUM(amount),0) as total_valor FROM transactions")
    tx_stats = c.fetchone()
    total_transactions = tx_stats["total_tx"] or 0
    receita_total = tx_stats["total_valor"] or 0.0

    # Total pago ao fornecedor
    c.execute("SELECT COALESCE(SUM(preco_fornecedor),0) as total_fornecedor FROM transactions")
    fornecedor = c.fetchone()["total_fornecedor"] or 0.0

    # Lucro líquido (opcional)
    lucro = receita_total - fornecedor

    # Total de desbloqueios (considerando transactions.purpose = 'unlock')
    c.execute("SELECT COUNT(*) as total_unlocks FROM transactions WHERE purpose = 'unlock'")
    total_unlocks = c.fetchone()["total_unlocks"] or 0

    # Desbloqueios pendentes (limit 10)
    c.execute("""
        SELECT t.id, t.modelo, t.imei, t.status, u.email as user_email, t.created_at
        FROM transactions t
        JOIN users u ON u.id = t.user_id
        WHERE t.purpose = 'unlock' AND t.status = 'pending'
        ORDER BY t.created_at DESC
        LIMIT 10
    """)
    pendentes = c.fetchall()

    # Últimos usuários
    c.execute("SELECT id, first_name, last_name, email, created_at FROM users ORDER BY created_at DESC LIMIT 10")
    ultimos_usuarios = c.fetchall()

    # Últimos desbloqueios (últimos 10 registros em transactions com purpose=unlock)
    c.execute("""
        SELECT t.id, t.created_at as data_hora, u.email as user_email, t.modelo, t.status
        FROM transactions t
        LEFT JOIN users u ON u.id = t.user_id
        WHERE t.purpose = 'unlock'
        ORDER BY t.created_at DESC
        LIMIT 10
    """)
    ultimos_desbloqueios = c.fetchall()

    # Últimas 20 transações
    c.execute("SELECT * FROM transactions ORDER BY created_at DESC LIMIT 20")
    ultimas_transacoes = c.fetchall()

    # Últimos logs do sistema (logs_desbloqueio ou logs)
    # preferimos logs_desbloqueio se tiver; caso contrário, pega logs
    try:
        c.execute("""
            SELECT l.*, u.email as user_email
            FROM logs_desbloqueio l
            LEFT JOIN users u ON u.id = l.user_id
            ORDER BY l.data_hora DESC
            LIMIT 20
        """)
        ultimos_logs = c.fetchall()
    except Exception:
        c.execute("""
            SELECT l.*, u.email as user_email
            FROM logs l
            LEFT JOIN users u ON u.id = l.user_id
            ORDER BY l.created_at DESC
            LIMIT 20
        """)
        ultimos_logs = c.fetchall()

    # conn.close() — fechado pelo teardown

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        total_transactions=total_transactions,
        total_unlocks=total_unlocks,
        receita_total=receita_total,
        fornecedor=fornecedor,
        lucro=lucro,
        pendentes=pendentes,
        ultimos_usuarios=ultimos_usuarios,
        ultimos_desbloqueios=ultimos_desbloqueios,
        ultimas_transacoes=ultimas_transacoes,
        ultimos_logs=ultimos_logs
    )

# -----------------------
# Rota para criar sessão de checkout Stripe
# -----------------------
from flask import jsonify

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    """Cria uma sessão de pagamento no Stripe para pacotes ou desbloqueios."""
    try:
        data = request.json  # deve vir do frontend (JS ou fetch)
        pacote = data.get("pacote")
        modelo = data.get("modelo")   # usado se for desbloqueio
        purpose = data.get("purpose") # "package" ou "unlock"
        user_id = session.get("user_id")

        if not user_id:
            return jsonify({"error": "Usuário não autenticado"}), 401

        if not purpose or purpose not in ["package", "unlock"]:
            return jsonify({"error": "Purpose inválido"}), 400

        conn = get_db()
        c = conn.cursor()

        # Valor conforme o pacote ou desbloqueio
        if purpose == "package":
            pacote_info = PACOTES_USD.get(pacote)
            if not pacote_info:
                # conn.close() — fechado pelo teardown
                return jsonify({"error": "Pacote inválido"}), 400
            amount = int(pacote_info["price"] * 100)  # Stripe espera em centavos
            description = f"Pacote {pacote}"
        else:  # desbloqueio
            if not modelo:
                # conn.close() — fechado pelo teardown
                return jsonify({"error": "Modelo obrigatório para unlock"}), 400
            preco_unlock = UNLOCK_PRECOS.get(modelo, 99.99)  # fallback
            amount = int(preco_unlock * 100)
            description = f"Desbloqueio {modelo}"

        # Cria referência única de transação
        tx_ref = str(uuid.uuid4())

        # Grava transação no BD
        c.execute("""
            INSERT INTO transactions (tx_ref, user_id, pacote, modelo, amount, status, purpose, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (tx_ref, user_id, pacote, modelo, amount/100, "pending", purpose, now_str()))
        conn.commit()
        tx_id = c.lastrowid
        # conn.close() — fechado pelo teardown

        # Cria sessão Stripe
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": description},
                    "unit_amount": amount,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=url_for("dashboard", _external=True) + "?success=1",
            cancel_url=url_for("dashboard", _external=True) + "?canceled=1",
            client_reference_id=tx_ref
        )

        return jsonify({"id": checkout_session.id, "url": checkout_session.url})

    except Exception as e:
        log("ERROR", f"Erro ao criar checkout: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/checkout/<purpose>/<item>")
def checkout_page(purpose, item):
    """
    Renderiza a página de checkout para Stripe.
    purpose = "package" ou "unlock"
    item = nome do pacote (Bronze, Ouro, etc) ou modelo do iPhone
    """
    preco_usd = 0.0

    if purpose == "package":
        pacote_info = PACOTES_USD.get(item)
        if not pacote_info:
            flash("Pacote inválido.", "danger")
            return redirect(url_for("dashboard"))
        preco_usd = pacote_info["price"]

    elif purpose == "unlock":
        preco_usd = UNLOCK_PRECOS.get(item, 99.99)  # fallback se não definido

    else:
        flash("Tipo de checkout inválido.", "danger")
        return redirect(url_for("dashboard"))

    return render_template(
        "checkout.html",
        purpose=purpose,
        pacote=item if purpose == "package" else "",
        modelo=item if purpose == "unlock" else "",
        preco_usd=preco_usd
    )

@app.route("/services")
@login_required
def services():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM services ORDER BY group_name, nome")
    servicos = c.fetchall()
    # conn.close() — fechado pelo teardown
    return render_template("services.html", servicos=servicos)

@app.route("/comprar_servico/<int:service_id>", methods=["GET", "POST"])
@login_required
def comprar_servico(service_id):
    user = current_user()

    # Buscar serviço no banco
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM services WHERE id = ?", (service_id,))
    servico = c.fetchone()
    # conn.close() — fechado pelo teardown

    if not servico:
        flash("❌ Serviço não encontrado.", "danger")
        return redirect(url_for("services"))

    if request.method == "POST":
        imei = request.form.get("imei", "").strip()
        sn = request.form.get("sn", "").strip()

        payload = {
            "username": DHRU_USERNAME,       # ✅ do .env
            "apiaccesskey": DHRU_API_KEY,    # ✅ do .env
            "action": "placeimeiorder",
            "service": service_id
        }

        # Decide se envia IMEI ou SN
        if imei:
            payload["imei"] = imei
        elif sn:
            payload["imei"] = sn  # a API usa o mesmo campo "imei" mesmo para SN
        else:
            # Se o serviço exigir IMEI/SN mas não foi fornecido
            if (
                "iPhone" in servico["nome"]
                or ("iPad" in servico["nome"] and "WiFi" not in servico["nome"])
                or "Mac" in servico["nome"]
                or "Watch" in servico["nome"]
            ):
                flash("⚠️ Este serviço requer IMEI ou Serial Number.", "danger")
                return redirect(request.url)
            # Caso contrário → não precisa de nada

        try:
            resp = requests.post(DHRU_API_URL, data=payload, timeout=30)  # ✅ URL do .env
            resp.raise_for_status()
            result = resp.json()

            if "ERROR" in result:
                flash("❌ Erro: " + result["ERROR"][0], "danger")
            else:
                order_id = result.get("SUCCESS", {}).get("REFERENCEID")
                flash(f"✅ Pedido criado com sucesso! ID: {order_id}", "success")

                # ✅ Salvar pedido no banco, incluindo IMEI/SN
                conn = get_db()
                c = conn.cursor()
                c.execute("""
                    INSERT INTO orders (user_email, service_id, service_name, order_ref, imei, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    user["email"],
                    servico["id"],
                    servico["nome"],
                    order_id,
                    imei or sn,
                    "PROCESSING"
                ))
                conn.commit()
                # conn.close() — fechado pelo teardown

        except Exception as e:
            flash("⚠️ Erro ao criar pedido: " + str(e), "danger")

        return redirect(url_for("services"))

    return render_template("comprar_servico.html", servico=servico)

@app.route("/orders")
@login_required
def orders():
    user = current_user()
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE user_email = ? ORDER BY created_at DESC", (user["email"],))
    pedidos = c.fetchall()
    # conn.close() — fechado pelo teardown
    return render_template("orders.html", pedidos=pedidos)


@app.route("/order_status/<order_ref>")
@login_required
def order_status(order_ref):
    result = consultar_status(order_ref)
    if "error" in result:
        flash("❌ Erro ao consultar status: " + result["error"], "danger")
    else:
        status = result.get("SUCCESS", {}).get("STATUS", "UNKNOWN")

        # Atualizar no banco
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE orders SET status = ? WHERE order_ref = ?", (status, order_ref))
        conn.commit()
        # conn.close() — fechado pelo teardown

        flash(f"📌 Status do pedido {order_ref}: {status}", "info")

    return redirect(url_for("orders"))
    

@app.route("/admin/orders")
@login_required
def admin_orders():
    user = current_user()

    # Só ADM pode ver
    if not user.get("is_admin"):
        flash("❌ Acesso negado! Apenas administradores podem acessar esta página.", "danger")
        return redirect(url_for("dashboard"))

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM orders ORDER BY created_at DESC")
    pedidos = c.fetchall()
    # conn.close() — fechado pelo teardown

    return render_template("admin_orders.html", pedidos=pedidos)

@app.route("/pricing")
def pricing():
    return render_template("pricing.html")

@app.route("/support")
def support():
    return render_template("support.html")
    
    
@app.route("/admin/sync-services", methods=["POST"])
@login_required
def admin_sync_services():
    if not session.get("is_admin"):
        flash("Unauthorized", "danger")
        return redirect(url_for("dashboard"))
    # importa e executa script sync_services.py (ou função)
    import sync_services
    sync_services.main()
    flash("Services synchronized.", "success")
    return redirect(url_for("admin_dashboard"))

import re, json, sqlite3, requests, os
from flask import request, render_template, redirect, url_for, flash
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "t-lux.db")
DHRU_API_URL = os.getenv("DHRU_API_URL")
DHRU_API_KEY = os.getenv("DHRU_API_KEY")
DHRU_USERNAME = os.getenv("DHRU_USERNAME", "T-Lux")

def is_imei(s): return bool(re.fullmatch(r"\d{15}", s))

def dhru_check_imei(imei):
    """Consulta o serviço Apple GSX (ID 212) — retorna dados públicos, sem expor sensíveis"""
    payload = {
        "api_key": DHRU_API_KEY,
        "username": DHRU_USERNAME,
        "action": "place_order",
        "service_id": "212",
        "imei": imei
    }
    r = requests.post(DHRU_API_URL, data=payload, timeout=30)
    r.raise_for_status()
    return r.json()

def classify_device(imei_or_sn, check_info=None):
    s = imei_or_sn.strip().upper()
    cond = {}
    family = "Unknown"

    if is_imei(s):
        family = "iPhone_or_iPad"
        if check_info:
            txt = json.dumps(check_info).lower()
            cond["fmi_on"] = "fmi on" in txt
            cond["mdm"] = "mdm" in txt
            cond["cellular"] = True
    else:
        family = "Mac_or_Watch"
        cond["cellular"] = False
        if s.startswith("C") or s.startswith("F"):
            cond["chip"] = "T2"
    return family, cond

def find_rule_and_service(family, cond):
    conn = get_db()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM diagnosis_rules WHERE active=1 ORDER BY priority ASC")
    rules = c.fetchall()

    def match(rule):
        try:
            r = json.loads(rule["condition_json"])
        except:
            return False
        for k, v in r.items():
            if cond.get(k) != v:
                return False
        if r.get("device_family") and r["device_family"] != family:
            return False
        return True

    chosen = next((r for r in rules if match(r)), None)
    svc = None
    if chosen:
        c.execute("""
            SELECT * FROM services WHERE provider=? AND service_id=? AND available=1
        """, (chosen["provider"], chosen["recommended_service_id"]))
        svc = c.fetchone()
    # conn.close() — fechado pelo teardown
    return chosen, svc

#Diagnostico
@app.route("/diagnose", methods=["GET", "POST"])
def diagnose():
    if request.method == "GET":
        return render_template("diagnose.html")

    s = request.form.get("id", "").strip()
    if not s:
        flash("Insira um IMEI ou Serial.", "warning")
        return redirect(url_for("diagnose"))

    check_info = None
    if is_imei(s):
        try:
            check_info = dhru_check_imei(s)
        except Exception:
            check_info = None

    family, cond = classify_device(s, check_info)
    rule, service = find_rule_and_service(family, cond)

    if not service:
        flash("Não foi possível determinar automaticamente. Escolha manualmente.", "info")
        return redirect(url_for("services"))

    return render_template("diagnose_result.html",
                           input_value=s,
                           device_family=family,
                           conditions=cond,
                           rule=rule,
                           service=service)

from flask_babel import gettext as _

@app.route("/teste_i18n")
def teste_i18n():
    return _("Welcome to T-Lux Unlock System")

# -----------------------
# Error Handlers
# -----------------------
@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", message="The page you’re looking for was not found."), 404

@app.errorhandler(500)
def internal_error(e):
    return render_template("error.html", message="Internal server error. Please try again later."), 500

@app.route("/admin/clean_codes")
@admin_required
def admin_clean_codes():
    clean_expired_codes()
    flash("🧹 Old verification codes cleaned.", "info")
    return redirect(url_for("admin_dashboard"))

# -----------------------
# Bootstrap
# -----------------------
if __name__ == "__main__":
    with app.app_context():
        init_db()
        ensure_database_schema()  # ✅ garante estrutura do banco
    app.run(host="0.0.0.0", port=5000)


