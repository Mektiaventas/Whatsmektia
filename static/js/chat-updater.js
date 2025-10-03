// Actualizador automático de chats en tiempo real
(function () {
    // Configuración
    const REFRESH_INTERVAL = 2000; // 2 segundos
    let lastUpdateTimestamp = new Date().getTime();
    let isActive = true;
    let selectedChatId = null;

    // Obtener el ID del chat seleccionado (si existe)
    function initSelectedChat() {
        const urlParts = window.location.pathname.split('/');
        if (urlParts.length > 2 && urlParts[1] === 'chats') {
            selectedChatId = urlParts[2];
            console.log("🔍 Chat seleccionado:", selectedChatId);
        }
    }

    // Actualizar la lista de chats
    function updateChatList() {
        if (!isActive) return;

        fetch('/chats/data')
            .then(response => response.json())
            .then(data => {
                // Solo procesar si hay datos nuevos
                if (data.timestamp <= lastUpdateTimestamp) return;

                lastUpdateTimestamp = data.timestamp;
                processChats(data.chats);
            })
            .catch(error => console.error("Error actualizando chats:", error));
    }

    // Procesar la lista de chats y actualizar la interfaz
    function processChats(chats) {
        const chatContainer = document.querySelector('.chat-items');
        if (!chatContainer) return;

        // Organizar chats por fecha (más recientes primero)
        chats.sort((a, b) => new Date(b.ultima_fecha || 0) - new Date(a.ultima_fecha || 0));

        // Procesar cada chat
        chats.forEach(chat => {
            const existingChat = document.querySelector(`.chat-item[data-chat-num="${chat.numero}"]`);

            if (existingChat) {
                updateExistingChat(existingChat, chat);
            } else {
                addNewChat(chatContainer, chat);
            }
        });
    }

    // Actualizar un chat existente
    function updateExistingChat(element, chat) {
        // Actualizar el mensaje
        const msgElement = element.querySelector('.card-msg');
        if (msgElement && chat.ultimo_mensaje) {
            const newText = chat.tipo_mensaje === 'imagen' ?
                '📷 Imagen' :
                `${chat.ultimo_mensaje.substring(0, 35)}${chat.ultimo_mensaje.length > 35 ? '...' : ''}`;

            if (msgElement.textContent.trim() !== newText.trim()) {
                msgElement.textContent = newText;
                highlightNewMessage(element);
            }
        }

        // Actualizar la hora
        const timeElement = element.querySelector('.card-time');
        if (timeElement && chat.ultima_fecha) {
            const date = new Date(chat.ultima_fecha);
            timeElement.textContent = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }

        // Actualizar el contador de no leídos
        updateUnreadCount(element, chat.sin_leer);
    }

    // Añadir un nuevo chat a la lista
    function addNewChat(container, chat) {
        const newChatHtml = `
            <a href="/chats/${chat.numero}" class="chat-item ${chat.numero === selectedChatId ? 'selected' : ''}" data-chat-num="${chat.numero}">
                <div class="card-content">
                    <div class="card-title-row">
                        <div class="card-avatar-section">
                            <img src="${chat.imagen_url || '/static/icons/default-avatar.png'}" 
                                class="card-avatar" alt="Avatar" 
                                onerror="this.onerror=null;this.src='/static/icons/default-avatar.png';">
                        </div>
                        ${chat.numero | bandera ? `<img src="${chat.numero | bandera}" class="card-flag" alt="País">` : ''}
                        <span class="alias-view" data-num="${chat.numero}">
                            ${chat.nombre_mostrado}
                        </span>
                        <span class="alias-edit" style="display:none;">
                            <input type="text" value="${chat.alias || chat.nombre || ''}" data-num="${chat.numero}" maxlength="100" style="width: 110px;">
                        </span>
                        <button type="button" class="edit-alias-btn" data-num="${chat.numero}" title="Editar nombre">
                            ✏️
                        </button>
                    </div>
                    <div class="card-meta-row">
                        <span class="card-num">${chat.numero}</span>
                        <span class="card-time">
                            ${chat.ultima_fecha ? new Date(chat.ultima_fecha).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                        </span>
                    </div>
                    <div class="card-msg">
                        ${chat.tipo_mensaje === 'imagen' ?
                '📷 Imagen' :
                (chat.ultimo_mensaje ?
                    `${chat.ultimo_mensaje.substring(0, 35)}${chat.ultimo_mensaje.length > 35 ? '...' : ''}` :
                    'Sin mensajes')}
                    </div>
                    ${chat.sin_leer > 0 ? `<div class="card-unread">${chat.sin_leer}</div>` : ''}
                </div>
            </a>
        `;

        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = newChatHtml.trim();
        const newChatElement = tempDiv.firstChild;

        // Añadir al principio de la lista
        container.insertBefore(newChatElement, container.firstChild);

        // Añadir efecto de resaltado
        highlightNewMessage(newChatElement);

        // Configurar eventos para el botón de editar alias
        setupEditButton(newChatElement.querySelector('.edit-alias-btn'));
    }

    // Resaltar un mensaje nuevo con animación
    function highlightNewMessage(element) {
        element.classList.add('new-message');
        setTimeout(() => {
            element.classList.remove('new-message');
        }, 2000);
    }

    // Actualizar contador de mensajes no leídos
    function updateUnreadCount(element, count) {
        let unreadBadge = element.querySelector('.card-unread');

        if (count > 0) {
            if (unreadBadge) {
                unreadBadge.textContent = count;
            } else {
                unreadBadge = document.createElement('div');
                unreadBadge.className = 'card-unread';
                unreadBadge.textContent = count;
                element.querySelector('.card-content').appendChild(unreadBadge);
            }
        } else if (unreadBadge) {
            unreadBadge.remove();
        }
    }

    // Configurar eventos para el botón de editar
    function setupEditButton(button) {
        if (!button) return;

        button.addEventListener('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            const parent = this.closest('.card-title-row');
            activarEdicionAlias(parent);
        });
    }

    // Iniciar el actualizador automático
    function init() {
        initSelectedChat();

        // Solo iniciar si estamos en la página de chats
        if (document.querySelector('.chat-items')) {
            console.log("🚀 Iniciando actualizador automático de chats");

            // Actualizar cada REFRESH_INTERVAL milisegundos
            setInterval(updateChatList, REFRESH_INTERVAL);

            // Primera actualización inmediata
            updateChatList();

            // Pausar actualizaciones cuando la pestaña no está activa
            document.addEventListener('visibilitychange', function () {
                isActive = !document.hidden;
            });
        }
    }

    // Iniciar cuando el DOM esté listo
    document.addEventListener('DOMContentLoaded', init);
})();