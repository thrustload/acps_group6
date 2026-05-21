const state = {
  mode: "auto",
  selectedAgent: "",
  sessionId: "web-demo",
  agents: [],
  demoPrompts: [],
  sending: false,
};

const els = {
  modeAuto: document.querySelector("#mode-auto"),
  modeManual: document.querySelector("#mode-manual"),
  agentList: document.querySelector("#agent-list"),
  serviceStatus: document.querySelector("#service-status"),
  promptRow: document.querySelector("#prompt-row"),
  messages: document.querySelector("#messages"),
  chainList: document.querySelector("#chain-list"),
  form: document.querySelector("#chat-form"),
  input: document.querySelector("#message-input"),
  sendButton: document.querySelector("#send-button"),
};

const fallbackAgents = [
  {
    name: "天气穿搭管家",
    accent: "#1f6feb",
    description: "查询校园天气并给出穿搭、带伞、通勤建议。",
  },
  {
    name: "快递小助手",
    accent: "#f59e0b",
    description: "查询快递物流状态并规划校园取件时间。",
  },
  {
    name: "北邮校园外卖小助手",
    accent: "#16a34a",
    description: "查询食堂菜单、外卖下单和配送状态。",
  },
  {
    name: "约会规划师",
    accent: "#7c3aed",
    description: "规划校园周边餐厅、电影和约会动线。",
  },
];

const fallbackPrompts = [
  "下午去取快递，顺便吃饭，今天穿什么？",
  "下雨天和女朋友在学校附近约会怎么安排？",
  "帮我查快递并规划取件时间",
];

function setMode(mode) {
  state.mode = mode;
  els.modeAuto.classList.toggle("active", mode === "auto");
  els.modeManual.classList.toggle("active", mode === "manual");
  els.modeAuto.setAttribute("aria-pressed", String(mode === "auto"));
  els.modeManual.setAttribute("aria-pressed", String(mode === "manual"));
  renderAgents();
}

function renderAgents() {
  els.agentList.innerHTML = "";
  state.agents.forEach((agent) => {
    const button = document.createElement("button");
    button.className = "agent-button";
    button.type = "button";
    button.style.setProperty("--agent-color", agent.accent);
    button.textContent = agent.name;
    button.title = agent.description;
    button.classList.toggle("active", state.selectedAgent === agent.name);
    button.addEventListener("click", () => {
      state.selectedAgent = agent.name;
      setMode("manual");
    });
    els.agentList.appendChild(button);
  });
}

function renderPrompts() {
  els.promptRow.innerHTML = "";
  state.demoPrompts.forEach((prompt) => {
    const button = document.createElement("button");
    button.className = "prompt-chip";
    button.type = "button";
    button.textContent = prompt;
    button.addEventListener("click", () => {
      els.input.value = prompt;
      els.input.focus();
    });
    els.promptRow.appendChild(button);
  });
}

function renderStatus(bridge) {
  const online = bridge && bridge.online;
  els.serviceStatus.innerHTML = `
    <div class="section-label">服务状态</div>
    <p class="${online ? "status-online" : "status-offline"}">
      ${online ? "leader_bridge.py 在线" : "leader_bridge.py 未连接"}
    </p>
    <p>${online ? "可以开始演示多智能体调用。" : "请先运行：python leader_bridge.py"}</p>
  `;
}

function appendMessage(role, text, extraClass = "") {
  const message = document.createElement("div");
  message.className = `message ${role} ${extraClass}`.trim();
  message.textContent = text;
  els.messages.appendChild(message);
  els.messages.scrollTop = els.messages.scrollHeight;
  return message;
}

function renderChain(chain) {
  els.chainList.innerHTML = "";
  const items = chain && chain.length ? chain : [
    { label: "等待用户请求", status: "warning" },
  ];

  items.forEach((item, index) => {
    const row = document.createElement("div");
    row.className = "chain-item";
    const statusText = {
      done: "完成",
      failed: "失败",
      warning: "等待",
    }[item.status] || item.status;
    const elapsed = item.elapsed_ms ? `<div class="chain-meta">${item.elapsed_ms} ms</div>` : "";
    row.innerHTML = `
      <div class="chain-topline">
        <span>${index + 1}. ${item.label}</span>
        <span class="chain-status ${item.status}">${statusText}</span>
      </div>
      ${elapsed}
    `;
    els.chainList.appendChild(row);
  });
}

function setSending(sending) {
  state.sending = sending;
  els.sendButton.disabled = sending;
  els.input.disabled = sending;
  els.sendButton.textContent = sending ? "调用中" : "发送";
}

function applyFallbackData() {
  if (!state.agents.length) {
    state.agents = fallbackAgents;
  }
  if (!state.demoPrompts.length) {
    state.demoPrompts = fallbackPrompts;
  }
  if (!state.selectedAgent && state.agents.length) {
    state.selectedAgent = state.agents[0].name;
  }
}

async function loadStatus() {
  try {
    const response = await fetch("/api/status");
    if (!response.ok) {
      throw new Error("状态接口不可用");
    }
    const data = await response.json();
    state.agents = data.agents || [];
    state.demoPrompts = data.demo_prompts || [];
    applyFallbackData();
    renderAgents();
    renderPrompts();
    renderStatus(data.bridge);
    renderChain([]);
  } catch (error) {
    applyFallbackData();
    renderAgents();
    renderPrompts();
    renderStatus({ online: false, error: String(error) });
    renderChain([]);
  }
}

async function sendMessage(message) {
  appendMessage("user", message);
  const pending = appendMessage("assistant", "正在分析需求并调度校园智能体...");
  renderChain([
    { label: "用户请求", status: "done" },
    { label: "北邮个人助手解析意图", status: "warning" },
  ]);

  setSending(true);
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        mode: state.mode,
        selected_agent: state.selectedAgent,
        session_id: state.sessionId,
      }),
    });
    const data = await response.json();
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || "请求失败");
    }
    pending.textContent = data.reply;
    renderChain(data.chain);
  } catch (error) {
    pending.classList.remove("assistant");
    pending.classList.add("error");
    pending.textContent = `调用失败：${error.message}`;
    renderChain([
      { label: "用户请求", status: "done" },
      { label: "北邮个人助手", status: "failed" },
    ]);
  } finally {
    setSending(false);
    els.input.focus();
  }
}

els.modeAuto.addEventListener("click", () => setMode("auto"));
els.modeManual.addEventListener("click", () => setMode("manual"));

els.form.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = els.input.value.trim();
  if (!message || state.sending) return;
  els.input.value = "";
  sendMessage(message);
});

loadStatus();
