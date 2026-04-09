import { state, setConnected } from './state.js';
const WS_URL = 'wss://mandala-engineer-chat.onrender.com/ws';
let ws = null;
export function connect() {
    ws = new WebSocket(WS_URL);
    ws.onopen = () => { setConnected(true); ws.send(JSON.stringify({type:'init',session_id:'main'})); };
    ws.onclose = () => { setConnected(false); setTimeout(connect, 3000); };
    ws.onmessage = (e) => { const data = JSON.parse(e.data); handleMessage(data); };
    state.ws = ws;
}
function handleMessage(data) {
    if (data.type === 'connected') {
        document.getElementById('coreVersion').textContent = data.core_version || '';
    }
    if (data.type === 'stream') {
        window.dispatchEvent(new CustomEvent('stream', { detail: data.content }));
    }
}
export function send(text) { if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type:'ask',text,session_id:'main'})); }