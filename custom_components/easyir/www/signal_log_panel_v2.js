/** EasyIR Signal Log panel with authenticated HA API calls. */
class EasyIrSignalLogPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._offset = 0;
    this._loading = false;
    this._learnHubs = [];
    this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._initialized = true;
      this._render();
      this._bindActions();
      this._loadLearnHubs();
      this._load(false);
    }
  }

  get hass() {
    return this._hass;
  }

  _render() {
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          box-sizing: border-box;
          padding: 16px;
          color: var(--primary-text-color);
          background: var(--primary-background-color);
        }
        h2 {
          margin: 0 0 12px 0;
          font-size: 1.2rem;
        }
        .row {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
          align-items: center;
          margin-bottom: 8px;
        }
        label {
          font-size: 0.85rem;
          color: var(--secondary-text-color);
        }
        input, select, button {
          font: inherit;
          padding: 6px 8px;
        }
        input[type="text"], input[type="number"], select {
          border: 1px solid var(--divider-color);
          border-radius: 6px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
        }
        button {
          border: 1px solid var(--divider-color);
          border-radius: 6px;
          background: var(--card-background-color);
          color: var(--primary-text-color);
          cursor: pointer;
        }
        button:disabled {
          opacity: 0.6;
          cursor: default;
        }
        .status {
          margin: 6px 0 10px 0;
          font-size: 0.85rem;
          color: var(--secondary-text-color);
          min-height: 1em;
        }
        .status.error {
          color: var(--error-color, #d32f2f);
        }
        .status.ok {
          color: var(--success-color, #2e7d32);
        }
        table {
          width: 100%;
          border-collapse: collapse;
          background: var(--card-background-color);
        }
        th, td {
          border: 1px solid var(--divider-color);
          text-align: left;
          padding: 6px 8px;
          font-size: 0.8rem;
          vertical-align: top;
        }
        th {
          font-weight: 600;
        }
        td pre {
          margin: 0;
          white-space: pre-wrap;
          word-break: break-word;
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
          font-size: 0.75rem;
        }
      </style>
      <h2>EasyIR Signal Log</h2>
      <div class="row">
        <label for="learn-hub">Learn hub</label>
        <select id="learn-hub">
          <option value="">manual IEEE input</option>
        </select>
        <label for="learn-ieee">IEEE</label>
        <input id="learn-ieee" type="text" placeholder="aa:bb:cc:dd:ee:ff" />
        <label for="learn-endpoint">Endpoint</label>
        <input id="learn-endpoint" type="number" min="1" max="240" value="1" />
        <label for="learn-timeout">Timeout (s)</label>
        <input id="learn-timeout" type="number" min="5" max="120" value="20" />
        <button id="start-learn" type="button">StartLearn</button>
      </div>
      <div class="row">
        <label for="room">Room (area id)</label>
        <input id="room" type="text" placeholder="optional" />
        <label for="dir">Direction</label>
        <select id="dir">
          <option value="">all</option>
          <option value="inbound">inbound</option>
          <option value="outbound">outbound</option>
        </select>
        <label for="limit">Limit</label>
        <input id="limit" type="number" min="1" max="200" value="50" />
        <button id="load" type="button">Load</button>
        <button id="more" type="button" disabled>Older page</button>
      </div>
      <div class="status" id="status"></div>
      <table>
        <thead>
          <tr>
            <th>Time (UTC)</th>
            <th>Dir</th>
            <th>Room</th>
            <th>IEEE</th>
            <th>Protocol</th>
            <th>Decoded</th>
          </tr>
        </thead>
        <tbody id="rows"></tbody>
      </table>
    `;
  }

  _bindActions() {
    this.shadowRoot.getElementById("learn-hub").addEventListener("change", () => {
      this._onLearnHubChange();
    });
    this.shadowRoot.getElementById("start-learn").addEventListener("click", () => {
      this._startLearn();
    });
    this.shadowRoot.getElementById("load").addEventListener("click", () => {
      this._offset = 0;
      this._load(false);
    });
    this.shadowRoot.getElementById("more").addEventListener("click", () => {
      const limit = this._limitValue();
      this._offset += limit;
      this._load(true);
    });
  }

  _limitValue() {
    const raw = Number.parseInt(this.shadowRoot.getElementById("limit").value || "50", 10);
    if (Number.isNaN(raw)) return 50;
    return Math.max(1, Math.min(200, raw));
  }

  _buildPath() {
    const room = this.shadowRoot.getElementById("room").value.trim();
    const direction = this.shadowRoot.getElementById("dir").value;
    const params = new URLSearchParams({
      limit: String(this._limitValue()),
      offset: String(this._offset),
    });
    if (room) params.set("room_id", room);
    if (direction) params.set("direction", direction);
    return `easyir/signal_log/events?${params.toString()}`;
  }

  _setStatus(text) {
    const el = this.shadowRoot.getElementById("status");
    el.classList.remove("error", "ok");
    el.textContent = text;
  }

  _setStatusError(text) {
    const el = this.shadowRoot.getElementById("status");
    el.classList.remove("ok");
    el.classList.add("error");
    el.textContent = text;
  }

  _setStatusOk(text) {
    const el = this.shadowRoot.getElementById("status");
    el.classList.remove("error");
    el.classList.add("ok");
    el.textContent = text;
  }

  _learnPayload() {
    const selectedHubId = this.shadowRoot.getElementById("learn-hub").value.trim();
    const ieee = this.shadowRoot.getElementById("learn-ieee").value.trim();
    const endpointRaw = Number.parseInt(this.shadowRoot.getElementById("learn-endpoint").value || "1", 10);
    const timeoutRaw = Number.parseInt(this.shadowRoot.getElementById("learn-timeout").value || "20", 10);
    if (!selectedHubId && !ieee) {
      throw new Error("Learn target is required: select hub or enter IEEE");
    }
    const endpoint_id = Number.isNaN(endpointRaw) ? null : Math.max(1, Math.min(240, endpointRaw));
    const timeout_s = Number.isNaN(timeoutRaw) ? 20 : Math.max(5, Math.min(120, timeoutRaw));
    const payload = { timeout_s };
    if (selectedHubId) {
      payload.hub_id = selectedHubId;
    }
    if (ieee) {
      payload.ieee = ieee;
    }
    if (endpoint_id !== null) {
      payload.endpoint_id = endpoint_id;
    }
    return payload;
  }

  _hubLabel(hub) {
    const title = hub && hub.title ? String(hub.title) : "EasyIR hub";
    const ieee = hub && hub.ieee ? String(hub.ieee) : "";
    const profile = hub && hub.vendor_profile ? `, ${hub.vendor_profile}` : "";
    return ieee ? `${title} (${ieee}${profile})` : `${title}${profile}`;
  }

  _renderLearnHubOptions() {
    const select = this.shadowRoot.getElementById("learn-hub");
    if (!select) {
      return;
    }
    const current = select.value;
    select.innerHTML = `<option value="">manual IEEE input</option>`;
    for (const hub of this._learnHubs) {
      if (!hub || !hub.learn_supported) {
        continue;
      }
      const option = document.createElement("option");
      option.value = String(hub.hub_id || "");
      option.textContent = this._hubLabel(hub);
      select.appendChild(option);
    }
    if (current && [...select.options].some((opt) => opt.value === current)) {
      select.value = current;
    }
  }

  _onLearnHubChange() {
    const select = this.shadowRoot.getElementById("learn-hub");
    const hubId = select ? select.value.trim() : "";
    if (!hubId) {
      return;
    }
    const hub = this._learnHubs.find((item) => String(item.hub_id) === hubId);
    if (!hub) {
      return;
    }
    if (hub.ieee) {
      this.shadowRoot.getElementById("learn-ieee").value = String(hub.ieee);
    }
    if (hub.endpoint_id !== null && hub.endpoint_id !== undefined) {
      this.shadowRoot.getElementById("learn-endpoint").value = String(hub.endpoint_id);
    }
  }

  async _loadLearnHubs() {
    if (!this._hass) {
      return;
    }
    try {
      const data = await this._hass.callApi("GET", "easyir/signal_log/hubs");
      this._learnHubs = Array.isArray(data && data.hubs) ? data.hubs : [];
      this._renderLearnHubOptions();
      this._onLearnHubChange();
    } catch (_err) {
      this._learnHubs = [];
      this._renderLearnHubOptions();
    }
  }

  _extractErrorMessage(err) {
    if (!err) {
      return "Unknown error";
    }
    if (typeof err === "string") {
      return err;
    }
    if (err.message) {
      let msg = String(err.message);
      if (err.error && typeof err.error === "string") {
        msg += `: ${err.error}`;
      }
      return msg;
    }
    if (err.error && typeof err.error === "string") {
      return err.error;
    }
    if (err.body && typeof err.body === "string") {
      return err.body;
    }
    try {
      return JSON.stringify(err);
    } catch (_jsonErr) {
      return String(err);
    }
  }

  async _startLearn() {
    if (!this._hass || this._loading) {
      return;
    }
    let payload;
    try {
      payload = this._learnPayload();
    } catch (err) {
      this._setStatusError(err.message || String(err));
      return;
    }
    this._setBusy(true);
    this._setStatus("Starting learn... Press remote button now.");
    try {
      const result = await this._hass.callApi("POST", "easyir/signal_log/start_learn", payload);
      const vendor = result && result.vendor_profile ? ` vendor=${result.vendor_profile}` : "";
      const hub = result && result.hub_id ? ` hub=${result.hub_id}` : "";
      const codeLen = result && result.code ? ` code_len=${String(result.code).length}` : "";
      const source = result && result.source_encoding ? ` source=${result.source_encoding}` : "";
      this._setStatusOk(`Learn completed.${hub}${vendor}${source}${codeLen}`);
      this._offset = 0;
      await this._load(false);
    } catch (err) {
      const msg = this._extractErrorMessage(err);
      this._setStatusError(`StartLearn error: ${msg}`);
    } finally {
      this._setBusy(false);
    }
  }

  _setBusy(value) {
    this._loading = value;
    this.shadowRoot.getElementById("load").disabled = value;
    const more = this.shadowRoot.getElementById("more");
    if (value) {
      more.disabled = true;
    }
  }

  async _load(append) {
    if (!this._hass || this._loading) {
      return;
    }
    this._setBusy(true);
    this._setStatus("Loading...");
    try {
      const data = await this._hass.callApi("GET", this._buildPath());
      const rows = this.shadowRoot.getElementById("rows");
      if (!append) {
        rows.innerHTML = "";
      }
      for (const ev of data.events || []) {
        const tr = document.createElement("tr");
        const decoded = ev.decoded ? JSON.stringify(ev.decoded, null, 2) : "";
        tr.innerHTML = `
          <td>${ev.recorded_at || ""}</td>
          <td>${ev.direction || ""}</td>
          <td>${ev.room_id || ""}</td>
          <td>${ev.ieee || ""}</td>
          <td>${ev.protocol_hint || ""}</td>
          <td><pre>${decoded}</pre></td>
        `;
        rows.appendChild(tr);
      }
      const hasMore = Boolean(data.has_more);
      this.shadowRoot.getElementById("more").disabled = !hasMore;
      this._setStatus(`${(data.events || []).length} events${hasMore ? " (more available)" : ""}`);
    } catch (err) {
      const msg = (err && err.message) ? err.message : String(err);
      this._setStatus(`Error: ${msg}`);
      this.shadowRoot.getElementById("more").disabled = true;
    } finally {
      this._setBusy(false);
    }
  }
}

customElements.define("easyir-signal-log-panel", EasyIrSignalLogPanel);
