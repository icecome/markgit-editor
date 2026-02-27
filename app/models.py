from pydantic import BaseModel
from typing import Optional, Any

class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Optional[Any] = None

class FileCreateRequest(BaseModel):
    path: str
    content: str = ""

class FileSaveRequest(BaseModel):
    path: str
    content: str

class FileRenameRequest(BaseModel):
    oldPath: str
    newPath: str

class FileMoveRequest(BaseModel):
    sourcePath: str
    destPath: str

class FolderCreateRequest(BaseModel):
    path: str

class GitRepoRequest(BaseModel):
    gitRepo: str

class InitRequest(BaseModel):
    gitRepo: str = ""
