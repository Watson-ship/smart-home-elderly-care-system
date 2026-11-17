/* 家属端交互逻辑：原生 JS + fetch，无第三方依赖 */
(function () {
    "use strict";

    const TOKEN_KEY = "family_token";
    const USER_KEY = "family_user";

    const state = {
        token: localStorage.getItem(TOKEN_KEY) || "",
        user: JSON.parse(localStorage.getItem(USER_KEY) || "null"),
        videoTimer: null,
        alertPage: 1,
        alertPages: 1,
        planPage: 1,
        planPages: 1,
        recordPage: 1,
        recordPages: 1,
        editingPlanId: null
    };

    const $ = (sel) => document.querySelector(sel);

    /* ---------------- 基础工具 ---------------- */

    function toast(msg, isError) {
        const box = $("#toast");
        box.textContent = msg;
        box.className = "toast show" + (isError ? " error" : "");
        clearTimeout(toast._t);
        toast._t = setTimeout(() => { box.className = "toast"; }, 2200);
    }

    async function api(path, options) {
        const opts = Object.assign({}, options || {});
        const headers = Object.assign({}, opts.headers || {});
        if (state.token) headers["Authorization"] = "Bearer " + state.token;
        if (opts.body && typeof opts.body !== "string") {
            headers["Content-Type"] = "application/json";
            opts.body = JSON.stringify(opts.body);
        }
        opts.headers = headers;

        const res = await fetch(path, opts);
        let body = null;
        try { body = await res.json(); } catch (e) { /* 非 JSON 响应 */ }

        if (res.status === 401) {
            logout(true);
            throw new Error("登录已过期，请重新登录");
        }
        if (!res.ok || (body && body.code !== 0)) {
            const msg = (body && (body.msg || body.detail)) || ("请求失败 HTTP " + res.status);
            throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
        }
        return body ? body.data : null;
    }

    function fmtTime(v) {
        if (!v) return "-";
        return String(v).replace("T", " ").slice(0, 19);
    }

    const ALERT_TYPE = { fall: "跌倒", static: "静止异常", sos: "一键求助" };
    const ORDER_STATUS = { pending: "待派单", processing: "处置中", archived: "已归档" };

    /* ---------------- 登录 / 退出 ---------------- */

    async function doLogin() {
        const username = $("#loginUsername").value.trim();
        const password = $("#loginPassword").value;
        const err = $("#loginErr");
        err.textContent = "";
        if (!username || !password) { err.textContent = "请输入账号和密码"; return; }

        $("#loginBtn").disabled = true;
        try {
            const data = await api("/api/auth/login", { method: "POST", body: { username, password } });
            state.token = data.token;
            state.user = { user_id: data.user_id, role: data.role, elder_id: data.elder_id };
            localStorage.setItem(TOKEN_KEY, state.token);
            localStorage.setItem(USER_KEY, JSON.stringify(state.user));

            if (state.user.role !== "family") {
                toast("当前账号不是家属角色，部分功能可能不可用", true);
            }
            enterApp();
        } catch (e) {
            err.textContent = e.message;
        } finally {
            $("#loginBtn").disabled = false;
        }
    }

    function logout(expired) {
        state.token = "";
        state.user = null;
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
        stopVideo();
        $("#app").classList.add("hidden");
        $("#loginMask").style.display = "flex";
        if (expired) toast("登录已过期，请重新登录", true);
    }

    function enterApp() {
        $("#loginMask").style.display = "none";
        $("#app").classList.remove("hidden");
        const u = state.user || {};
        $("#whoami").textContent = `角色: ${u.role || "-"}　绑定老人 ID: ${u.elder_id == null ? "未绑定" : u.elder_id}`;
        switchTab("video");
    }

    /* ---------------- 标签切换 ---------------- */

    function switchTab(name) {
        ["video", "alert", "medicine", "bind"].forEach((t) => {
            $("#tab-" + t).classList.toggle("hidden", t !== name);
        });
        document.querySelectorAll(".sidebar button").forEach((b) => {
            b.classList.toggle("active", b.dataset.tab === name);
        });

        if (name !== "video") stopVideo();
        if (name === "alert") loadAlerts(1);
        if (name === "medicine") { loadPlans(1); loadStats(); searchRecords(1); }
        if (name === "bind") loadElders();
    }

    /* ---------------- 实时视频 ---------------- */

    function refreshFrame() {
        const sn = $("#videoSn").value.trim();
        if (!sn) { toast("请先填写设备序列号", true); stopVideo(); return; }
        const img = $("#videoImg");
        img.src = `/api/device/stream/${encodeURIComponent(sn)}?t=${Date.now()}`;
    }

    function startVideo() {
        const sn = $("#videoSn").value.trim();
        if (!sn) { toast("请先填写设备序列号", true); return; }
        localStorage.setItem("family_video_sn", sn);
        stopVideo();
        $("#videoStatus").innerHTML = '<span class="status-dot"></span>连接中...';
        refreshFrame();
        state.videoTimer = setInterval(refreshFrame, 5000);
    }

    function stopVideo() {
        if (state.videoTimer) { clearInterval(state.videoTimer); state.videoTimer = null; }
    }

    function initVideo() {
        const saved = localStorage.getItem("family_video_sn");
        if (saved) $("#videoSn").value = saved;

        $("#videoStart").addEventListener("click", startVideo);
        $("#videoStop").addEventListener("click", () => {
            stopVideo();
            $("#videoStatus").innerHTML = '<span class="status-dot"></span>已停止';
        });

        const img = $("#videoImg");
        img.addEventListener("load", () => {
            img.classList.remove("hidden");
            $("#videoPlaceholder").classList.add("hidden");
            $("#videoStatus").innerHTML = '<span class="status-dot online"></span>在线 · 画面已更新 ' + new Date().toLocaleTimeString();
        });
        img.addEventListener("error", () => {
            img.classList.add("hidden");
            $("#videoPlaceholder").classList.remove("hidden");
            $("#videoPlaceholder").textContent = "暂无画面（该设备未上传截图或不在线）";
            $("#videoStatus").innerHTML = '<span class="status-dot offline"></span>离线 / 暂无画面';
        });
    }

    /* ---------------- 告警中心 ---------------- */

    async function loadAlerts(page) {
        state.alertPage = page || 1;
        const handled = $("#alertFilter").value;
        const size = Number($("#alertSize").value);
        let q = `?page=${state.alertPage}&size=${size}`;
        if (handled !== "") q += `&handled=${handled}`;

        const body = $("#alertBody");
        body.innerHTML = '<tr><td colspan="6" class="empty">加载中...</td></tr>';
        try {
            const data = await api("/api/alert" + q);
            state.alertPages = data.pages || 1;

            if (!data.items.length) {
                body.innerHTML = '<tr><td colspan="6" class="empty">暂无告警</td></tr>';
            } else {
                body.innerHTML = data.items.map((a) => {
                    const type = ALERT_TYPE[a.alert_type] || a.alert_type;
                    const shot = a.screenshot_url
                        ? `<img class="thumb" src="${a.screenshot_url}" alt="截图">`
                        : '<span class="hint">无</span>';
                    const badge = a.is_handled
                        ? '<span class="badge ok">已处置</span>'
                        : '<span class="badge warn">未处置</span>';
                    const handleBtn = a.is_handled
                        ? '<button class="btn small" disabled>已处置</button>'
                        : `<button class="btn small danger" data-handle="${a.id}">标记已处置</button>`;
                    return `<tr>
                        <td>${a.id}</td>
                        <td>${shot}</td>
                        <td>${type}</td>
                        <td>${fmtTime(a.create_time)}</td>
                        <td>${badge}</td>
                        <td>
                            <button class="btn small" data-detail="${a.id}">详情</button>
                            ${handleBtn}
                        </td>
                    </tr>`;
                }).join("");
            }
            $("#alertPageInfo").textContent = `第 ${data.page || state.alertPage} / ${state.alertPages} 页，共 ${data.total} 条`;
            $("#alertPrev").disabled = state.alertPage <= 1;
            $("#alertNext").disabled = state.alertPage >= state.alertPages;
        } catch (e) {
            body.innerHTML = `<tr><td colspan="6" class="empty">${e.message}</td></tr>`;
        }
    }

    async function openAlertDetail(id) {
        try {
            const d = await api(`/api/alert/${id}`);
            const shot = $("#detailShot");
            if (d.screenshot_url) {
                shot.src = d.screenshot_url;
                shot.classList.remove("hidden");
            } else {
                shot.removeAttribute("src");
                shot.classList.add("hidden");
            }

            const rows = [
                ["告警 ID", d.id],
                ["老人", d.elder_name || ("ID " + d.elder_id)],
                ["类型", ALERT_TYPE[d.alert_type] || d.alert_type],
                ["发生时间", fmtTime(d.create_time)],
                ["处置状态", d.is_handled ? "已处置" : "未处置"],
                ["处置人", d.handled_by_name || "-"],
                ["处置时间", fmtTime(d.handle_time)],
                ["工单号", d.order_id || "-"],
                ["工单状态", ORDER_STATUS[d.order_status] || d.order_status || "-"]
            ];
            $("#detailKv").innerHTML = rows
                .map(([k, v]) => `<div class="k">${k}</div><div>${v == null ? "-" : v}</div>`)
                .join("");

            const btn = $("#detailHandle");
            btn.classList.remove("hidden");
            btn.disabled = !!d.is_handled;
            btn.textContent = d.is_handled ? "已处置" : "标记已处置";
            btn.dataset.id = d.id;

            $("#alertModal").classList.add("show");
        } catch (e) {
            toast(e.message, true);
        }
    }

    async function handleAlert(id) {
        try {
            await api(`/api/alert/${id}/handle`, { method: "POST" });
            toast("已标记为已处置");
            $("#alertModal").classList.remove("show");
            loadAlerts(state.alertPage);
        } catch (e) {
            toast(e.message, true);
        }
    }

    function initAlerts() {
        $("#alertRefresh").addEventListener("click", () => loadAlerts(1));
        $("#alertFilter").addEventListener("change", () => loadAlerts(1));
        $("#alertSize").addEventListener("change", () => loadAlerts(1));
        $("#alertPrev").addEventListener("click", () => loadAlerts(state.alertPage - 1));
        $("#alertNext").addEventListener("click", () => loadAlerts(state.alertPage + 1));

        $("#alertBody").addEventListener("click", (ev) => {
            const detailBtn = ev.target.closest("[data-detail]");
            if (detailBtn) { openAlertDetail(Number(detailBtn.dataset.detail)); return; }
            const handleBtn = ev.target.closest("[data-handle]");
            if (handleBtn) { handleAlert(Number(handleBtn.dataset.handle)); }
        });

        $("#detailClose").addEventListener("click", () => $("#alertModal").classList.remove("show"));
        $("#alertModal").addEventListener("click", (ev) => {
            if (ev.target.id === "alertModal") $("#alertModal").classList.remove("show");
        });
        $("#detailHandle").addEventListener("click", (ev) => handleAlert(Number(ev.target.dataset.id)));
    }

    /* ---------------- 用药计划 ---------------- */

    async function loadPlans(page) {
        state.planPage = page || 1;
        const status = $("#planStatus").value;
        let q = `?page=${state.planPage}&size=10`;
        if (status !== "") q += `&status=${status}`;

        const body = $("#planBody");
        body.innerHTML = '<tr><td colspan="6" class="empty">加载中...</td></tr>';
        try {
            const data = await api("/api/medicine/plans" + q);
            state.planPages = data.pages || 1;

            if (!data.items.length) {
                body.innerHTML = '<tr><td colspan="6" class="empty">暂无用药计划</td></tr>';
            } else {
                body.innerHTML = data.items.map((p) => `<tr>
                    <td>${p.id}</td>
                    <td>${p.medicine_name}</td>
                    <td>${p.take_time || "-"}</td>
                    <td>${p.cycle === "daily" ? "每天" : p.cycle === "two_day" ? "隔天" : p.cycle}</td>
                    <td>${p.status ? '<span class="badge ok">启用</span>' : '<span class="badge off">停用</span>'}</td>
                    <td>
                        <button class="btn small" data-edit="${p.id}">编辑</button>
                        <button class="btn small danger" data-del="${p.id}">删除</button>
                    </td>
                </tr>`).join("");
            }
            $("#planPageInfo").textContent = `第 ${data.page || state.planPage} / ${state.planPages} 页，共 ${data.total} 条`;
            $("#planPrev").disabled = state.planPage <= 1;
            $("#planNext").disabled = state.planPage >= state.planPages;

            // 缓存一份，编辑时回填
            state.plans = data.items;
        } catch (e) {
            body.innerHTML = `<tr><td colspan="6" class="empty">${e.message}</td></tr>`;
        }
    }

    function openPlanModal(plan) {
        state.editingPlanId = plan ? plan.id : null;
        $("#planModalTitle").textContent = plan ? "编辑用药计划" : "新增用药计划";
        $("#planName").value = plan ? plan.medicine_name : "";
        $("#planTime").value = plan && plan.take_time ? plan.take_time.slice(0, 5) : "";
        $("#planCycle").value = plan ? plan.cycle : "daily";
        $("#planStatusField").value = plan ? String(plan.status) : "1";
        $("#planStatusWrap").style.display = plan ? "block" : "none";
        $("#planModal").classList.add("show");
    }

    async function savePlan() {
        const name = $("#planName").value.trim();
        const time = $("#planTime").value;
        const cycle = $("#planCycle").value;
        const status = Number($("#planStatusField").value);

        if (!name) { toast("请填写药品名称", true); return; }
        if (!time) { toast("请选择服药时间", true); return; }

        const body = { medicine_name: name, take_time: time.length === 5 ? time + ":00" : time, cycle };
        try {
            if (state.editingPlanId) {
                body.status = status;
                await api(`/api/medicine/plans/${state.editingPlanId}`, { method: "PUT", body });
                toast("已保存修改");
            } else {
                await api("/api/medicine/plans", { method: "POST", body });
                toast("已新增计划");
            }
            $("#planModal").classList.remove("show");
            loadPlans(state.planPage);
        } catch (e) {
            toast(e.message, true);
        }
    }

    async function deletePlan(id) {
        if (!confirm(`确定删除用药计划 ${id} 吗？该计划下的服药记录也会一起删除。`)) return;
        try {
            await api(`/api/medicine/plans/${id}`, { method: "DELETE" });
            toast("已删除");
            loadPlans(state.planPage);
        } catch (e) {
            toast(e.message, true);
        }
    }

    /* ---------------- 服药记录 + 统计 ---------------- */

    function todayStr(offsetDays) {
        const d = new Date();
        d.setDate(d.getDate() + (offsetDays || 0));
        return d.toISOString().slice(0, 10);
    }

    async function loadStats() {
        try {
            const data = await api("/api/medicine/records/stats?days=7");
            const bars = (data.daily || []).map((d) => {
                const h = Math.max(3, Math.round(d.rate));
                return `<div class="bar-item" title="${d.date} 已服${d.taken}/共${d.total}">
                    <div class="bar-rate">${d.rate}%</div>
                    <div class="bar-fill" style="height:${h}%"></div>
                    <div class="bar-date">${d.date.slice(5)}</div>
                </div>`;
            }).join("");
            $("#statsBars").innerHTML = bars || '<div class="empty">暂无数据</div>';
            $("#statsText").textContent = `近 7 天：共确认 ${data.total} 次，已服 ${data.taken} 次，未服 ${data.untaken} 次，按时服药率 ${data.rate}%`;
        } catch (e) {
            $("#statsText").textContent = "统计加载失败：" + e.message;
        }
    }

    async function searchRecords(page) {
        state.recordPage = page || 1;
        const start = $("#recordStart").value;
        const end = $("#recordEnd").value;
        let q = `?page=${state.recordPage}&size=10`;
        if (start) q += `&start_date=${start}`;
        if (end) q += `&end_date=${end}`;

        const body = $("#recordBody");
        body.innerHTML = '<tr><td colspan="5" class="empty">加载中...</td></tr>';
        try {
            const data = await api("/api/medicine/record" + q);
            state.recordPages = data.pages || 1;

            if (!data.items.length) {
                body.innerHTML = '<tr><td colspan="5" class="empty">该时间段没有服药记录</td></tr>';
            } else {
                body.innerHTML = data.items.map((r) => `<tr>
                    <td>${r.id}</td>
                    <td>${r.plan_id}</td>
                    <td>${r.remind_date}</td>
                    <td>${r.take_result === "taken" ? '<span class="badge ok">已服</span>' : '<span class="badge warn">未服</span>'}</td>
                    <td>${fmtTime(r.record_time)}</td>
                </tr>`).join("");
            }
            $("#recordPageInfo").textContent = `第 ${data.page || state.recordPage} / ${state.recordPages} 页，共 ${data.total} 条`;
            $("#recordPrev").disabled = state.recordPage <= 1;
            $("#recordNext").disabled = state.recordPage >= state.recordPages;
        } catch (e) {
            body.innerHTML = `<tr><td colspan="5" class="empty">${e.message}</td></tr>`;
        }
    }

    function initMedicine() {
        $("#planStatus").addEventListener("change", () => loadPlans(1));
        $("#planRefresh").addEventListener("click", () => loadPlans(state.planPage));
        $("#planPrev").addEventListener("click", () => loadPlans(state.planPage - 1));
        $("#planNext").addEventListener("click", () => loadPlans(state.planPage + 1));
        $("#planAdd").addEventListener("click", () => openPlanModal(null));
        $("#planCancel").addEventListener("click", () => $("#planModal").classList.remove("show"));
        $("#planSave").addEventListener("click", savePlan);
        $("#planModal").addEventListener("click", (ev) => {
            if (ev.target.id === "planModal") $("#planModal").classList.remove("show");
        });

        $("#planBody").addEventListener("click", (ev) => {
            const editBtn = ev.target.closest("[data-edit]");
            if (editBtn) {
                const id = Number(editBtn.dataset.edit);
                const plan = (state.plans || []).find((p) => p.id === id);
                openPlanModal(plan);
                return;
            }
            const delBtn = ev.target.closest("[data-del]");
            if (delBtn) deletePlan(Number(delBtn.dataset.del));
        });

        $("#recordStart").value = todayStr(-6);
        $("#recordEnd").value = todayStr(0);
        $("#recordSearch").addEventListener("click", () => searchRecords(1));
        $("#recordPrev").addEventListener("click", () => searchRecords(state.recordPage - 1));
        $("#recordNext").addEventListener("click", () => searchRecords(state.recordPage + 1));
    }

    /* ---------------- 绑定管理 ---------------- */

    async function loadElders() {
        const sel = $("#bindElder");
        sel.innerHTML = '<option value="">加载中...</option>';
        try {
            const data = await api("/api/elder?page=1&size=100");
            if (!data.items.length) {
                sel.innerHTML = '<option value="">暂无老人档案</option>';
                return;
            }
            sel.innerHTML = data.items
                .map((e) => `<option value="${e.id}">${e.id} - ${e.elder_name}${e.address ? "（" + e.address + "）" : ""}</option>`)
                .join("");
        } catch (e) {
            sel.innerHTML = `<option value="">加载失败：${e.message}</option>`;
        }
    }

    async function doBind() {
        const elderId = Number($("#bindElder").value);
        const sn = $("#bindSn").value.trim();
        const out = $("#bindResult");
        if (!elderId) { out.textContent = "请选择老人"; return; }
        if (!sn) { out.textContent = "请填写摄像头序列号"; return; }

        try {
            const data = await api("/api/device/bind", { method: "POST", body: { device_sn: sn, elder_id: elderId } });
            out.textContent = `绑定成功：${data.device_name}（${data.device_sn}）→ 老人 ID ${data.elder_id}`;
            toast("绑定成功");
        } catch (e) {
            out.textContent = "绑定失败：" + e.message;
            toast(e.message, true);
        }
    }

    /* ---------------- 启动 ---------------- */

    function boot() {
        $("#loginBtn").addEventListener("click", doLogin);
        $("#loginPassword").addEventListener("keydown", (ev) => { if (ev.key === "Enter") doLogin(); });
        $("#logoutBtn").addEventListener("click", () => logout(false));

        document.querySelectorAll(".sidebar button").forEach((btn) => {
            btn.addEventListener("click", () => switchTab(btn.dataset.tab));
        });

        initVideo();
        initAlerts();
        initMedicine();
        $("#bindBtn").addEventListener("click", doBind);

        if (state.token) {
            enterApp();
        }
    }

    boot();
})();
