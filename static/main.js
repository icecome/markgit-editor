lucide.createIcons();

const TreeNode = {
    name: 'TreeNode',
    props: {
        node: Object,
        level: Number,
        expandedPaths: Object,
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
                    <svg v-if="hasChildren" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
                </span>
                <span class="tree-toggle" v-else></span>
                <span class="tree-icon">
                    <svg v-if="node.type === 'directory'" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                    <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                </span>
                <span class="tree-name">{{ node.name }}</span>
                <span v-if="node.type === 'file' && node.size" class="file-size">{{ formatSize(node.size) }}</span>
                <div class="tree-actions">
                    <span class="tree-action-btn" @click.stop="$emit('rename', node)" title="重命名">
                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                    </span>
                    <span class="tree-action-btn delete" @click.stop="$emit('delete', node)" title="删除">
                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
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
                contentEditor: null, files: [], fileTree: [], expandedPaths: new Set(),
                selectedFile: null, editingFilePath: '', currentDirectory: '', changes: [],
                loading: false, gitRepo: '', sidebarCollapsed: false, panelOpen: false,
                panelType: '', panelTitle: '', newFileName: '', newFileContent: '',
                newFolderName: '', renameFile_: null, renameNewName: '', moveFile_: null,
                moveSourcePath: '', moveDestPath: '', contextMenuVisible: false,
                contextMenuX: 0, contextMenuY: 0, contextMenuFile: null,
                toastVisible: false, toastMessage: '', toastType: 'info', toastIcon: 'info',
                modalVisible: false, modalTitle: '', modalMessage: '', modalType: 'info',
                modalIcon: 'info', modalDetails: [], modalConfirmClass: 'btn-primary',
                modalCallback: null, modalFile_: null,
                currentTheme: localStorage.getItem('theme') || 'light',
                codeTheme: localStorage.getItem('codeTheme') || 'github',
                editorMode: localStorage.getItem('editorMode') || 'wysiwyg',
                hasUnsavedChanges: false,
                saving: false,
                committing: false,
                lastSavedContent: '',
                sessionId: sessionStorage.getItem('sessionId') || '',  // 使用 sessionStorage
                userId: localStorage.getItem('userId') || '',  // userId 持久化
                repositoryInitialized: false,
                hasRemote: false,
                excludePatterns: localStorage.getItem('excludePatterns') || '',
                simplePatterns: localStorage.getItem('simplePatterns') || '',
                useWhitelist: localStorage.getItem('useWhitelist') === 'true',
                whitelistExceptions: localStorage.getItem('whitelistExceptions') || ''
            };
        },
        computed: {
            fileCount() { return this.files.filter(f => f.type === 'file').length; },
            folderCount() { return this.files.filter(f => f.type === 'directory').length; }
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
                // 不保存到 localStorage，只发送到后端
                axios.post('/api/git-repo', { gitRepo: this.gitRepo }, { headers: this.getHeaders() })
                    .then(response => { 
                        this.closePanel(); 
                        this.showToast('配置已保存，请点击初始化按钮', 'success'); 
                    })
                    .catch(error => { 
                        this.errorHandler(error); 
                    }); 
            },
            
            toggleSidebar() { this.sidebarCollapsed = !this.sidebarCollapsed; },
            selectDirectory(path) { this.currentDirectory = path; this.hideContextMenu(); },
            async commit() {
                this.committing = true;
                try { 
                    await axios.post('/api/commit', {}, { headers: this.getHeaders() }); 
                    this.closePanel(); 
                    this.showToast('提交成功', 'success'); 
                    this.changes = []; 
                }
                catch (error) { this.errorHandler(error); }
                finally { this.committing = false; }
            },
            async showChangesPanel() {
                try { const response = await axios.get('/api/posts/changes', { headers: this.getHeaders() }); this.changes = response.data.data || []; this.panelTitle = '提交变更'; this.panelType = 'changes'; this.panelOpen = true; this.$nextTick(() => lucide.createIcons()); }
                catch (error) { this.errorHandler(error); }
            },
            async saveFile() {
                if (!this.editingFilePath || !this.contentEditor || this.saving) return;
                this.saving = true;
                try { await axios.post('/api/file/save', { path: this.editingFilePath, content: this.contentEditor.getValue() }, { headers: this.getHeaders() }); this.showToast('保存成功', 'success'); this.hasUnsavedChanges = false; this.lastSavedContent = this.contentEditor.getValue(); }
                catch (error) { this.errorHandler(error); }
                finally { this.saving = false; }
            },
            async selectFile(file) {
                if (this.hasUnsavedChanges) { await this.saveFile(); }
                this.selectedFile = file; this.editingFilePath = file.path; this.loading = true;
                try { const response = await axios.get('/api/file/content', { params: { file_path: file.path }, headers: this.getHeaders() }); await this.$nextTick(); this.createEditor(file.path, response.data); this.lastSavedContent = response.data; this.hasUnsavedChanges = false; }
                catch (error) { this.errorHandler(error); }
                finally { this.loading = false; }
            },
            toggleExpand(path) { if (this.expandedPaths.has(path)) this.expandedPaths.delete(path); else this.expandedPaths.add(path); this.expandedPaths = new Set(this.expandedPaths); },
            async initWorkspace() {
                if (!this.gitRepo) { this.showToast('请先配置 Git 仓库地址', 'error'); return; }
                
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
                try { await axios.post('/api/pull', {}, { headers: this.getHeaders() }); await this.getFiles(); this.showToast('拉取成功', 'success'); }
                catch (error) { this.errorHandler(error); }
            },
            showNewFilePanel() { this.newFileName = ''; this.newFileContent = ''; this.panelTitle = '新建文件'; this.panelType = 'newfile'; this.panelOpen = true; this.$nextTick(() => lucide.createIcons()); },
            showNewFilePanelAt(path) { this.currentDirectory = path; this.newFileName = ''; this.newFileContent = ''; this.panelTitle = '新建文件'; this.panelType = 'newfile'; this.panelOpen = true; this.hideContextMenu(); this.$nextTick(() => lucide.createIcons()); },
            showNewFolderPanel() { this.newFolderName = ''; this.panelTitle = '新建文件夹'; this.panelType = 'newfolder'; this.panelOpen = true; this.$nextTick(() => lucide.createIcons()); },
            showNewFolderPanelAt(path) { this.currentDirectory = path; this.newFolderName = ''; this.panelTitle = '新建文件夹'; this.panelType = 'newfolder'; this.panelOpen = true; this.hideContextMenu(); this.$nextTick(() => lucide.createIcons()); },
            showConfigPanel() { this.panelTitle = '使用说明'; this.panelType = 'config'; this.panelOpen = true; this.$nextTick(() => lucide.createIcons()); },
            showThemePanel() { this.panelTitle = '主题与设置'; this.panelType = 'theme'; this.panelOpen = true; this.$nextTick(() => lucide.createIcons()); },
            setTheme(theme) {
                this.currentTheme = theme; localStorage.setItem('theme', theme);
                if (theme === 'light') { document.documentElement.removeAttribute('data-theme'); } else { document.documentElement.setAttribute('data-theme', theme); }
                if (this.contentEditor) { const content = this.contentEditor.getValue(); this.createEditor(this.editingFilePath, content); }
                this.$nextTick(() => lucide.createIcons());
            },
            setCodeTheme(theme) {
                this.codeTheme = theme; localStorage.setItem('codeTheme', theme);
                if (this.contentEditor) { const content = this.contentEditor.getValue(); this.createEditor(this.editingFilePath, content); }
            },
            setEditorMode(mode) {
                this.editorMode = mode; localStorage.setItem('editorMode', mode);
                if (this.contentEditor) { const content = this.contentEditor.getValue(); this.createEditor(this.editingFilePath, content); }
            },
            exportToWechat() { if (!this.contentEditor) return; const html = this.contentEditor.getHTML(); const wechatStyle = this.applyWechatStyle(html); this.copyToClipboard(wechatStyle, '微信公众号格式已复制到剪贴板'); },
            exportToHTML() {
                if (!this.contentEditor) return;
                const html = this.contentEditor.getHTML(); const fullHtml = this.wrapFullHTML(html);
                const blob = new Blob([fullHtml], { type: 'text/html' }); const url = URL.createObjectURL(blob);
                const a = document.createElement('a'); a.href = url; a.download = (this.editingFilePath.split('/').pop().replace(/\.[^/.]+$/, '') || 'document') + '.html'; a.click();
                URL.revokeObjectURL(url); this.showToast('HTML文件已导出', 'success');
            },
            copyAsMarkdown() { if (!this.contentEditor) return; const markdown = this.contentEditor.getValue(); this.copyToClipboard(markdown, 'Markdown内容已复制到剪贴板'); },
            applyWechatStyle(html) {
                const sanitizedHtml = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(html) : html;
                const wechatStyles = `<style>body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.8; color: #333; padding: 20px; }h1, h2, h3, h4, h5, h6 { margin-top: 24px; margin-bottom: 16px; font-weight: 600; line-height: 1.25; }h1 { font-size: 2em; border-bottom: 1px solid #eaecef; padding-bottom: .3em; }h2 { font-size: 1.5em; border-bottom: 1px solid #eaecef; padding-bottom: .3em; }p { margin-bottom: 16px; }code { padding: 0.2em 0.4em; margin: 0; font-size: 85%; background-color: rgba(27,31,35,.05); border-radius: 3px; font-family: SFMono-Regular, Consolas, Liberation Mono, Menlo, monospace; }pre { padding: 16px; overflow: auto; font-size: 85%; line-height: 1.45; background-color: #f6f8fa; border-radius: 6px; }pre code { background-color: transparent; padding: 0; }blockquote { padding: 0 1em; color: #6a737d; border-left: 0.25em solid #dfe2e5; margin: 0 0 16px 0; }table { border-spacing: 0; border-collapse: collapse; margin-bottom: 16px; }table th, table td { padding: 6px 13px; border: 1px solid #dfe2e5; }table th { font-weight: 600; background-color: #f6f8fa; }table tr:nth-child(2n) { background-color: #f6f8fa; }img { max-width: 100%; box-sizing: content-box; background-color: #fff; }a { color: #0366d6; text-decoration: none; }a:hover { text-decoration: underline; }</style>`;
                return wechatStyles + sanitizedHtml;
            },
            wrapFullHTML(html) {
                const sanitizedHtml = typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(html) : html;
                return `<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>${this.escapeHtml(this.editingFilePath.split('/').pop())}</title><link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/${this.codeTheme}.min.css"><style>body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.8; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }h1, h2, h3, h4, h5, h6 { margin-top: 24px; margin-bottom: 16px; font-weight: 600; line-height: 1.25; }h1 { font-size: 2em; border-bottom: 1px solid #eaecef; padding-bottom: .3em; }h2 { font-size: 1.5em; border-bottom: 1px solid #eaecef; padding-bottom: .3em; }p { margin-bottom: 16px; }code { padding: 0.2em 0.4em; margin: 0; font-size: 85%; background-color: rgba(27,31,35,.05); border-radius: 3px; font-family: SFMono-Regular, Consolas, Liberation Mono, Menlo, monospace; }pre { padding: 16px; overflow: auto; font-size: 85%; line-height: 1.45; background-color: #f6f8fa; border-radius: 6px; }pre code { background-color: transparent; padding: 0; }blockquote { padding: 0 1em; color: #6a737d; border-left: 0.25em solid #dfe2e5; margin: 0 0 16px 0; }table { border-spacing: 0; border-collapse: collapse; margin-bottom: 16px; width: 100%; }table th, table td { padding: 6px 13px; border: 1px solid #dfe2e5; }table th { font-weight: 600; background-color: #f6f8fa; }table tr:nth-child(2n) { background-color: #f6f8fa; }img { max-width: 100%; }a { color: #0366d6; text-decoration: none; }a:hover { text-decoration: underline; }</style></head><body>${sanitizedHtml}</body></html>`;
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
            showRenamePanel(file) { this.renameFile_ = file; this.renameNewName = file.name; this.panelTitle = '重命名'; this.panelType = 'rename'; this.panelOpen = true; this.hideContextMenu(); this.$nextTick(() => lucide.createIcons()); },
            showMovePanel(file) { this.moveFile_ = file; this.moveSourcePath = file.path; this.moveDestPath = file.path; this.panelTitle = '移动文件'; this.panelType = 'move'; this.panelOpen = true; this.hideContextMenu(); this.$nextTick(() => lucide.createIcons()); },
            closePanel() { this.panelOpen = false; this.panelType = ''; },
            async createFile() {
                if (!this.newFileName) { this.showToast('请输入文件名', 'error'); return; }
                const fullPath = this.currentDirectory ? this.currentDirectory + '/' + this.newFileName : this.newFileName;
                try { await axios.post('/api/file/create', { path: fullPath, content: this.newFileContent }, { headers: this.getHeaders() }); this.closePanel(); await this.getFiles(); if (this.currentDirectory) { this.expandedPaths.add(this.currentDirectory); this.expandedPaths = new Set(this.expandedPaths); } this.showToast('文件创建成功', 'success'); }
                catch (error) { this.errorHandler(error); }
            },
            async createFolder() {
                if (!this.newFolderName) { this.showToast('请输入文件夹名', 'error'); return; }
                const fullPath = this.currentDirectory ? this.currentDirectory + '/' + this.newFolderName : this.newFolderName;
                try { await axios.post('/api/folder/create', { path: fullPath }, { headers: this.getHeaders() }); this.closePanel(); await this.getFiles(); if (this.currentDirectory) { this.expandedPaths.add(this.currentDirectory); this.expandedPaths = new Set(this.expandedPaths); } this.showToast('文件夹创建成功', 'success'); }
                catch (error) { this.errorHandler(error); }
            },
            async renameFile() {
                if (!this.renameNewName) { this.showToast('请输入新名称', 'error'); return; }
                const oldPath = this.renameFile_.path; const parentPath = oldPath.substring(0, oldPath.lastIndexOf('/')); const newPath = parentPath ? parentPath + '/' + this.renameNewName : this.renameNewName;
                try { await axios.post('/api/file/rename', { oldPath: oldPath, newPath: newPath }, { headers: this.getHeaders() }); this.closePanel(); await this.getFiles(); if (this.editingFilePath === oldPath) this.editingFilePath = newPath; this.showToast('重命名成功', 'success'); }
                catch (error) { this.errorHandler(error); }
            },
            async moveFile() {
                if (!this.moveDestPath) { this.showToast('请输入目标路径', 'error'); return; }
                try { await axios.post('/api/file/move', { sourcePath: this.moveSourcePath, destPath: this.moveDestPath }, { headers: this.getHeaders() }); this.closePanel(); await this.getFiles(); if (this.editingFilePath === this.moveSourcePath) this.editingFilePath = this.moveDestPath; this.showToast('移动成功', 'success'); }
                catch (error) { this.errorHandler(error); }
            },
            async deleteFile(file) {
                this.showModal({
                    title: '删除确认', message: `确定要删除 "${file.name}" 吗？`, type: 'danger', icon: 'trash-2', confirmClass: 'btn-primary',
                    callback: async () => {
                        try {
                            await axios.delete('/api/file/delete', { params: { file_path: file.path }, headers: this.getHeaders() });
                            if (this.editingFilePath === file.path) { if (this.contentEditor) { this.contentEditor.destroy(); this.contentEditor = null; } this.editingFilePath = ''; this.hasUnsavedChanges = false; }
                            await this.getFiles(); this.showToast('删除成功', 'success');
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
                const vditorTheme = this.currentTheme === 'dark' || this.currentTheme === 'purple' ? 'dark' : 'classic';
                const self = this;
                this.contentEditor = new Vditor('vditor', {
                    height: '100%', toolbarConfig: { pin: true }, cache: { enable: false },
                    after: () => { self.contentEditor.setValue(rawContent); self.lastSavedContent = rawContent; },
                    preview: { markdown: { linkBase: filePath.substring(0, filePath.lastIndexOf('/')) }, theme: { current: vditorTheme } },
                    hljs: { style: this.codeTheme, lineNumber: true },
                    input: () => { self.hasUnsavedChanges = true; if (self.autoSaveTimer) clearTimeout(self.autoSaveTimer); self.autoSaveTimer = setTimeout(() => { self.saveFile(); }, 3000); },
                    mode: this.editorMode, theme: vditorTheme
                });
            },
            errorHandler(error) {
                console.error(error);
                const message = error.response?.data?.detail || '操作失败，请重试'; this.showToast(message, 'error');
            },
            showToast(message, type = 'info') { this.toastMessage = message; this.toastType = type; this.toastIcon = type === 'success' ? 'check-circle' : type === 'error' ? 'alert-circle' : 'info'; this.toastVisible = true; this.$nextTick(() => lucide.createIcons()); setTimeout(() => { this.toastVisible = false; }, 3000); },
            showModal(options) { this.modalTitle = options.title || '确认'; this.modalMessage = options.message || ''; this.modalType = options.type || 'info'; this.modalIcon = options.icon || 'info'; this.modalDetails = options.details || []; this.modalConfirmClass = options.confirmClass || 'btn-primary'; this.modalCallback = options.callback || null; this.modalVisible = true; this.$nextTick(() => lucide.createIcons()); },
            confirmModal() { this.modalVisible = false; if (this.modalCallback) { this.modalCallback(); this.modalCallback = null; } },
            cancelModal() { this.modalVisible = false; this.modalCallback = null; },

            saveExcludePatterns() {
                localStorage.setItem('excludePatterns', this.excludePatterns);
                localStorage.setItem('simplePatterns', this.simplePatterns);
                localStorage.setItem('useWhitelist', this.useWhitelist);
                localStorage.setItem('whitelistExceptions', this.whitelistExceptions);
                this.showToast('设置已保存，刷新页面后生效', 'success');
                this.closePanel();
            },
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
            showContextMenu(event, file) { this.contextMenuVisible = true; this.contextMenuX = event.clientX; this.contextMenuY = event.clientY; this.contextMenuFile = file; this.$nextTick(() => lucide.createIcons()); },
            hideContextMenu() { this.contextMenuVisible = false; this.contextMenuFile = null; },
            openFile() { if (this.contextMenuFile && this.contextMenuFile.type === 'file') this.selectFile(this.contextMenuFile); this.hideContextMenu(); },
            newFileAtContext() { if (this.contextMenuFile) this.showNewFilePanelAt(this.contextMenuFile.path); },
            newFolderAtContext() { if (this.contextMenuFile) this.showNewFolderPanelAt(this.contextMenuFile.path); },
            renameContext() { if (this.contextMenuFile) this.showRenamePanel(this.contextMenuFile); },
            moveContext() { if (this.contextMenuFile) this.showMovePanel(this.contextMenuFile); },
            deleteContext() { if (this.contextMenuFile) this.deleteFile(this.contextMenuFile); }
        },
        async mounted() {
            if (this.currentTheme && this.currentTheme !== 'light') { document.documentElement.setAttribute('data-theme', this.currentTheme); }
            this._clickHandler = () => { this.hideContextMenu(); };
            document.addEventListener('click', this._clickHandler);
            await this.$nextTick();
            lucide.createIcons();
            await this.createOrUseSession();
            await this.initApp();
            
            // 初始化 OAuth 组件（如果可用）
            if (typeof oauth !== 'undefined') {
                oauth.init();
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
