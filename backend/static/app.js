// HVAC Copilot - Chat UI Application

const API_BASE = '';  // Same origin
let sessionId = null;
let pendingImage = null;

// DOM Elements
const chatContainer = document.getElementById('chatContainer');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const cameraBtn = document.getElementById('cameraBtn');
const cameraInput = document.getElementById('cameraInput');
const voiceBtn = document.getElementById('voiceBtn');
const imagePreview = document.getElementById('imagePreview');
const previewImg = document.getElementById('previewImg');
const removeImage = document.getElementById('removeImage');
const loadingOverlay = document.getElementById('loadingOverlay');
const taskTemplate = document.getElementById('taskTemplate');
const stepProgress = document.getElementById('stepProgress');
const stepNumber = document.getElementById('stepNumber');
const stepDescription = document.getElementById('stepDescription');
const progressFill = document.getElementById('progressFill');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    startSession();
});

function setupEventListeners() {
    // Camera button
    cameraBtn.addEventListener('click', () => {
        cameraInput.click();
    });

    // Camera input change
    cameraInput.addEventListener('change', handleImageSelect);

    // Remove image preview
    removeImage.addEventListener('click', clearImage);

    // Send button
    sendBtn.addEventListener('click', sendMessage);

    // Enter key to send
    messageInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Voice button (placeholder)
    voiceBtn.addEventListener('click', () => {
        alert('Voice input coming soon! For now, type your question or take a photo.');
    });

    // Task template change
    taskTemplate.addEventListener('change', () => {
        // Start a new session with the new task
        startSession();
    });
}

async function startSession() {
    try {
        const response = await fetch(`${API_BASE}/sessions/chat/start`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                task_template: taskTemplate.value,
            }),
        });

        if (response.ok) {
            const data = await response.json();
            sessionId = data.session_id;
            console.log('Session started:', sessionId);
        } else {
            // For demo mode without auth, generate local session ID
            sessionId = 'demo-' + Date.now();
            console.log('Demo mode - session:', sessionId);
        }
    } catch (error) {
        // Offline/demo mode
        sessionId = 'demo-' + Date.now();
        console.log('Demo mode (offline) - session:', sessionId);
    }
}

function handleImageSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith('image/')) {
        alert('Please select an image file');
        return;
    }

    // Validate file size (max 10MB)
    if (file.size > 10 * 1024 * 1024) {
        alert('Image too large. Please select an image under 10MB.');
        return;
    }

    // Store the pending image
    pendingImage = file;

    // Show preview
    const reader = new FileReader();
    reader.onload = (e) => {
        previewImg.src = e.target.result;
        imagePreview.classList.remove('hidden');
    };
    reader.readAsDataURL(file);

    // Clear the input so same file can be selected again
    cameraInput.value = '';
}

function clearImage() {
    pendingImage = null;
    previewImg.src = '';
    imagePreview.classList.add('hidden');
}

async function sendMessage() {
    const text = messageInput.value.trim();

    // Need either text or image
    if (!text && !pendingImage) {
        return;
    }

    // Add user message to chat
    addUserMessage(text, pendingImage);

    // Clear inputs
    messageInput.value = '';
    const imageToSend = pendingImage;
    clearImage();

    // Show loading
    showLoading(true);

    try {
        let response;

        if (imageToSend) {
            // Send image (with optional text)
            response = await sendImageToAPI(imageToSend, text);
        } else {
            // Send text only
            response = await sendTextToAPI(text);
        }

        // Add AI response
        addAIMessage(response);

        // Update step progress if applicable
        updateStepProgress(response);

    } catch (error) {
        console.error('Error:', error);
        addAIMessage({
            message: 'Sorry, I encountered an error. Please try again.',
            hazards: [],
            suggested_action: null,
        });
    } finally {
        showLoading(false);
    }
}

async function sendImageToAPI(imageFile, message) {
    const formData = new FormData();
    formData.append('image', imageFile);
    if (message) {
        formData.append('message', message);
    }

    const response = await fetch(`${API_BASE}/sessions/${sessionId}/image`, {
        method: 'POST',
        body: formData,
    });

    if (!response.ok) {
        // Demo mode fallback
        return generateDemoResponse(message, true);
    }

    return response.json();
}

async function sendTextToAPI(message) {
    const response = await fetch(`${API_BASE}/sessions/${sessionId}/message`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message }),
    });

    if (!response.ok) {
        // Demo mode fallback
        return generateDemoResponse(message, false);
    }

    return response.json();
}

