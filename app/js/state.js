export const state = {
    ws: null,
    messages: [],
    connected: false
};
export function setConnected(val) {
    state.connected = val;
    window.dispatchEvent(new CustomEvent('connection-change', { detail: val }));
}