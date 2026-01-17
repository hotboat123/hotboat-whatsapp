// State Management
let currentConversation = null;
let conversations = [];
let messagesCache = {};
let isLoadingOlderMessages = false;
const MESSAGES_PAGE_SIZE = 20;
const MAX_REFRESH_LIMIT = 500;
const mobileMediaQuery = window.matchMedia('(max-width: 900px)');

function setViewportHeightVar() {
    const vh = window.innerHeight * 0.01;
    document.documentElement.style.setProperty('--vh', `${vh}px`);
}

// API Base URL
const API_BASE = window.location.origin;
const DEFAULT_TIME_ZONE = 'America/Santiago';

function normalizeMessages(messages = []) {
    if (!Array.isArray(messages)) {
        return [];
    }

    const normalized = messages.map((msg = {}, index) => {
        const candidateFields = [
            msg.message_text,
            msg.content,
            msg.response_text,
            msg.message,
            msg.text
        ];

        let messageText = '';
        for (const field of candidateFields) {
            if (typeof field === 'string') {
                const trimmed = field.trim();
                if (trimmed.length > 0) {
                    messageText = trimmed;
                    break;
                }
            } else if (field !== null && field !== undefined) {
                const asString = String(field).trim();
                if (asString.length > 0) {
                    messageText = asString;
                    break;
                }
            }
        }

        const isImage = (msg.message_type ?? msg.type) === 'image';
        const urlCandidates = [
            msg.media_url,
            msg.response_text,
            msg.message_text,
            msg.content,
            msg.text
        ];
        const httpRegex = /^(https?:\/\/|\/api\/media\/)/i;
        const mediaUrl = urlCandidates.find(u => typeof u === 'string' && httpRegex.test(u));

        const inferredDirection =
            msg.direction ??
            (msg.role === 'assistant' ? 'outgoing' :
                msg.role === 'system' ? 'outgoing' :
                msg.role === 'user' ? 'incoming' :
                msg.response_text ? 'outgoing' :
                'incoming');

        const timestamp =
            msg.timestamp ??
            msg.created_at ??
            msg.message_timestamp ??
            msg.updated_at ??
            new Date().toISOString();

        const parsedTimestamp = Date.parse(timestamp);
        const sortKey = Number.isNaN(parsedTimestamp) ? null : parsedTimestamp;

        return {
            id: msg.id ?? `msg_${Date.now()}_${index}`,
            message_text: messageText,
            direction: inferredDirection === 'outgoing' ? 'outgoing' : 'incoming',
            message_type: isImage ? 'image' : (msg.message_type ?? msg.type ?? 'text'),
            media_url: mediaUrl,
            timestamp,
            _sortKey: sortKey,
            _originalIndex: index
        };
    });

    return normalized
        .sort((a, b) => {
            const aKey = a._sortKey ?? Number.MAX_SAFE_INTEGER;
            const bKey = b._sortKey ?? Number.MAX_SAFE_INTEGER;
            if (aKey !== bKey) {
                return aKey - bKey;
            }
            return a._originalIndex - b._originalIndex;
        })
        .map(({ _sortKey, _originalIndex, ...msg }) => msg);
}

function sortMessagesChronologically(messages = []) {
    return [...messages].sort((a, b) => {
        const aTime = new Date(a.timestamp).getTime();
        const bTime = new Date(b.timestamp).getTime();
        return aTime - bTime;
    });
}

function mergeMessageLists(existing = [], incoming = []) {
    const map = new Map();
    [...existing, ...incoming].forEach(msg => {
        if (msg && msg.id) {
            map.set(msg.id, msg);
        }
    });
    return sortMessagesChronologically(Array.from(map.values()));
}

function setupResponsiveLayout() {
    updateMobileLayout();
    if (mobileMediaQuery.addEventListener) {
        mobileMediaQuery.addEventListener('change', updateMobileLayout);
    } else if (mobileMediaQuery.addListener) {
        mobileMediaQuery.addListener(updateMobileLayout);
    }
    window.addEventListener('resize', () => {
        updateMobileLayout();
        setViewportHeightVar();
    });
    window.addEventListener('orientationchange', () => {
        setViewportHeightVar();
        setTimeout(() => {
            setViewportHeightVar();
            updateMobileLayout();
        }, 200);
    });
}

