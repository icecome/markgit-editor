/**
 * OAuth 2.0 Device Authorization Flow 组件
 * 独立模块，不依赖主应用
 */

class OAuthComponent {
    constructor() {
        this.oauthSessionId = sessionStorage.getItem('oauthSessionId') || '';
        this.oauthAuthenticated = false;
        this.oauthUser = null;
        this.oauthPollTimer = null;
        this.pollInterval = 5000;
        this.isRequestingDeviceCode = false;
        this.currentDeviceCode = null;
    }

    /**
     * 初始化 OAuth 组件
     */
    async init() {
        console.log('OAuth Component initializing...');
        
        // 恢复 OAuth 会话
        if (this.oauthSessionId) {
            console.log('Found existing OAuth session');
            const authenticated = await this.checkStatus();
            if (!authenticated) {
                console.log('OAuth session invalid, showing login button');
                this.updateUI();
            }
        } else {
            console.log('No existing OAuth session, showing login button');
            // 显示登录按钮
            this.updateUI();
        }
    }

    /**
     * 开始 OAuth 登录流程
     */
    async startLogin() {
        console.log('OAuth startLogin called');
        
        if (this.isRequestingDeviceCode) {
            console.log('Already requesting device code, please wait...');
            return;
        }
        
        if (this.currentDeviceCode) {
            console.log('Device code already exists, showing existing dialog');
            this.showAuthDialog(this.currentDeviceCode);
            this.startPolling(this.currentDeviceCode);
            return;
        }
        
        this.isRequestingDeviceCode = true;
        
        try {
            console.log('Requesting device code from server...');
            const response = await axios.get('/api/auth/device-code');
            const deviceCode = response.data;
            
            console.log('Device code received:', deviceCode);
            
            this.currentDeviceCode = deviceCode;
            
            this.showAuthDialog(deviceCode);
            
            this.startPolling(deviceCode);
            
        } catch (error) {
            console.error('OAuth 登录失败:', error);
            
            let errorMsg = 'OAuth 登录失败';
            if (error.response) {
                if (error.response.status === 404) {
                    errorMsg = 'OAuth 服务不可用，请检查服务器配置';
                } else if (error.response.status === 500) {
                    errorMsg = 'GitHub OAuth 配置错误，请联系管理员';
                } else {
                    errorMsg = error.response.data?.detail || error.response.data || 'OAuth 登录失败';
                }
            }
            
            this.showErrorDialog(errorMsg);
        } finally {
            this.isRequestingDeviceCode = false;
        }
    }

    /**
     * HTML 转义函数 - 防止 XSS 攻击
     */
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * 显示授权对话框（原生 DOM 实现）
     */
    showAuthDialog(deviceCode) {
        // 创建对话框
        const dialog = document.createElement('div');
        dialog.id = 'oauth-dialog';
        dialog.className = 'modal-overlay';
        
        // 使用转义后的用户数据，防止 XSS
        const safeUserCode = this.escapeHtml(deviceCode.user_code);
        const safeVerificationUri = this.escapeHtml(deviceCode.verification_uri);
        const safeVerificationUriComplete = this.escapeHtml(deviceCode.verification_uri_complete);
        const expiresInMinutes = Math.floor(deviceCode.expires_in / 60);
        
        dialog.innerHTML = `
            <div class="modal" style="max-width: 450px;">
                <div class="modal-header">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="oauth-icon">
                        <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
                    </svg>
                    <h3>GitHub 授权</h3>
                </div>
                <div class="modal-body">
                    ${deviceCode.qr_code ? `
                        <div class="oauth-qr-container">
                            <img src="${this.escapeHtml(deviceCode.qr_code)}" alt="QR Code" class="oauth-qr-code">
                            <p class="oauth-qr-hint">使用手机扫描二维码授权</p>
                        </div>
                    ` : ''}
                    
                    <div class="oauth-user-code-container">
                        <p class="oauth-user-code-label">或访问以下地址并输入用户码：</p>
                        <a href="${safeVerificationUriComplete}" 
                           target="_blank" 
                           class="oauth-verification-link"
                           rel="noopener noreferrer">
                            ${safeVerificationUri}
                        </a>
                        <div class="oauth-user-code">
                            ${safeUserCode}
                        </div>
                    </div>
                    
                    <div class="oauth-waiting-container">
                        <div class="oauth-spinner"></div>
                        <p class="oauth-waiting-text">等待授权...</p>
                        <p class="oauth-hint">授权后自动登录</p>
                        <p class="oauth-hint oauth-expiry">
                            设备码将在 ${expiresInMinutes} 分钟后过期
                        </p>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" id="oauth-close-btn">取消</button>
                </div>
            </div>
        `;
        
        document.body.appendChild(dialog);
        this.currentDialog = dialog;
        
        // 绑定关闭事件
        const closeBtn = document.getElementById('oauth-close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.closeDialog());
        }
        
        // 添加样式
        this.addStyles();
    }

