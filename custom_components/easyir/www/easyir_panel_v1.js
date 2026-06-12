/** EasyIR main panel: hubs tree + remote wizard grid. */
class EasyIrMainPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._state = { hubs: [] };
    this._areas = [];
    this._discoverableHubs = [];
    this._wizard = null;
    this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._initialized = true;
      this._render();
      this._bind();
      this._loadState();
    }
  }

  get hass() {
    return this._hass;
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; padding:16px; color:var(--primary-text-color); }
        h2 { margin:0 0 12px 0; }
        .row { display:flex; gap:8px; align-items:center; margin-bottom:12px; }
        button {
          border:1px solid var(--divider-color);
          border-radius:10px;
          background:var(--card-background-color);
          color:var(--primary-text-color);
          padding:10px 14px;
          cursor:pointer;
        }
        .status { min-height:1.2em; margin-bottom:12px; color:var(--secondary-text-color); }
        .status.error { color: var(--error-color, #d32f2f); }
        .tree { display:flex; flex-direction:column; gap:10px; }
        .hub {
          border:1px solid var(--divider-color);
          border-radius:12px;
          padding:10px 12px;
          background:var(--card-background-color);
        }
        .hub-title { font-weight:600; margin-bottom:8px; }
        .remote-list { display:grid; gap:6px; padding-left:12px; }
        .remote-item {
          border:1px solid var(--divider-color);
          border-radius:8px;
          padding:8px;
          background:var(--secondary-background-color, rgba(255,255,255,0.02));
        }
        .hint { color:var(--secondary-text-color); font-size:0.9rem; }
        .modal-wrap {
          position:fixed; inset:0; display:none; align-items:center; justify-content:center;
          background:rgba(0,0,0,0.55); z-index:1000;
        }
        .modal-wrap.open { display:flex; }
        .modal {
          width:min(980px, 94vw);
          max-height:90vh;
          overflow:auto;
          border-radius:16px;
          background:var(--card-background-color);
          border:1px solid var(--divider-color);
          padding:16px;
        }
        .wizard-title { font-size:1.1rem; font-weight:600; margin-bottom:10px; }
        .wizard-sub { color:var(--secondary-text-color); margin-bottom:10px; }
        .grid {
          display:grid;
          grid-template-columns:repeat(auto-fill, minmax(180px, 1fr));
          gap:10px;
        }
        .grid.devices {
          max-height:48vh;
          overflow:auto;
          padding-right:4px;
        }
        .card {
          border:1px solid var(--divider-color);
          border-radius:10px;
          padding:10px;
          cursor:pointer;
          user-select:none;
          background:var(--secondary-background-color, rgba(255,255,255,0.02));
        }
        .card.selected {
          outline:2px solid var(--accent-color, #03a9f4);
          border-color:var(--accent-color, #03a9f4);
        }
        .field { display:flex; flex-direction:column; gap:6px; margin:10px 0; }
        input, select {
          border:1px solid var(--divider-color);
          border-radius:8px;
          padding:8px;
          background:var(--card-background-color);
          color:var(--primary-text-color);
        }
        .actions { display:flex; gap:8px; justify-content:flex-end; margin-top:12px; }
      </style>
      <h2>EasyIR</h2>
      <div class="row">
        <button id="add-hub">Добавить хаб</button>
        <button id="add-remote">Добавить пульт</button>
      </div>
      <div class="status" id="status"></div>
      <div class="tree" id="tree"></div>
      <div class="modal-wrap" id="modal-wrap">
        <div class="modal">
          <div id="modal-body"></div>
        </div>
      </div>
    `;
  }

  _bind() {
    this.shadowRoot.getElementById("add-hub").addEventListener("click", () => this._openHubDialog());
    this.shadowRoot.getElementById("add-remote").addEventListener("click", () => this._openRemoteWizard());
  }

  _setStatus(text, isError = false) {
    const el = this.shadowRoot.getElementById("status");
    el.textContent = text || "";
    el.classList.toggle("error", Boolean(isError));
  }

  _openModal(html) {
    this.shadowRoot.getElementById("modal-body").innerHTML = html;
    this.shadowRoot.getElementById("modal-wrap").classList.add("open");
  }

  _closeModal() {
    this.shadowRoot.getElementById("modal-wrap").classList.remove("open");
    this.shadowRoot.getElementById("modal-body").innerHTML = "";
    this._wizard = null;
  }

  async _loadState() {
    if (!this._hass) return;
    try {
      const data = await this._hass.callApi("GET", "easyir/ui/state");
      this._state = data || { hubs: [] };
      this._renderTree();
    } catch (err) {
      this._setStatus(`Ошибка загрузки дерева: ${err && err.message ? err.message : String(err)}`, true);
    }
  }

  _renderTree() {
    const tree = this.shadowRoot.getElementById("tree");
    tree.innerHTML = "";
    const hubs = (this._state && this._state.hubs) || [];
    if (!hubs.length) {
      tree.innerHTML = `<div class="hint">Нет настроенных хабов EasyIR.</div>`;
      return;
    }
    for (const hub of hubs) {
      const wrapper = document.createElement("div");
      wrapper.className = "hub";
      const remotes = Array.isArray(hub.remotes) ? hub.remotes : [];
      const remotesHtml = remotes.length
        ? remotes.map((r) =>
            `<div class="remote-item"><strong>${this._esc(r.title || "Пульт")}</strong><div class="hint">${this._esc(r.profile_path || "")}</div></div>`
          ).join("")
        : `<div class="hint">Пультов пока нет.</div>`;
      wrapper.innerHTML = `
        <div class="hub-title">${this._esc(hub.title || "IR Hub")} <span class="hint">(${this._esc(hub.ieee || "")})</span></div>
        <div class="remote-list">${remotesHtml}</div>
      `;
      tree.appendChild(wrapper);
    }
  }

  async _openHubDialog() {
    if (!this._hass) return;
    try {
      const [discover, areas] = await Promise.all([
        this._hass.callApi("GET", "easyir/ui/hubs/discover"),
        this._hass.callApi("GET", "easyir/ui/areas"),
      ]);
      this._discoverableHubs = (discover && discover.devices) || [];
      this._areas = (areas && areas.areas) || [];
      if (!this._discoverableHubs.length) {
        this._setStatus("Все поддерживаемые хабы уже добавлены.");
        return;
      }
      const hubOptions = this._discoverableHubs
        .map((d) => `<option value="${this._escAttr(d.device_id)}">${this._esc(d.label)}</option>`)
        .join("");
      const areaOptions = [`<option value="">(без комнаты)</option>`]
        .concat(this._areas.map((a) => `<option value="${this._escAttr(a.area_id)}">${this._esc(a.name)}</option>`))
        .join("");
      this._openModal(`
        <div class="wizard-title">Добавить хаб</div>
        <div class="wizard-sub">Выберите устройство, укажите имя и комнату.</div>
        <div class="field"><label>Устройство</label><select id="hub-device">${hubOptions}</select></div>
        <div class="field"><label>Имя хаба</label><input id="hub-name" type="text" value="${this._escAttr(this._discoverableHubs[0].default_name || "")}"/></div>
        <div class="field"><label>Комната</label><select id="hub-area">${areaOptions}</select></div>
        <div class="actions">
          <button id="cancel">Отмена</button>
          <button id="create-hub">Создать</button>
        </div>
      `);
      this.shadowRoot.getElementById("cancel").addEventListener("click", () => this._closeModal());
      this.shadowRoot.getElementById("hub-device").addEventListener("change", (ev) => {
        const val = ev.target.value;
        const item = this._discoverableHubs.find((d) => d.device_id === val);
        if (item) this.shadowRoot.getElementById("hub-name").value = item.default_name || "";
      });
      this.shadowRoot.getElementById("create-hub").addEventListener("click", async () => {
        const device_id = this.shadowRoot.getElementById("hub-device").value;
        const hub_name = this.shadowRoot.getElementById("hub-name").value.trim();
        const area_id = this.shadowRoot.getElementById("hub-area").value.trim();
        if (!hub_name) {
          this._setStatus("Введите имя хаба.", true);
          return;
        }
        try {
          await this._hass.callApi("POST", "easyir/ui/hubs", { device_id, hub_name, area_id });
          this._setStatus("Хаб добавлен.");
          this._closeModal();
          await this._loadState();
        } catch (err) {
          this._setStatus(`Ошибка добавления хаба: ${err && err.message ? err.message : String(err)}`, true);
        }
      });
    } catch (err) {
      this._setStatus(`Ошибка загрузки данных хаба: ${err && err.message ? err.message : String(err)}`, true);
    }
  }

  _remoteTypeCards() {
    return [
      { value: "climate", label: "Кондиционер / климат" },
      { value: "tv", label: "ТВ" },
      { value: "other", label: "Другое" },
    ];
  }

  async _openRemoteWizard() {
    if (!this._hass) return;
    const hubs = (this._state && this._state.hubs) || [];
    if (!hubs.length) {
      this._setStatus("Сначала добавьте хаб.");
      return;
    }
    this._wizard = {
      step: 1,
      hub_id: hubs[0].hub_id,
      remote_type: null,
      brand: null,
      profile_choice: null,
      brands: [],
      devices: [],
      remote_name: "",
    };
    this._renderWizardStep();
  }

  async _loadBrandsForType() {
    const response = await this._hass.callApi(
      "GET",
      `easyir/ui/catalog?remote_type=${encodeURIComponent(this._wizard.remote_type)}`
    );
    this._wizard.brands = (response && response.brands) || [];
    this._wizard.brand = this._wizard.brands.length ? this._wizard.brands[0].brand : null;
  }

  async _loadDevicesForBrand() {
    const response = await this._hass.callApi(
      "GET",
      `easyir/ui/catalog?remote_type=${encodeURIComponent(this._wizard.remote_type)}&brand=${encodeURIComponent(this._wizard.brand)}`
    );
    this._wizard.devices = (response && response.devices) || [];
    this._wizard.profile_choice = this._wizard.devices.length ? this._wizard.devices[0].value : null;
  }

  _wizardHubSelectHtml() {
    const hubs = (this._state && this._state.hubs) || [];
    const options = hubs
      .map((h) => `<option value="${this._escAttr(h.hub_id)}" ${h.hub_id === this._wizard.hub_id ? "selected" : ""}>${this._esc(h.title)}</option>`)
      .join("");
    return `<div class="field"><label>Хаб</label><select id="wiz-hub">${options}</select></div>`;
  }

  _renderWizardStep() {
    if (!this._wizard) return;
    const w = this._wizard;
    if (w.step === 1) {
      const cards = this._remoteTypeCards()
        .map((item) => `<div class="card ${w.remote_type === item.value ? "selected" : ""}" data-type="${this._escAttr(item.value)}">${this._esc(item.label)}</div>`)
        .join("");
      this._openModal(`
        <div class="wizard-title">Шаг 1 из 3: тип пульта</div>
        ${this._wizardHubSelectHtml()}
        <div class="grid">${cards}</div>
        <div class="actions">
          <button id="wiz-cancel">Отмена</button>
          <button id="wiz-next" ${w.remote_type ? "" : "disabled"}>Далее</button>
        </div>
      `);
      this.shadowRoot.querySelectorAll(".card[data-type]").forEach((node) => {
        node.addEventListener("click", () => {
          w.remote_type = node.dataset.type;
          this._renderWizardStep();
        });
      });
      this.shadowRoot.getElementById("wiz-hub").addEventListener("change", (ev) => {
        w.hub_id = ev.target.value;
      });
      this.shadowRoot.getElementById("wiz-cancel").addEventListener("click", () => this._closeModal());
      this.shadowRoot.getElementById("wiz-next").addEventListener("click", async () => {
        try {
          await this._loadBrandsForType();
          if (!w.brands.length) {
            this._setStatus("Для выбранного типа пульта профили не найдены.", true);
            return;
          }
          w.step = 2;
          this._renderWizardStep();
        } catch (err) {
          this._setStatus(`Ошибка загрузки брендов: ${err && err.message ? err.message : String(err)}`, true);
        }
      });
      return;
    }

    if (w.step === 2) {
      const cards = w.brands
        .map((item) => `<div class="card ${w.brand === item.brand ? "selected" : ""}" data-brand="${this._escAttr(item.brand)}"><strong>${this._esc(item.brand)}</strong><div class="hint">${item.count} моделей</div></div>`)
        .join("");
      this._openModal(`
        <div class="wizard-title">Шаг 2 из 3: бренд</div>
        <div class="wizard-sub">Сетка брендов без длинного списка.</div>
        <div class="grid">${cards}</div>
        <div class="actions">
          <button id="wiz-back">Назад</button>
          <button id="wiz-cancel">Отмена</button>
          <button id="wiz-next" ${w.brand ? "" : "disabled"}>Далее</button>
        </div>
      `);
      this.shadowRoot.querySelectorAll(".card[data-brand]").forEach((node) => {
        node.addEventListener("click", () => {
          w.brand = node.dataset.brand;
          this._renderWizardStep();
        });
      });
      this.shadowRoot.getElementById("wiz-back").addEventListener("click", () => {
        w.step = 1;
        this._renderWizardStep();
      });
      this.shadowRoot.getElementById("wiz-cancel").addEventListener("click", () => this._closeModal());
      this.shadowRoot.getElementById("wiz-next").addEventListener("click", async () => {
        try {
          await this._loadDevicesForBrand();
          if (!w.devices.length) {
            this._setStatus("Для выбранного бренда профили не найдены.", true);
            return;
          }
          w.step = 3;
          this._renderWizardStep();
        } catch (err) {
          this._setStatus(`Ошибка загрузки устройств: ${err && err.message ? err.message : String(err)}`, true);
        }
      });
      return;
    }

    const cards = w.devices
      .map((item) => `<div class="card ${w.profile_choice === item.value ? "selected" : ""}" data-profile="${this._escAttr(item.value)}">${this._esc(item.label)}</div>`)
      .join("");
    this._openModal(`
      <div class="wizard-title">Шаг 3 из 3: устройство</div>
      <div class="wizard-sub">Сетка устройств (несколько колонок, с прокруткой).</div>
      <div class="grid devices">${cards}</div>
      <div class="field"><label>Имя пульта (необязательно)</label><input id="wiz-remote-name" type="text" value="${this._escAttr(w.remote_name || "")}" placeholder="Например: LG в гостиной"/></div>
      <div class="actions">
        <button id="wiz-back">Назад</button>
        <button id="wiz-cancel">Отмена</button>
        <button id="wiz-create" ${w.profile_choice ? "" : "disabled"}>Создать пульт</button>
      </div>
    `);
    this.shadowRoot.querySelectorAll(".card[data-profile]").forEach((node) => {
      node.addEventListener("click", () => {
        w.profile_choice = node.dataset.profile;
        this._renderWizardStep();
      });
    });
    this.shadowRoot.getElementById("wiz-remote-name").addEventListener("input", (ev) => {
      w.remote_name = ev.target.value;
    });
    this.shadowRoot.getElementById("wiz-back").addEventListener("click", () => {
      w.step = 2;
      this._renderWizardStep();
    });
    this.shadowRoot.getElementById("wiz-cancel").addEventListener("click", () => this._closeModal());
    this.shadowRoot.getElementById("wiz-create").addEventListener("click", async () => {
      try {
        await this._hass.callApi("POST", "easyir/ui/remotes", {
          hub_id: w.hub_id,
          remote_type: w.remote_type,
          brand: w.brand,
          profile_choice: w.profile_choice,
          remote_name: w.remote_name || "",
        });
        this._setStatus("Пульт добавлен.");
        this._closeModal();
        await this._loadState();
      } catch (err) {
        this._setStatus(`Ошибка создания пульта: ${err && err.message ? err.message : String(err)}`, true);
      }
    });
  }

  _esc(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;");
  }

  _escAttr(value) {
    return this._esc(value).replaceAll('"', "&quot;");
  }
}

customElements.define("easyir-main-panel", EasyIrMainPanel);

