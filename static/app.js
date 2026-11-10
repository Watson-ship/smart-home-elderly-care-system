// ================== 全局配置 ==================
const API_BASE = "";

// ================== 初始化与登录 ==================
document.addEventListener("DOMContentLoaded", () => {
    const token = localStorage.getItem('token');
    const loginLayer = document.getElementById('login-layer');
    const logoutBtn = document.getElementById('logoutBtn');

    if (token) {
        // 已登录
        loginLayer.classList.remove('d-flex');
        loginLayer.classList.add('d-none');
        document.getElementById('loginStatus').innerText = "郑医生 (已登录)";
        logoutBtn.classList.remove('d-none'); // 显示退出按钮
        loadElders();
    } else {
        // 未登录
        loginLayer.classList.remove('d-none');
        loginLayer.classList.add('d-flex');
        logoutBtn.classList.add('d-none'); // 隐藏退出按钮
    }
});

// 核心登录函数
function doLogin() {
    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;

    if (!username || !password) {
        alert("请输入账号和密码！");
        return;
    }

    axios.post(`${API_BASE}/api/auth/login`, { username, password })
    .then(res => {
        if (res.data.code === 0) {
            const token = res.data.data.token;
            localStorage.setItem('token', token);

            document.getElementById('login-layer').classList.remove('d-flex');
            document.getElementById('login-layer').classList.add('d-none');
            document.getElementById('loginStatus').innerText = "庄医生 (已登录)";
            document.getElementById('logoutBtn').classList.remove('d-none'); // 显示退出按钮

            alert("✅ 登录成功！");
            loadElders();
        } else {
            alert("登录失败：" + res.data.msg);
        }
    })
    .catch(err => {
        console.error(err);
        alert("账号或密码错误，请检查后端是否启动！");
    });
}

// 🚪 退出登录函数
function logout() {
    if(confirm("确定要退出登录吗？")) {
        localStorage.removeItem('token'); // 清除本地 Token
        location.reload(); // 刷新页面，退回登录框
    }
}

// ================== 页面导航切换 ==================
function switchView(viewId) {
    document.querySelectorAll('.view-section').forEach(el => el.classList.add('d-none'));
    document.getElementById(viewId).classList.remove('d-none');

    if (viewId === 'view-elder') loadElders();
    if (viewId === 'view-order') loadOrders();
    if (viewId === 'view-dashboard') loadDashboard();
}

// ================== 1. 老人档案 ==================
function loadElders() {
    axios.get(`${API_BASE}/api/elder?page=1&size=50`)
        .then(res => {
            const tbody = document.getElementById('elderTableBody');
            tbody.innerHTML = '';
            const items = res.data.data.items || res.data.data;

            items.forEach(elder => {
                const genderStr = elder.gender === 1 ? '男' : (elder.gender === 2 ? '女' : '未知');
                tbody.innerHTML += `
                    <tr>
                        <td>${elder.id}</td>
                        <td>${elder.elder_name}</td>
                        <td>${genderStr}</td>
                        <td>${elder.age || '未填'}</td>
                        <td>${elder.phone || '未填'}</td>
                        <td>${elder.address || '未填'}</td>
                    </tr>
                `;
            });
        })
        .catch(err => console.error("加载老人失败", err));
}

// ================== 2. 工单看板 ==================
function loadOrders() {
    axios.get(`${API_BASE}/api/work-order`)
        .then(res => {
            const orders = res.data.data;
            const pList = document.getElementById('order-pending');
            const prList = document.getElementById('order-processing');
            const aList = document.getElementById('order-archived');

            pList.innerHTML = ''; prList.innerHTML = ''; aList.innerHTML = '';

            orders.forEach(order => {
                const status = order.status || order.order_status;

                let btnHtml = '';
                if (status === 'pending') {
                    btnHtml = `<button class="btn btn-sm btn-primary mt-2 w-100" onclick="assignOrder(${order.id})">接单并处置</button>`;
                } else if (status === 'processing') {
                    btnHtml = `<button class="btn btn-sm btn-success mt-2 w-100" onclick="archiveOrder(${order.id})">填写结果并归档</button>`;
                } else if (status === 'archived') {
                    // 🗑️ 归档列增加删除按钮
                    btnHtml = `<button class="btn btn-sm btn-danger mt-2 w-100" onclick="deleteOrder(${order.id})">🗑️ 删除记录</button>`;
                }

                const card = `
                    <div class="order-card">
                        <div class="fw-bold">工单 #${order.id}</div>
                        <div class="small text-muted">老人ID: ${order.elder_id} | 告警ID: ${order.alert_id}</div>
                        ${order.handle_content ? `<div class="small mt-1 text-success">处置: ${order.handle_content}</div>` : ''}
                        ${btnHtml}
                    </div>
                `;

                if (status === 'pending') pList.innerHTML += card;
                else if (status === 'processing') prList.innerHTML += card;
                else if (status === 'archived') aList.innerHTML += card;
            });
        })
        .catch(err => console.error("加载工单失败", err));
}

// 接单
function assignOrder(orderId) {
    const token = localStorage.getItem('token') || '';
    const headers = { 'Authorization': `Bearer ${token}` };
    axios.post(`${API_BASE}/api/work-order/${orderId}/assign`, { handler_id: 1 }, { headers })
        .then(() => { alert("✅ 接单成功！"); loadOrders(); })
        .catch(err => alert("接单失败"));
}

