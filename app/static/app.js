// State Management
let currentConversation = null;
let conversations = [];
let messagesCache = {};
let isLoadingOlderMessages = false;
const MESSAGES_PAGE_SIZE = 20;
const MAX_REFRESH_LIMIT = 500;
const mobileMediaQuery = window.matchMedia('(max-width: 900px)');

// API Base URL
const API_BASE = window.location.origin;

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
            message_type: msg.message_type ?? msg.type ?? 'text',
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
    window.addEventListener('resize', updateMobileLayout);
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
    `;
}

// Send Message (Reply in Conversation)
async function sendMessage(event) {
    event.preventDefault();
    
    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    
    if (!message || !currentConversation) return;
    
    try {
        const response = await fetch(`${API_BASE}/api/send-message`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                to: currentConversation.phone_number,
                message: message
            })
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
    
    if (!phone || !message) return;
    
    try {
        const response = await fetch(`${API_BASE}/api/send-message`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                to: phone,
                message: message
            })
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
        return date.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
    } else if (diff < 604800000) { // Less than 7 days
        return date.toLocaleDateString('es-ES', { weekday: 'short' });
    } else {
        return date.toLocaleDateString('es-ES', { month: 'short', day: 'numeric' });
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
        minute: '2-digit'
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

window.loadOlderMessages = loadOlderMessages;
window.showConversationList = showConversationList;

