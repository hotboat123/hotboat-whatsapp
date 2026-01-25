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

        const messageType = msg.message_type ?? msg.type ?? 'text';
        const isImage = messageType === 'image';
        const isAudio = messageType === 'audio';
        
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
            message_type: messageType,
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
    console.log('🔄 Loading conversations with unread badges...');
    try {
        const response = await fetch(`${API_BASE}/api/conversations`);
        if (!response.ok) throw new Error('Failed to load conversations');
        
        const data = await response.json();
        console.log('📊 Raw API response:', data);
        const rawConversations = data.conversations || [];

        // Group by phone number and keep latest entry
        const grouped = new Map();
        rawConversations.forEach(item => {
            const phone = item.phone_number;
            
            // Format last message based on type
            let lastMessage = item.last_message ?? item.message_text ?? item.response_text ?? '';
            const messageType = item.message_type || item.type;
            
            // If it's an image, show a nice preview instead of "[imagen sin texto]"
            if (messageType === 'image') {
                const caption = item.message_text || '';
                if (caption && caption !== '[Imagen sin texto]' && caption !== '[imagen sin texto]' && !caption.startsWith('[')) {
                    lastMessage = `📷 ${caption}`;
                } else {
                    lastMessage = '📷 Imagen';
                }
            } else if (messageType === 'audio') {
                lastMessage = '🎤 Audio';
            } else if (messageType === 'video') {
                const caption = item.message_text || '';
                if (caption && !caption.startsWith('[')) {
                    lastMessage = `🎥 ${caption}`;
                } else {
                    lastMessage = '🎥 Video';
                }
            }
            
            const timestamp = item.last_message_at ?? item.created_at ?? new Date().toISOString();
            const customerName = item.customer_name || phone;

            const existing = grouped.get(phone);
            if (!existing || new Date(timestamp) > new Date(existing.last_message_at)) {
                grouped.set(phone, {
                    phone_number: phone,
                    customer_name: customerName,
                    last_message: lastMessage,
                    last_message_at: timestamp,
                    created_at: timestamp,
                    unread_count: item.unread_count || 0  // ✅ Added unread_count
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
    
    container.innerHTML = conversations.map(conv => {
        const unreadCount = conv.unread_count || 0;
        const unreadBadge = unreadCount > 0 ? `<span class="unread-indicator">${unreadCount}</span>` : '';
        
        // Debug: log conversations with unread
        if (unreadCount > 0) {
            console.log(`📬 Unread: ${conv.customer_name || conv.phone_number} has ${unreadCount} unread messages`);
        }
        
        return `
        <div class="conversation-item ${currentConversation?.phone_number === conv.phone_number ? 'active' : ''}" 
             onclick="selectConversation('${conv.phone_number}')">
            <div class="conversation-header">
                <div class="conversation-name">
                    ${conv.customer_name || conv.phone_number}
                    ${unreadBadge}
                </div>
                <div class="conversation-time">${formatTime(conv.last_message_at || conv.created_at)}</div>
            </div>
            <div class="conversation-preview">
                ${truncate(conv.last_message || 'No messages', 50)}
            </div>
        </div>
    `;
    }).join('');
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
        
        // Update bot toggle state from lead info
        const botEnabled = data.lead?.bot_enabled !== false;
        updateBotToggleUI(botEnabled);
        
        loadLeadInfo(phoneNumber);
        
        renderCurrentChat({ scrollToBottom: true });
        renderConversations();
        showChatView();
        updateMobileLayout();
        
        // Mark conversation as read
        await markConversationAsRead(phoneNumber);
        
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
            const isAudio = (msg.message_type === 'audio');
            // For images/audio, the URL can be in media_url (outgoing) or response_text (incoming)
            const mediaUrl = msg.media_url || msg.response_text;
            
            // Debug log for audio messages
            if (isAudio) {
                console.log('🎤 Audio message:', {
                    id: msg.id,
                    message_type: msg.message_type,
                    media_url: msg.media_url,
                    response_text: msg.response_text,
                    finalMediaUrl: mediaUrl,
                    message_text: msg.message_text
                });
            }
            
            if (isImage && mediaUrl && !mediaUrl.startsWith('[')) {
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
            
            if (isAudio && mediaUrl && !mediaUrl.startsWith('[')) {
                const audioId = `audio_${msg.id}`;
                // Add timestamp to force refresh
                const audioSrc = `${mediaUrl}?t=${Date.now()}`;
                return `
                    <div class="message ${direction === 'outgoing' ? 'outgoing' : 'incoming'}">
                        <div class="message-text">
                            <div class="audio-message">
                                <div class="audio-icon">🎤</div>
                                <audio id="${audioId}" controls preload="metadata" style="width: 100%; max-width: 250px;">
                                    <source src="${audioSrc}" type="audio/ogg; codecs=opus">
                                    <source src="${audioSrc}" type="audio/mpeg">
                                    <source src="${audioSrc}" type="audio/mp4">
                                    <source src="${audioSrc}" type="audio/webm">
                                    Tu navegador no soporta audio
                                </audio>
                            </div>
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
    
    // Add error listeners to audio elements
    setTimeout(() => {
        const audioElements = messagesContainer.querySelectorAll('audio');
        audioElements.forEach(audio => {
            audio.addEventListener('error', (e) => {
                console.error('❌ Audio error:', {
                    id: audio.id,
                    src: audio.currentSrc,
                    error: audio.error ? {
                        code: audio.error.code,
                        message: audio.error.message
                    } : 'Unknown error'
                });
            });
            
            audio.addEventListener('loadedmetadata', () => {
                console.log('✅ Audio loaded:', {
                    id: audio.id,
                    src: audio.currentSrc,
                    duration: audio.duration
                });
            });
            
            audio.addEventListener('canplay', () => {
                console.log('✅ Audio can play:', audio.id);
            });
        });
    }, 100);
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
    `;
}

// Toggle Bot for Lead (from input area)
async function toggleBotFromInput(enabled) {
    if (!currentConversation) {
        showToast('Selecciona una conversación primero', 'warning');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/leads/${currentConversation.phone_number}/bot-toggle`, {
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
        updateBotToggleUI(enabled);
        
        showToast(`${enabled ? '🤖 Bot activado' : '🤐 Bot desactivado'} para este usuario`, 'success');
        
        // Update lead info if visible
        if (currentConversation) {
            await loadLeadInfo(currentConversation.phone_number);
        }
        
    } catch (error) {
        console.error('Error toggling bot:', error);
        showToast('Error al cambiar estado del bot', 'error');
        
        // Revert checkbox
        const checkbox = document.getElementById('botToggleCheckbox');
        if (checkbox) {
            checkbox.checked = !enabled;
        }
    }
}

// Update bot toggle UI
function updateBotToggleUI(enabled) {
    const checkbox = document.getElementById('botToggleCheckbox');
    const text = document.getElementById('botToggleText');
    
    if (checkbox) {
        checkbox.checked = enabled;
    }
    
    if (text) {
        text.textContent = enabled ? '🤖 Bot Activo' : '🤐 Bot Inactivo';
    }
}

// Send Message (Reply in Conversation)
async function sendMessage(event) {
    event.preventDefault();
    
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    
    // Check if user recorded an audio
    if (recordedAudioBlob) {
        await sendAudioFromRecording();
        return;
    }
    
    // Check if user selected an image file
    if (selectedImageFile) {
        await sendImageFromFile(selectedImageFile, message);
        return;
    }
    
    if (!message || !currentConversation) return;
    
    try {
        const payload = {
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
            message_text: message,
            direction: 'outgoing',
            message_type: 'text',
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
    
    // Check if user selected an image file
    if (selectedNewImageFile) {
        if (!phone) {
            showToast('Ingresa un número de teléfono', 'error');
            return;
        }
        await sendNewImageFromFile(selectedNewImageFile, phone, message);
        return;
    }
    
    if (!phone || !message) return;
    
    try {
        const payload = {
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

// Audio recording
let mediaRecorder = null;
let audioChunks = [];
let recordedAudioBlob = null;
let recordingStartTime = null;
let recordingInterval = null;

async function toggleAudioRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        stopAudioRecording();
        return;
    }
    
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];
        recordedAudioBlob = null;
        
        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };
        
        mediaRecorder.onstop = () => {
            const mimeType = mediaRecorder.mimeType || 'audio/webm';
            recordedAudioBlob = new Blob(audioChunks, { type: mimeType });
            showAudioPreview(recordedAudioBlob);
            
            // Stop all tracks
            stream.getTracks().forEach(track => track.stop());
            
            if (recordingInterval) {
                clearInterval(recordingInterval);
                recordingInterval = null;
            }
        };
        
        mediaRecorder.start();
        recordingStartTime = Date.now();
        
        // Update UI
        document.getElementById('audioRecordingStatus').style.display = 'block';
        document.getElementById('microphoneButton').classList.add('recording');
        
        // Start timer
        recordingInterval = setInterval(updateRecordingTime, 100);
        
        showToast('🎤 Grabando audio...', 'info');
        
    } catch (error) {
        console.error('Error accessing microphone:', error);
        showToast('No se pudo acceder al micrófono', 'error');
    }
}

function updateRecordingTime() {
    if (!recordingStartTime) return;
    const elapsed = Math.floor((Date.now() - recordingStartTime) / 1000);
    const minutes = Math.floor(elapsed / 60);
    const seconds = elapsed % 60;
    document.getElementById('recordingTime').textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
}

function stopAudioRecording() {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
        document.getElementById('audioRecordingStatus').style.display = 'none';
        document.getElementById('microphoneButton').classList.remove('recording');
    }
}

function cancelAudioRecording() {
    if (mediaRecorder) {
        if (mediaRecorder.state === 'recording') {
            mediaRecorder.stop();
        }
        mediaRecorder = null;
    }
    audioChunks = [];
    recordedAudioBlob = null;
    recordingStartTime = null;
    
    if (recordingInterval) {
        clearInterval(recordingInterval);
        recordingInterval = null;
    }
    
    document.getElementById('audioRecordingStatus').style.display = 'none';
    document.getElementById('audioPreview').style.display = 'none';
    document.getElementById('microphoneButton').classList.remove('recording');
}

function showAudioPreview(blob) {
    const audioUrl = URL.createObjectURL(blob);
    const audioPlayer = document.getElementById('audioPreviewPlayer');
    audioPlayer.src = audioUrl;
    document.getElementById('audioPreview').style.display = 'block';
}

function clearAudioRecording() {
    recordedAudioBlob = null;
    audioChunks = [];
    document.getElementById('audioPreview').style.display = 'none';
    const audioPlayer = document.getElementById('audioPreviewPlayer');
    if (audioPlayer.src) {
        URL.revokeObjectURL(audioPlayer.src);
        audioPlayer.src = '';
    }
}

async function sendAudioFromRecording() {
    if (!recordedAudioBlob) {
        console.error('No audio blob available');
        showToast('No hay audio grabado', 'error');
        return;
    }
    
    if (!currentConversation) {
        console.error('No conversation selected');
        showToast('Selecciona una conversación primero', 'error');
        return;
    }
    
    try {
        console.log('📤 Sending audio...', {
            blobSize: recordedAudioBlob.size,
            blobType: recordedAudioBlob.type,
            to: currentConversation.phone_number
        });
        
        showToast('Enviando audio...', 'info');
        
        // Create a file from the blob
        const file = new File([recordedAudioBlob], `audio_${Date.now()}.webm`, {
            type: recordedAudioBlob.type || 'audio/webm'
        });
        
        console.log('📦 Created file:', {
            name: file.name,
            size: file.size,
            type: file.type
        });
        
        const formData = new FormData();
        formData.append('audio', file);
        formData.append('to', currentConversation.phone_number);
        
        console.log('🔄 Fetching API...');
        const response = await fetch(`${API_BASE}/api/upload-and-send-audio`, {
            method: 'POST',
            body: formData
        });
        
        console.log('📡 Response status:', response.status);
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error('❌ Server error:', response.status, errorText);
            let errorMessage = 'Failed to send audio';
            try {
                const errorJson = JSON.parse(errorText);
                errorMessage = errorJson.detail || errorMessage;
            } catch (e) {
                errorMessage = errorText || errorMessage;
            }
            throw new Error(errorMessage);
        }
        
        const result = await response.json();
        console.log('✅ Audio sent successfully:', result);
        
        // Add to UI
        const timestamp = new Date().toISOString();
        const newMessage = {
            id: result?.message_id || `temp_${Date.now()}`,
            message_text: '[Audio]',
            direction: 'outgoing',
            message_type: 'audio',
            media_url: result.media_url || `/api/media/${result.media_id}`,
            timestamp
        };
        
        currentConversation.messages.push(newMessage);
        renderCurrentChat();
        
        // Update conversations list
        const conversationIndex = conversations.findIndex(conv => conv.phone_number === currentConversation.phone_number);
        if (conversationIndex >= 0) {
            conversations[conversationIndex].last_message = '🎤 Audio';
            conversations[conversationIndex].last_message_at = timestamp;
        }
        renderConversations();
        
        // Clear recording
        clearAudioRecording();
        
        showToast('¡Audio enviado! ✅', 'success');
        
        // Refresh conversation
        setTimeout(() => selectConversation(currentConversation.phone_number), 2000);
        
    } catch (error) {
        console.error('❌ Error sending audio:', error);
        showToast('Error al enviar audio: ' + error.message, 'error');
    }
}

window.handleImageFileSelect = handleImageFileSelect;
window.clearImageSelection = clearImageSelection;
window.handleNewImageFileSelect = handleNewImageFileSelect;
window.clearNewImageSelection = clearNewImageSelection;
window.loadOlderMessages = loadOlderMessages;
window.showConversationList = showConversationList;
window.toggleAudioRecording = toggleAudioRecording;
window.stopAudioRecording = stopAudioRecording;
window.cancelAudioRecording = cancelAudioRecording;
window.clearAudioRecording = clearAudioRecording;

// Mark conversation as read
async function markConversationAsRead(phoneNumber) {
    try {
        const response = await fetch(`${API_BASE}/api/conversations/${phoneNumber}/mark-read`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        if (!response.ok) {
            console.warn('Failed to mark conversation as read');
            return;
        }
        
        // Update the unread count in the local conversations array
        const conv = conversations.find(c => c.phone_number === phoneNumber);
        if (conv) {
            conv.unread_count = 0;
            renderConversations(); // Re-render to remove the badge
        }
        
        console.log(`Conversation marked as read for ${phoneNumber}`);
    } catch (error) {
        console.error('Error marking conversation as read:', error);
        // Don't show toast error - this is a background operation
    }
}
