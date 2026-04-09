class ProtocolBar extends HTMLElement {
    connectedCallback() {
        this.innerHTML = `
            <div class="proto-bar">
                <button data-proto="internal/onboarding" title="Онбординг">ON</button>
                <button data-proto="internal/registry_sync" title="Синхронизация">SYNC</button>
                <button data-proto="internal/ideas_roadmaps" title="Идеи и роадмапы">IDEAS</button>
                <button data-proto="deep_analysis" title="Глубокий анализ">DEEP</button>
            </div>
        `;
        this.querySelectorAll('button').forEach(btn => {
            btn.addEventListener('click', () => {
                const proto = btn.dataset.proto;
                window.dispatchEvent(new CustomEvent('activate-protocol', { detail: proto }));
            });
        });
    }
}
customElements.define('protocol-bar', ProtocolBar);