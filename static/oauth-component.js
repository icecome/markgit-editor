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
            const response = await axios.get('/api/auth/device-code');
            const deviceCode = response.data;
            
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
     * 显示授权对话框（原生 DOM 实现）
     */
    showAuthDialog(deviceCode) {
        // 创建对话框
        const dialog = document.createElement('div');
        dialog.id = 'oauth-dialog';
        dialog.className = 'modal-overlay';
        dialog.innerHTML = `
            <div class="modal" style="max-width: 450px;">
                <div class="modal-header">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: #333;">
                        <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
                    </svg>
                    <h3>GitHub 授权</h3>
                </div>
                <div class="modal-body">
                    ${deviceCode.qr_code ? `
                        <div style="text-align: center; margin: 20px 0;">
                            <img src="${deviceCode.qr_code}" alt="QR Code" style="max-width: 200px; border: 1px solid #ddd; padding: 10px; border-radius: 8px;">
                            <p style="margin-top: 10px; color: #666;">使用手机扫描二维码授权</p>
                        </div>
                    ` : ''}
                    
                    <div style="text-align: center; margin: 20px 0;">
                        <p style="color: #666; margin-bottom: 10px;">或访问以下地址并输入用户码：</p>
                        <a href="${deviceCode.verification_uri_complete}" 
                           target="_blank" 
                           style="color: #0366d6; text-decoration: none; font-size: 14px; display: block; margin-bottom: 10px;">
                            ${deviceCode.verification_uri}
                        </a>
                        <div style="background: #f6f8fa; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 18px; letter-spacing: 2px; color: #24292e; display: inline-block;">
                            ${deviceCode.user_code}
                        </div>
                    </div>
                    
                    <div style="text-align: center; color: #666;">
                        <div class="spinner" style="display: inline-block; width: 20px; height: 20px; border: 2px solid #e1e4e8; border-top-color: #0366d6; border-radius: 50%; animation: spin 1s linear infinite;"></div>
                        <p style="margin-top: 10px;">等待授权...</p>
                        <p style="font-size: 12px; color: #999;">授权后自动登录</p>
                        <p style="font-size: 12px; color: #999; margin-top: 10px;">
                            设备码将在 ${Math.floor(deviceCode.expires_in / 60)} 分钟后过期
                        </p>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="oauth.closeDialog()">取消</button>
                </div>
            </div>
        `;
        
        document.body.appendChild(dialog);
        this.currentDialog = dialog;
        
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
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: #ef4444;">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="12" y1="8" x2="12" y2="12"></line>
                        <line x1="12" y1="16" x2="12.01" y2="16"></line>
                    </svg>
                    <h3>错误</h3>
                </div>
                <div class="modal-body">
                    <p style="color: #24292e; font-size: 14px; line-height: 1.6;">${message}</p>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-primary" onclick="oauth.closeErrorDialog()">确定</button>
                </div>
            </div>
        `;
        
        document.body.appendChild(dialog);
        this.currentErrorDialog = dialog;
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
        this.stopPolling();
        
        // 使用 GitHub 返回的间隔时间，默认 5 秒
        let pollInterval = (deviceCode.interval || 5) * 1000;
        
        this.pollTimer = setInterval(async () => {
            try {
                const response = await axios.post('/api/auth/token', {
                    device_code: deviceCode.device_code
                });
                
                // 授权成功
                this.stopPolling();
                this.oauthSessionId = response.data.session_id;
                sessionStorage.setItem('oauthSessionId', this.oauthSessionId);
                this.oauthAuthenticated = true;
                
                // 关闭对话框
                this.closeDialog();
                
                // 获取用户信息
                await this.checkStatus();
                
                // 触发回调
                if (this.onLoginSuccess) {
                    this.onLoginSuccess(this.oauthUser);
                }
                
            } catch (error) {
                if (error.response?.status === 400) {
                    const errorMsg = error.response.data.detail || error.response.data;
                    
                    if (errorMsg === 'authorization_pending') {
                        // 继续等待，检查是否有新的间隔时间
                        const newInterval = error.response.headers['x-interval'];
                        if (newInterval) {
                            console.log(`服务器要求新的轮询间隔：${newInterval}秒`);
                            this.stopPolling();
                            pollInterval = parseInt(newInterval) * 1000;
                            this.startPolling(deviceCode);
                        }
                        return;
                    } else if (errorMsg === 'access_denied') {
                        this.stopPolling();
                        this.closeDialog();
                        alert('授权已被拒绝');
                    } else if (errorMsg === 'expired_token') {
                        this.stopPolling();
                        this.closeDialog();
                        alert('授权码已过期，请重试');
                    } else if (errorMsg === 'slow_down') {
                        // GitHub 要求降低轮询频率
                        const newInterval = error.response.data.interval || 15;
                        console.log(`GitHub 要求降低轮询频率：${newInterval}秒`);
                        // 重置轮询间隔
                        this.stopPolling();
                        pollInterval = newInterval * 1000;
                        this.startPolling(deviceCode);
                    }
                } else {
                    console.error('OAuth 轮询失败:', error);
                }
            }
        }, pollInterval);
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
                    <button class="btn btn-ghost btn-sm" onclick="oauth.logout()" title="登出" style="padding: 2px 6px;">
                        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                            <polyline points="16 17 21 12 16 7"></polyline>
                            <line x1="21" y1="12" x2="9" y2="12"></line>
                        </svg>
                    </button>
                </div>
            `;
        } else {
            // 未登录状态 - 显示登录按钮
            container.innerHTML = `
                <button class="btn btn-primary btn-sm" onclick="oauth.startLogin()" title="使用 GitHub 登录" style="margin-right: 10px; display: inline-flex; align-items: center; gap: 4px;">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"></path>
                    </svg>
                    <span>登录</span>
                </button>
            `;
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
                background: rgba(0, 0, 0, 0.5);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 9999;
            }
            
            .modal {
                background: white;
                border-radius: 12px;
                padding: 24px;
                max-width: 450px;
                width: 90%;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            }
            
            .modal-header {
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 20px;
                padding-bottom: 16px;
                border-bottom: 1px solid #e1e4e8;
            }
            
            .modal-header h3 {
                margin: 0;
                font-size: 18px;
                font-weight: 600;
                color: #24292e;
            }
            
            .modal-body {
                margin-bottom: 20px;
            }
            
            .modal-footer {
                display: flex;
                justify-content: flex-end;
                gap: 8px;
                padding-top: 16px;
                border-top: 1px solid #e1e4e8;
            }
            
            .btn {
                padding: 8px 16px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                border: 1px solid transparent;
                transition: all 0.2s;
            }
            
            .btn-secondary {
                background: #f6f8fa;
                border-color: rgba(27,31,35,.15);
                color: #24292e;
            }
            
            .btn-secondary:hover {
                background: #f3f4f6;
                border-color: rgba(27,31,35,.3);
            }
            
            .btn-primary {
                background: #0366d6;
                color: white;
            }
            
            .btn-primary:hover {
                background: #0256b9;
            }
            
            .btn-sm {
                padding: 4px 12px;
                font-size: 13px;
            }
            
            .btn-ghost {
                background: transparent;
                color: #586069;
            }
            
            .btn-ghost:hover {
                background: rgba(27,31,35,.05);
            }
        `;
        
        document.head.appendChild(style);
    }
}

// 创建全局实例
const oauth = new OAuthComponent();

// 自动初始化
document.addEventListener('DOMContentLoaded', function() {
    oauth.init();
});

// 如果 DOM 已经加载完成，立即初始化
if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(() => oauth.init(), 100);
}
