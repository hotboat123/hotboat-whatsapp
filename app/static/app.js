// State Management
let currentConversation = null;
let conversations = [];
let messagesCache = {};
let isLoadingOlderMessages = false;
const MESSAGES_PAGE_SIZE = 20;
const MAX_REFRESH_LIMIT = 500;
const mobileMediaQuery = window.matchMedia('(max-width: 900px)');
let currentSearchTab = 'chats'; // 'chats' or 'messages'
let allMessagesForSearch = []; // Cache for message search
let conversationsLimit = 50; // Increments by 50 on each "Cargar más" (50 -> 100 -> 150 -> 200...)
let conversationsHasMore = true; // True if API returned full page (may have more)
let isLoadingMoreConversations = false;
const CONVERSATIONS_LOAD_MORE_STEP = 50;

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
    initPWA();
    loadQuickReplyButtons();
    _initParentMessages();
});

// ── PWA / Web Push ────────────────────────────────────────────────────────────

let _swRegistration = null;

async function initPWA() {
    if (!('serviceWorker' in navigator)) return;

    try {
        _swRegistration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
        console.log('✅ Service Worker registered');

        // Listen for SW → open chat messages
        navigator.serviceWorker.addEventListener('message', (event) => {
            if (event.data?.type === 'OPEN_CHAT' && event.data.phone) {
                selectConversation(event.data.phone);
            }
        });

        // Auto-open conversation from URL params (?phone=...&prefill=...&priority=N)
        const urlParams = new URLSearchParams(window.location.search);
        const phoneParam = urlParams.get('phone');
        const prefillParam = urlParams.get('prefill');
        const priorityParam = urlParams.get('priority');
        if (phoneParam) {
            const trySelect = setInterval(() => {
                if (conversations.length > 0) {
                    clearInterval(trySelect);
                    selectConversation(phoneParam);
                    if (prefillParam) {
                        setTimeout(() => {
                            const input = document.getElementById('messageInput');
                            if (input) {
                                input.value = decodeURIComponent(prefillParam);
                                input.dispatchEvent(new Event('input'));
                                input.focus();
                            }
                        }, 600);
                    }
                    if (priorityParam !== null) {
                        setTimeout(() => updatePriority(parseInt(priorityParam, 10)), 900);
                    }
                }
            }, 300);
            setTimeout(() => clearInterval(trySelect), 5000);
        }

        // Check push state — show bell button if not yet subscribed
        await _checkPushState();
    } catch (err) {
        console.warn('Service Worker registration failed:', err);
    }
}

// ── Parent-frame message bridge ───────────────────────────────────────────────
// Listens for window.postMessage from the admin panel (admin-bookings.html)
// so the Popeye button can open a specific conversation and pre-fill a message.
//
// Supported message types:
//   { type: 'OPEN_CHAT', phone: '56912345678' }
//   { type: 'OPEN_CHAT', phone: '...', prefillMessage: 'Hola ...' }
function _initParentMessages() {
    window.addEventListener('message', (event) => {
        const d = event.data;
        if (!d || d.type !== 'OPEN_CHAT' || !d.phone) return;

        const openAndPrefill = () => {
            selectConversation(d.phone);
            if (d.prefillMessage) {
                // Wait a tick for selectConversation to finish rendering
                setTimeout(() => {
                    const input = document.getElementById('messageInput');
                    if (input) {
                        input.value = d.prefillMessage;
                        input.dispatchEvent(new Event('input'));
                        input.focus();
                    }
                }, 600);
            }
        };

        if (conversations.length > 0) {
            openAndPrefill();
        } else {
            // Conversations not loaded yet — wait for them
            const t = setInterval(() => {
                if (conversations.length > 0) {
                    clearInterval(t);
                    openAndPrefill();
                }
            }, 300);
            setTimeout(() => clearInterval(t), 6000);
        }

        // Also set priority if requested
        if (d.setPriority !== undefined) {
            setTimeout(() => updatePriority(d.setPriority), 900);
        }
    });
}

async function _checkPushState() {
    if (!('PushManager' in window) || !_swRegistration) return;
    if (Notification.permission === 'denied') return;

    try {
        const resp = await fetch('/api/push/vapid-public-key');
        const { publicKey } = await resp.json();
        if (!publicKey) { console.warn('No VAPID public key from server'); return; }

        const existing = await _swRegistration.pushManager.getSubscription();
        if (existing) {
            // Already subscribed — refresh server record silently
            await savePushSubscription(existing);
            _updateNotifBtn('active');
            console.log('✅ Push already subscribed');
        } else if (Notification.permission === 'granted') {
            // Permission was granted before but subscription expired — resubscribe silently
            try {
                const subscription = await _swRegistration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: _urlBase64ToUint8Array(publicKey),
                });
                await savePushSubscription(subscription);
                _updateNotifBtn('active');
                console.log('✅ Push auto-resubscribed after expiry');
            } catch (resubErr) {
                console.warn('Auto-resubscribe failed:', resubErr);
                _updateNotifBtn('inactive');
            }
        } else {
            // No permission yet — show bell so user can tap to enable
            _updateNotifBtn('inactive');
        }
    } catch (err) {
        console.warn('Push state check failed:', err);
    }
}

// Called when user taps the 🔔 button
async function requestPushPermission() {
    if (!('PushManager' in window) || !_swRegistration) {
        showToast('Tu navegador no soporta notificaciones push', 'error');
        return;
    }
    try {
        const resp = await fetch('/api/push/vapid-public-key');
        const { publicKey } = await resp.json();
        if (!publicKey) { showToast('Servidor sin VAPID key configurada', 'error'); return; }

        const permission = await Notification.requestPermission();
        if (permission !== 'granted') {
            showToast('Permiso de notificaciones denegado', 'error');
            return;
        }
        const subscription = await _swRegistration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: _urlBase64ToUint8Array(publicKey),
        });
        await savePushSubscription(subscription);
        _updateNotifBtn('active');
        showToast('✅ Notificaciones activadas', 'success');
        console.log('✅ Push subscribed:', subscription.endpoint.slice(0, 60));
    } catch (err) {
        showToast('Error activando notificaciones: ' + err.message, 'error');
        console.error('Push subscribe failed:', err);
    }
}

function _updateNotifBtn(state) {
    const btn = document.getElementById('btnNotif');
    if (!btn) return;
    if (state === 'active') {
        btn.style.display = 'none'; // hidden when working fine
    } else {
        btn.style.display = '';    // visible when needs action
        btn.title = 'Tap para activar notificaciones';
    }
}

