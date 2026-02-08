const APP_MODE = (document.body.getAttribute("data-mode") || "stakeholder").toUpperCase();
const chatEl = document.getElementById("chat");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send");
const submitBtn = document.getElementById("submitRefund");
const submitHint = document.getElementById("submitHint");
const v2pre = document.getElementById("v2json");

const devSidebar = document.getElementById("devSidebar");
const backdrop = document.getElementById("backdrop");
const openDev = document.getElementById("openDev");
const closeDev = document.getElementById("closeDev");
const devTokenEl = document.getElementById("devToken");
const saveToken = document.getElementById("saveToken");
const devStatus = document.getElementById("devStatus");
const artifactList = document.getElementById("artifactList");
const btnReplay = document.getElementById("btnReplay");

const btnOverride = document.getElementById("btnOverride");
const opId = document.getElementById("opId");
const ovDecision = document.getElementById("ovDecision");
const ovReason = document.getElementById("ovReason");
const overrideStatus = document.getElementById("overrideStatus");

let state = {};
let lastAttemptId = null;
let devEnabled = false;

function mdToHtml(md){
  // tiny markdown: **bold**
  return md.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}
function addMsg(role, html){
  const div = document.createElement("div");
  div.className = "msg " + (role === "user" ? "user" : "assistant");
  div.innerHTML = `<div class="role">${role === "user" ? "You" : "Assistant"}</div><div class="body">${html}</div>`;
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
}

async function api(path, opts={}){
  const res = await fetch(path, {
    headers: {"Content-Type":"application/json", ...(opts.headers||{})},
    ...opts
  });
  if(!res.ok){
    const txt = await res.text();
    throw new Error(txt || ("HTTP " + res.status));
  }
  return res.json();
}

function computeSubmitEnabled(){
  const ok = !!state.order_id && !!state.reason_code && !!state.requested_resolution;
  submitBtn.disabled = !ok;
  submitHint.textContent = ok ? "Ready. Submitting will create an action_attempt_id (commit boundary)." : "Submit is enabled once order + reason + resolution are provided.";
}

async function sendMessage(msg){
  if(!msg.trim()) return;
  addMsg("user", mdToHtml(msg));
  inputEl.value = "";
  inputEl.style.height = "44px";

  const resp = await api("/api/chat", {method:"POST", body: JSON.stringify({message: msg, state})});
  state = resp.state || state;
  computeSubmitEnabled();
  addMsg("assistant", mdToHtml(resp.reply_markdown || ""));
}

sendBtn.addEventListener("click", () => sendMessage(inputEl.value));
inputEl.addEventListener("keydown", (e) => {
  if(e.key === "Enter" && !e.shiftKey){
    e.preventDefault();
    sendMessage(inputEl.value);
  }
});
inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + "px";
});

document.querySelectorAll(".chip").forEach(b => {
  b.addEventListener("click", () => {
    const msg = b.dataset.msg;
    if(msg) sendMessage(msg);
  });
});
document.getElementById("chipSubmit").addEventListener("click", () => {
  addMsg("assistant", "Click <strong>Submit refund request</strong> below when ready.");
});

submitBtn.addEventListener("click", async () => {
  const payload = {
    order_id: state.order_id,
    reason_code: state.reason_code,
    requested_resolution: state.requested_resolution,
    claim_flags: []
  };
  addMsg("assistant", "Submitting request…");
  try{
    const res = await api("/api/refund/submit", {method:"POST", body: JSON.stringify(payload)});
    lastAttemptId = res.action_attempt_id;
    addMsg("assistant", `Request submitted. Reference: <strong>${lastAttemptId}</strong>`);
    await refreshV2();
    if(devSidebar && !devSidebar.classList.contains("hidden")) await refreshDevArtifacts();
  }catch(err){
    addMsg("assistant", "Submit failed.");
    console.error(err);
  }
});

async function refreshV2(){
  if(!lastAttemptId) return;
  const v2 = await api(`/api/v2/${lastAttemptId}`);
  v2pre.textContent = JSON.stringify(v2, null, 2);

  const needsOverride = !!(v2.authority && v2.authority.override_required);
  btnOverride.disabled = !(devEnabled && needsOverride);
  btnReplay.disabled = !devEnabled;
}

async function loadConfig(){
  const cfg = await api("/api/config");

  // LLM (NRB-only) toggle
  const llmToggle = document.getElementById("llmToggle");
  const llmBadge = document.getElementById("llmBadge");
  window.__LLM_ENABLED = !!cfg.llm_enabled;

  if(llmToggle){
    llmToggle.checked = (localStorage.getItem("manithy_llm") === "1");
    llmToggle.disabled = !window.__LLM_ENABLED;
    if(llmToggle.parentElement){
      llmToggle.parentElement.style.opacity = window.__LLM_ENABLED ? "1" : "0.5";
    }
    if(llmBadge){
      llmBadge.textContent = window.__LLM_ENABLED ? ((cfg.llm_model || "LLM") + " available") : "LLM disabled";
    }
    llmToggle.addEventListener("change", ()=>{
      localStorage.setItem("manithy_llm", llmToggle.checked ? "1" : "0");
    });
  }
  devStatus.textContent = cfg.dev_enabled ? "Dev mode is available on this server." : "Dev mode is not enabled on this server.";
  return cfg.dev_enabled;
}