    /**
     * 关闭对话框
     */
    closeDialog() {
        if (this.currentDialog) {
            this.currentDialog.remove();
            this.currentDialog = null;
        }
        this.stopPolling();
        this.currentDeviceCode = null;
    }

    /**
     * 显示错误对话框
     */
    showErrorDialog(message) {
        const dialog = document.createElement('div');
        dialog.id = 'oauth-error-dialog';
        dialog.className = 'modal-overlay';
        dialog.innerHTML = `
            <div class="modal" style="max-width: 400px;">
                <div class="modal-header">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="oauth-icon oauth-icon-error">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="8" x2="12" y2="12"></line>
                        <line x1="12" y1="16" x2="12.01" y2="16"></line>
                    </svg>
                    <h3>错误</h3>
                </div>
                <div class="modal-body">
                    <p class="oauth-error-message">${message}</p>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-primary" id="oauth-error-close-btn">确定</button>
                </div>
            </div>
        `;
        
        document.body.appendChild(dialog);
        this.currentErrorDialog = dialog;
        
        // 绑定关闭事件
        const closeBtn = document.getElementById('oauth-error-close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.closeErrorDialog());
        }
    }

    /**
     * 关闭错误对话框
     */
    closeErrorDialog() {
        if (this.currentErrorDialog) {
            this.currentErrorDialog.remove();
            this.currentErrorDialog = null;
        }
    }

    /**
     * 开始轮询令牌
     */
    startPolling(deviceCode) {
        // 先清理旧的定时器，防止内存泄漏
        this.stopPolling();
        
        // 使用 GitHub 返回的间隔时间，默认 5 秒
        let pollInterval = (deviceCode.interval || 5) * 1000;
        
        this.pollTimer = setInterval(async () => {
            try {
                const response = await axios.post('/api/auth/token', {
                    device_code: deviceCode.device_code,
                    grant_type: 'urn:ietf:params:oauth:grant-type:device_code'
                }, {
                    headers: { 
                        'Content-Type': 'application/json'
                    }
                });
                
                console.log('OAuth 令牌获取成功:', response.data);
                
                // 保存令牌和会话 ID
                this.oauthToken = response.data.access_token;
                this.oauthSessionId = response.data.session_id;
                sessionStorage.setItem('oauthSessionId', this.oauthSessionId);
                
                // 停止轮询
                this.stopPolling();
                
                // 更新 UI 和状态
                await this.checkStatus();
                
                // 关闭对话框
                if (this.currentDialog) {
                    this.closeDialog();
                }
                
                // 触发登录成功事件
                if (this.onLoginSuccess) {
                    this.onLoginSuccess();
                }
                
            } catch (error) {
                if (error.response && error.response.data) {
                    const errorData = error.response.data;
                    const errorInfo = errorData.detail || errorData;
                    const errorType = errorInfo.error || errorData.error;
                    
                    if (errorType === 'authorization_pending') {
                        // 继续等待 - 这是正常状态，不需要日志
                        // console.debug('等待用户授权...');
                    } else if (errorType === 'slow_down') {
                        const newInterval = ((errorInfo.interval || errorData.interval || 10)) * 1000;
                        console.log(`GitHub 要求降低轮询频率：${newInterval/1000}秒`);
                        // 重置轮询间隔
                        this.stopPolling();
                        this.pollInterval = newInterval;
                        this.startPolling(deviceCode);
                    } else if (errorType === 'expired_token' || errorType === 'access_denied') {
                        console.error('OAuth 授权失败:', errorType);
                        this.stopPolling();
                        this.showErrorDialog(`授权失败：${errorInfo.error_description || errorData.error_description || errorType}`);
                    } else {
                        // 其他错误，记录详细日志
                        console.warn('OAuth 轮询收到未知错误:', errorData);
                    }
                } else {
                    // 网络错误或其他非 HTTP 错误
                    console.debug('OAuth 轮询网络错误，继续重试:', error.message);
                }
            }
        }, this.pollInterval);
    }

