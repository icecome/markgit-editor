import hashlib
key = "my-secret-password"
print(f"密钥: {key}")
print(f"哈希值: {hashlib.sha256(key.encode()).hexdigest()}")