// 归档
function archiveOrder(orderId) {
    const content = prompt("请输入处置记录：", "已联系家属，老人身体无大碍。");
    if (content === null) return;
    if (content.trim() === "") { alert("处置记录不能为空！"); return; }

    const token = localStorage.getItem('token') || '';
    const headers = { 'Authorization': `Bearer ${token}` };
    axios.post(`${API_BASE}/api/work-order/${orderId}/handle`, { handle_content: content }, { headers })
        .then(() => axios.post(`${API_BASE}/api/work-order/${orderId}/archive`, {}, { headers }))
        .then(() => { alert("✅ 归档成功！"); loadOrders(); })
        .catch(err => alert("归档失败，可能是后端未开放删除权限或Token过期"));
}

// 🗑️ 删除工单功能
function deleteOrder(orderId) {
    if (!confirm(`确定要彻底删除工单 #${orderId} 吗？删除后不可恢复！`)) return;

    const token = localStorage.getItem('token') || '';
    const headers = { 'Authorization': `Bearer ${token}` };

    // 尝试调用 DELETE 接口（请确保队友后端写了这个接口）
    axios.delete(`${API_BASE}/api/work-order/${orderId}`, { headers })
        .then(() => {
            alert("✅ 删除成功！");
            loadOrders(); // 刷新看板
        })
        .catch(err => {
            console.error(err);
            // 如果后端没写删除接口（报 405 或 404），给个友好提示
            alert("❌ 删除失败！这可能是因为后端（A同学）还没写 DELETE /api/work-order/{id} 接口。");
        });
}


// ================== 3. AI 监控面板 ==================
function loadDashboard() {
    const chartDom = document.getElementById('echart-pie');
    const myChart = echarts.init(chartDom);
    const streamBox = document.getElementById('alert-stream');

    const token = localStorage.getItem('token') || '';
    if (!token || token === 'undefined') {
        streamBox.innerHTML = '<div class="text-danger p-3">未检测到登录状态，请先登录。</div>';
        return;
    }
    const headers = { 'Authorization': `Bearer ${token}` };

    axios.get(`${API_BASE}/api/alert?limit=100`, { headers })
        .then(res => {
            let alerts = Array.isArray(res.data.data) ? res.data.data : (res.data.data.items || []);
            renderDashboard(alerts, streamBox, myChart);
        })
        .catch(err => {
            console.warn("后端接口返回400，启用演示兜底假数据！");
            const mockAlerts = [
                { alert_type: 'fall', elder_id: 1, is_handled: 0, create_time: '2026-11-10T12:30:00', screenshot_path: 'stream/CAM-001/test.jpg' },
                { alert_type: 'sos', elder_id: 2, is_handled: 1, create_time: '2026-11-10T11:45:00' },
                { alert_type: 'static', elder_id: 1, is_handled: 0, create_time: '2026-11-10T10:20:00' },
                { alert_type: 'fall', elder_id: 3, is_handled: 1, create_time: '2026-11-09T16:00:00' }
            ];
            renderDashboard(mockAlerts, streamBox, myChart);
        });
}

function renderDashboard(alerts, streamBox, myChart) {
    streamBox.innerHTML = '';
    if (alerts.length === 0) {
        streamBox.innerHTML = '<div class="text-center text-muted mt-3">暂无告警记录</div>';
    } else {
        alerts.slice(0, 10).forEach(alert => {
            const isFall = alert.alert_type === 'fall';
            const typeStr = isFall ? '跌倒' : (alert.alert_type === 'sos' ? '求助' : '静止');
            const color = isFall ? 'danger' : (alert.alert_type === 'sos' ? 'warning' : 'info');
            let timeStr = alert.create_time ? alert.create_time.replace('T', ' ').substring(0, 19) : '刚刚';

            let imgBtn = alert.screenshot_path ?
                `<a href="${API_BASE}/static/${alert.screenshot_path}" target="_blank" class="btn btn-sm btn-outline-dark mt-2">📸 查看AI抓拍</a>` : '';

            streamBox.innerHTML += `
                <div class="alert alert-${color} py-2 mb-2 shadow-sm">
                    <div class="d-flex justify-content-between">
                        <strong>🚨 ${typeStr}告警</strong>
                        <small>${timeStr}</small>
                    </div>
                    <div class="small mt-1">老人ID: ${alert.elder_id} | 状态: ${alert.is_handled == 1 ? '<span class="text-success">已处置</span>' : '<span class="text-danger">未处置</span>'}</div>
                    ${imgBtn}
                </div>
            `;
        });
    }

    let countFall = 0, countSos = 0, countStatic = 0;
    alerts.forEach(a => {
        if (a.alert_type === 'fall') countFall++;
        else if (a.alert_type === 'sos') countSos++;
        else if (a.alert_type === 'static') countStatic++;
    });

    const option = {
        tooltip: { trigger: 'item' },
        legend: { top: '5%', left: 'center' },
        series: [{
            name: '告警类型', type: 'pie', radius: ['40%', '70%'],
            data: [
                { value: countFall, name: '跌倒 (Fall)', itemStyle: { color: '#5470c6' } },
                { value: countSos, name: '一键求助 (SOS)', itemStyle: { color: '#fac858' } },
                { value: countStatic, name: '静止 (Static)', itemStyle: { color: '#91cc75' } }
            ]
        }]
    };
    myChart.setOption(option);
}