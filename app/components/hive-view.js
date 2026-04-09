class HiveView extends HTMLElement {
    connectedCallback() { this.innerHTML = `<div class="hive-placeholder">Карта сот  в разработке</div>`; }
}
customElements.define('hive-view', HiveView);