function isMobileLayout() {
    return mobileMediaQuery.matches;
}

function updateMobileLayout() {
    const mainContent = document.querySelector('.main-content');
    if (!mainContent) return;
    const mobile = isMobileLayout();
    mainContent.classList.toggle('mobile', mobile);

    if (!mobile) {
        mainContent.classList.remove('show-chat', 'show-conversations');
        return;
    }

    // Ensure one of the views is visible
    if (!mainContent.classList.contains('show-chat') && !mainContent.classList.contains('show-conversations')) {
        if (currentConversation) {
            mainContent.classList.add('show-chat');
        } else {
            mainContent.classList.add('show-conversations');
        }
    }
}

function showConversationList() {
    if (!isMobileLayout()) return;
    const mainContent = document.querySelector('.main-content');
    if (!mainContent) return;
    mainContent.scrollTop = 0;
    mainContent.classList.add('show-conversations');
    mainContent.classList.remove('show-chat');
}

function showChatView() {
    if (!isMobileLayout()) return;
    const mainContent = document.querySelector('.main-content');
    if (!mainContent) return;
    mainContent.classList.add('show-chat');
    mainContent.classList.remove('show-conversations');
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setViewportHeightVar();
    loadConversations();
    setupEventListeners();
    setInterval(loadConversations, 10000); // Refresh every 10 seconds
    setInterval(refreshCurrentConversation, 5000); // Refresh current chat every 5 seconds
    setupResponsiveLayout();
});

// Event Listeners
function setupEventListeners() {
    const messageInput = document.getElementById('messageInput');
    const newMessageText = document.getElementById('newMessageText');
    
    if (messageInput) {
        messageInput.addEventListener('input', () => {
            updateCharCount('messageInput', 'charCount');
        });
    }
    
    if (newMessageText) {
        newMessageText.addEventListener('input', () => {
            updateCharCount('newMessageText', 'newMsgCharCount');
        });
    }
}

// Character Counter
function updateCharCount(inputId, counterId) {
    const input = document.getElementById(inputId);
    const counter = document.getElementById(counterId);
    if (input && counter) {
        counter.textContent = input.value.length;
    }
}

// Load Conversations
async function loadConversations() {
    try {
        const response = await fetch(`${API_BASE}/api/conversations`);
        if (!response.ok) throw new Error('Failed to load conversations');
        
        const data = await response.json();
        const rawConversations = data.conversations || [];

        // Group by phone number and keep latest entry
        const grouped = new Map();
        rawConversations.forEach(item => {
            const phone = item.phone_number;
            const lastMessage = item.last_message ?? item.message_text ?? item.response_text ?? '';
            const timestamp = item.last_message_at ?? item.created_at ?? new Date().toISOString();
            const customerName = item.customer_name || phone;

            const existing = grouped.get(phone);
            if (!existing || new Date(timestamp) > new Date(existing.last_message_at)) {
                grouped.set(phone, {
                    phone_number: phone,
                    customer_name: customerName,
                    last_message: lastMessage,
                    last_message_at: timestamp,
                    created_at: timestamp
                });
            }
        });

        conversations = Array.from(grouped.values()).sort(
            (a, b) => new Date(b.last_message_at) - new Date(a.last_message_at)
        );

        renderConversations();
        
        updateStatus('connected', 'Connected');
    } catch (error) {
        console.error('Error loading conversations:', error);
        updateStatus('disconnected', 'Connection Error');
        showToast('Failed to load conversations', 'error');
    }
}

async function fetchConversationData(phoneNumber, { limit = MESSAGES_PAGE_SIZE, before = null } = {}) {
    const params = new URLSearchParams();
    params.append('limit', Math.min(Math.max(limit, 1), MAX_REFRESH_LIMIT).toString());
    if (before) {
        params.append('before', before);
    }

    const response = await fetch(`${API_BASE}/api/conversations/${phoneNumber}?${params.toString()}`);
    if (!response.ok) throw new Error('Failed to load conversation');
    return response.json();
}

