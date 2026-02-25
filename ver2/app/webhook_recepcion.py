from flask import Blueprint, request, make_response
import json
from openai import OpenAI
from ver2.configuracion import Config
from ver2.services import get_db_connection
from .whatsapp_envio import enviar_texto
from .herramientas import buscar_productos, derivar_a_asesor

webhook_bp = Blueprint('webhook', __name__)
client_ds = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# --- FUNCIONES DE PERSISTENCIA (Se mantienen igual) ---
def obtener_historial(conn, user_phone, limite=10):
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT mensaje, respuesta FROM conversaciones WHERE numero = %s ORDER BY id DESC LIMIT %s", (user_phone, limite))
    rows = cur.fetchall()
    cur.close()
    historial = []
    for row in reversed(rows):
        if row['mensaje']: historial.append({"role": "user", "content": row['mensaje']})
        if row['respuesta']: historial.append({"role": "assistant", "content": row['respuesta']})
    return historial

def guardar_mensaje(conn, user_phone, user_text, tenant_slug):
    cur = conn.cursor()
    cur.execute("INSERT INTO conversaciones (numero, mensaje, tipo_mensaje, dominio) VALUES (%s, %s, 'texto', %s)", (user_phone, user_text, tenant_slug))
    last_id = cur.lastrowid
    return last_id

def guardar_respuesta(conn, record_id, respuesta_ia):
    cur = conn.cursor()
    cur.execute("UPDATE conversaciones SET respuesta = %s, respuesta_tipo_mensaje = 'texto' WHERE id = %s", (respuesta_ia, record_id))
    cur.close()

# --- DEFINICIÓN DE HERRAMIENTAS PARA LA IA ---
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_productos",
            "description": "Busca en el catálogo de precios cuando el usuario pregunta por un producto, modelo o costo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_texto": {"type": "string", "description": "El producto o modelo a buscar"}
                },
                "required": ["query_texto"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "derivar_a_asesor",
            "description": "Se usa cuando el cliente pide hablar con un humano o el tema es muy complejo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "motivo": {"type": "string", "description": "Razón de la transferencia"}
                }
            }
        }
    }
]

@webhook_bp.route('/webhook', methods=['POST'])
def recibir_mensajes():
    data = request.get_json()
    try:
        entry = data.get('entry', [{}])[0]
        changes = entry.get('changes', [{}])[0]
        value = changes.get('value', {})
        
        if 'messages' in value:
            message = value['messages'][0]
            phone_id_receptor = value.get('metadata', {}).get('phone_number_id')
            raw_phone = message.get('from')
            user_text = message.get('text', {}).get('body')
            user_phone = '52' + raw_phone[3:] if raw_phone.startswith('521') else raw_phone

            # 1. Identificar el Tenant
            tenant_slug = None
            conn_maestra = get_db_connection({'db_name': Config.CLIENTES_DB_NAME})
            cur_m = conn_maestra.cursor(dictionary=True)
            cur_m.execute("SELECT dominio FROM cliente WHERE wa_phone_id = %s", (phone_id_receptor,))
            res_maestra = cur_m.fetchone()
            cur_m.close()
            conn_maestra.close()

            if res_maestra: tenant_slug = res_maestra['dominio']
            elif phone_id_receptor == Config.get_tenant_config('API_V2').get('wa_phone_id'): tenant_slug = 'API_V2'
            if not tenant_slug: return make_response("NOT_FOUND", 200)

            # 2. Conexión y Datos de IA
            config_db = Config.get_tenant_config(tenant_slug)
            conn_tenant = get_db_connection(config_db)
            
            print(f"\n📩 MENSAJE: {user_text} ({tenant_slug})")

            historial_previo = obtener_historial(conn_tenant, user_phone)
            mensaje_id = guardar_mensaje(conn_tenant, user_phone, user_text, tenant_slug)
            conn_tenant.commit()

            cur_t = conn_tenant.cursor(dictionary=True)
            cur_t.execute("SELECT ia_nombre, negocio_nombre, que_hace, tono, lenguaje, restricciones FROM configuracion LIMIT 1")
            brain = cur_t.fetchone()
            cur_t.close()

            # 3. PRIMERA CONSULTA: Detectar Intención
            prompt_sistema = f"Eres {brain['ia_nombre']}, {brain['que_hace']}. Tono: {brain['tono']}. Restricciones: {brain['restricciones']}. Si no conoces un precio, USA la herramienta buscar_productos."
            
            messages_ia = [{"role": "system", "content": prompt_sistema}]
            messages_ia.extend(historial_previo)
            messages_ia.append({"role": "user", "content": user_text})

            response = client_ds.chat.completions.create(
                model="deepseek-chat",
                messages=messages_ia,
                tools=TOOLS
            )

            obj_respuesta = response.choices[0].message

            # 4. ¿La IA quiere usar una herramienta?
            if obj_respuesta.tool_calls:
                for tool_call in obj_respuesta.tool_calls:
                    nombre_f = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    
                    print(f"🛠️ IA usando herramienta: {nombre_f} con {args}")

                    if nombre_f == "buscar_productos":
                        resultado_f = buscar_productos(conn_tenant, args['query_texto'])
                    elif nombre_f == "derivar_a_asesor":
                        resultado_f = derivar_a_asesor(args.get('motivo', 'No especificado'))
                    
                    # IMPORTANTE: Metemos la respuesta de la DB al historial de la IA
                    messages_ia.append(obj_respuesta)
                    messages_ia.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(resultado_f) 
                    })

                # Segunda llamada: Aquí la IA ya tiene los datos y redacta la respuesta final
                segunda_res = client_ds.chat.completions.create(
                    model="deepseek-chat",
                    messages=messages_ia
                )
                respuesta_ia = segunda_res.choices[0].message.content

                # Limpieza por si DeepSeek se pone "técnico"
                if "<｜" in respuesta_ia:
                    respuesta_ia = respuesta_ia.split(">")[-1].strip()
            else:
                respuesta_ia = obj_respuesta.content

            # 5. Finalizar y Enviar
            # Si la IA está "alucinando" con el historial viejo, le recordamos que sea breve
            if len(respuesta_ia) > 1000:
                respuesta_ia = respuesta_ia[:1000] + "..."

            print(f"🤖 RESPUESTA FINAL: {respuesta_ia}")
            guardar_respuesta(conn_tenant, mensaje_id, respuesta_ia)
            conn_tenant.commit()
            conn_tenant.close()

            enviar_texto(user_phone, respuesta_ia, config_db)

    except Exception as e:
        print(f"❌ ERROR EN WEBHOOK: {e}")
    
    return make_response("EVENT_RECEIVED", 200)

@webhook_bp.route('/webhook', methods=['GET'])
def verificar_webhook():
    # (Se mantiene igual tu verificación de GET)
    return "OK", 200
