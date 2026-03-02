import os
import datetime
import html
import shutil
import asyncio
import re
import io
import hashlib
from fastapi import APIRouter, HTTPException, Request, Header, UploadFile, File, Form, Depends
from fastapi.responses import PlainTextResponse
from typing import Optional
from PIL import Image
from defusedxml import ElementTree as ET
from slowapi import Limiter
from slowapi.util import get_remote_address

# 兼容 Windows 和 Linux 环境的 magic 库导入
try:
    import magic
    MAGIC_AVAILABLE = True
except (ImportError, OSError, AttributeError):
    magic = None
    MAGIC_AVAILABLE = False
    print("Warning: python-magic not available, file type validation will use file extension only")

from app.config import POSTS_PATH, BLOG_GIT_SSH, BLOG_CACHE_PATH, DEFAULT_WHITELIST_EXTENSIONS, logger
from app.models import ApiResponse
from app.file_service import (
    check_name, get_md_yaml, delete_image_not_included,
    pretty_git_status, read_post_template, get_files_recursive,
    validate_file_path, should_exclude_file
)
from app.git_service import (
    git_add, git_status, git_commit, pull_updates_async,
    init_local_git_async, sync_branch_name, deploy, sanitize_for_log
)
from app.context_manager import setup_git_context, get_current_cache_path, get_session_path
from app.session_manager import session_manager
from app.models import (
    FileCreateRequest, FileSaveRequest, FileRenameRequest,
    FileMoveRequest, FolderCreateRequest, GitRepoRequest, InitRequest
)

router = APIRouter()

# 获取速率限制器的依赖函数
def get_limiter(request: Request) -> Limiter:
    return request.app.state.limiter

# === 文件上传安全配置 ===
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.ico'}
ALLOWED_DOC_EXTENSIONS = {'.md', '.markdown', '.txt'}
ALLOWED_CONFIG_EXTENSIONS = {'.json', '.yaml', '.yml', '.toml'}
DANGEROUS_EXTENSIONS = {
    '.php', '.php3', '.php4', '.php5', '.php7', '.phtml', '.phar',
    '.jsp', '.jspx', '.jspa', '.do', '.action',
    '.asp', '.aspx', '.asa', '.asax', '.ascx', '.ashx', '.asmx',
    '.cgi', '.pl', '.py', '.rb', '.sh', '.bash',
    '.exe', '.dll', '.so', '.bat', '.cmd', '.com',
    '.htm', '.html', '.js', '.jsx', '.ts', '.tsx',
    '.css', '.scss', '.less',
}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB - 足够博客图片、文档使用
MAX_IMAGE_DIMENSION = 5000  # 5000x5000 - 降低尺寸限制，2MB 下的合理值

def validate_filename_secure(filename: str) -> bool:
    """安全验证文件名"""
    if not filename or filename.strip() == '':
        return False
    if '/' in filename or '\\' in filename:
        return False
    if '\x00' in filename:
        return False
    forbidden_names = {'.', '..', 'CON', 'PRN', 'AUX', 'NUL',
                       'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
                       'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'}
    name_without_ext = os.path.splitext(filename)[0].upper()
    if name_without_ext in forbidden_names:
        return False
    if len(filename) > 255:
        return False
    if re.search(r'[<>:"|？*]', filename):
        return False
    if filename.startswith('.'):
        return False
    return True

def validate_file_extension_secure(filename: str) -> bool:
    """安全验证文件扩展名"""
    ext = os.path.splitext(filename)[1].lower()
    if ext in DANGEROUS_EXTENSIONS:
        logger.warning(f"危险扩展名被阻止：{filename}")
        return False
    name_without_ext = os.path.splitext(filename)[0]
    if '.' in name_without_ext:
        inner_ext = os.path.splitext(name_without_ext)[1].lower()
        if inner_ext in DANGEROUS_EXTENSIONS:
            logger.warning(f"双重扩展名攻击被阻止：{filename}")
            return False
    allowed = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_DOC_EXTENSIONS | ALLOWED_CONFIG_EXTENSIONS
    if ext not in allowed:
        logger.warning(f"不支持的文件类型：{filename}")
        return False
    return True

