#!/usr/bin/env python3
import os
from dotenv import load_dotenv

load_dotenv()

print("=== REVISIÓN DE VARIABLES DE ENTORNO ===")
print(f"VERIFY_TOKEN: {os.getenv('VERIFY_TOKEN')}")
print(f"WHATSAPP_TOKEN: {os.getenv('WHATSAPP_TOKEN')}")
print(f"OPENAI_API_KEY: {os.getenv('OPENAI_API_KEY')}")
print(f"DB_HOST: {os.getenv('DB_HOST')}")
print(f"DB_USER: {os.getenv('DB_USER')}")
print(f"DB_PASSWORD: {os.getenv('DB_PASSWORD')}")
print(f"DB_NAME: {os.getenv('DB_NAME')}")
print(f"MI_NUMERO_BOT: {os.getenv('MI_NUMERO_BOT')}")
print(f"ALERT_NUMBER: {os.getenv('ALERT_NUMBER')}")
print(f"PHONE_NUMBER_ID: {os.getenv('PHONE_NUMBER_ID')}")