// Render Conversations List
function renderConversations() {
    const container = document.getElementById('conversationsList');
    if (!container) return;
    
    if (conversations.length === 0) {
        container.innerHTML = '<div style="padding: 2rem; text-align: center; color: var(--text-secondary);">No conversations yet</div>';
        return;
    }
    
    container.innerHTML = conversations.map(conv => `
        <div class="conversation-item ${currentConversation?.phone_number === conv.phone_number ? 'active' : ''}" 
             onclick="selectConversation('${conv.phone_number}')">
            <div class="conversation-header">
                <div class="conversation-name">${conv.customer_name || conv.phone_number}</div>
                <div class="conversation-time">${formatTime(conv.last_message_at || conv.created_at)}</div>
            </div>
            <div class="conversation-preview">
                ${truncate(conv.last_message || 'No messages', 50)}
            </div>
        </div>
    `).join('');
}

// Select Conversation
async function selectConversation(phoneNumber) {
    try {
        const data = await fetchConversationData(phoneNumber, { limit: MESSAGES_PAGE_SIZE });
        currentConversation = {
            phone_number: phoneNumber,
            customer_name: data.lead?.customer_name || phoneNumber,
            messages: normalizeMessages(data.messages),
            hasMore: Boolean(data.has_more),
            nextCursor: data.next_cursor || null
        };
        
        loadLeadInfo(phoneNumber);
        
        renderCurrentChat({ scrollToBottom: true });
        renderConversations();
        showChatView();
        updateMobileLayout();
        
    } catch (error) {
        console.error('Error selecting conversation:', error);
        showToast('Failed to load conversation', 'error');
    }
}

// Refresh Current Conversation (auto-refresh)
async function refreshCurrentConversation() {
    if (!currentConversation) return;
    
    try {
        const existingCount = currentConversation.messages?.length || 0;
        const limit = Math.min(
            Math.max(existingCount, MESSAGES_PAGE_SIZE),
            MAX_REFRESH_LIMIT
        );
        
        const data = await fetchConversationData(currentConversation.phone_number, { limit });
        const normalized = normalizeMessages(data.messages);
        const mergedMessages = mergeMessageLists(currentConversation.messages || [], normalized);
        
        const hadChanges = mergedMessages.length !== (currentConversation.messages || []).length ||
            (mergedMessages.length && currentConversation.messages?.length &&
                mergedMessages[mergedMessages.length - 1]?.id !== currentConversation.messages[currentConversation.messages.length - 1]?.id);
        
        currentConversation.messages = mergedMessages;
        currentConversation.hasMore = Boolean(data.has_more) || Boolean(currentConversation.hasMore);
        
        if (data.next_cursor) {
            if (!currentConversation.nextCursor) {
                currentConversation.nextCursor = data.next_cursor;
            } else {
                currentConversation.nextCursor = data.next_cursor < currentConversation.nextCursor
                    ? data.next_cursor
                    : currentConversation.nextCursor;
            }
        }
        
        if (hadChanges) {
            renderCurrentChat();
        }
    } catch (error) {
        console.log('Auto-refresh failed:', error);
    }
}

async function loadOlderMessages() {
    if (!currentConversation || !currentConversation.hasMore || isLoadingOlderMessages) {
        return;
    }

    isLoadingOlderMessages = true;
    const loadButton = document.getElementById('loadOlderButton');
    if (loadButton) {
        loadButton.disabled = true;
        loadButton.textContent = 'Cargando...';
    }

    try {
        const beforeCursor = currentConversation.nextCursor;
        const data = await fetchConversationData(currentConversation.phone_number, {
            limit: MESSAGES_PAGE_SIZE,
            before: beforeCursor
        });

        const olderMessages = normalizeMessages(data.messages);
        currentConversation.messages = mergeMessageLists(currentConversation.messages || [], olderMessages);
        currentConversation.hasMore = Boolean(data.has_more);

        if (data.next_cursor) {
            if (!currentConversation.nextCursor) {
                currentConversation.nextCursor = data.next_cursor;
            } else {
                currentConversation.nextCursor = data.next_cursor < currentConversation.nextCursor
                    ? data.next_cursor
                    : currentConversation.nextCursor;
            }
        } else if (!currentConversation.hasMore) {
            currentConversation.nextCursor = null;
        }

        renderCurrentChat({ scrollToBottom: false, preserveScroll: true });
    } catch (error) {
        console.error('Error loading older messages:', error);
        showToast('No se pudieron cargar mensajes anteriores', 'error');
    } finally {
        isLoadingOlderMessages = false;
        const button = document.getElementById('loadOlderButton');
        if (button) {
            button.disabled = false;
            button.textContent = 'Ver mensajes anteriores';
        }
    }
}