function generateDemoResponse(message, hasImage) {
    // Demo responses when API is not available
    const lowerMsg = (message || '').toLowerCase();

    if (hasImage) {
        return {
            message: "I can see your image. In a live session, I would analyze this and provide specific guidance based on what I see. For now, this is demo mode.\n\nTo get real AI analysis, please configure your Google API key and start the backend server.",
            hazards: ['Demo mode - no real analysis'],
            suggested_action: 'Start the backend with: uvicorn backend.api.main:app --reload',
        };
    }

    if (lowerMsg.includes('thermostat') || lowerMsg.includes('install')) {
        return {
            message: "For thermostat installation, I'd typically walk you through:\n\n1. Turn off power at the breaker\n2. Remove the old thermostat faceplate\n3. Label and disconnect wires\n4. Mount new baseplate\n5. Connect wires to matching terminals\n6. Attach faceplate and restore power\n\nTake a photo of your current setup, and I can give specific guidance!",
            hazards: ['Always verify power is off before working on electrical'],
            suggested_action: 'Send a photo of your current thermostat wiring',
        };
    }

    if (lowerMsg.includes('cool') || lowerMsg.includes('ac')) {
        return {
            message: "For AC not cooling issues, let's check:\n\n1. Is the thermostat set correctly?\n2. Is the air filter clean?\n3. Are the condenser coils dirty?\n4. Is the refrigerant level adequate?\n\nSend me a photo of the unit and I can help diagnose further.",
            hazards: [],
            suggested_action: 'Check and replace air filter if dirty',
        };
    }

    return {
        message: "I'm here to help! In demo mode, I can show you the interface, but for real AI-powered guidance:\n\n1. Configure your .env file with API keys\n2. Run: uvicorn backend.api.main:app --reload\n3. Then take a photo or ask a question!\n\nWhat HVAC task are you working on today?",
        hazards: [],
        suggested_action: null,
    };
}

function addUserMessage(text, imageFile) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user';

    let content = '<div class="message-content">';

    // Add image if present
    if (imageFile) {
        const reader = new FileReader();
        reader.onload = (e) => {
            const img = messageDiv.querySelector('.message-image');
            if (img) img.src = e.target.result;
        };
        reader.readAsDataURL(imageFile);
        content += '<img class="message-image" src="" alt="Uploaded image">';
    }

    // Add text if present
    if (text) {
        content += `<p>${escapeHtml(text)}</p>`;
    } else if (imageFile) {
        content += '<p><em>Photo sent</em></p>';
    }

    content += '</div>';
    content += `<div class="user-avatar">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
            <circle cx="12" cy="7" r="4"/>
        </svg>
    </div>`;

    messageDiv.innerHTML = content;
    chatContainer.appendChild(messageDiv);
    scrollToBottom();
}

function addAIMessage(response) {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message ai';

    let content = '<div class="ai-avatar">AI</div>';
    content += '<div class="message-content">';

    // Main message
    const paragraphs = response.message.split('\n\n');
    paragraphs.forEach(p => {
        if (p.trim()) {
            // Convert single newlines to <br> within paragraphs
            const formatted = escapeHtml(p).replace(/\n/g, '<br>');
            content += `<p>${formatted}</p>`;
        }
    });

    // Hazards
    if (response.hazards && response.hazards.length > 0) {
        content += '<div class="hazard-warning">';
        content += '<div class="hazard-title">⚠️ Safety Warning</div>';
        content += '<ul>';
        response.hazards.forEach(h => {
            content += `<li>${escapeHtml(h)}</li>`;
        });
        content += '</ul></div>';
    }

    // Suggested action
    if (response.suggested_action) {
        content += '<div class="suggested-action">';
        content += '<div class="action-title">✓ Next Step</div>';
        content += `<p>${escapeHtml(response.suggested_action)}</p>`;
        content += '</div>';
    }

    content += '</div>';

    messageDiv.innerHTML = content;
    chatContainer.appendChild(messageDiv);
    scrollToBottom();
}

function updateStepProgress(response) {
    // Extract step info from response if present
    const stepMatch = response.message.match(/step\s*(\d+)/i);
    if (stepMatch) {
        const step = parseInt(stepMatch[1]);
        stepNumber.textContent = `Step ${step}`;

        // Estimate total steps based on task
        const totalSteps = 6;  // Default
        const progress = Math.min((step / totalSteps) * 100, 100);
        progressFill.style.width = `${progress}%`;

        stepProgress.classList.remove('hidden');
    }
}

function showLoading(show) {
    if (show) {
        loadingOverlay.classList.remove('hidden');
    } else {
        loadingOverlay.classList.add('hidden');
    }
}

function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
