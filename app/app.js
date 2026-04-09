import { connect, send } from './js/ws.js';
const chatView = document.querySelector('chat-view');
const input = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const statusDot = document.getElementById('statusDot');
connect();
window.addEventListener('connection-change', (e) => {
    statusDot.className = 'dot' + (e.detail ? '' : ' error');
});
window.addEventListener('activate-protocol', (e) => {
    const proto = e.detail;
    input.value = `активируй протокол ${proto.replace(/_/g,' ')}`;
    send(input.value);
    input.value = '';
});
sendBtn.addEventListener('click', () => {
    if (!input.value.trim()) return;
    chatView.addMessage('user', input.value);
    send(input.value);
    input.value = '';
});
window.addEventListener('stream', (e) => {
    let lastMsg = chatView.querySelector('.msg.assistant:last-child');
    if (!lastMsg) { chatView.addMessage('assistant', ''); lastMsg = chatView.querySelector('.msg.assistant:last-child'); }
    lastMsg.querySelector('.bubble').textContent += e.detail;
});