// Render Current Chat
function renderCurrentChat(options = {}) {
    const {
        scrollToBottom = true,
        preserveScroll = false
    } = options;

    const chatName = document.getElementById('currentChatName');
    const chatPhone = document.getElementById('currentChatPhone');
    const messagesContainer = document.getElementById('messagesContainer');
    const messageInputArea = document.getElementById('messageInputArea');
    const previousScrollHeight = preserveScroll ? messagesContainer.scrollHeight : null;
    const previousScrollTop = preserveScroll ? messagesContainer.scrollTop : null;
    
    if (!currentConversation) {
        chatName.textContent = 'Select a conversation';
        chatPhone.textContent = '';
        messagesContainer.innerHTML = `
            <div class="welcome-message">
                <h2>👋 Welcome to Kia-Ai</h2>
                <p>Select a conversation from the left to view messages</p>
                <p>or click "New Message" to send a custom message</p>
            </div>
        `;
        messageInputArea.style.display = 'none';
        showConversationList();
        updateMobileLayout();
        return;
    }
    
    chatName.textContent = currentConversation.customer_name;
    chatPhone.textContent = currentConversation.phone_number;
    messageInputArea.style.display = 'block';
    
    // Render messages
    if (currentConversation.messages.length === 0) {
        const loadMoreHtml = currentConversation.hasMore ? `
            <div class="load-more-container">
                <button class="btn-secondary load-more-btn" onclick="loadOlderMessages()" id="loadOlderButton">
                    Ver mensajes anteriores
                </button>
            </div>
        ` : '';

        messagesContainer.innerHTML = `
            ${loadMoreHtml}
            <div class="welcome-message">
                <p>No messages in this conversation</p>
                <p>Start by sending a message below</p>
            </div>
        `;
    } else {
        const messagesHtml = currentConversation.messages.map(msg => {
            const text = (msg.message_text ?? msg.content ?? '').trim();
            const direction = msg.direction ?? (msg.role === 'assistant' ? 'outgoing' : 'incoming');
            const sanitized = escapeHtml(text || '').replace(/\n/g, '<br>');
            const isImage = (msg.message_type === 'image');
            const mediaUrl = msg.media_url;
            
            if (isImage && mediaUrl) {
                return `
                    <div class="message ${direction === 'outgoing' ? 'outgoing' : 'incoming'}">
                        <div class="message-text">
                            <div style="margin-bottom: 0.35rem;">${sanitized || '[Imagen]'}</div>
                            <a href="${mediaUrl}" target="_blank" rel="noopener">
                                <img src="${mediaUrl}" alt="Imagen" style="max-width: 220px; border-radius: 6px;" />
                            </a>
                        </div>
                        <div class="message-time">${formatTime(msg.timestamp)}</div>
                    </div>
                `;
            }

            return `
                <div class="message ${direction === 'outgoing' ? 'outgoing' : 'incoming'}">
                    <div class="message-text">${sanitized || '&nbsp;'}</div>
                    <div class="message-time">${formatTime(msg.timestamp)}</div>
                </div>
            `;
        }).join('');

        const loadMoreHtml = currentConversation.hasMore ? `
            <div class="load-more-container">
                <button class="btn-secondary load-more-btn" onclick="loadOlderMessages()" id="loadOlderButton">
                    Ver mensajes anteriores
                </button>
            </div>
        ` : '';

        messagesContainer.innerHTML = `${loadMoreHtml}${messagesHtml}`;
        
        if (preserveScroll && previousScrollHeight !== null && previousScrollTop !== null) {
            const newScrollHeight = messagesContainer.scrollHeight;
            messagesContainer.scrollTop = newScrollHeight - previousScrollHeight + previousScrollTop;
        } else if (scrollToBottom) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }

    showChatView();
    updateMobileLayout();
}

