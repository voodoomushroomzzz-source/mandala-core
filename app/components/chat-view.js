class ChatView extends HTMLElement {
    connectedCallback() { this.innerHTML = `<div class="messages" id="messages"></div>`; }
    addMessage(role, content) {
        const msg = document.createElement('div');
        msg.className = `msg ${role}`;
        msg.innerHTML = `<div class="bubble">${content}</div>`;
        this.querySelector('.messages').appendChild(msg);
        this.scrollTop = this.scrollHeight;
    }
    clear() { this.innerHTML = `<div class="messages"></div>`; }
}
customElements.define('chat-view', ChatView);