async function savePushSubscription(subscription) {
    const json = subscription.toJSON();
    await fetch('/api/push/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint: json.endpoint, keys: json.keys }),
    });
}

function _urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = atob(base64);
    return Uint8Array.from([...rawData].map(c => c.charCodeAt(0)));
}

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
async function loadConversations(limit = null) {
    const useLimit = limit !== null ? limit : conversationsLimit;
    console.log('🔄 Loading conversations (limit:', useLimit, ')...');
    try {
        const response = await fetch(`${API_BASE}/api/conversations?limit=${useLimit}`);
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
                    unread_count: item.unread_count || 0,
                    priority: item.priority || 0,
                    ad_source: item.ad_source || null,
                    ad_audience: item.ad_audience || null
                });
            }
        });

        const processed = Array.from(grouped.values()).sort(
            (a, b) => new Date(b.last_message_at) - new Date(a.last_message_at)
        );

        // Update allConversations (used for search fallback and when search is cleared)
        allConversations = [...processed];

        // If user has search text, keep showing search results (like WhatsApp)
        const searchInput = document.getElementById('searchConversations');
        const hasSearch = searchInput && searchInput.value.trim().length > 0;
        if (hasSearch) {
            await filterConversations();
        } else {
            conversations = processed;
            conversationsHasMore = rawConversations.length >= useLimit;
            renderConversations();
        }

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

    const displayConvs = activePriorityFilter === 0
        ? conversations
        : conversations.filter(c => (c.priority || 0) === activePriorityFilter);

    if (displayConvs.length === 0) {
        container.innerHTML = '<div style="padding: 2rem; text-align: center; color: var(--text-secondary);">No conversations yet</div>';
        return;
    }

    container.innerHTML = displayConvs.map(conv => {
        const unreadCount = conv.unread_count || 0;
        const unreadBadge = unreadCount > 0 ? `<span class="unread-indicator">${unreadCount}</span>` : '';
        
        // Priority badge
        const priority = conv.priority || 0;
        const priorityColors = ['#808080', '#dc3545', '#ffc107', '#28a745', '#1db954'];
        const priorityNames = ['Sin prioridad', 'Alta', 'Media', 'Baja', 'Ya reservó'];
        const priorityLabels = [null, '1', '2', '3', '0'];
        const priorityBadge = priority > 0 ?
            `<span class="priority-badge" style="background-color: ${priorityColors[priority]}" title="Prioridad: ${priorityNames[priority]}">${priorityLabels[priority]}</span>` : '';

        // Debug: log conversations with unread
        if (unreadCount > 0) {
            console.log(`📬 Unread: ${conv.customer_name || conv.phone_number} has ${unreadCount} unread messages`);
        }

        const adBadge = conv.ad_source
            ? `<span style="font-size:.43rem;background:#1a4f9f;color:#fff;border-radius:4px;padding:1px 6px;display:inline-block;vertical-align:middle;margin-left:5px" title="Anuncio: ${conv.ad_source}">📢 ${conv.ad_source}</span>`
            : '';
        const audienceBadge = conv.ad_audience
            ? `<span style="font-size:.43rem;background:#1a5c3a;color:#fff;border-radius:4px;padding:1px 6px;display:inline-block;vertical-align:middle;margin-left:3px" title="Audiencia: ${conv.ad_audience}">👥 ${conv.ad_audience}</span>`
            : '';

        return `
        <div class="conversation-item ${currentConversation?.phone_number === conv.phone_number ? 'active' : ''}"
             onclick="selectConversation('${conv.phone_number}')">
            <div class="conversation-header">
                <div class="conversation-name">
                    ${conv.customer_name || conv.phone_number}
                    ${unreadBadge}
                    ${priorityBadge}
                    ${adBadge}
                    ${audienceBadge}
                </div>
                <div class="conversation-time">${formatTime(conv.last_message_at || conv.created_at)}</div>
            </div>
            <div class="conversation-preview">
                ${truncate(conv.last_message || 'No messages', 50)}
            </div>
        </div>
    `;
    }).join('') + (
        // "Cargar más" button: only when NOT searching and may have more
        (() => {
            const searchInput = document.getElementById('searchConversations');
            const hasSearch = searchInput && searchInput.value.trim().length > 0;
            if (hasSearch || !conversationsHasMore) return '';
            return `
                <div class="load-more-conversations" style="padding: 1rem; text-align: center;">
                    <button type="button" class="btn-secondary" onclick="loadMoreConversations()" style="width: 100%;" ${isLoadingMoreConversations ? 'disabled' : ''}>
                        ${isLoadingMoreConversations ? 'Cargando...' : `Ver más conversaciones (${conversations.length} mostradas)`}
                    </button>
                </div>
            `;
        })()
    );
}

// Load more conversations (50 more each click: 100, 150, 200...)
async function loadMoreConversations() {
    if (isLoadingMoreConversations) return;
    isLoadingMoreConversations = true;
    conversationsLimit += CONVERSATIONS_LOAD_MORE_STEP;
    try {
        await loadConversations(conversationsLimit);
    } finally {
        isLoadingMoreConversations = false;
        renderConversations();
    }
}

