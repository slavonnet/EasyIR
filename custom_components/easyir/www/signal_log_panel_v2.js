/** EasyIR Signal Log panel with authenticated HA API calls. */
class EasyIrSignalLogPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._offset = 0;
    this._loading = false;
    this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._initialized = true;
      this._render();
      this._bindActions();
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
    this.shadowRoot.getElementById("status").textContent = text;
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