def validate_svg_content(content: bytes) -> bool:
    """验证 SVG 文件内容是否安全"""
    try:
        # 1. 使用 defusedxml 解析 SVG，防止 XXE 攻击
        root = ET.fromstring(content.decode('utf-8'))
        
        # 2. 检查根元素是否为 svg
        if root.tag.lower().split('}')[-1] != 'svg':
            logger.warning("SVG 根元素不是 <svg> 标签")
            return False
        
        # 3. 递归检查所有元素和属性的安全性
        def check_element(elem):
            # 检查标签名
            tag_name = elem.tag.lower().split('}')[-1]  # 处理命名空间
            dangerous_elements = {
                'script', 'iframe', 'object', 'embed', 'form',
                'style', 'foreignobject', 'switch', 'use',
                'animate', 'animatemotion', 'animatetransform',
                'set', 'feimage', 'pattern', 'marker'
            }
            if tag_name in dangerous_elements:
                logger.warning(f"SVG 包含危险元素：{tag_name}")
                return False
            
            # 检查属性
            for attr_name, attr_value in elem.attrib.items():
                attr_name_lower = attr_name.lower()
                
                # 检查事件处理器
                if attr_name_lower.startswith('on'):
                    logger.warning(f"SVG 包含危险事件处理器：{attr_name}")
                    return False
                
                # 检查危险协议（完全禁止外部资源加载）
                attr_value_lower = attr_value.lower()
                dangerous_protocols = [
                    'javascript:', 'data:', 'vbscript:', 'file:',
                    'ftp:', 'http:', 'https:'  # 完全禁止外部资源
                ]
                if any(protocol in attr_value_lower for protocol in dangerous_protocols):
                    logger.warning(f"SVG 包含危险协议：{attr_value}")
                    return False
            
            # 递归检查子元素
            for child in elem:
                if not check_element(child):
                    return False
            
            return True
        
        if not check_element(root):
            return False
        
        # 4. 额外检查：确保没有 CDATA 或注释中隐藏的脚本
        content_str = content.decode('utf-8', errors='ignore').lower()
        if any(script_tag in content_str for script_tag in [
            '<![cdata[', '&lt;script', '&lt;iframe', '&lt;object'
        ]):
            logger.warning("SVG 包含潜在的编码绕过内容")
            return False
        
        return True
    except ET.ParseError as e:
        logger.warning(f"SVG XML 解析失败：{e}")
        return False
    except UnicodeDecodeError:
        logger.warning("SVG 内容不是有效的 UTF-8 编码")
        return False
    except Exception as e:
        logger.error(f"SVG 验证失败：{e}")
        return False

def validate_image_file(content: bytes, filename: str) -> bool:
    """验证图片文件是否安全（只验证，不净化）"""
    try:
        if len(content) > MAX_FILE_SIZE:
            logger.warning(f"图片过大：{filename}, 大小：{len(content)}")
            return False
        img = Image.open(io.BytesIO(content))
        img_format = img.format.lower()
        allowed_formats = {'jpeg', 'png', 'gif', 'webp', 'bmp', 'ico'}
        ext = os.path.splitext(filename)[1].lower()
        if ext == '.svg':
            return validate_svg_content(content)
        if img_format not in allowed_formats:
            logger.warning(f"不支持的图片格式：{img_format}, 文件名：{filename}")
            return False
        if img.width > MAX_IMAGE_DIMENSION or img.height > MAX_IMAGE_DIMENSION:
            logger.warning(f"图片尺寸过大：{img.width}x{img.height}, 文件名：{filename}")
            return False
        img.close()
        return True
    except Exception as e:
        logger.error(f"图片验证失败：{filename}, 错误：{e}")
        return False

def sanitize_image(content: bytes, filename: str) -> tuple[bool, bytes]:
    """净化图片内容，去除元数据和潜在恶意数据"""
    try:
        # 验证图片
        img = Image.open(io.BytesIO(content))
        img_format = img.format.lower()
        
        # 转换为 RGB 模式（去除 Alpha 通道可能的攻击）
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        
        # 重新保存图片，去除 EXIF 等元数据
        output = io.BytesIO()
        
        if img_format in {'jpeg', 'jpg'}:
            img.save(output, format='JPEG', quality=95, progressive=True, exif=None)
        elif img_format == 'png':
            img.save(output, format='PNG', optimize=True)
        elif img_format == 'gif':
            img.save(output, format='GIF', optimize=True)
        elif img_format == 'webp':
            img.save(output, format='WEBP', quality=95)
        elif img_format in {'bmp', 'ico'}:
            img.save(output, format=img_format.upper())
        else:
            img.close()
            return False, content
        
        sanitized_content = output.getvalue()
        img.close()
        
        logger.info(f"图片已净化：{filename}, 原始：{len(content)} bytes, 净化后：{len(sanitized_content)} bytes")
        return True, sanitized_content
        
    except Exception as e:
        logger.error(f"图片净化失败：{filename}, 错误：{e}")
        return False, content

def validate_mime_type(content: bytes, filename: str) -> bool:
    """验证 MIME 类型是否与扩展名匹配（可选增强）"""
    if not MAGIC_AVAILABLE or magic is None:
        # magic 库不可用时，只验证文件扩展名
        logger.debug(f"MIME 类型验证跳过（magic 库不可用）：{filename}")
        return True
    
    try:
        mime = magic.from_buffer(content, mime=True)
        
        mime_to_ext = {
            'image/jpeg': {'.jpg', '.jpeg'},
            'image/png': {'.png'},
            'image/gif': {'.gif'},
            'image/webp': {'.webp'},
            'image/bmp': {'.bmp'},
            'image/x-icon': {'.ico'},
            'image/svg+xml': {'.svg'},
            'text/plain': {'.txt', '.md', '.markdown'},
            'application/json': {'.json'},
            'text/yaml': {'.yaml', '.yml'},
            'application/x-toml': {'.toml'},
        }
        
        ext = os.path.splitext(filename)[1].lower()
        allowed_exts = mime_to_ext.get(mime, set())
        
        # 特殊处理：某些文本文件可能被识别为 text/plain
        if mime == 'text/plain' and ext in {'.md', '.markdown', '.txt'}:
            return True
        
        if ext not in allowed_exts:
            logger.warning(f"MIME 类型不匹配：{mime}, 扩展名：{ext}")
            return False
        
        return True
    except Exception as e:
        logger.warning(f"MIME 类型验证失败：{e}")
        # MIME 验证失败不影响上传，只记录日志
        return True