    /**
     * 停止轮询
     */
    stopPolling() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
    }

    /**
     * 清理 OAuth 组件资源
     */
    cleanup() {
        this.stopPolling();
        this.currentDeviceCode = null;
        this.pollInterval = 5000;  // 重置为默认值
    }

    /**
     * 检查 OAuth 状态
     */
    async checkStatus() {
        try {
            const response = await axios.get('/api/auth/status', {
                headers: { 
                    'X-Session-ID': this.oauthSessionId 
                }
            });
            
            if (response.data.authenticated) {
                this.oauthAuthenticated = true;
                this.oauthUser = response.data.user;
                this.updateUI();
                return true;
            } else {
                this.oauthAuthenticated = false;
                this.oauthUser = null;
                this.oauthSessionId = '';
                sessionStorage.removeItem('oauthSessionId');
                this.updateUI();
                return false;
            }
        } catch (error) {
            this.oauthAuthenticated = false;
            this.oauthUser = null;
            this.updateUI();
            return false;
        }
    }

    /**
     * 登出
     */
    async logout() {
        try {
            await axios.post('/api/auth/logout', {}, {
                headers: { 'X-Session-ID': this.oauthSessionId }
            });
            
            this.oauthSessionId = '';
            sessionStorage.removeItem('oauthSessionId');
            this.oauthAuthenticated = false;
            this.oauthUser = null;
            this.updateUI();
            
            if (this.onLogoutSuccess) {
                this.onLogoutSuccess();
            }
        } catch (error) {
            console.error('OAuth 登出失败:', error);
        }
    }

    /**
     * 更新 UI
     */
    updateUI() {
        const container = document.getElementById('oauth-container');
        if (!container) {
            console.warn('OAuth container not found');
            return;
        }
        
        if (this.oauthAuthenticated && this.oauthUser) {
            // 已登录状态
            container.innerHTML = `
                <div style="display: flex; align-items: center; gap: 8px; margin-right: 10px;">
                    <img src="${this.oauthUser.avatar_url}" 
                         alt="${this.oauthUser.login}" 
                         style="width: 24px; height: 24px; border-radius: 50%; vertical-align: middle;">
                    <span style="font-size: 13px; vertical-align: middle;">${this.oauthUser.login}</span>
                    <button id="oauth-logout-btn" class="btn btn-ghost btn-sm" title="登出" style="padding: 2px 6px;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                            <polyline points="16 17 21 12 16 7"></polyline>
                            <line x1="21" y1="12" x2="9" y2="12"></line>
                        </svg>
                    </button>
                </div>
            `;
            
            // 绑定登出事件
            const logoutBtn = document.getElementById('oauth-logout-btn');
            if (logoutBtn) {
                logoutBtn.addEventListener('click', () => this.logout());
            }
        } else {
            // 未登录状态 - 显示登录按钮
            container.innerHTML = `
                <button id="oauth-login-btn" class="btn btn-primary btn-sm" title="使用 GitHub 登录" style="margin-right: 10px; display: inline-flex; align-items: center; gap: 4px;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
                    </svg>
                    <span>登录</span>
                </button>
            `;
            
            // 绑定登录事件
            const loginBtn = document.getElementById('oauth-login-btn');
            if (loginBtn) {
                loginBtn.addEventListener('click', () => this.startLogin());
            }
        }
        
        // 重新渲染图标
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    /**
     * 添加样式
     */
    addStyles() {
        if (document.getElementById('oauth-styles')) return;
        
        const style = document.createElement('style');
        style.id = 'oauth-styles';
        style.textContent = `
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
            
            .modal-overlay {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.4);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 9999;
                backdrop-filter: blur(4px);
            }
            
            .modal {
                background: var(--bg-secondary, #ffffff);
                border-radius: var(--radius-lg, 16px);
                padding: 24px;
                max-width: 450px;
                width: 90%;
                box-shadow: var(--shadow-lg, 0 10px 30px rgba(0, 0, 0, 0.1));
                border: 1px solid var(--border-color, #e2e8f0);
            }
            
            .modal-header {
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 20px;
                padding-bottom: 16px;
                border-bottom: 1px solid var(--border-color, #e2e8f0);
            }
            
            .modal-header h3 {
                margin: 0;
                font-size: 18px;
                font-weight: 700;
                color: var(--text-primary, #22252a);
                letter-spacing: -0.02em;
            }
            
            .oauth-icon {
                width: 24px;
                height: 24px;
                color: var(--accent-color, #2196f3);
                flex-shrink: 0;
            }
            
            .oauth-icon-error {
                color: var(--toast-error-color, #ef4444);
            }
            
            .modal-body {
                margin-bottom: 20px;
            }
            
            .modal-footer {
                display: flex;
                justify-content: flex-end;
                gap: 12px;
                padding-top: 16px;
                border-top: 1px solid var(--border-color, #e2e8f0);
                background: var(--bg-tertiary, #f1f5f9);
                margin: 0 -24px -24px -24px;
                padding: 20px 24px;
                border-radius: 0 0 var(--radius-lg, 16px) var(--radius-lg, 16px);
            }
            
            .oauth-qr-container {
                text-align: center;
                margin: 20px 0;
                display: flex;
                flex-direction: column;
                align-items: center;
            }
            
            .oauth-qr-code {
                max-width: 200px;
                border: 1px solid var(--border-color, #e2e8f0);
                padding: 10px;
                border-radius: var(--radius-md, 12px);
                background: var(--bg-secondary, #ffffff);
                display: block;
                margin: 0 auto;
            }
            
            .oauth-qr-hint {
                margin-top: 10px;
                color: var(--text-secondary, #64748b);
                font-size: 14px;
            }
            
            .oauth-user-code-container {
                text-align: center;
                margin: 20px 0;
            }
            
            .oauth-user-code-label {
                color: var(--text-secondary, #64748b);
                margin-bottom: 10px;
                font-size: 14px;
            }
            
            .oauth-verification-link {
                color: var(--accent-color, #2196f3);
                text-decoration: none;
                font-size: 14px;
                display: block;
                margin-bottom: 10px;
                font-weight: 600;
            }
            
            .oauth-verification-link:hover {
                text-decoration: underline;
            }
            
            .oauth-user-code {
                background: var(--bg-tertiary, #f1f5f9);
                padding: 12px;
                border-radius: var(--radius-md, 12px);
                font-family: 'Courier New', monospace;
                font-size: 18px;
                letter-spacing: 2px;
                color: var(--text-primary, #22252a);
                display: inline-block;
                border: 1.5px solid var(--border-color, #e2e8f0);
                font-weight: 700;
            }
            
            .oauth-waiting-container {
                text-align: center;
            }
            
            .oauth-spinner {
                display: inline-block;
                width: 20px;
                height: 20px;
                border: 2px solid var(--border-color, #e2e8f0);
                border-top-color: var(--accent-color, #2196f3);
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }
            
            .oauth-waiting-text {
                margin-top: 10px;
                color: var(--text-primary, #22252a);
                font-size: 14px;
                font-weight: 600;
            }
            
            .oauth-hint {
                font-size: 12px;
                color: var(--text-tertiary, #94a3b8);
                margin-top: 6px;
            }
            
            .oauth-expiry {
                margin-top: 10px;
            }
            
            .oauth-error-message {
                color: var(--text-secondary, #64748b);
                font-size: 14px;
                line-height: 1.6;
            }
            
            .btn {
                padding: 10px 20px;
                border-radius: var(--radius-full, 9999px);
                font-size: 13px;
                font-weight: 600;
                cursor: pointer;
                border: none;
                transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            }
            
            .btn-secondary {
                background: var(--bg-secondary, #ffffff);
                border: 1px solid var(--border-color, #e2e8f0);
                color: var(--text-secondary, #64748b);
            }
            
            .btn-secondary:hover {
                background: var(--bg-tertiary, #f1f5f9);
                border-color: var(--accent-color, #2196f3);
                color: var(--accent-color, #2196f3);
                transform: translateY(-1px);
            }
            
            .btn-primary {
                background: var(--accent-color, #2196f3);
                color: white;
                box-shadow: var(--shadow-sm, 0 1px 3px rgba(0, 0, 0, 0.1));
            }
            
            .btn-primary:hover {
                background: var(--accent-hover, #1976d2);
                transform: translateY(-2px);
                box-shadow: var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.1));
            }
            
            .btn-sm {
                padding: 6px 14px;
                font-size: 12px;
            }
        `;
        
        document.head.appendChild(style);
    }
}

// 创建全局实例
const oauth = new OAuthComponent();

// 注意：不在这里自动初始化，由 main.js 中的 Vue 应用控制初始化时机
// document.addEventListener('DOMContentLoaded', function() {
//     oauth.init();
// });
