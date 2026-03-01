/**
 * 图标渲染器 - 优化性能，避免重复渲染
 * 
 * 工作原理:
 * 1. 使用 Set 跟踪已渲染的图标
 * 2. 只渲染新的或重新创建的图标
 * 3. 使用 requestAnimationFrame 优化渲染时机
 * 4. 使用防抖避免频繁调用
 */
const IconRenderer = {
    timer: null,
    pending: false,
    renderedIcons: new Set(),  // 跟踪已渲染的图标
    
    /**
     * 渲染图标 - 只在需要时渲染
     */
    render() {
        if (this.pending) return;
        this.pending = true;
        requestAnimationFrame(() => {
            try {
                if (typeof lucide !== 'undefined') {
                    // 检查是否有新的图标需要渲染
                    const elements = document.querySelectorAll('[data-lucide]');
                    let hasNewIcons = false;
                    
                    elements.forEach(el => {
                        const iconName = el.getAttribute('data-lucide');
                        // 如果图标没有渲染过，或者元素被重新创建了（没有子元素）
                        if (!this.renderedIcons.has(iconName) || !el.querySelector('svg')) {
                            hasNewIcons = true;
                        }
                    });
                    
                    // 只有在新图标时才重新渲染
                    if (hasNewIcons) {
                        lucide.createIcons();
                        // 更新已渲染图标集合
                        this.renderedIcons.clear();
                        elements.forEach(el => {
                            this.renderedIcons.add(el.getAttribute('data-lucide'));
                        });
                    }
                }
            } catch (error) {
                // 忽略图标渲染错误，通常是因为元素还未准备好
                console.debug('Icon render error (ignored):', error.message);
            }
            this.pending = false;
        });
    },
    
    /**
     * 延迟渲染 - 防抖版本
     * @param {number} delay - 延迟时间 (毫秒)
     */
    renderDelayed(delay = 100) {
        if (this.timer) clearTimeout(this.timer);
        this.timer = setTimeout(() => this.render(), delay);
    },
    
    /**
     * 清空缓存 - 强制重新渲染所有图标
     */
    clearCache() {
        this.renderedIcons.clear();
    }
};

const TreeNode = {
    name: 'TreeNode',
    props: {
        node: Object,
        level: Number,
        expandedPaths: Set,
        selectedPath: String,
        editingPath: String,
        currentDirectory: String
    },
    emits: ['toggle', 'select', 'selectDirectory', 'rename', 'delete', 'move', 'contextmenu', 'newfile', 'newfolder'],
    computed: {
        isExpanded() { return this.expandedPaths.has(this.node.path); },
        isSelected() { return this.selectedPath === this.node.path; },
        isEditing() { return this.editingPath === this.node.path; },
        isCurrentDirectory() { return this.currentDirectory === this.node.path; },
        hasChildren() { return this.node.children && this.node.children.length > 0; },
        indentStyle() { return { paddingLeft: (this.level * 16) + 'px' }; }
    },
    methods: {
        toggle() { if (this.node.type === 'directory') this.$emit('toggle', this.node.path); },
        select() {
            if (this.node.type === 'file') { this.$emit('select', this.node); }
            else { this.$emit('selectDirectory', this.node.path); this.toggle(); }
        },
        onContextmenu(e) { e.preventDefault(); e.stopPropagation(); this.$emit('contextmenu', e, this.node); },
        formatSize(bytes) {
            if (!bytes) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        }
    },
    template: `
        <div>
            <div class="tree-item" :class="{ 'selected': isSelected || isCurrentDirectory, 'editing': isEditing }" :style="indentStyle" @click="select" @contextmenu="onContextmenu">
                <span class="tree-toggle" v-if="node.type === 'directory'" @click.stop="toggle" :class="{ 'expanded': isExpanded }">
                    <i v-if="hasChildren" data-lucide="chevron-right" style="width: 16px; height: 16px;"></i>
                </span>
                <span class="tree-toggle" v-else></span>
                <span class="tree-icon">
                    <i v-if="node.type === 'directory'" data-lucide="folder" style="width: 16px; height: 16px;"></i>
                    <i v-else data-lucide="file-text" style="width: 16px; height: 16px;"></i>
                </span>
                <span class="tree-name">{{ node.name }}</span>
                <span v-if="node.type === 'file' && node.size" class="file-size">{{ formatSize(node.size) }}</span>
                <div class="tree-actions">
                    <span class="tree-action-btn" @click.stop="$emit('rename', node)" title="重命名">
                        <i data-lucide="edit-3" style="width: 12px; height: 12px;"></i>
                    </span>
                    <span class="tree-action-btn delete" @click.stop="$emit('delete', node)" title="删除">
                        <i data-lucide="trash-2" style="width: 12px; height: 12px;"></i>
                    </span>
                </div>
            </div>
            <div v-if="node.type === 'directory' && hasChildren && isExpanded" class="tree-children">
                <tree-node v-for="child in node.children" :key="child.path" :node="child" :level="level + 1" :expanded-paths="expandedPaths" :selected-path="selectedPath" :editing-path="editingPath" :current-directory="currentDirectory" @toggle="$emit('toggle', $event)" @select="$emit('select', $event)" @select-directory="$emit('selectDirectory', $event)" @rename="$emit('rename', $event)" @delete="$emit('delete', $event)" @move="$emit('move', $event)" @contextmenu="$emit('contextmenu', $event, $event)" @newfile="$emit('newfile', $event)" @newfolder="$emit('newfolder', $event)"></tree-node>
            </div>
        </div>
    `
};