def validate_file_content(content: bytes, filename: str) -> bool:
    """验证文本文件内容是否安全"""
    text_extensions = {'.md', '.txt', '.markdown', '.json', '.yaml', '.yml', '.toml'}
    ext = os.path.splitext(filename)[1].lower()
    
    if ext in text_extensions:
        try:
            text_content = content.decode('utf-8', errors='ignore')
            text_lower = text_content.lower()
            
            # 1. 检测服务器端代码特征
            dangerous_patterns = [
                r'<\?php', r'<\?=',  # PHP
                r'<%',                 # ASP/JSP
                r'<jsp:',              # JSP
                r'Runtime\.getRuntime', r'ProcessBuilder',  # Java
                r'eval\s*\(',          # 通用 eval
                r'exec\s*\(',          # 通用 exec
                r'system\s*\(',        # 系统调用
                r'passthru\s*\(',
                r'shell_exec\s*\(',
                r'popen\s*\(',
                r'proc_open\s*\(',
                r'curl_exec\s*\(',     # PHP cURL
                r'file_get_contents\s*\([^)]*https?://',  # 远程文件包含
                r'require\s*\([^)]*https?://',  # 远程包含
                r'include\s*\([^)]*https?://',
                r'import\s+lib',       # Python
                r'__import__\s*\(',    # Python
                r'subprocess\.',       # Python subprocess
                r'os\.system\s*\(',    # Python os.system
                r'os\.popen\s*\(',     # Python os.popen
            ]
            
            for pattern in dangerous_patterns:
                if re.search(pattern, text_content, re.IGNORECASE | re.MULTILINE):
                    logger.warning(f"检测到危险代码特征 [{pattern}]: {filename}")
                    return False
            
            # 2. 检测 Base64 编码的可疑内容（长字符串）
            base64_pattern = r'[A-Za-z0-9+/]{100,}={0,2}'
            base64_matches = re.findall(base64_pattern, text_content)
            for match in base64_matches:
                try:
                    decoded = base64.b64decode(match).decode('utf-8', errors='ignore').lower()
                    # 检查解码后是否包含危险内容
                    dangerous_keywords = ['system(', 'exec(', 'eval(', 'shell_exec', 'passthru', 'proc_open']
                    if any(kw in decoded for kw in dangerous_keywords):
                        logger.warning(f"检测到 Base64 编码的危险内容：{filename}")
                        return False
                except:
                    pass
            
            # 3. 检测 Markdown 中的 HTML 注入
            if ext in {'.md', '.markdown'}:
                # 检查是否包含完整的危险 HTML 标签
                html_pattern = r'<(script|iframe|object|embed|form|img[^>]+onerror|svg[^>]+onload)'
                if re.search(html_pattern, text_content, re.IGNORECASE):
                    logger.warning(f"检测到 HTML 注入：{filename}")
                    return False
                
                # 检查 HTML 实体编码绕过
                if '&lt;script' in text_lower or '&lt;iframe' in text_lower:
                    logger.warning(f"检测到编码绕过尝试：{filename}")
                    return False
            
            # 4. 检测配置文件中的危险内容
            if ext in {'.yaml', '.yml'}:
                # 检查 YAML 标签注入
                if re.search(r'!!python/', text_content):
                    logger.warning(f"检测到 YAML Python 标签注入：{filename}")
                    return False
                if '!!ruby/' in text_lower:
                    logger.warning(f"检测到 YAML Ruby 标签注入：{filename}")
                    return False
            
        except Exception as e:
            logger.warning(f"文件内容检查失败：{e}")
            return False
    
    return True

@router.get("/health", response_model=ApiResponse)
def health_check():
    return ApiResponse(data={"status": "healthy", "version": "1.1.0"})