// Load Lead Info
async function loadLeadInfo(phoneNumber) {
    try {
        const response = await fetch(`${API_BASE}/leads/${phoneNumber}`);
        if (!response.ok) throw new Error('Failed to load lead info');
        
        const data = await response.json();
        renderLeadInfo(data.lead);
        
    } catch (error) {
        console.error('Error loading lead info:', error);
    }
}

// Render Lead Info
function renderLeadInfo(lead) {
    const container = document.getElementById('leadInfo');
    if (!container || !lead) return;
    
    const statusClass = lead.lead_status || 'unknown';
    const statusText = formatLeadStatus(lead.lead_status);
    
    container.innerHTML = `
        <div class="info-item">
            <div class="info-label">Phone Number</div>
            <div class="info-value">${lead.phone_number}</div>
        </div>
        <div class="info-item">
            <div class="info-label">Name</div>
            <div class="info-value">${lead.customer_name || 'Unknown'}</div>
        </div>
        <div class="info-item">
            <div class="info-label">Status</div>
            <div class="info-value">
                <span class="lead-status ${statusClass}">${statusText}</span>
            </div>
        </div>
        <div class="info-item">
            <div class="info-label">First Contact</div>
            <div class="info-value">${formatDate(lead.created_at)}</div>
        </div>
        <div class="info-item">
            <div class="info-label">Last Contact</div>
            <div class="info-value">${formatDate(lead.last_contact_at)}</div>
        </div>
        ${lead.notes ? `
            <div class="info-item">
                <div class="info-label">Notes</div>
                <div class="info-value">${escapeHtml(lead.notes)}</div>
            </div>
        ` : ''}
        <div class="info-item" style="border-top: 1px solid #2a4a5a; padding-top: 1rem; margin-top: 1rem;">
            <div class="info-label">
                <span style="font-weight: 600;">🤖 Bot Automático</span>
            </div>
            <div class="info-value">
                <label class="bot-toggle-container" style="display: flex; align-items: center; gap: 0.75rem; cursor: pointer;">
                    <input 
                        type="checkbox" 
                        id="botToggle" 
                        ${lead.bot_enabled !== false ? 'checked' : ''} 
                        onchange="toggleBot('${lead.phone_number}', this.checked)"
                        style="width: 20px; height: 20px; cursor: pointer;"
                    >
                    <span id="botToggleLabel" style="color: ${lead.bot_enabled !== false ? '#4ade80' : '#94a3b8'}; font-weight: 500;">
                        ${lead.bot_enabled !== false ? 'Activo - Bot responderá automáticamente' : 'Inactivo - Solo modo manual'}
                    </span>
                </label>
                <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 0.5rem;">
                    ${lead.bot_enabled !== false 
                        ? '✓ El bot procesará y responderá mensajes automáticamente' 
                        : '⚠️ Debes responder manualmente a este usuario'
                    }
                </div>
            </div>
        </div>
    `;
}

// Toggle Bot for Lead
async function toggleBot(phoneNumber, enabled) {
    try {
        showToast(`${enabled ? 'Activando' : 'Desactivando'} bot...`, 'info');
        
        const response = await fetch(`${API_BASE}/leads/${phoneNumber}/bot-toggle`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ bot_enabled: enabled })
        });
        
        if (!response.ok) {
            throw new Error('Failed to toggle bot');
        }
        
        const result = await response.json();
        
        // Update UI
        const label = document.getElementById('botToggleLabel');
        if (label) {
            label.textContent = enabled 
                ? 'Activo - Bot responderá automáticamente' 
                : 'Inactivo - Solo modo manual';
            label.style.color = enabled ? '#4ade80' : '#94a3b8';
        }
        
        showToast(`✅ Bot ${enabled ? 'activado' : 'desactivado'} correctamente`, 'success');
        
        // Reload lead info to update description
        if (currentConversation) {
            await loadLeadInfo(currentConversation.phone_number);
        }
        
    } catch (error) {
        console.error('Error toggling bot:', error);
        showToast('Error al cambiar estado del bot', 'error');
        
        // Revert checkbox
        const checkbox = document.getElementById('botToggle');
        if (checkbox) {
            checkbox.checked = !enabled;
        }
    }
}

