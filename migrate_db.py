#!/usr/bin/env python3
# =============================================
# 🔄 MIGRATION SCRIPT — T-LUX Unlock System
# Autor: Blindspot (Harry)
# Última atualização: 2025-10-24
# =============================================

import sqlite3
import os

DB_PATH = os.getenv("DB_FILE", os.path.join(os.path.dirname(__file__), "t-lux.db"))
SQL_FILE = os.path.join(os.path.dirname(__file__), "migrate_all.sql")

def migrate_database():
    """Executa a migração completa do banco T-Lux."""
    print("🚀 Iniciando migração automática do banco T-Lux...")
    if not os.path.exists(SQL_FILE):
        print("❌ Arquivo migrate_all.sql não encontrado.")
        return

    # Lê o conteúdo do arquivo SQL
    with open(SQL_FILE, "r", encoding="utf-8") as f:
        sql_script = f.read()

    # Conecta ao banco SQLite
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    try:
        # Executa todos os comandos SQL
        c.executescript(sql_script)
        conn.commit()
        print("✅ Migração concluída com sucesso!")

        # Mostra as tabelas existentes (debug)
        c.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in c.fetchall()]
        print(f"📦 Tabelas criadas/atualizadas: {', '.join(tables)}")

    except Exception as e:
        print(f"⚠️ Erro durante a migração: {e}")

    finally:
        conn.close()
        print("🔒 Conexão encerrada.")


if __name__ == "__main__":
    migrate_database()