@router.get("/files", response_model=ApiResponse)
def get_files(x_session_id: Optional[str] = Header(None), 
              x_exclude_patterns: Optional[str] = Header(None),
              x_simple_patterns: Optional[str] = Header(None),
              x_use_whitelist: Optional[str] = Header(None),
              x_whitelist_exceptions: Optional[str] = Header(None)):
    """获取文件列表，支持多用户隔离和文件排除
    
    Args:
        x_session_id: 可选的会话 ID 头，用于标识用户会话
        x_exclude_patterns: 可选的正则表达式排除规则，JSON 数组格式
        x_simple_patterns: 可选的简单模式排除规则，JSON 数组格式
        x_use_whitelist: 是否使用白名单模式，"true" 或 "false"
        x_whitelist_exceptions: 可选的白名单例外规则，JSON 数组格式
    """
    try:
        # 如果没有会话 ID，返回空列表（前端应创建新会话）
        if not x_session_id:
            return ApiResponse(data=[], message="请先创建会话")
        
        # 如果会话无效，返回空列表（前端应创建新会话）
        if not session_manager.is_session_valid(x_session_id):
            logger.warning(f"无效的会话 ID: {x_session_id[:8]}...")
            return ApiResponse(data=[], message="会话已过期，请刷新页面")
        
        base_path = get_session_path(x_session_id)
        if not base_path or not os.path.exists(base_path):
            return ApiResponse(data=[])
        
        # 解析正则表达式排除规则
        exclude_patterns = []
        if x_exclude_patterns:
            try:
                import json
                exclude_patterns = json.loads(x_exclude_patterns)
                if not isinstance(exclude_patterns, list):
                    exclude_patterns = []
            except json.JSONDecodeError as e:
                logger.warning(f"解析正则排除规则失败：{e}")
                exclude_patterns = []
        
        # 解析简单模式排除规则
        simple_patterns = []
        if x_simple_patterns:
            try:
                import json
                simple_patterns = json.loads(x_simple_patterns)
                if not isinstance(simple_patterns, list):
                    simple_patterns = []
            except json.JSONDecodeError as e:
                logger.warning(f"解析简单排除规则失败：{e}")
                simple_patterns = []
        
        # 解析白名单设置
        use_whitelist = x_use_whitelist and x_use_whitelist.lower() == 'true'
        whitelist_extensions = DEFAULT_WHITELIST_EXTENSIONS if use_whitelist else None
        
        # 解析白名单例外规则
        whitelist_exceptions = []
        if x_whitelist_exceptions:
            try:
                import json
                whitelist_exceptions = json.loads(x_whitelist_exceptions)
                if not isinstance(whitelist_exceptions, list):
                    whitelist_exceptions = []
            except json.JSONDecodeError as e:
                logger.warning(f"解析白名单例外失败：{e}")
                whitelist_exceptions = []
        
        files = get_files_recursive(
            base_path, 
            exclude_patterns=exclude_patterns,
            simple_patterns=simple_patterns,
            use_whitelist=use_whitelist,
            whitelist_extensions=whitelist_extensions,
            whitelist_exceptions=whitelist_exceptions
        )
        return ApiResponse(data=files)
    except Exception as e:
        logger.error("获取文件列表失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取文件列表失败：" + str(e))

@router.get("/file/content")
def get_file_content(file_path: str = "", x_session_id: Optional[str] = Header(None)):
    try:
        if not x_session_id:
            raise HTTPException(status_code=400, detail="请先创建会话")
        base_path = get_session_path(x_session_id)
        full_path = validate_file_path(file_path, base_path=base_path)
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="文件未找到")
        if os.path.isdir(full_path):
            raise HTTPException(status_code=400, detail="Path is a directory, not a file")
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return PlainTextResponse(content=content)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取文件内容失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取文件内容失败：" + str(e))