// Send Message (Reply in Conversation)
async function sendMessage(event) {
    event.preventDefault();
    
    const input = document.getElementById('messageInput');
    const sendAsImageCheckbox = document.getElementById('sendAsImage');
    const imageUrlInput = document.getElementById('messageImageUrl');
    const message = input.value.trim();
    const imageUrl = imageUrlInput ? imageUrlInput.value.trim() : '';
    const sendAsImage = sendAsImageCheckbox && sendAsImageCheckbox.checked && imageUrl.length > 0;
    
    // Check if user selected an image file
    if (selectedImageFile) {
        await sendImageFromFile(selectedImageFile, message);
        return;
    }
    
    if ((!message && !sendAsImage) || !currentConversation) return;
    
    try {
        const payload = sendAsImage ? {
            to: currentConversation.phone_number,
            type: 'image',
            image_url: imageUrl,
            caption: message || undefined
        } : {
            to: currentConversation.phone_number,
            message: message
        };
        
        const response = await fetch(`${API_BASE}/api/send-message`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload)
        });
        
        if (!response.ok) throw new Error('Failed to send message');
        
        const result = await response.json();
        
        // Optimistically append outgoing message to the UI
        const timestamp = new Date().toISOString();
        const newMessage = {
            id: result?.message_id || `temp_${Date.now()}`,
            message_text: message || (sendAsImage ? '[Imagen enviada]' : ''),
            direction: 'outgoing',
            message_type: sendAsImage ? 'image' : 'text',
            timestamp
        };

        currentConversation.messages.push(newMessage);
        renderCurrentChat();

        // Update conversations list preview
        const conversationIndex = conversations.findIndex(conv => conv.phone_number === currentConversation.phone_number);
        if (conversationIndex >= 0) {
            conversations[conversationIndex].last_message = message;
            conversations[conversationIndex].last_message_at = timestamp;
        } else {
            loadConversations();
        }
        renderConversations();
        
        // Clear input
        input.value = '';
        if (imageUrlInput) imageUrlInput.value = '';
        if (sendAsImageCheckbox) sendAsImageCheckbox.checked = false;
        updateCharCount('messageInput', 'charCount');
        
        showToast('Message sent successfully! ✅', 'success');
        
        // Refresh conversation (ensure DB sync)
        setTimeout(() => selectConversation(currentConversation.phone_number), 1500);
        
    } catch (error) {
        console.error('Error sending message:', error);
        showToast('Failed to send message', 'error');
    }
}