function openDevDrawer(){
  // Desktop uses show/hide; mobile uses drawer + backdrop
  const isMobile = window.matchMedia("(max-width: 900px)").matches;
  devSidebar.classList.remove("hidden");
  if(isMobile){
    devSidebar.classList.add("open");
    backdrop.classList.add("show");
  }
}
function closeDevDrawer(){
  const isMobile = window.matchMedia("(max-width: 900px)").matches;
  if(isMobile){
    devSidebar.classList.remove("open");
    backdrop.classList.remove("show");
  }else{
    devSidebar.classList.add("hidden");
  }
}
openDev.addEventListener("click", async () => {
  openDevDrawer();
  devEnabled = await loadConfig();
  btnReplay.disabled = !devEnabled;
  if(lastAttemptId && devEnabled) await refreshDevArtifacts();
});
closeDev.addEventListener("click", closeDevDrawer);
backdrop && backdrop.addEventListener("click", closeDevDrawer);
window.addEventListener("resize", () => {
  // Reset backdrop when moving between breakpoints
  const isMobile = window.matchMedia("(max-width: 900px)").matches;
  if(!isMobile){
    backdrop.classList.remove("show");
    devSidebar.classList.remove("open");
  }
});

saveToken.addEventListener("click", async () => {
  localStorage.setItem("manithy_dev_token", devTokenEl.value);
  await refreshDevArtifacts();
  await refreshV2();
});

function getDevHeaders(){
  const tok = localStorage.getItem("manithy_dev_token") || "";
  devTokenEl.value = tok;
  return tok ? {"X-Manithy-Dev-Token": tok} : {};
}

function badgeFor(name){
  if(name.startsWith("NRB_V2")) return {cls:"v2", text:"V2_ONLY"};
  if(name.startsWith("RB-09") || name.startsWith("RB-10") || name.startsWith("RB-03") || name.startsWith("RB-05") || name.startsWith("RB-07") || name.startsWith("RB-08") || name.startsWith("RB-02")) return {cls:"rbproof", text:"RB_PROOF"};
  return {cls:"rbint", text:"RB_INTERNAL"};
}

async function refreshDevArtifacts(){
  if(!lastAttemptId) return;
  try{
    const res = await fetch(`/api/dev/artifacts/${lastAttemptId}`, {headers: getDevHeaders()});
    if(!res.ok){
      artifactList.innerHTML = `<div class="muted">Not authorized (token required).</div>`;
      return;
    }
    const data = await res.json();
    artifactList.innerHTML = "";
    (data.artifacts || []).forEach(a => {
      const b = badgeFor(a.name);
      const card = document.createElement("div");
      card.className = "card";
      card.innerHTML = `
        <div class="cardHeader">
          <div><strong>${a.name}</strong></div>
          <div class="badge ${b.cls}">${b.text}</div>
        </div>
        ${a.kind === "bin_meta" ? `<pre>size_bytes: ${a.size_bytes}\nsha256: ${a.sha256}</pre>` : `<pre>${escapeHtml(a.content || "")}</pre>`}
      `;
      artifactList.appendChild(card);
    });
    devEnabled = true;
  }catch(e){
    console.error(e);
  }
}

btnReplay.addEventListener("click", async () => {
  if(!lastAttemptId) return;
  overrideStatus.textContent = "";
  try{
    const res = await fetch(`/api/dev/replay/${lastAttemptId}`, {method:"POST", headers: {"Content-Type":"application/json", ...getDevHeaders()}, body:"{}"});
    if(!res.ok){
      devStatus.textContent = "Replay not authorized.";
      return;
    }
    const data = await res.json();
    devStatus.textContent = `Replay: ${data.status} (${data.code})`;
    await refreshDevArtifacts();
  }catch(e){
    devStatus.textContent = "Replay failed.";
  }
});

btnOverride.addEventListener("click", async () => {
  if(!lastAttemptId) return;
  overrideStatus.textContent = "";
  try{
    const payload = {operator_id: opId.value.trim(), decision: ovDecision.value, reason_code: ovReason.value};
    const res = await fetch(`/api/dev/override/${lastAttemptId}`, {method:"POST", headers: {"Content-Type":"application/json", ...getDevHeaders()}, body: JSON.stringify(payload)});
    if(!res.ok){
      overrideStatus.textContent = "Override not authorized / invalid.";
      return;
    }
    overrideStatus.textContent = "Override committed.";
    await refreshV2();
    await refreshDevArtifacts();
  }catch(e){
    overrideStatus.textContent = "Override failed.";
  }
});

function escapeHtml(s){
  return (s||"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
}

// Boot
addMsg("assistant", "Hi! I can help with a refund. Share your <strong>order number</strong> (e.g., ORD-10001).");
computeSubmitEnabled();


// Mode lens: Stakeholder vs Developer
(function initModeLens(){
  const link = document.getElementById("switchModeLink");
  const openDevBtn = document.getElementById("openDev");
  const devSidebar = document.getElementById("devSidebar");
  const backdrop = document.getElementById("backdrop");

  if(link){
    if(APP_MODE === "DEVELOPER"){
      link.textContent = "Switch to Stakeholder";
      link.setAttribute("href","/stakeholder");
    }else{
      link.textContent = "Switch to Developer";
      link.setAttribute("href","/developer");
    }
  }

  // In Stakeholder mode, dev UI must be invisible and inaccessible
  if(APP_MODE !== "DEVELOPER"){
    if(openDevBtn) openDevBtn.style.display = "none";
    if(devSidebar) devSidebar.classList.add("hidden");
    if(devSidebar) devSidebar.classList.remove("open");
    if(backdrop) backdrop.classList.remove("show");
  }
})();