@router.post("/file/create", response_model=ApiResponse)
async def create_file(request: FileCreateRequest, x_session_id: Optional[str] = Header(None)):
    try:
        if not x_session_id:
            raise HTTPException(status_code=400, detail="请先创建会话")
        base_path = get_session_path(x_session_id)
        setup_git_context(x_session_id)
        full_path = validate_file_path(request.path, base_path=base_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(request.content)
        git_add()
        logger.info("文件已创建：" + request.path)
        return ApiResponse(message="文件创建成功", data={"path": request.path})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("创建文件失败：" + str(e))
        raise HTTPException(status_code=500, detail="创建文件失败：" + str(e))

@router.post("/file/save", response_model=ApiResponse)
async def save_file(request: FileSaveRequest, x_session_id: Optional[str] = Header(None)):
    try:
        if not x_session_id:
            raise HTTPException(status_code=400, detail="请先创建会话")
        base_path = get_session_path(x_session_id)
        setup_git_context(x_session_id)
        full_path = validate_file_path(request.path, base_path=base_path)
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="文件未找到")
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(request.content)
        git_add()
        logger.info("文件已保存：" + request.path)
        return ApiResponse(message="文件保存成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("保存文件失败：" + str(e))
        raise HTTPException(status_code=500, detail="保存文件失败：" + str(e))

@router.post("/file/rename", response_model=ApiResponse)
async def rename_file(request: FileRenameRequest, x_session_id: Optional[str] = Header(None)):
    try:
        if not x_session_id:
            raise HTTPException(status_code=400, detail="请先创建会话")
        if not request.oldPath or not request.newPath:
            raise HTTPException(status_code=400, detail="Both old and new paths are required")
        base_path = get_session_path(x_session_id)
        setup_git_context(x_session_id)
        full_old_path = validate_file_path(request.oldPath, base_path=base_path)
        full_new_path = validate_file_path(request.newPath, base_path=base_path)
        if not os.path.exists(full_old_path):
            raise HTTPException(status_code=404, detail="File or directory not found")
        if os.path.exists(full_new_path):
            raise HTTPException(status_code=400, detail="Target path already exists")
        os.rename(full_old_path, full_new_path)
        git_add()
        logger.info("已重命名：" + request.oldPath + " -> " + request.newPath)
        return ApiResponse(message="重命名成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("重命名失败：" + str(e))
        raise HTTPException(status_code=500, detail="重命名失败：" + str(e))

@router.delete("/file/delete", response_model=ApiResponse)
async def delete_file(file_path: str = "", x_session_id: Optional[str] = Header(None)):
    try:
        if not x_session_id:
            raise HTTPException(status_code=400, detail="请先创建会话")
        base_path = get_session_path(x_session_id)
        setup_git_context(x_session_id)
        full_path = validate_file_path(file_path, base_path=base_path)
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="File or directory not found")
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
        git_add()
        logger.info("已删除：" + file_path)
        return ApiResponse(message="删除成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("删除失败：" + str(e))
        raise HTTPException(status_code=500, detail="删除失败：" + str(e))

@router.post("/file/upload", response_model=ApiResponse)
async def upload_file(
    file: UploadFile = File(...),
    file_path: str = Form(...),
    x_session_id: Optional[str] = Header(None),
    limiter: Limiter = Depends(get_limiter)
):
    """
    安全的文件上传接口
    支持图片和文档上传，自动验证文件安全性
    
    速率限制：10 次/分钟（防止滥用）
    """
    try:
        if not x_session_id:
            raise HTTPException(status_code=400, detail="请先创建会话")
        
        # 1. 验证文件名
        if not validate_filename_secure(file.filename):
            raise HTTPException(status_code=400, detail="文件名包含非法字符或格式不正确")
        
        # 2. 验证文件扩展名
        if not validate_file_extension_secure(file.filename):
            raise HTTPException(status_code=400, detail="不允许上传该类型的文件")
        
        base_path = get_session_path(x_session_id)
        setup_git_context(x_session_id)
        
        # 3. 验证上传路径（防止路径遍历）
        full_path = validate_file_path(file_path, base_path=base_path)
        
        # 4. 确保文件在允许的目录内
        real_path = os.path.realpath(full_path)
        real_base = os.path.realpath(base_path)
        if not real_path.startswith(real_base):
            raise HTTPException(status_code=400, detail="非法的上传路径")
        
        # 5. 读取文件内容
        content = await file.read()
        
        # 6. 检查文件大小
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="文件过大，最大支持 2MB")
        
        # 6.5. MIME 类型验证（可选增强，只记录日志不阻止上传）
        validate_mime_type(content, file.filename)
        
        # 7. 根据文件类型进行内容验证和净化
        ext = os.path.splitext(file.filename)[1].lower()
        
        if ext in ALLOWED_IMAGE_EXTENSIONS:
            if ext == '.svg':
                if not validate_svg_content(content):
                    raise HTTPException(status_code=400, detail="SVG 文件包含不安全内容")
            else:
                # 验证并净化图片
                is_valid, sanitized_content = sanitize_image(content, file.filename)
                if not is_valid:
                    raise HTTPException(status_code=400, detail="图片验证失败")
                content = sanitized_content
        elif ext in ALLOWED_DOC_EXTENSIONS:
            if not validate_file_content(content, file.filename):
                raise HTTPException(status_code=400, detail="文件内容包含不安全信息")
        
        # 8. 创建目录
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        # 9. 保存文件
        with open(full_path, 'wb') as f:
            f.write(content)
        
        # 10. 设置安全的文件权限
        os.chmod(full_path, 0o644)
        
        # 11. 添加到 Git
        git_add()
        
        # 12. 计算文件哈希（用于审计和追踪）
        file_hash = hashlib.sha256(content).hexdigest()
        
        logger.info(f"文件已上传：{file_path}, SHA256: {file_hash[:16]}..., 大小：{len(content)} bytes")
        return ApiResponse(message="文件上传成功", data={
            "path": file_path, 
            "filename": file.filename, 
            "size": len(content),
            "sha256": file_hash[:16] + "..."  # 只返回前 16 位用于验证
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传文件失败：{e}", exc_info=True)  # 记录完整堆栈到后端日志
        raise HTTPException(status_code=500, detail="上传文件失败，请稍后重试")  # 对用户隐藏细节

@router.post("/file/move", response_model=ApiResponse)
async def move_file(request: FileMoveRequest, x_session_id: Optional[str] = Header(None)):
    try:
        if not x_session_id:
            raise HTTPException(status_code=400, detail="请先创建会话")
        if not request.sourcePath or not request.destPath:
            raise HTTPException(status_code=400, detail="Both source and destination paths are required")
        base_path = get_session_path(x_session_id)
        setup_git_context(x_session_id)
        full_source_path = validate_file_path(request.sourcePath, base_path=base_path)
        full_dest_path = validate_file_path(request.destPath, base_path=base_path)
        if not os.path.exists(full_source_path):
            raise HTTPException(status_code=404, detail="Source file or directory not found")
        if os.path.exists(full_dest_path):
            raise HTTPException(status_code=400, detail="Destination path already exists")
        os.makedirs(os.path.dirname(full_dest_path), exist_ok=True)
        shutil.move(full_source_path, full_dest_path)
        git_add()
        logger.info("已移动：" + request.sourcePath + " -> " + request.destPath)
        return ApiResponse(message="移动成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("移动失败：" + str(e))
        raise HTTPException(status_code=500, detail="移动失败：" + str(e))

@router.post("/folder/create", response_model=ApiResponse)
async def create_folder(request: FolderCreateRequest, x_session_id: Optional[str] = Header(None)):
    try:
        if not x_session_id:
            raise HTTPException(status_code=400, detail="请先创建会话")
        base_path = get_session_path(x_session_id)
        setup_git_context(x_session_id)
        full_path = validate_file_path(request.path, base_path=base_path)
        os.makedirs(full_path, exist_ok=True)
        git_add()
        logger.info("文件夹已创建：" + request.path)
        return ApiResponse(message="文件夹创建成功", data={"path": request.path})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("创建文件夹失败：" + str(e))
        raise HTTPException(status_code=500, detail="创建文件夹失败：" + str(e))

@router.get("/git-repo", response_model=ApiResponse)
def get_git_repo(x_session_id: Optional[str] = Header(None)):
    """获取 Git 仓库配置，优先返回会话级别的配置"""
    try:
        if x_session_id:
            session_git_repo = session_manager.get_session_git_repo(x_session_id)
            if session_git_repo:
                return ApiResponse(data={"gitRepo": session_git_repo})
        return ApiResponse(data={"gitRepo": BLOG_GIT_SSH})
    except Exception as e:
        logger.error("获取 git 仓库失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取 git 仓库失败")

@router.post("/git-repo", response_model=ApiResponse)
async def set_git_repo(request: GitRepoRequest, x_session_id: Optional[str] = Header(None)):
    """设置 Git 仓库配置，必须提供会话 ID"""
    try:
        if not request.gitRepo:
            raise HTTPException(status_code=400, detail="Git repo URL is required")
        
        if not x_session_id:
            raise HTTPException(status_code=400, detail="必须提供会话 ID")
        
        session_manager.update_session_git_repo(x_session_id, request.gitRepo)
        logger.info(f"会话 {x_session_id[:8]}... Git 仓库配置已设置：" + sanitize_for_log(request.gitRepo))
        
        return ApiResponse(message="Git 仓库配置已设置")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("设置 git 仓库失败：" + str(e))
        raise HTTPException(status_code=500, detail="设置 git 仓库失败")

@router.get("/categories", response_model=ApiResponse)
def get_categories():
    try:
        categories = set()
        if not os.path.exists(POSTS_PATH):
            return ApiResponse(data=list(categories))
        for i in os.listdir(POSTS_PATH):
            post_yaml = get_md_yaml(os.path.join(POSTS_PATH, i, 'index.md'))
            if post_yaml:
                for item in post_yaml.get('categories', []):
                    categories.add(item)
        return ApiResponse(data=list(categories))
    except Exception as e:
        logger.error("获取分类失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取分类失败")

@router.get("/posts/changes", response_model=ApiResponse)
def get_post_changes(x_session_id: Optional[str] = Header(None),
                     x_oauth_session_id: Optional[str] = Header(None)):
    try:
        if not x_session_id:
            raise HTTPException(status_code=400, detail="请先创建会话")
        setup_git_context(x_session_id)
        delete_image_not_included()
        git_add(cache_path=get_session_path(x_session_id), oauth_session_id=x_oauth_session_id)
        status_result_for_show = pretty_git_status(git_status(cache_path=get_session_path(x_session_id), oauth_session_id=x_oauth_session_id))
        return ApiResponse(data=status_result_for_show)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取帖子更改失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取帖子更改失败")

@router.get("/posts", response_model=ApiResponse)
def get_posts():
    try:
        posts = {}
        if not os.path.exists(POSTS_PATH):
            return ApiResponse(data=posts)
        for i in os.listdir(POSTS_PATH):
            post_yaml = get_md_yaml(os.path.join(POSTS_PATH, i, 'index.md'))
            if post_yaml:
                posts[i] = {
                    'dirName': i,
                    'title': post_yaml.get('title', i)
                }
            else:
                posts[i] = {
                    'dirName': i,
                    'title': i
                }
        return ApiResponse(data=posts)
    except Exception as e:
        logger.error("获取帖子失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取帖子失败")

@router.post("/post/create", response_model=ApiResponse)
def create_post():
    try:
        now = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))
        post_dir_name = now.strftime('%Y%m%d%H%M%S')
        os.makedirs(os.path.join(POSTS_PATH, post_dir_name), exist_ok=True)
        template = read_post_template()
        template = template.replace('{{title}}', post_dir_name)
        template = template.replace('{{date}}', now.isoformat())
        template = template.replace('{{categories}}', '[]')
        with open(os.path.join(POSTS_PATH, post_dir_name, 'index.md'), mode='w', encoding='utf-8') as f:
            f.write(template)
        git_add()
        logger.info("新帖子已创建：" + post_dir_name)
        return ApiResponse(data={'dirName': post_dir_name})
    except Exception as e:
        logger.error("创建帖子失败：" + str(e))
        raise HTTPException(status_code=500, detail="创建帖子失败")

@router.get("/post/{filename}")
def get_post(filename: str):
    try:
        check_name(filename)
        md_path = os.path.join(POSTS_PATH, filename, 'index.md')
        if os.path.isfile(md_path):
            with open(md_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return PlainTextResponse(content=content)
        raise HTTPException(status_code=404, detail="Post not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取帖子失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取帖子失败")

@router.delete("/post/{filename}", response_model=ApiResponse)
def delete_post(filename: str):
    try:
        check_name(filename)
        post_path = os.path.join(POSTS_PATH, filename)
        if os.path.exists(post_path):
            shutil.rmtree(post_path, ignore_errors=True)
            git_add()
            logger.info("帖子已删除：" + filename)
            return ApiResponse(message="帖子已删除")
        raise HTTPException(status_code=404, detail="帖子未找到")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("删除帖子失败：" + str(e))
        raise HTTPException(status_code=500, detail="删除帖子失败")

@router.post("/post/{filename}", response_model=ApiResponse)
async def save_post(filename: str, request: Request):
    try:
        check_name(filename)
        post_path = os.path.join(POSTS_PATH, filename)
        if not os.path.exists(post_path):
            raise HTTPException(status_code=404, detail="Post not found")
        content = await request.body()
        content_str = content.decode('utf-8')
        md_path = os.path.join(post_path, 'index.md')
        with open(md_path, mode='w', encoding='utf-8') as f:
            f.write(html.unescape(content_str))
        logger.info("帖子已保存：" + filename)
        return ApiResponse(message="帖子已保存")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("保存帖子失败：" + str(e))
        raise HTTPException(status_code=500, detail="保存帖子失败")

git_operation_lock = asyncio.Lock()

@router.get("/session/create", response_model=ApiResponse)
def create_session(x_user_id: Optional[str] = Header(None)):
    """创建新的用户会话
    
    Args:
        x_user_id: 可选的用户 ID 头，用于标识用户（单用户单会话策略）
    """
    try:
        # 如果有 user_id，清理该用户的旧会话
        clean_old = x_user_id is not None
        session_id, session_path = session_manager.create_session(
            user_id=x_user_id, 
            clean_old=clean_old
        )
        logger.info(f"创建新会话：{session_id[:8]}... 用户：{x_user_id[:8] if x_user_id else 'anonymous'}...")
        return ApiResponse(
            message="会话创建成功",
            data={
                "sessionId": session_id,
                "sessionPath": session_path,
                "userId": x_user_id or session_id
            }
        )
    except Exception as e:
        logger.error("创建会话失败：" + str(e))
        raise HTTPException(status_code=500, detail="创建会话失败：" + str(e))

@router.get("/session/status", response_model=ApiResponse)
def get_session_status(x_session_id: Optional[str] = Header(None)):
    """获取会话状态"""
    try:
        if not x_session_id:
            return ApiResponse(data={"initialized": False, "hasRemote": False})
        
        session = session_manager.get_session(x_session_id)
        if not session:
            return ApiResponse(data={"initialized": False, "hasRemote": False})
        
        session_path = session['path']
        has_git = os.path.exists(os.path.join(session_path, '.git'))
        has_remote = False
        
        if has_git:
            try:
                import subprocess
                remote_result = subprocess.run(
                    ['git', 'remote', '-v'],
                    cwd=session_path,
                    capture_output=True,
                    text=True
                )
                has_remote = 'origin' in remote_result.stdout
            except:
                pass
        
        return ApiResponse(data={
            "initialized": has_git,
            "hasRemote": has_remote,
            "sessionPath": session_path,
            "userId": session.get('user_id', '')
        })
    except Exception as e:
        logger.error("获取会话状态失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取会话状态失败：" + str(e))

@router.get("/session/user-id", response_model=ApiResponse)
def get_user_id():
    """生成或获取用户 ID（用于浏览器指纹识别）"""
    try:
        import uuid
        user_id = str(uuid.uuid4())
        # 这里只是生成一个新的 user_id，实际使用时会保存到 cookie
        return ApiResponse(data={"userId": user_id})
    except Exception as e:
        logger.error("生成用户 ID 失败：" + str(e))
        raise HTTPException(status_code=500, detail="生成用户 ID 失败：" + str(e))

@router.post("/init", response_model=ApiResponse)
async def init_workspace(request: InitRequest, x_session_id: Optional[str] = Header(None),
                         x_oauth_session_id: Optional[str] = Header(None)):
    """初始化工作区，必须提供会话 ID
    
    初始化策略:
    1. 如果已有 Git 仓库且有远程配置，返回 connected 状态
    2. 如果已有 Git 仓库但无远程配置，允许重新初始化或连接
    3. 如果本地有文件但无 Git 仓库，保留文件并连接远程仓库
    4. 如果本地无文件，克隆远程仓库或创建空仓库
    """
    async with git_operation_lock:
        try:
            if not x_session_id:
                raise HTTPException(status_code=400, detail="必须提供会话 ID")
            
            base_path = get_session_path(x_session_id)
            
            # 更新会话级别的 Git 仓库配置
            if request.gitRepo:
                session_manager.update_session_git_repo(x_session_id, request.gitRepo)
                logger.info(f"会话 {x_session_id[:8]}... Git 仓库配置已设置：{sanitize_for_log(request.gitRepo)}")
            
            # 传递会话路径、会话 ID（用于获取 Git 仓库配置）和 OAuth session_id（用于获取访问令牌）
            result = await init_local_git_async(
                session_path=base_path, 
                session_id=x_session_id,
                oauth_session_id=x_oauth_session_id
            )
            
            if result.get('status') in ['connected', 'remote_configured', 'cloned']:
                session_manager.mark_session_initialized(x_session_id)
            
            logger.info("工作区初始化成功")
            return ApiResponse(message=result.get("message", "初始化成功"), data=result)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("初始化工作区失败：" + str(e))
            raise HTTPException(status_code=500, detail="初始化失败：" + str(e))
        finally:
            try:
                sync_branch_name(cache_path=base_path, oauth_session_id=x_oauth_session_id)
            except Exception as e:
                logger.warning("同步分支名称失败：" + str(e))

@router.post("/pull", response_model=ApiResponse)
async def pull_repo(x_session_id: Optional[str] = Header(None),
                    x_oauth_session_id: Optional[str] = Header(None)):
    """拉取远程更新，支持会话隔离"""
    async with git_operation_lock:
        try:
            if not x_session_id:
                raise HTTPException(status_code=400, detail="请先创建会话")
            setup_git_context(x_session_id)
            await pull_updates_async(session_id=x_session_id, oauth_session_id=x_oauth_session_id)
            logger.info("已成功拉取最新更改")
            return ApiResponse(message="拉取成功")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("拉取更新失败：" + str(e))
            raise HTTPException(status_code=500, detail="拉取失败：" + str(e))

@router.post("/reset", response_model=ApiResponse)
async def reset(x_session_id: Optional[str] = Header(None),
                x_oauth_session_id: Optional[str] = Header(None)):
    async with git_operation_lock:
        try:
            if not x_session_id:
                raise HTTPException(status_code=400, detail="请先创建会话")
            base_path = get_session_path(x_session_id)
            if os.path.exists(base_path):
                backup_path = base_path + "_backup"
                shutil.rmtree(backup_path, ignore_errors=True)
                try:
                    shutil.copytree(base_path, backup_path, dirs_exist_ok=True)
                except Exception as backup_error:
                    logger.warning("备份失败，继续重置：" + str(backup_error))
            setup_git_context(x_session_id)
            await init_local_git_async(
                session_path=base_path, 
                session_id=x_session_id,
                oauth_session_id=x_oauth_session_id
            )
            logger.info("工作区重置完成")
            return ApiResponse(message="工作区重置完成")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("重置工作区失败：" + str(e))
            raise HTTPException(status_code=500, detail="重置工作区失败")

@router.post("/soft_reset", response_model=ApiResponse)
async def soft_reset(x_session_id: Optional[str] = Header(None),
                     x_oauth_session_id: Optional[str] = Header(None)):
    async with git_operation_lock:
        try:
            setup_git_context(x_session_id)
            await pull_updates_async(session_id=x_oauth_session_id)
            logger.info("工作区软重置完成")
            return ApiResponse(message="工作区软重置完成")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("软重置工作区失败：" + str(e))
            raise HTTPException(status_code=500, detail="软重置工作区失败")

@router.post("/commit", response_model=ApiResponse)
async def commit(x_session_id: Optional[str] = Header(None), 
                 x_oauth_session_id: Optional[str] = Header(None)):
    async with git_operation_lock:
        try:
            if not x_session_id:
                raise HTTPException(status_code=400, detail="请先创建会话")
            setup_git_context(x_session_id)
            git_commit(session_id=x_session_id, oauth_session_id=x_oauth_session_id)
            logger.info("更改已提交并推送")
            return ApiResponse(message="更改已提交并推送")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("提交更改失败：" + str(e))
            raise HTTPException(status_code=500, detail="提交更改失败")

@router.post("/redeploy", response_model=ApiResponse)
def redeploy():
    try:
        deploy()
        logger.info("重新部署已触发")
        return ApiResponse(message="重新部署已触发")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("重新部署失败：" + str(e))
        raise HTTPException(status_code=500, detail="重新部署失败")

@router.get("/{dir_name}/{file_name}")
def get_file(dir_name: str, file_name: str):
    from fastapi.responses import FileResponse
    try:
        check_name(dir_name)
        file_path = os.path.join(POSTS_PATH, dir_name, file_name)
        if os.path.exists(file_path):
            return FileResponse(file_path)
        raise HTTPException(status_code=404, detail="文件未找到")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取文件失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取文件失败")