async function sendImageFromFile(file, caption = '') {
    if (!currentConversation) return;
    
    try {
        // Validate file before sending
        if (!file || !file.type.startsWith('image/')) {
            throw new Error('El archivo debe ser una imagen válida');
        }

        // Check file size - warn if very large but allow it (server will compress)
        const fileSizeMB = file.size / (1024 * 1024);
        console.log(`📤 Sending image from mobile/desktop: ${file.name}, size: ${fileSizeMB.toFixed(2)} MB, type: ${file.type}`);
        
        if (fileSizeMB > 5) {
            showToast(`Comprimiendo imagen (${fileSizeMB.toFixed(1)}MB)...`, 'info');
        } else {
            showToast('Subiendo imagen...', 'info');
        }
        
        const formData = new FormData();
        formData.append('image', file);
        formData.append('to', currentConversation.phone_number);
        if (caption) formData.append('caption', caption);
        
        const response = await fetch(`${API_BASE}/api/upload-and-send-image`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('❌ Server error:', response.status, errorText);
            let errorMessage = 'Failed to upload image';
            try {
                const errorJson = JSON.parse(errorText);
                errorMessage = errorJson.detail || errorMessage;
            } catch (e) {
                errorMessage = errorText || errorMessage;
            }
            throw new Error(errorMessage);
        }
        
        const result = await response.json();
        console.log('✅ Image upload response:', result);
        
        // Verify the response has the required data
        if (!result || (!result.media_id && !result.media_url)) {
            console.error('❌ Invalid server response:', result);
            throw new Error('El servidor no devolvió información de la imagen');
        }
        
        // Now add the image to the UI only if everything succeeded
        const timestamp = new Date().toISOString();
        const newMessage = {
            id: result?.message_id || `temp_${Date.now()}`,
            message_text: caption || '',
            direction: 'outgoing',
            message_type: 'image',
            media_url: result.media_url || `/api/media/${result.media_id}`,
            timestamp
        };

        currentConversation.messages.push(newMessage);
        renderCurrentChat();

        // Update conversations list preview
        const conversationIndex = conversations.findIndex(conv => conv.phone_number === currentConversation.phone_number);
        if (conversationIndex >= 0) {
            conversations[conversationIndex].last_message = caption || '[Imagen]';
            conversations[conversationIndex].last_message_at = timestamp;
        }
        renderConversations();
        
        // Clear inputs and preview
        document.getElementById('messageInput').value = '';
        clearImageSelection();
        updateCharCount('messageInput', 'charCount');
        
        showToast('¡Imagen enviada! ✅', 'success');
        
        // Refresh conversation after a short delay to sync with server
        setTimeout(() => selectConversation(currentConversation.phone_number), 2000);
        
    } catch (error) {
        console.error('❌ Error sending image:', error);
        showToast('Error al enviar imagen: ' + error.message, 'error');
        
        // Don't add the message to UI if there was an error
        // User will see the error toast instead
    }
}

// Show New Message Modal
function showNewMessageModal() {
    const modal = document.getElementById('newMessageModal');
    modal.classList.add('active');
}

// Close New Message Modal
function closeNewMessageModal() {
    const modal = document.getElementById('newMessageModal');
    modal.classList.remove('active');
    document.getElementById('newMessageForm').reset();
    updateCharCount('newMessageText', 'newMsgCharCount');
}

// Send New Message
async function sendNewMessage(event) {
    event.preventDefault();
    
    const phone = document.getElementById('recipientPhone').value.trim();
    const message = document.getElementById('newMessageText').value.trim();
    const sendAsImageCheckbox = document.getElementById('newSendAsImage');
    const imageUrlInput = document.getElementById('newMessageImageUrl');
    const imageUrl = imageUrlInput ? imageUrlInput.value.trim() : '';
    const sendAsImage = sendAsImageCheckbox && sendAsImageCheckbox.checked && imageUrl.length > 0;
    
    // Check if user selected an image file
    if (selectedNewImageFile) {
        if (!phone) {
            showToast('Ingresa un número de teléfono', 'error');
            return;
        }
        await sendNewImageFromFile(selectedNewImageFile, phone, message);
        return;
    }
    
    if (!phone || (!message && !sendAsImage)) return;
    
    try {
        const payload = sendAsImage ? {
            to: phone,
            type: 'image',
            image_url: imageUrl,
            caption: message || undefined
        } : {
            to: phone,
            message: message
        };
        
        const response = await fetch(`${API_BASE}/api/send-message`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to send message');
        }
        
        showToast('Message sent successfully! ✅', 'success');
        closeNewMessageModal();
        
        // Refresh conversations and select the new one
        setTimeout(() => {
            loadConversations();
            selectConversation(phone);
        }, 1000);
        
    } catch (error) {
        console.error('Error sending new message:', error);
        showToast(error.message || 'Failed to send message', 'error');
    }
}

async function sendNewImageFromFile(file, phone, caption = '') {
    try {
        showToast('Subiendo imagen...', 'info');
        
        const formData = new FormData();
        formData.append('image', file);
        formData.append('to', phone);
        if (caption) formData.append('caption', caption);
        
        const response = await fetch(`${API_BASE}/api/upload-and-send-image`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to upload image');
        }
        
        showToast('¡Imagen enviada! ✅', 'success');
        closeNewMessageModal();
        
        // Clear selection
        clearNewImageSelection();
        
        // Refresh conversations and select the new one
        setTimeout(() => {
            loadConversations();
            selectConversation(phone);
        }, 1000);
        
    } catch (error) {
        console.error('Error sending image:', error);
        showToast('Error al enviar imagen: ' + error.message, 'error');
    }
}