// Select Conversation
async function selectConversation(phoneNumber) {
    // Track which phone was last requested to abort stale responses
    selectConversation._pendingPhone = phoneNumber;
    try {
        const data = await fetchConversationData(phoneNumber, { limit: MESSAGES_PAGE_SIZE });

        // Abort if the user selected a different conversation while this was loading
        if (selectConversation._pendingPhone !== phoneNumber) return;

        currentConversation = {
            phone_number: phoneNumber,
            customer_name: data.lead?.customer_name || phoneNumber,
            messages: normalizeMessages(data.messages),
            hasMore: Boolean(data.has_more),
            nextCursor: data.next_cursor || null,
            priority: data.lead?.priority || 0,
            ad_source: data.lead?.ad_source || null,
            ad_platform: data.lead?.ad_platform || null,
            ad_media_type: data.lead?.ad_media_type || null,
            ad_audience: data.lead?.ad_audience || null,
        };

        // Update bot toggle state from lead info
        const botEnabled = data.lead?.bot_enabled !== false;
        updateBotToggleUI(botEnabled);
        
        // Update priority UI
        updatePriorityUI(currentConversation.priority);

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

    // Capture phone before the async call to detect mid-flight conversation changes
    const targetPhone = currentConversation.phone_number;

    try {
        const existingCount = currentConversation.messages?.length || 0;
        const limit = Math.min(
            Math.max(existingCount, MESSAGES_PAGE_SIZE),
            MAX_REFRESH_LIMIT
        );

        const data = await fetchConversationData(targetPhone, { limit });

        // Discard if the user switched to a different conversation while fetching
        if (!currentConversation || currentConversation.phone_number !== targetPhone) return;

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
            const container = document.getElementById('messagesContainer');
            const isNearBottom = container
                ? container.scrollHeight - container.scrollTop - container.clientHeight < 120
                : true;
            renderCurrentChat({ scrollToBottom: isNearBottom, preserveScroll: !isNearBottom });
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
    const targetPhone = currentConversation.phone_number;
    const loadButton = document.getElementById('loadOlderButton');
    if (loadButton) {
        loadButton.disabled = true;
        loadButton.textContent = 'Cargando...';
    }

    try {
        const beforeCursor = currentConversation.nextCursor;
        const data = await fetchConversationData(targetPhone, {
            limit: MESSAGES_PAGE_SIZE,
            before: beforeCursor
        });

        // Discard if conversation changed while loading
        if (!currentConversation || currentConversation.phone_number !== targetPhone) return;

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
    const adSourceEl = document.getElementById('currentChatAdSource');
    const adSourceText = document.getElementById('currentChatAdSourceText');
    if (adSourceEl && adSourceText) {
        adSourceEl.style.display = 'inline-block';
        if (currentConversation.ad_source) {
            const platformIcon = currentConversation.ad_platform === 'instagram' ? '📸' : currentConversation.ad_platform === 'facebook' ? '👥' : '📢';
            const mediaIcon = currentConversation.ad_media_type === 'video' ? ' 🎬' : currentConversation.ad_media_type === 'image' ? ' 🖼️' : '';
            const audiencePart = currentConversation.ad_audience ? `  👥 ${currentConversation.ad_audience}` : '';
            adSourceText.textContent = `${platformIcon} ${currentConversation.ad_source}${mediaIcon}${audiencePart}`;
            adSourceEl.style.background = '#1a4f9f';
            adSourceEl.style.color = '#fff';
        } else {
            adSourceText.textContent = '📢 no hay ad asociado';
            adSourceEl.style.background = 'transparent';
            adSourceEl.style.color = '#888';
        }
    }
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
        // Collect the last 10 incoming text message IDs for translation
        const translatableIds = new Set();
        if (activeTranslateLang) {
            const incomingTextMsgs = currentConversation.messages.filter(m => {
                const dir = m.direction ?? (m.role === 'assistant' ? 'outgoing' : 'incoming');
                const t = (m.message_type || 'text');
                return dir === 'incoming' && t !== 'image' && t !== 'audio' && m.id;
            });
            incomingTextMsgs.slice(-10).forEach(m => translatableIds.add(m.id));
        }

        const messagesHtml = currentConversation.messages.map(msg => {
            const text = (msg.message_text ?? msg.content ?? '').trim();
            const direction = msg.direction ?? (msg.role === 'assistant' ? 'outgoing' : 'incoming');
            const sanitized = escapeHtml(text || '').replace(/\n/g, '<br>');
            const isImage = (msg.message_type === 'image');
            const isAudio = (msg.message_type === 'audio');
            const isIncoming = direction === 'incoming';
            const messageId = msg.id || '';
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
            
            let messageHtml = '';
            
            if (isImage && mediaUrl && !mediaUrl.startsWith('[')) {
                messageHtml = `
                    <div class="message ${isIncoming ? 'received incoming' : 'sent outgoing'}" data-message-id="${messageId}">
                        <div class="message-text">
                            <div style="margin-bottom: 0.35rem;">${sanitized || '[Imagen]'}</div>
                            <a href="${mediaUrl}" target="_blank" rel="noopener">
                                <img src="${mediaUrl}" alt="Imagen" style="max-width: 220px; border-radius: 6px;" />
                            </a>
                        </div>
                        <div class="message-time">${formatTime(msg.timestamp)}</div>
                    </div>
                `;
            } else if (isAudio && mediaUrl && !mediaUrl.startsWith('[')) {
                const audioId = `audio_${msg.id}`;
                // Add timestamp to force refresh
                const audioSrc = `${mediaUrl}?t=${Date.now()}`;
                // Use preload="auto" for mobile to ensure complete audio loading
                const preloadMode = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent) ? 'auto' : 'metadata';
                messageHtml = `
                    <div class="message ${isIncoming ? 'received incoming' : 'sent outgoing'}" data-message-id="${messageId}">
                        <div class="message-text">
                            <div class="audio-message">
                                <div class="audio-icon">🎤</div>
                                <audio id="${audioId}" controls preload="${preloadMode}" style="width: 100%; max-width: 250px;">
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
            } else {
                let translationHtml = '';
                if (isIncoming && activeTranslateLang && text && translatableIds.has(messageId)) {
                    const cacheKey = `${messageId}_${activeTranslateLang}`;
                    const cached = translationCache[cacheKey];
                    if (cached !== 'ERROR') {
                        const translatedText = cached && cached !== '⏳' ? '🌐 ' + cached : '⏳ traduciendo...';
                        translationHtml = `<div class="incoming-translation" data-msg-id="${messageId}" style="margin-top:4px;font-size:0.78rem;color:#94a3b8;border-top:1px solid rgba(255,255,255,0.08);padding-top:4px;font-style:italic;">${escapeHtml(translatedText)}</div>`;
                        if (!cached) translateIncomingMessage(messageId, text);
                    }
                }
                messageHtml = `
                    <div class="message ${isIncoming ? 'received incoming' : 'sent outgoing'}" data-message-id="${messageId}">
                        <div class="message-text">${sanitized || '&nbsp;'}${translationHtml}</div>
                        <div class="message-time">${formatTime(msg.timestamp)}</div>
                    </div>
                `;
            }
            
            // Wrap incoming messages in message-wrapper for reactions
            if (isIncoming && messageId) {
                return `<div class="message-wrapper" data-message-id="${messageId}">${messageHtml}</div>`;
            }
            
            return messageHtml;
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
        const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
        
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
            
            // Mobile-specific: Ensure complete audio buffering before play
            if (isMobile) {
                let isFirstPlay = true;
                
                audio.addEventListener('play', async (e) => {
                    if (isFirstPlay && audio.readyState < 3) { // HAVE_FUTURE_DATA
                        console.log('🔄 Buffering audio on mobile:', audio.id);
                        e.preventDefault();
                        audio.pause();
                        
                        // Wait for enough data to be loaded
                        await new Promise((resolve) => {
                            const checkReady = () => {
                                if (audio.readyState >= 3) { // HAVE_FUTURE_DATA
                                    console.log('✅ Audio ready to play:', audio.id);
                                    resolve();
                                } else {
                                    setTimeout(checkReady, 50);
                                }
                            };
                            checkReady();
                        });
                        
                        isFirstPlay = false;
                        audio.play();
                    }
                });
            }
        });
    }, 100);
}

// Load Lead Info
async function loadLeadInfo(phoneNumber) {
    try {
        const response = await fetch(`${API_BASE}/leads/${phoneNumber}`);
        if (!response.ok) throw new Error('Failed to load lead info');

        const data = await response.json();

        // Discard if the user navigated to a different conversation while fetching
        if (selectConversation._pendingPhone !== phoneNumber) return;

        renderLeadInfo(data.lead);
        // Load booking card AFTER renderLeadInfo so innerHTML reset never wipes it
        loadBookingContext(phoneNumber);

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
        ${lead.ad_source ? `
            <div class="info-item">
                <div class="info-label">📢 Anuncio</div>
                <div class="info-value" style="color:#4a9fff;font-weight:600">${escapeHtml(lead.ad_source)}</div>
            </div>
        ` : ''}
        ${lead.ad_platform ? `
            <div class="info-item">
                <div class="info-label">${lead.ad_platform === 'instagram' ? '📸 Plataforma' : '👥 Plataforma'}</div>
                <div class="info-value">${lead.ad_platform === 'instagram' ? 'Instagram' : 'Facebook'}</div>
            </div>
        ` : ''}
        ${lead.ad_media_type ? `
            <div class="info-item">
                <div class="info-label">${lead.ad_media_type === 'video' ? '🎬 Creativo' : '🖼️ Creativo'}</div>
                <div class="info-value">${lead.ad_media_type === 'video' ? 'Video' : 'Imagen'}${lead.ad_creative_url ? ` <a href="${lead.ad_creative_url}" target="_blank" style="color:#4a9fff;font-size:.75rem">ver</a>` : ''}</div>
            </div>
        ` : ''}
        ${lead.notes ? `
            <div class="info-item">
                <div class="info-label">Notes</div>
                <div class="info-value">${escapeHtml(lead.notes)}</div>
            </div>
        ` : ''}
    `;
}

// Booking context panel — quick-create reservation from chat data
async function loadBookingContext(phoneNumber) {
    try {
        const r = await fetch(`${API_BASE}/api/conversations/${phoneNumber}/booking-context`);
        if (!r.ok) return;
        const ctx = await r.json();
        if (selectConversation._pendingPhone !== phoneNumber) return;
        renderBookingContext(ctx);
    } catch (e) {
        console.error('Error loading booking context:', e);
    }
}

function renderBookingContext(ctx) {
    const existing = document.getElementById('bookingContextCard');
    if (existing) existing.remove();

    const container = document.getElementById('leadInfo');
    if (!container) return;

    const hasAny = ctx.name || ctx.email || ctx.date_display || ctx.time || ctx.quantity;

    const card = document.createElement('div');
    card.id = 'bookingContextCard';
    card.style.cssText = 'margin:.5rem .5rem 1rem;background:var(--surface-2,#1e2535);border:1px solid var(--border,#2a3347);border-radius:10px;padding:.85rem .9rem;';

    const row = (icon, label, val) => val
        ? `<div style="display:flex;align-items:center;gap:.5rem;margin:.25rem 0;font-size:.8rem;">
             <span style="color:var(--muted,#8899aa);width:14px;text-align:center">${icon}</span>
             <span style="color:var(--muted,#8899aa);width:52px;flex-shrink:0">${label}</span>
             <span style="color:var(--text,#e0e6f0);font-weight:500;word-break:break-all">${escapeHtml(String(val))}</span>
           </div>`
        : '';

    card.innerHTML = `
        <div style="font-size:.72rem;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:var(--muted,#8899aa);margin-bottom:.6rem;">
            📋 Datos de reserva
        </div>
        ${row('👤','Nombre', ctx.name)}
        ${row('📱','Teléfono', ctx.phone)}
        ${row('📧','Email', ctx.email)}
        ${row('📅','Fecha', ctx.date_display)}
        ${row('⏰','Hora', ctx.time)}
        ${row('👥','Personas', ctx.quantity)}
        ${!hasAny ? '<div style="font-size:.78rem;color:var(--muted,#8899aa)">Sin datos aún</div>' : ''}
        <div style="display:flex;gap:.5rem;margin-top:.75rem;">
            <button onclick="copyBookingData()" title="Copiar datos al portapapeles"
                style="flex:1;padding:.45rem .5rem;font-size:.78rem;background:var(--surface,#151c2c);border:1px solid var(--border,#2a3347);color:var(--text,#e0e6f0);border-radius:7px;cursor:pointer;">
                📋 Copiar
            </button>
            <button onclick="openBookingFromContext()" title="Crear reserva con estos datos"
                style="flex:1;padding:.45rem .5rem;font-size:.78rem;background:#2563eb;border:none;color:#fff;border-radius:7px;cursor:pointer;font-weight:600;">
                📅 Crear reserva
            </button>
        </div>`;

    container.appendChild(card);
    window._lastBookingCtx = ctx;
}

function copyBookingData() {
    const ctx = window._lastBookingCtx;
    if (!ctx) return;
    const lines = [
        ctx.name      ? `Nombre: ${ctx.name}` : null,
        ctx.phone     ? `Teléfono: ${ctx.phone}` : null,
        ctx.email     ? `Email: ${ctx.email}` : null,
        ctx.date_display ? `Fecha: ${ctx.date_display}` : null,
        ctx.time      ? `Hora: ${ctx.time}` : null,
        ctx.quantity  ? `Personas: ${ctx.quantity}` : null,
    ].filter(Boolean);
    navigator.clipboard.writeText(lines.join('\n')).then(() => {
        showToast('Datos copiados al portapapeles ✓', 'success');
    }).catch(() => {
        showToast('Error al copiar', 'error');
    });
}

function openBookingFromContext() {
    const ctx = window._lastBookingCtx;
    if (!ctx) return;
    const msg = {
        type: 'hotboat-open-booking',
        prefill: {
            nombre:   ctx.name || '',
            telefono: ctx.phone || '',
            email:    ctx.email || '',
            fecha:    ctx.date_iso || '',
            hora:     ctx.time || '',
            personas: ctx.quantity || '',
        }
    };
    // If running inside the admin iframe, send to parent; otherwise broadcast
    try { window.parent.postMessage(msg, '*'); } catch(e) {}
    try { window.postMessage(msg, '*'); } catch(e) {}
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

// ── Collapse input panel ───────────────────────────────────────────────────
function toggleInputCollapse() {
    const area = document.getElementById('messageInputArea');
    const btn  = document.getElementById('collapseInputBtn');
    if (!area) return;
    const collapsed = area.classList.toggle('collapsed');
    if (btn) btn.textContent = collapsed ? '▲' : '▼';
}

// Show/hide the lead + booking info panel on mobile (bottom sheet)
function toggleLeadPanel() {
    const panel = document.getElementById('rightPanel');
    const btn   = document.getElementById('toggleInfoBtn');
    const btnP  = document.getElementById('toggleInfoBtnPanel');
    if (!panel) return;
    const visible = panel.classList.toggle('mobile-visible');
    if (btn)  btn.textContent  = visible ? '▼' : '▲';
    if (btnP) btnP.textContent = visible ? '▼' : '▲';
}

// ── Translation language selector ──────────────────────────────────────────
let activeTranslateLang = null;
const translationCache = {}; // { messageId: translatedText }

function toggleTranslateLang(lang) {
    if (activeTranslateLang === lang) {
        activeTranslateLang = null;
    } else {
        activeTranslateLang = lang;
    }
    ['EN','PT','FR'].forEach(l => {
        const btn = document.getElementById(`translateBtn${l}`);
        if (btn) btn.classList.toggle('active', activeTranslateLang === l.toLowerCase());
    });
    // Re-render chat to show/hide translations
    renderCurrentChat({ scrollToBottom: false, preserveScroll: true });
}

async function translateText(text, targetLang) {
    const resp = await fetch('/api/translate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text, target_lang: targetLang})
    });
    if (!resp.ok) throw new Error('Translation failed');
    const data = await resp.json();
    return data.translated;
}

async function translateIncomingMessage(msgId, text) {
    if (!msgId || !text || !activeTranslateLang) return;
    const cacheKey = `${msgId}_${activeTranslateLang}`;
    if (translationCache[cacheKey] && translationCache[cacheKey] !== 'ERROR') return;
    translationCache[cacheKey] = '⏳'; // placeholder
    try {
        const translated = await translateText(text, 'es');
        translationCache[cacheKey] = translated;
        const els = document.querySelectorAll(`.incoming-translation[data-msg-id="${msgId}"]`);
        els.forEach(e => { e.textContent = '🌐 ' + translated; });
    } catch (e) {
        translationCache[cacheKey] = 'ERROR'; // truthy → won't retry on next render
        const els = document.querySelectorAll(`.incoming-translation[data-msg-id="${msgId}"]`);
        els.forEach(e => { e.textContent = ''; });
    }
}

// Send Message (Reply in Conversation)
async function sendMessage(event) {
    event.preventDefault();

    const input = document.getElementById('messageInput');
    let message = input.value.trim();

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

    // Translate if a language is selected
    if (activeTranslateLang) {
        try {
            const sendBtn = document.querySelector('#messageForm button[type="submit"]');
            if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = '⏳'; }
            message = await translateText(message, activeTranslateLang);
            if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = 'Send'; }
        } catch(e) {
            console.error('Translation error:', e);
            // Proceed with original message if translation fails
        }
    }

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

        // Refresh conversation — capture phone NOW so a mid-flight navigation can't redirect back
        const _sentPhone = currentConversation.phone_number;
        setTimeout(() => {
            if (selectConversation._pendingPhone === _sentPhone) selectConversation(_sentPhone);
        }, 1500);
        
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

        const _imgPhone = currentConversation.phone_number;
        setTimeout(() => {
            if (selectConversation._pendingPhone === _imgPhone) selectConversation(_imgPhone);
        }, 2000);
        
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

// Switch Search Tab
function switchSearchTab(tab) {
    currentSearchTab = tab;
    
    // Update tab UI
    const tabs = document.querySelectorAll('.search-tab');
    tabs.forEach(t => {
        if (t.dataset.tab === tab) {
            t.classList.add('active');
        } else {
            t.classList.remove('active');
        }
    });
    
    // Update placeholder
    const searchInput = document.getElementById('searchInput');
    if (tab === 'chats') {
        searchInput.placeholder = 'Buscar en chats...';
    } else {
        searchInput.placeholder = 'Buscar en mensajes...';
    }
    
    // Clear and re-run search
    handleSearch();
}

// Handle Search (dispatcher)
function handleSearch() {
    const searchInput = document.getElementById('searchInput');
    const query = searchInput.value.trim().toLowerCase();
    
    if (currentSearchTab === 'chats') {
        searchInChats(query);
    } else {
        searchInMessages(query);
    }
}

// Search in Chats (names)
function searchInChats(query) {
    const conversationsList = document.getElementById('conversationsList');
    const searchResultsList = document.getElementById('searchResultsList');
    
    // Show conversations list, hide search results
    conversationsList.style.display = 'block';
    searchResultsList.style.display = 'none';
    
    if (!query) {
        // Show all conversations
        const items = document.querySelectorAll('.conversation-item');
        items.forEach(item => {
            item.style.display = 'block';
        });
        return;
    }
    
    // Filter conversations
    const items = document.querySelectorAll('.conversation-item');
    items.forEach(item => {
        const text = item.textContent.toLowerCase();
        item.style.display = text.includes(query) ? 'block' : 'none';
    });
}

// Search in Messages
async function searchInMessages(query) {
    const conversationsList = document.getElementById('conversationsList');
    const searchResultsList = document.getElementById('searchResultsList');
    
    if (!query) {
        // Show conversations list when no query
        conversationsList.style.display = 'block';
        searchResultsList.style.display = 'none';
        return;
    }
    
    // Show search results, hide conversations
    conversationsList.style.display = 'none';
    searchResultsList.style.display = 'block';
    
    // Show loading
    searchResultsList.innerHTML = '<div class="search-no-results">Buscando mensajes...</div>';
    
    try {
        // Search through all conversations
        const results = [];
        
        for (const conv of conversations) {
            // Fetch messages for this conversation
            const data = await fetchConversationData(conv.phone_number, { limit: 100 });
            const messages = normalizeMessages(data.messages);
            
            // Search in messages
            messages.forEach(msg => {
                const text = (msg.message_text || '').toLowerCase();
                if (text.includes(query)) {
                    results.push({
                        phone: conv.phone_number,
                        name: conv.customer_name || conv.phone_number,
                        message: msg.message_text,
                        timestamp: msg.timestamp,
                        messageId: msg.id
                    });
                }
            });
        }
        
        // Sort by timestamp (most recent first)
        results.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        
        // Render results
        renderMessageSearchResults(results, query);
        
    } catch (error) {
        console.error('Error searching messages:', error);
        searchResultsList.innerHTML = '<div class="search-no-results">Error al buscar mensajes</div>';
    }
}

// Render Message Search Results
function renderMessageSearchResults(results, query) {
    const searchResultsList = document.getElementById('searchResultsList');
    
    if (results.length === 0) {
        searchResultsList.innerHTML = '<div class="search-no-results">No se encontraron mensajes</div>';
        return;
    }
    
    // Highlight function
    const highlightText = (text, query) => {
        const regex = new RegExp(`(${escapeRegExp(query)})`, 'gi');
        return text.replace(regex, '<span class="highlight">$1</span>');
    };
    
    const html = results.map(result => {
        const highlightedMessage = highlightText(truncate(result.message, 100), query);
        
        return `
            <div class="search-result-item" onclick="selectConversationFromSearch('${result.phone}')">
                <div class="search-result-contact">${result.name}</div>
                <div class="search-result-message">${highlightedMessage}</div>
                <div class="search-result-time">${formatTime(result.timestamp)}</div>
            </div>
        `;
    }).join('');
    
    searchResultsList.innerHTML = html;
}

// Helper function to escape regex special characters
function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Select conversation from search result
async function selectConversationFromSearch(phoneNumber) {
    // Clear search
    document.getElementById('searchInput').value = '';
    
    // Switch back to chats tab
    switchSearchTab('chats');
    
    // Select conversation
    await selectConversation(phoneNumber);
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

        const _audioPhone = currentConversation.phone_number;
        setTimeout(() => {
            if (selectConversation._pendingPhone === _audioPhone) selectConversation(_audioPhone);
        }, 2000);
        
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
window.switchSearchTab = switchSearchTab;
window.handleSearch = handleSearch;
window.selectConversationFromSearch = selectConversationFromSearch;
window.updatePriority = updatePriority;
window.sendQuickReply = sendQuickReply;

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

// ========================================
// MESSAGE REACTIONS
// ========================================

// Available reaction emojis
const REACTION_EMOJIS = ['❤️', '😬', '😏', '🙏', '🙌', '💪', '👌', '😭', '🤷‍♂️', '🤦‍♂️', '😔', '😐', '🤔'];

// Currently active reaction menu
let activeReactionMenu = null;

// Add click listeners for received messages (to show reaction menu)
function attachReactionListeners() {
    const messagesContainer = document.getElementById('messagesContainer');
    if (!messagesContainer) return;
    
    // Use event delegation
    messagesContainer.addEventListener('click', (e) => {
        // Find if the click is on a received message
        const messageWrapper = e.target.closest('.message-wrapper');
        if (messageWrapper) {
            const messageElement = messageWrapper.querySelector('.message.received');
            if (messageElement) {
                showReactionMenu(messageWrapper, messageElement);
            }
        }
    });
    
    // Close menu when clicking outside
    document.addEventListener('click', (e) => {
        if (activeReactionMenu && !e.target.closest('.message-wrapper') && !e.target.closest('.reaction-menu')) {
            closeReactionMenu();
        }
    });
}

// Show reaction menu for a message
function showReactionMenu(wrapper, messageElement) {
    // Close any existing menu
    closeReactionMenu();
    
    // Get message ID
    const messageId = wrapper.getAttribute('data-message-id');
    if (!messageId) {
        console.warn('Message ID not found');
        return;
    }
    
    // Create reaction menu
    const menu = document.createElement('div');
    menu.className = 'reaction-menu';
    
    // Add reaction emojis
    REACTION_EMOJIS.forEach(emoji => {
        const emojiSpan = document.createElement('span');
        emojiSpan.className = 'reaction-emoji';
        emojiSpan.textContent = emoji;
        emojiSpan.onclick = (e) => {
            e.stopPropagation();
            sendReaction(messageId, emoji);
            closeReactionMenu();
        };
        menu.appendChild(emojiSpan);
    });
    
    // Add menu to wrapper
    wrapper.style.position = 'relative';
    wrapper.appendChild(menu);
    activeReactionMenu = menu;
    
    console.log(`📌 Reaction menu shown for message ${messageId}`);
}

// Close reaction menu
function closeReactionMenu() {
    if (activeReactionMenu) {
        activeReactionMenu.remove();
        activeReactionMenu = null;
    }
}

// ========================================
// PRIORITY AND QUICK REPLY FUNCTIONS
// ========================================

// Update conversation priority
async function updatePriority(priority) {
    if (!currentConversation) {
        showToast('Selecciona una conversación primero', 'warning');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/conversations/${currentConversation.phone_number}/priority`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ priority: priority })
        });
        
        if (!response.ok) {
            throw new Error('Failed to update priority');
        }
        
        const result = await response.json();
        
        // Update UI
        updatePriorityUI(priority);
        
        // Update in conversations list
        const conv = conversations.find(c => c.phone_number === currentConversation.phone_number);
        if (conv) {
            conv.priority = priority;
            renderConversations();
        }
        
        showToast('Prioridad actualizada', 'success');
        
    } catch (error) {
        console.error('Error updating priority:', error);
        showToast('Error al actualizar prioridad', 'error');
    }
}

// Update priority UI buttons
function updatePriorityUI(priority) {
    for (let i = 0; i <= 4; i++) {
        const btn = document.getElementById(`priorityBtn${i}`);
        if (btn) {
            if (i === priority) btn.classList.add('active');
            else btn.classList.remove('active');
        }
    }
}

// ── Dynamic quick-reply buttons ───────────────────────────────────────────────

let _qrButtons = [];  // cached from API

async function loadQuickReplyButtons() {
    try {
        const r = await fetch('/api/admin/bot/quick-replies');
        const d = await r.json();
        _qrButtons = d.buttons || [];
    } catch (e) {
        console.warn('Could not load quick-reply buttons:', e);
        _qrButtons = [];
    }
    renderQuickReplyButtons();
}

function renderQuickReplyButtons() {
    const container = document.getElementById('quick-reply-dynamic');
    if (!container) return;
    if (!_qrButtons.length) {
        container.innerHTML = '<span style="color:var(--muted);font-size:.75rem">Sin botones configurados</span>';
        return;
    }
    container.innerHTML = _qrButtons.map(b => {
        const lbl = b.button_label || String(b.menu_option);
        return `<button type="button" class="quick-reply-btn" onclick="sendQuickReply(${b.menu_option})" title="${lbl}">${lbl}</button>`;
    }).join('');
}

// Send quick reply menu option
async function sendQuickReply(menuOption) {
    if (!currentConversation) {
        showToast('Selecciona una conversación primero', 'warning');
        return;
    }

    const btn = _qrButtons.find(b => b.menu_option === menuOption);
    const label = btn ? btn.button_label : String(menuOption);

    try {
        showToast(`Enviando: ${label}…`, 'info');

        const response = await fetch(`${API_BASE}/api/conversations/${currentConversation.phone_number}/quick-reply`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ menu_option: menuOption, translate_to: activeTranslateLang || null })
        });

        if (!response.ok) throw new Error('Failed to send quick reply');

        showToast(`"${label}" enviado`, 'success');
        await selectConversation(currentConversation.phone_number);

    } catch (error) {
        console.error('Error sending quick reply:', error);
        showToast('Error al enviar respuesta rápida', 'error');
    }
}

// Send reaction to backend
async function sendReaction(messageId, emoji) {
    if (!currentConversation) {
        console.warn('No active conversation');
        return;
    }
    
    // Clean message ID - remove any suffixes like "_in" or "_out"
    const cleanMessageId = String(messageId).replace(/_in$|_out$/, '');
    
    console.log(`➡️ Sending reaction ${emoji} to message ${cleanMessageId} (original: ${messageId})`);
    
    try {
        const response = await fetch(`${API_BASE}/api/messages/${cleanMessageId}/react`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                emoji: emoji,
                phone_number: currentConversation.phone_number
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const result = await response.json();
        console.log('✅ Reaction sent:', result);
        
        showToast(`Reacción ${emoji} enviada`, 'success');
        
        // Optionally refresh the conversation to show the reaction
        // setTimeout(() => selectConversation(currentConversation.phone_number), 500);
        
    } catch (error) {
        console.error('❌ Error sending reaction:', error);
        showToast('Error al enviar reacción', 'error');
    }
}

// Initialize reactions when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    attachReactionListeners();
    console.log('✅ Reaction listeners attached');

    // Initialize search
    initializeSearch();

    // Mark "Todas" as active by default
    const btn0 = document.getElementById('pfBtn0');
    if (btn0) btn0.classList.add('active');
});

// ==================== SEARCH FUNCTIONALITY ====================

let allConversations = []; // Store all conversations for search
let searchCache = new Map(); // Cache for message searches
let filterDebounceTimer = null;
let activePriorityFilter = 0; // 0=all, 1=alta, 2=media, 3=baja

function togglePriorityFilter(p) {
    activePriorityFilter = (activePriorityFilter === p) ? 0 : p;
    [0, 1, 2, 3].forEach(i => {
        const btn = document.getElementById(`pfBtn${i}`);
        if (btn) btn.classList.toggle('active', i === activePriorityFilter);
    });
    renderConversations();
}

// Debounced filter - prevents excessive API calls while typing
function debouncedFilterConversations() {
    if (filterDebounceTimer) clearTimeout(filterDebounceTimer);
    filterDebounceTimer = setTimeout(() => filterConversations(), 300);
}

// Initialize search functionality
function initializeSearch() {
    const searchInput = document.getElementById('searchConversations');
    const searchInMessages = document.getElementById('searchInMessages');
    
    // Show search options when input is focused
    searchInput.addEventListener('focus', () => {
        const searchOptions = searchInput.parentElement.querySelector('.search-options');
        if (searchOptions) {
            searchOptions.style.display = 'block';
        }
    });
    
    // Store all conversations for filtering
    allConversations = [...conversations];
}

// Main filter function
async function filterConversations() {
    const searchInput = document.getElementById('searchConversations');
    const searchInMessages = document.getElementById('searchInMessages');
    const query = searchInput.value.trim();
    
    // If empty, show all conversations
    if (!query) {
        conversations = [...allConversations];
        renderConversations();
        return;
    }
    
    const queryLower = query.toLowerCase();
    
    // Check if searching in messages
    const searchMessages = searchInMessages && searchInMessages.checked;
    
    // Check if query looks like a phone number (3+ digits)
    const phoneOnly = query.replace(/\D/g, '');
    const isPhoneSearch = phoneOnly.length >= 3;
    
    if (isPhoneSearch) {
        // Search by phone number - use API to find in entire database
        await searchByPhoneNumber(phoneOnly, queryLower, searchMessages);
    } else if (searchMessages) {
        // Search in ALL messages - use backend API (searches entire database)
        await searchInAllMessages(queryLower);
    } else {
        // Quick search in contact info only (local)
        searchInContactInfo(queryLower);
    }
}

// Search by phone number - calls API to search entire database
async function searchByPhoneNumber(phoneDigits, queryLower, searchInMessages) {
    showSearching('Buscando por número...');
    
    try {
        const response = await fetch(`${API_BASE}/api/conversations/search?q=${encodeURIComponent(phoneDigits)}`);
        const data = await response.json();
        const apiResults = data.conversations || [];
        
        if (searchInMessages && apiResults.length > 0) {
            // Also search in message content for these conversations
            const merged = [];
            for (const conv of apiResults) {
                const convData = await fetchConversationData(conv.phone_number, { limit: 100 });
                const matchCount = countMessageMatches(convData.messages || [], queryLower);
                merged.push({ ...conv, matchType: 'phone', matchCount: matchCount + 1 });
            }
            merged.sort((a, b) => (b.matchCount || 0) - (a.matchCount || 0));
            conversations = merged;
        } else {
            conversations = apiResults;
        }
        
        renderConversations();
        showSearchResults(conversations.length, conversations.length);
    } catch (error) {
        console.error('Error searching by phone:', error);
        showToast('Error al buscar por número', 'error');
        // Fallback to local search
        searchInContactInfo(queryLower);
    }
}

// Quick search: Filter by contact name or phone number (local only)
function searchInContactInfo(query) {
    conversations = allConversations.filter(conv => {
        const name = (conv.customer_name || '').toLowerCase();
        const phone = (conv.phone_number || '').toLowerCase();
        const lastMessage = (conv.last_message || '').toLowerCase();
        
        return name.includes(query) || 
               phone.includes(query) || 
               lastMessage.includes(query);
    });
    
    renderConversations();
    
    // Show result count
    showSearchResults(conversations.length, allConversations.length);
}

// Search in ALL messages - calls backend API (entire database)
async function searchInAllMessages(query) {
    showSearching('Buscando en todo el historial... (puede tardar unos segundos)');
    
    try {
        const response = await fetch(`${API_BASE}/api/conversations/search-messages?q=${encodeURIComponent(query)}`);
        
        if (!response.ok) {
            const errText = await response.text();
            console.error('Search API error:', response.status, errText);
            throw new Error(`Error ${response.status}: ${errText}`);
        }
        
        const data = await response.json();
        const results = data.conversations || [];
        
        if (data.error) {
            console.error('Search API returned error:', data.error);
        }
        console.log('[Buscar mensajes] Encontradas', results.length, 'conversaciones para "' + query + '"');
        
        conversations = results;
        renderConversations();
        showSearchResults(results.length, results.length);
    } catch (error) {
        console.error('Error searching messages:', error);
        showToast('Error al buscar: ' + (error.message || 'Intenta de nuevo'), 'error');
        // Fallback to local search
        await searchInMessageContent(query);
    }
}

// Search in message content (legacy - local only, used as fallback)
async function searchInMessageContent(query) {
    const results = [];
    const searchPromises = [];
    
    // Show loading indicator
    showSearching('Buscando en mensajes...');
    
    try {
        // Search through each conversation
        for (const conv of allConversations) {
            // Check contact info first (instant)
            const name = (conv.customer_name || '').toLowerCase();
            const phone = (conv.phone_number || '').toLowerCase();
            
            if (name.includes(query) || phone.includes(query)) {
                results.push({
                    ...conv,
                    matchType: 'contact',
                    matchCount: 1
                });
                continue;
            }
            
            // Check if we have cached messages for this conversation
            const cacheKey = conv.phone_number;
            let messages = searchCache.get(cacheKey);
            
            // If not cached or cache is old, fetch from API
            if (!messages) {
                searchPromises.push(
                    fetchConversationData(conv.phone_number, { limit: 100 })
                        .then(data => {
                            messages = data.messages || [];
                            searchCache.set(cacheKey, messages);
                            return { conv, messages };
                        })
                        .catch(() => ({ conv, messages: [] }))
                );
            } else {
                // Use cached messages
                const matchCount = countMessageMatches(messages, query);
                if (matchCount > 0) {
                    results.push({
                        ...conv,
                        matchType: 'message',
                        matchCount
                    });
                }
            }
        }
        
        // Wait for all API calls to complete
        const fetchedResults = await Promise.all(searchPromises);
        
        // Process fetched messages
        fetchedResults.forEach(({ conv, messages }) => {
            const matchCount = countMessageMatches(messages, query);
            if (matchCount > 0) {
                results.push({
                    ...conv,
                    matchType: 'message',
                    matchCount
                });
            }
        });
        
        // Sort by relevance (match count, then date)
        results.sort((a, b) => {
            if (a.matchType === 'contact' && b.matchType !== 'contact') return -1;
            if (a.matchType !== 'contact' && b.matchType === 'contact') return 1;
            if (a.matchCount !== b.matchCount) return b.matchCount - a.matchCount;
            return new Date(b.last_message_at || b.created_at) - new Date(a.last_message_at || a.created_at);
        });
        
        conversations = results;
        renderConversations();
        showSearchResults(results.length, allConversations.length);
        
    } catch (error) {
        console.error('Error searching messages:', error);
        showToast('Error al buscar en mensajes', 'error');
        // Fallback to contact search
        searchInContactInfo(query);
    }
}

// Count how many messages match the query
function countMessageMatches(messages, query) {
    if (!messages || !Array.isArray(messages)) return 0;
    
    const normalizeForSearch = (str) => {
        return (str || '')
            .toLowerCase()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, ''); // Remove accents
    };
    const queryNorm = normalizeForSearch(query);
    
    let count = 0;
    messages.forEach(msg => {
        // API returns message_text, response_text; normalized uses content or message_text
        const textToSearch = normalizeForSearch(
            [msg.content, msg.message_text, msg.response_text, msg.text]
                .filter(Boolean)
                .join(' ')
        );
        if (textToSearch.includes(queryNorm)) {
            count++;
        }
    });
    return count;
}

// Show search results count
function showSearchResults(found, total) {
    const container = document.getElementById('conversationsList');
    if (!container) return;
    
    // Remove existing result message
    const existing = container.querySelector('.search-result-message');
    if (existing) existing.remove();
    
    // Add result message
    if (found === 0) {
        container.insertAdjacentHTML('afterbegin', `
            <div class="search-result-message" style="padding: 1rem; text-align: center; color: var(--text-secondary); background: var(--bg-light); margin-bottom: 0.5rem; border-radius: 8px;">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">🔍</div>
                <div>No se encontraron resultados</div>
            </div>
        `);
    } else {
        const msg = (found === total || typeof total !== 'number') 
            ? `✓ ${found} conversación${found !== 1 ? 'es' : ''} encontrada${found !== 1 ? 's' : ''}`
            : `✓ ${found} de ${total} conversaciones`;
        container.insertAdjacentHTML('afterbegin', `
            <div class="search-result-message" style="padding: 0.75rem; text-align: center; color: var(--primary); background: var(--bg-light); margin-bottom: 0.5rem; border-radius: 8px; font-size: 0.9rem;">
                ${msg}
            </div>
        `);
    }
}

// Show searching indicator
function showSearching(message = 'Buscando...') {
    const container = document.getElementById('conversationsList');
    if (!container) return;
    
    container.innerHTML = `
        <div style="padding: 3rem; text-align: center; color: var(--text-secondary);">
            <div style="font-size: 2rem; margin-bottom: 1rem;">🔍</div>
            <div>${message}</div>
        </div>
    `;
}

// Clear search and restore all conversations
function clearSearch() {
    const searchInput = document.getElementById('searchConversations');
    if (searchInput) {
        searchInput.value = '';
    }
    conversations = [...allConversations];
    renderConversations();
}