if (typeof Vue !== 'undefined') {
    const { createApp } = Vue;
    
    const app = createApp({
        components: { TreeNode },
        data() {
            return {
                contentEditor: null, files: [], fileTree: [], expandedPathsList: [],
                selectedFile: null, editingFilePath: '', currentDirectory: '', changes: [],
                loading: false, gitRepo: '', sidebarCollapsed: false, panelOpen: false,
                panelType: '', panelTitle: '', newFileName: '', newFileContent: '',
                newFolderName: '', renameTargetFile: null, renameNewName: '', moveTargetFile: null,
                moveSourcePath: '', moveDestPath: '', contextMenuVisible: false,
                contextMenuX: 0, contextMenuY: 0, contextMenuFile: null,
                toastVisible: false, toastMessage: '', toastType: 'info', toastIcon: 'info',
                modalVisible: false, modalTitle: '', modalMessage: '', modalType: 'info',
                modalIcon: 'info', modalDetails: [], modalConfirmClass: 'btn-primary',
                // 上传相关
                selectedFileForUpload: null, uploadFileName: '',
                modalCallback: null, modalTargetFile: null,
                currentColor: localStorage.getItem('themeColor') || 'blue',
                currentMode: localStorage.getItem('themeMode') || 'light',
                editorMode: localStorage.getItem('editorMode') || 'wysiwyg',
                hasUnsavedChanges: false,
                saving: false,
                committing: false,
                lastSavedContent: '',
                sessionId: sessionStorage.getItem('sessionId') || '',
                userId: localStorage.getItem('userId') || '',
                repositoryInitialized: false,
                hasRemote: false,
                excludePatterns: localStorage.getItem('excludePatterns') || '',
                simplePatterns: localStorage.getItem('simplePatterns') || '',
                useWhitelist: localStorage.getItem('useWhitelist') === 'true',
                whitelistExceptions: localStorage.getItem('whitelistExceptions') || ''
            };
        },
        computed: {
            expandedPaths() { return new Set(this.expandedPathsList); },
            fileStats() {
                let files = 0, folders = 0;
                for (const f of this.files) {
                    if (f.type === 'file') files++;
                    else folders++;
                }
                return { files, folders };
            },
            fileCount() { return this.fileStats.files; },
            folderCount() { return this.fileStats.folders; }
        },
        methods: {
            getHeaders() {
                const headers = { 'Content-Type': 'application/json' };
                if (this.sessionId) {
                    headers['X-Session-ID'] = this.sessionId;
                }
                // 添加 OAuth Session ID（用于 Git 认证）
                const oauthSessionId = sessionStorage.getItem('oauthSessionId');
                if (oauthSessionId) {
                    headers['X-OAuth-Session-ID'] = oauthSessionId;
                }
                return headers;
            },
            async initApp() {
                await this.checkSessionStatus();
                
                // 获取后端保存的 Git 仓库配置
                axios.get('/api/git-repo', { headers: this.getHeaders() })
                    .then(response => { 
                        if (response.data && response.data.data) { 
                            const backendGitRepo = response.data.data.gitRepo || '';
                            // 只有当会话有效时才使用后端配置
                            if (this.sessionId && this.repositoryInitialized) {
                                this.gitRepo = backendGitRepo;
                            } else {
                                // 会话无效或无配置，清空 gitRepo
                                this.gitRepo = '';
                            }
                        } 
                    })
                    .catch(error => console.error('Failed to get git repo config:', error));
                
                this.getFiles();
            },
            async checkSessionStatus() {
                if (!this.sessionId) {
                    this.repositoryInitialized = false;
                    this.hasRemote = false;
                    return;
                }
                try {
                    const response = await axios.get('/api/session/status', { headers: this.getHeaders() });
                    if (response.data && response.data.data) {
                        this.repositoryInitialized = response.data.data.initialized || false;
                        this.hasRemote = response.data.data.hasRemote || false;
                    }
                } catch (error) {
                    console.error('Failed to check session status:', error);
                    this.repositoryInitialized = false;
                    this.hasRemote = false;
                }
            },
            async createOrUseSession() {
                // 确保有 userId
                if (!this.userId) {
                    await this.initUserId();
                }
                
                if (this.sessionId) {
                    await this.checkSessionStatus();
                    // 如果会话无效，清除旧会话创建新会话
                    if (!this.repositoryInitialized && !this.hasRemote) {
                        const statusResponse = await axios.get('/api/session/status', { headers: this.getHeaders() });
                        if (!statusResponse.data.data || !statusResponse.data.data.initialized) {
                            // 会话确实无效，清除并重新创建
                            sessionStorage.removeItem('sessionId');
                            this.sessionId = '';
                            this.gitRepo = '';
                        }
                    }
                    if (this.sessionId) {
                        return;
                    }
                }
                
                try {
                    // 创建新会话，传递 userId（单用户单会话策略）
                    const headers = {
                        ...this.getHeaders(),
                        'X-User-ID': this.userId
                    };
                    const response = await axios.get('/api/session/create', { headers });
                    if (response.data && response.data.data) {
                        this.sessionId = response.data.data.sessionId;
                        sessionStorage.setItem('sessionId', this.sessionId);  // 使用 sessionStorage
                        this.gitRepo = ''; // 新会话不保留 Git 配置
                        await this.checkSessionStatus();
                        this.showToast('新会话已创建，请配置远程仓库地址', 'success');
                    }
                } catch (error) {
                    console.error('Failed to create session:', error);
                }
            },
            
            async initUserId() {
                // 从 localStorage 获取 userId，如果没有则生成新的
                let userId = localStorage.getItem('userId');
                if (!userId) {
                    try {
                        const response = await axios.get('/api/session/user-id');
                        if (response.data && response.data.data) {
                            userId = response.data.data.userId;
                            localStorage.setItem('userId', userId);
                            this.userId = userId;
                        }
                    } catch (error) {
                        console.error('Failed to initialize user ID:', error);
                        // 如果 API 失败，生成一个临时的 userId
                        userId = 'user_' + Date.now();
                        localStorage.setItem('userId', userId);
                        this.userId = userId;
                    }
                } else {
                    this.userId = userId;
                }
            },
            
            saveRepoConfig() {
                axios.post('/api/git-repo', { gitRepo: this.gitRepo }, { headers: this.getHeaders() })
                    .then(response => { 
                        this.showToast('仓库配置已保存', 'success'); 
                    })
                    .catch(error => { 
                        this.errorHandler(error); 
                    }); 
            },
            async saveAllSettings() {
                this.saving = true;
                try {
                    if (this.gitRepo) {
                        await axios.post('/api/git-repo', { gitRepo: this.gitRepo }, { headers: this.getHeaders() });
                    }
                    localStorage.setItem('excludePatterns', this.excludePatterns);
                    localStorage.setItem('simplePatterns', this.simplePatterns);
                    localStorage.setItem('useWhitelist', this.useWhitelist);
                    localStorage.setItem('whitelistExceptions', this.whitelistExceptions);
                    
                    this.showToast('设置已保存', 'success');
                    this.closePanel();
                    await this.getFiles();
                }
                catch (error) { 
                    this.errorHandler(error); 
                }
                finally {
                    this.saving = false;
                }
            },
            
            toggleSidebar() { 
                console.log('toggleSidebar clicked, current state:', this.sidebarCollapsed);
                this.sidebarCollapsed = !this.sidebarCollapsed;
                console.log('toggleSidebar new state:', this.sidebarCollapsed);
                // 等待 DOM 更新后再渲染图标
                this.$nextTick(() => {
                    if (typeof IconRenderer !== 'undefined') {
                        IconRenderer.render();
                    }
                });
            },
            selectDirectory(path) { this.currentDirectory = path; this.hideContextMenu(); },
            async commit() {
                if (this.changes.length === 0) {
                    this.showToast('没有需要提交的变更', 'info');
                    return;
                }
                this.committing = true;
                IconRenderer.render();
                try {
                    const response = await axios.post('/api/commit', {}, { headers: this.getHeaders() });
                    
                    // 检查提交是否成功
                    if (!response.data || response.data.success === false) {
                        throw new Error(response.data?.message || '提交失败');
                    }
                    
                    this.showToast(response.data?.message || '提交成功', 'success'); 
                    this.changes = []; 
                    this.closePanel();
                    await this.getFiles();
                }
                catch (error) { 
                    console.error('提交失败:', error);
                    const errorMsg = error.response?.data?.message || error.message || '提交失败，请重试';
                    this.showToast(errorMsg, 'error');
                }
                finally { 
                    this.committing = false;
                    IconRenderer.render();
                }
            },
            async showChangesPanel() {
                try { 
                    const response = await axios.get('/api/posts/changes', { headers: this.getHeaders() }); 
                    this.changes = response.data.data || []; 
                    this.panelTitle = '提交变更'; 
                    this.panelType = 'changes'; 
                    this.panelOpen = true; 
                    this.$nextTick(() => IconRenderer.render());
                }
                catch (error) { this.errorHandler(error); }
            },
            handleFileSelect(event) {
                const file = event.target.files[0];
                if (file) {
                    this.selectedFileForUpload = file;
                    this.uploadFileName = file.name;  // 默认使用原文件名
                }
            },
            async uploadFile() {
                if (!this.selectedFileForUpload) {
                    this.showToast('请选择文件', 'error');
                    return;
                }
                
                const fileName = this.uploadFileName || this.selectedFileForUpload.name;
                const fullPath = this.buildFullPath(this.currentDirectory, fileName);
                
                // 验证文件名和路径
                if (!this.validateFileName(fileName) || !this.validatePath(fullPath)) {
                    return;
                }
                
                const formData = new FormData();
                formData.append('file', this.selectedFileForUpload);
                formData.append('path', fullPath);
                
                try {
                    await axios.post('/api/file/upload', formData, {
                        headers: {
                            ...this.getHeaders(),
                            'Content-Type': 'multipart/form-data'
                        }
                    });
                    await this.refreshAfterOperation();
                    this.showToast('文件上传成功', 'success');
                }
                catch (error) {
                    this.errorHandler(error);
                }
            },
            async getChanges() {
                try { 
                    const response = await axios.get('/api/posts/changes', { headers: this.getHeaders() }); 
                    this.changes = response.data.data || [];
                }
                catch (error) { 
                    console.debug('获取变更失败：', error.message);
                    // 静默失败，不影响用户体验
                }
            },
            async saveFile() {
                if (!this.editingFilePath || !this.contentEditor || this.saving) return;
                this.saving = true;
                // 保存状态变化时清空图标缓存
                IconRenderer.clearCache();
                try { 
                    const response = await axios.post('/api/file/save', { path: this.editingFilePath, content: this.contentEditor.getValue() }, { headers: this.getHeaders() });
                    
                    // 检查响应是否成功
                    if (!response.data || response.data.success === false) {
                        throw new Error(response.data?.message || '保存失败，服务器返回错误');
                    }
                    
                    this.showToast(response.data?.message || '保存成功', 'success'); 
                    this.hasUnsavedChanges = false; 
                    this.lastSavedContent = this.contentEditor.getValue();
                    // 保存成功后自动获取变更列表
                    await this.getChanges();
                }
                catch (error) { 
                    console.error('保存文件失败:', error);
                    const errorMsg = error.response?.data?.message || error.message || '保存失败，请检查网络连接';
                    this.showToast(errorMsg, 'error');
                    // 恢复未保存状态，让用户知道需要重新保存
                    this.hasUnsavedChanges = true;
                }
                finally { 
                    this.saving = false;
                    // 保存完成后再渲染一次图标
                    IconRenderer.render();
                }
            },
            async selectFile(file) {
                if (this.hasUnsavedChanges) { await this.saveFile(); }
                this.selectedFile = file; this.editingFilePath = file.path; this.loading = true;
                try { const response = await axios.get('/api/file/content', { params: { file_path: file.path }, headers: this.getHeaders() }); await this.$nextTick(); this.createEditor(file.path, response.data); this.lastSavedContent = response.data; this.hasUnsavedChanges = false; }
                catch (error) { this.errorHandler(error); }
                finally { this.loading = false; }
            },
            toggleExpand(path) {
                const index = this.expandedPathsList.indexOf(path);
                if (index > -1) {
                    this.expandedPathsList.splice(index, 1);
                } else {
                    this.expandedPathsList.push(path);
                }
            },
            async initWorkspace() {
                if (!this.sessionId) {
                    this.showToast('请先进行 OAuth 登录', 'error');
                    return;
                }
                
                if (!this.gitRepo) { 
                    this.showToast('请先配置 Git 仓库地址', 'error'); 
                    this.showConfigPanel();
                    return; 
                }
                
                await this.checkSessionStatus();
                
                let modalDetails = [];
                let modalTitle = '初始化仓库';
                
                if (this.repositoryInitialized && this.hasRemote) {
                    modalTitle = '仓库已连接';
                    modalDetails = [
                        '当前仓库已经初始化并连接了远程仓库',
                        '您可以选择：',
                        '- 点击确认重新初始化（会保留本地文件）',
                        '- 取消以使用现有仓库'
                    ];
                } else if (this.repositoryInitialized && !this.hasRemote) {
                    modalDetails = [
                        '当前仓库已初始化但未配置远程仓库',
                        '将为您配置远程仓库地址：' + this.gitRepo
                    ];
                } else {
                    modalDetails = [
                        '如果已配置远程仓库地址，将自动克隆到本地',
                        '如果本地已有文件，将被保留'
                    ];
                }
                
                this.showModal({
                    title: modalTitle, message: '是否确定初始化仓库？', type: 'info', icon: 'git-branch-plus',
                    details: modalDetails,
                    confirmClass: 'btn-primary',
                    callback: async () => {
                        try {
                            const response = await axios.post('/api/init', { gitRepo: this.gitRepo }, { headers: this.getHeaders() });
                            await this.getFiles();
                            await this.checkSessionStatus();
                            this.showToast(response.data.message || '初始化成功', 'success');
                        } catch (error) { this.errorHandler(error); }
                    }
                });
            },
            async pullRepo() {
                if (!this.sessionId) {
                    this.showToast('请先进行 OAuth 登录', 'error');
                    return;
                }
                
                if (!this.repositoryInitialized) {
                    this.showToast('请先初始化仓库', 'error');
                    return;
                }
                
                try { 
                    await axios.post('/api/pull', {}, { headers: this.getHeaders() }); 
                    await this.getFiles(); 
                    this.showToast('拉取成功', 'success'); 
                }
                catch (error) { 
                    this.errorHandler(error); 
                }
            },
            showNewFilePanel() { this.newFileName = ''; this.newFileContent = ''; this.panelTitle = '新建文件'; this.panelType = 'newfile'; this.panelOpen = true; },
            showNewFilePanelAt(path) { this.currentDirectory = path; this.newFileName = ''; this.newFileContent = ''; this.panelTitle = '新建文件'; this.panelType = 'newfile'; this.panelOpen = true; this.hideContextMenu(); },
            showNewFolderPanel() { this.newFolderName = ''; this.panelTitle = '新建文件夹'; this.panelType = 'newfolder'; this.panelOpen = true; },
            showNewFolderPanelAt(path) { this.currentDirectory = path; this.newFolderName = ''; this.panelTitle = '新建文件夹'; this.panelType = 'newfolder'; this.panelOpen = true; this.hideContextMenu(); },
            showUploadPanel() { 
                this.selectedFileForUpload = null; 
                this.uploadFileName = ''; 
                this.panelTitle = '上传文件'; 
                this.panelType = 'upload'; 
                this.panelOpen = true; 
            },
            showConfigPanel() { 
                console.log('showConfigPanel called');
                this.panelTitle = '使用说明'; 
                this.panelType = 'config'; 
                this.panelOpen = true; 
            },
            showThemePanel() { 
                console.log('showThemePanel called');
                this.panelTitle = '主题与设置'; 
                this.panelType = 'theme'; 
                this.panelOpen = true; 
            },
            setColor(color) {
                this.currentColor = color;
                localStorage.setItem('themeColor', color);
                document.documentElement.setAttribute('data-color', color);
                this.$nextTick(() => IconRenderer.render());
            },
            /**
             * 设置显示模式 (浅色/深色)
             * @param {string} mode - 'light' 或 'dark'
             */
            setMode(mode) {
                this.currentMode = mode;
                localStorage.setItem('themeMode', mode);
                if (mode === 'light') {
                    document.documentElement.removeAttribute('data-mode');
                } else {
                    document.documentElement.setAttribute('data-mode', 'dark');
                }
                if (this.contentEditor) {
                    const vditorTheme = mode === 'dark' ? 'dark' : 'classic';
                    // 使用正确的 Vditor API 切换主题
                    this.contentEditor.setTheme(vditorTheme, {
                        theme: vditorTheme,
                        previewTheme: vditorTheme
                    });
                }
                this.$nextTick(() => IconRenderer.render());
            },
            setEditorMode(mode) {
                this.editorMode = mode; localStorage.setItem('editorMode', mode);
                if (this.contentEditor) { const content = this.contentEditor.getValue(); this.createEditor(this.editingFilePath, content); }
            },
            escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            },
            copyToClipboard(text, message) {
                navigator.clipboard.writeText(text).then(() => { this.showToast(message, 'success'); }).catch(() => {
                    const textarea = document.createElement('textarea'); textarea.value = text; document.body.appendChild(textarea); textarea.select(); document.execCommand('copy'); document.body.removeChild(textarea); this.showToast(message, 'success');
                });
            },
            showRenamePanel(file) { this.renameTargetFile = file; this.renameNewName = file.name; this.panelTitle = '重命名'; this.panelType = 'rename'; this.panelOpen = true; this.hideContextMenu(); this.$nextTick(() => IconRenderer.render()); },
            showMovePanel(file) { this.moveTargetFile = file; this.moveSourcePath = file.path; this.moveDestPath = file.path; this.panelTitle = '移动文件'; this.panelType = 'move'; this.panelOpen = true; this.hideContextMenu(); this.$nextTick(() => IconRenderer.render()); },
            closePanel() { 
                this.panelOpen = false; 
                // 等待动画完成后清空面板类型
                setTimeout(() => {
                    this.panelType = '';
                }, 300);
            },
            /**
             * 验证文件名是否合法
             * @param {string} name - 要验证的文件名
             * @returns {boolean} - 是否合法
             */
            validateFileName(name) {
                if (!name || name.trim() === '') {
                    this.showToast('文件名不能为空', 'error');
                    return false;
                }
                
                // 检查长度
                if (name.length > 255) {
                    this.showToast('文件名过长 (最大 255 个字符)', 'error');
                    return false;
                }
                
                // 检查非法字符
                const invalidChars = /[<>:"\/\\|？*]/;
                if (invalidChars.test(name)) {
                    this.showToast('文件名包含非法字符 (< > : " / \\ | ? *)', 'error');
                    return false;
                }
                
                // 检查保留名称
                const reservedNames = ['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'];
                const upperName = name.toUpperCase().split('.')[0];
                if (reservedNames.includes(upperName)) {
                    this.showToast('文件名使用了系统保留名称', 'error');
                    return false;
                }
                
                // 检查是否以点开头 (隐藏文件)
                if (name.startsWith('.')) {
                    this.showToast('文件名不能以点开头', 'error');
                    return false;
                }
                
                return true;
            },

            /**
             * 验证路径是否合法
             * @param {string} path - 要验证的路径
             * @returns {boolean} - 是否合法
             */
            validatePath(path) {
                if (!path || path.trim() === '') {
                    this.showToast('路径不能为空', 'error');
                    return false;
                }
                
                // 检查路径遍历攻击
                if (path.includes('..')) {
                    this.showToast('非法路径', 'error');
                    return false;
                }
                
                // 检查绝对路径
                if (path.startsWith('/') || path.startsWith('\\') || /^[a-zA-Z]:/.test(path)) {
                    this.showToast('只能使用相对路径', 'error');
                    return false;
                }
                
                // 检查总长度
                if (path.length > 500) {
                    this.showToast('路径过长', 'error');
                    return false;
                }
                
                return true;
            },

            /**
             * 构建完整文件路径
             * @param {string} directory - 目录路径
             * @param {string} fileName - 文件名
             * @returns {string} 完整路径
             */
            buildFullPath(directory, fileName) {
                return directory ? `${directory}/${fileName}` : fileName;
            },

            /**
             * 操作后刷新文件列表和变更
             * 用于文件创建、删除、重命名、移动等操作后
             */
            async refreshAfterOperation() {
                this.closePanel();
                await this.getFiles();
                await this.getChanges();
                if (this.currentDirectory && !this.expandedPathsList.includes(this.currentDirectory)) {
                    this.expandedPathsList.push(this.currentDirectory);
                }
            },

            async createFile() {
                if (!this.newFileName) { this.showToast('请输入文件名', 'error'); return; }
                
                // 验证文件名
                if (!this.validateFileName(this.newFileName)) {
                    return;
                }
                
                const fullPath = this.buildFullPath(this.currentDirectory, this.newFileName);
                
                // 验证完整路径
                if (!this.validatePath(fullPath)) {
                    return;
                }
                
                try { 
                    await axios.post('/api/file/create', { path: fullPath, content: this.newFileContent }, { headers: this.getHeaders() }); 
                    await this.refreshAfterOperation();
                    this.showToast('文件创建成功', 'success'); 
                }
                catch (error) { this.errorHandler(error); }
            },
            async createFolder() {
                if (!this.newFolderName) { this.showToast('请输入文件夹名', 'error'); return; }
                
                // 验证文件夹名
                if (!this.validateFileName(this.newFolderName)) {
                    return;
                }
                
                const fullPath = this.buildFullPath(this.currentDirectory, this.newFolderName);
                
                // 验证完整路径
                if (!this.validatePath(fullPath)) {
                    return;
                }
                
                try { 
                    await axios.post('/api/folder/create', { path: fullPath }, { headers: this.getHeaders() }); 
                    await this.refreshAfterOperation();
                    this.showToast('文件夹创建成功', 'success'); 
                }
                catch (error) { this.errorHandler(error); }
            },
            async renameFile() {
                if (!this.renameNewName) { this.showToast('请输入新名称', 'error'); return; }
                
                // 验证新文件名
                if (!this.validateFileName(this.renameNewName)) {
                    return;
                }
                
                const oldPath = this.renameTargetFile.path; 
                const parentPath = oldPath.substring(0, oldPath.lastIndexOf('/')); 
                const newPath = this.buildFullPath(parentPath, this.renameNewName);
                
                try { 
                    await axios.post('/api/file/rename', { oldPath: oldPath, newPath: newPath }, { headers: this.getHeaders() }); 
                    await this.refreshAfterOperation();
                    if (this.editingFilePath === oldPath) this.editingFilePath = newPath; 
                    this.showToast('重命名成功', 'success'); 
                }
                catch (error) { this.errorHandler(error); }
            },
            async moveFile() {
                if (!this.moveDestPath) { this.showToast('请输入目标路径', 'error'); return; }
                
                // 验证目标路径
                if (!this.validatePath(this.moveDestPath)) {
                    return;
                }
                
                try { 
                    await axios.post('/api/file/move', { sourcePath: this.moveSourcePath, destPath: this.moveDestPath }, { headers: this.getHeaders() }); 
                    await this.refreshAfterOperation();
                    if (this.editingFilePath === this.moveSourcePath) this.editingFilePath = this.moveDestPath; 
                    this.showToast('移动成功', 'success'); 
                }
                catch (error) { this.errorHandler(error); }
            },
            async deleteFile(file) {
                this.showModal({
                    title: '删除确认', message: `确定要删除 "${file.name}" 吗？`, type: 'danger', icon: 'trash-2', confirmClass: 'btn-primary',
                    callback: async () => {
                        try {
                            await axios.delete('/api/file/delete', { params: { file_path: file.path }, headers: this.getHeaders() });
                            if (this.editingFilePath === file.path) { 
                                if (this.contentEditor) { 
                                    this.contentEditor.destroy(); 
                                    this.contentEditor = null; 
                                } 
                                this.editingFilePath = ''; 
                                this.hasUnsavedChanges = false; 
                            }
                            await this.refreshAfterOperation();
                            this.showToast('删除成功', 'success');
                        } catch (error) { this.errorHandler(error); }
                    }
                });
            },
            async getFiles() {
                this.loading = true;
                try {
                    // 获取并发送所有过滤规则
                    const excludePatterns = this.getExcludePatterns();
                    const simplePatterns = this.getSimplePatterns();
                    const whitelistExceptions = this.getWhitelistExceptions();
                    const headers = {
                        ...this.getHeaders(),
                        'X-Exclude-Patterns': JSON.stringify(excludePatterns),
                        'X-Simple-Patterns': JSON.stringify(simplePatterns),
                        'X-Use-Whitelist': this.useWhitelist ? 'true' : 'false',
                        'X-Whitelist-Exceptions': JSON.stringify(whitelistExceptions)
                    };
                    
                    const response = await axios.get('/api/files', { headers });
                    
                    // 检查会话是否过期
                    if (response.data.message && response.data.message.includes('会话已过期')) {
                        console.warn('会话已过期，创建新会话...');
                        localStorage.removeItem('sessionId');
                        this.sessionId = '';
                        await this.createOrUseSession();
                        // 重新获取文件
                        return this.getFiles();
                    }
                    
                    this.files = response.data.data || [];
                    this.buildFileTree();
                    
                    IconRenderer.render();
                    
                    if (this.files.length === 0 && this.sessionId) {
                        await this.checkSessionStatus();
                        if (!this.repositoryInitialized) {
                        }
                    }
                }
                catch (error) { this.errorHandler(error); }
                finally { this.loading = false; }
            },
            buildFileTree() {
                const root = { children: {} }; const sortedFiles = [...this.files].sort((a, b) => a.path.localeCompare(b.path));
                for (const file of sortedFiles) {
                    const parts = file.path.split('/').filter(p => p); let current = root; let currentPath = '';
                    for (let i = 0; i < parts.length; i++) {
                        const part = parts[i]; const isLast = i === parts.length - 1;
                        currentPath = currentPath ? currentPath + '/' + part : part;
                        if (!current.children[part]) {
                            if (isLast) { current.children[part] = { name: part, path: currentPath, type: file.type, size: file.size, children: file.type === 'directory' ? {} : undefined }; }
                            else { current.children[part] = { name: part, path: currentPath, type: 'directory', children: {} }; }
                        } else if (isLast && file.type === 'directory') { current.children[part].type = 'directory'; if (!current.children[part].children) current.children[part].children = {}; }
                        current = current.children[part];
                    }
                }
                const convertToArray = (node) => {
                    if (!node.children) return node;
                    const children = Object.values(node.children).map(convertToArray).sort((a, b) => { if (a.type !== b.type) return a.type === 'directory' ? -1 : 1; return a.name.localeCompare(b.name); });
                    return { ...node, children };
                };
                this.fileTree = Object.values(root.children).map(convertToArray).sort((a, b) => { if (a.type !== b.type) return a.type === 'directory' ? -1 : 1; return a.name.localeCompare(b.name); });
            },
            createEditor(filePath, rawContent) {
                if (this.contentEditor) this.contentEditor.destroy();
                const vditorTheme = this.currentMode === 'dark' ? 'dark' : 'classic';
                const self = this;
                this.contentEditor = new Vditor('vditor', {
                    height: '100%', 
                    toolbarConfig: { pin: true }, 
                    cache: { enable: false },
                    theme: vditorTheme,
                    preview: { 
                        markdown: { 
                            linkBase: filePath.substring(0, filePath.lastIndexOf('/')) 
                        }, 
                        theme: { 
                            current: vditorTheme 
                        } 
                    },
                    hljs: { lineNumber: true },
                    input: () => { 
                        self.hasUnsavedChanges = true; 
                        if (self.autoSaveTimer) clearTimeout(self.autoSaveTimer); 
                        self.autoSaveTimer = setTimeout(() => { self.saveFile(); }, 3000); 
                    },
                    mode: this.editorMode,
                    after: () => { 
                        self.contentEditor.setValue(rawContent); 
                        self.lastSavedContent = rawContent; 
                    }
                });
            },
            errorHandler(error) {
                console.error(error);
                const message = error.response?.data?.detail || '操作失败，请重试'; this.showToast(message, 'error');
            },
            /**
             * 显示 Toast 提示
             * @param {string} message - 提示信息
             * @param {string} type - 提示类型：'success' | 'error' | 'info' | 'warning'
             */
            showToast(message, type = 'info') { this.toastMessage = message; this.toastType = type; this.toastIcon = type === 'success' ? 'check-circle' : type === 'error' ? 'alert-circle' : 'info'; this.toastVisible = true; this.$nextTick(() => IconRenderer.render()); setTimeout(() => { this.toastVisible = false; }, 3000); },
            /**
             * 显示模态对话框
             * @param {Object} options - 对话框配置
             * @param {string} options.title - 标题
             * @param {string} options.message - 消息内容
             * @param {string} options.type - 类型：'info' | 'danger' | 'warning'
             * @param {string} options.icon - 图标名称
             * @param {Function} options.callback - 确认回调
             */
            showModal(options) { this.modalTitle = options.title || '确认'; this.modalMessage = options.message || ''; this.modalType = options.type || 'info'; this.modalIcon = options.icon || 'info'; this.modalDetails = options.details || []; this.modalConfirmClass = options.confirmClass || 'btn-primary'; this.modalCallback = options.callback || null; this.modalVisible = true; this.$nextTick(() => IconRenderer.render()); },
            confirmModal() { this.modalVisible = false; if (this.modalCallback) { this.modalCallback(); this.modalCallback = null; } },
            cancelModal() { this.modalVisible = false; this.modalCallback = null; },

            getExcludePatterns() {
                if (!this.excludePatterns) return [];
                return this.excludePatterns.split('\n').map(p => p.trim()).filter(p => p.length > 0);
            },
            getSimplePatterns() {
                if (!this.simplePatterns) return [];
                return this.simplePatterns.split('\n').map(p => p.trim()).filter(p => p.length > 0);
            },
            getWhitelistExceptions() {
                if (!this.whitelistExceptions) return [];
                return this.whitelistExceptions.split('\n').map(p => p.trim()).filter(p => p.length > 0);
            },
            addPattern(pattern) {
                // 如果当前为空，直接设置
                if (!this.excludePatterns || this.excludePatterns.trim() === '') {
                    this.excludePatterns = pattern;
                } else {
                    // 否则追加到末尾
                    this.excludePatterns = this.excludePatterns.trimEnd() + '\n' + pattern;
                }
                this.showToast('已添加正则规则：' + pattern, 'info');
            },
            addSimplePattern(pattern) {
                // 如果当前为空，直接设置
                if (!this.simplePatterns || this.simplePatterns.trim() === '') {
                    this.simplePatterns = pattern;
                } else {
                    // 否则追加到末尾
                    this.simplePatterns = this.simplePatterns.trimEnd() + '\n' + pattern;
                }
                this.showToast('已添加简单规则：' + pattern, 'info');
            },
            showContextMenu(event, file) { this.contextMenuVisible = true; this.contextMenuX = event.clientX; this.contextMenuY = event.clientY; this.contextMenuFile = file; this.$nextTick(() => IconRenderer.render()); },
            hideContextMenu() { this.contextMenuVisible = false; this.contextMenuFile = null; },
            openFile() { if (this.contextMenuFile && this.contextMenuFile.type === 'file') this.selectFile(this.contextMenuFile); this.hideContextMenu(); },
            newFileAtContext() { if (this.contextMenuFile) this.showNewFilePanelAt(this.contextMenuFile.path); },
            newFolderAtContext() { if (this.contextMenuFile) this.showNewFolderPanelAt(this.contextMenuFile.path); },
            renameContext() { if (this.contextMenuFile) this.showRenamePanel(this.contextMenuFile); },
            moveContext() { if (this.contextMenuFile) this.showMovePanel(this.contextMenuFile); },
            deleteContext() { if (this.contextMenuFile) this.deleteFile(this.contextMenuFile); }
        },
        async mounted() {
            document.documentElement.setAttribute('data-color', this.currentColor);
            if (this.currentMode === 'dark') {
                document.documentElement.setAttribute('data-mode', 'dark');
            }
            this._clickHandler = () => { this.hideContextMenu(); };
            document.addEventListener('click', this._clickHandler);
            await this.$nextTick();
            IconRenderer.render();
            await this.createOrUseSession();
            await this.initApp();
            
            // 初始化 OAuth 组件
            if (typeof oauth !== 'undefined') {
                console.log('Initializing OAuth component...');
                oauth.init();
            } else {
                console.error('OAuth component not found!');
            }
        },
        beforeUnmount() {
            if (this.autoSaveTimer) { clearTimeout(this.autoSaveTimer); this.autoSaveTimer = null; }
            if (this.contentEditor) { this.contentEditor.destroy(); this.contentEditor = null; }
            if (this._clickHandler) { document.removeEventListener('click', this._clickHandler); this._clickHandler = null; }
        }
    });
    app.mount('#app');
} else { console.error('Vue is not loaded'); }