// Filter Conversations
function filterConversations() {
    const searchInput = document.getElementById('searchConversations');
    const filter = searchInput.value.toLowerCase();
    
    const items = document.querySelectorAll('.conversation-item');
    items.forEach(item => {
        const text = item.textContent.toLowerCase();
        item.style.display = text.includes(filter) ? 'block' : 'none';
    });
}

// Update Status Indicator
function updateStatus(status, text) {
    const indicator = document.getElementById('statusIndicator');
    const statusText = document.getElementById('statusText');
    
    indicator.className = `status-indicator ${status}`;
    statusText.textContent = text;
}

// Show Toast Notification
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Utility Functions
function formatTime(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 86400000) { // Less than 24 hours
        return date.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', timeZone: DEFAULT_TIME_ZONE });
    } else if (diff < 604800000) { // Less than 7 days
        return date.toLocaleDateString('es-ES', { weekday: 'short', timeZone: DEFAULT_TIME_ZONE });
    } else {
        return date.toLocaleDateString('es-ES', { month: 'short', day: 'numeric', timeZone: DEFAULT_TIME_ZONE });
    }
}

function formatDate(timestamp) {
    if (!timestamp) return 'Never';
    const date = new Date(timestamp);
    return date.toLocaleDateString('es-ES', { 
        year: 'numeric', 
        month: 'long', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        timeZone: DEFAULT_TIME_ZONE
    });
}

function formatLeadStatus(status) {
    const statuses = {
        'potential_client': 'Potential Client',
        'customer': 'Customer',
        'bad_lead': 'Bad Lead',
        'unknown': 'Unknown'
    };
    return statuses[status] || 'Unknown';
}

function truncate(str, length) {
    if (!str) return '';
    return str.length > length ? str.substring(0, length) + '...' : str;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Image upload handling - Chat area
let selectedImageFile = null;

function handleImageFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    if (!file.type.startsWith('image/')) {
        showToast('Por favor selecciona un archivo de imagen', 'error');
        return;
    }
    
    // Show info if file is large (will be compressed automatically)
    const fileSizeMB = file.size / (1024 * 1024);
    if (fileSizeMB > 5) {
        showToast(`Imagen grande (${fileSizeMB.toFixed(1)}MB) - se comprimirá automáticamente`, 'info');
    }
    
    selectedImageFile = file;
    
    // Show preview
    const reader = new FileReader();
    reader.onload = (e) => {
        document.getElementById('previewImg').src = e.target.result;
        document.getElementById('imagePreview').style.display = 'block';
    };
    reader.readAsDataURL(file);
}

function clearImageSelection() {
    selectedImageFile = null;
    document.getElementById('imageFileInput').value = '';
    document.getElementById('imagePreview').style.display = 'none';
}

// Image upload handling - New message modal
let selectedNewImageFile = null;

function handleNewImageFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    if (!file.type.startsWith('image/')) {
        showToast('Por favor selecciona un archivo de imagen', 'error');
        return;
    }
    
    // Show info if file is large (will be compressed automatically)
    const fileSizeMB = file.size / (1024 * 1024);
    if (fileSizeMB > 5) {
        showToast(`Imagen grande (${fileSizeMB.toFixed(1)}MB) - se comprimirá automáticamente`, 'info');
    }
    
    selectedNewImageFile = file;
    
    // Show preview
    const reader = new FileReader();
    reader.onload = (e) => {
        document.getElementById('newPreviewImg').src = e.target.result;
        document.getElementById('newImagePreview').style.display = 'block';
    };
    reader.readAsDataURL(file);
}

function clearNewImageSelection() {
    selectedNewImageFile = null;
    document.getElementById('newImageFileInput').value = '';
    document.getElementById('newImagePreview').style.display = 'none';
}

window.handleImageFileSelect = handleImageFileSelect;
window.clearImageSelection = clearImageSelection;
window.handleNewImageFileSelect = handleNewImageFileSelect;
window.clearNewImageSelection = clearNewImageSelection;
window.loadOlderMessages = loadOlderMessages;
window.showConversationList = showConversationList;

