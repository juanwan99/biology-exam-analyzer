#!/usr/bin/env python3
"""测试Gemini API调用"""
import os
import base64
from openai import OpenAI

# 读取环境变量
api_key = "sk-KNR6uS7DvEjWMHccFqLWJzRfxoahxyZKg9hWBHnsHLSiEAQK"
api_base = "https://www.chataiapi.com/v1"
model = "gemini-2.5-flash-preview-05-20-nothinking"

print(f"API Key: {api_key[:15]}...")
print(f"API Base: {api_base}")
print(f"Model: {model}\n")

# 创建客户端
client = OpenAI(api_key=api_key, base_url=api_base)

# 测试1：简单文本
print("=" * 60)
print("测试1：简单文本请求")
print("=" * 60)
try:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Say hello"}],
        max_tokens=50
    )
    print(f"✅ 成功: {response.choices[0].message.content}")
    print(f"   finish_reason: {response.choices[0].finish_reason}")
    print(f"   tokens: {response.usage.total_tokens}\n")
except Exception as e:
    print(f"❌ 失败: {e}\n")

# 测试2：文本+小图片
print("=" * 60)
print("测试2：文本 + 小图片（1KB）")
print("=" * 60)
small_img = b'\x89PNG\r\n\x1a\n' + (b'\x00' * 1000)
small_b64 = base64.b64encode(small_img).decode('utf-8')

try:
    response = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image?"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{small_b64}"}}
            ]
        }],
        max_tokens=100
    )
    print(f"✅ 成功: {response.choices[0].message.content[:100]}...")
    print(f"   finish_reason: {response.choices[0].finish_reason}")
    print(f"   tokens: {response.usage.total_tokens}\n")
except Exception as e:
    print(f"❌ 失败: {e}\n")

# 测试3：文本+大图片（200KB）
print("=" * 60)
print("测试3：文本 + 大图片（200KB）")
print("=" * 60)
large_img = b'\x89PNG\r\n\x1a\n' + (b'\x00' * (200 * 1024))
large_b64 = base64.b64encode(large_img).decode('utf-8')

try:
    response = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{large_b64}"}}
            ]
        }],
        max_tokens=100
    )
    print(f"✅ 成功: {response.choices[0].message.content[:100]}...")
    print(f"   finish_reason: {response.choices[0].finish_reason}")
    print(f"   tokens: {response.usage.total_tokens}\n")
except Exception as e:
    print(f"❌ 失败: {e}\n")

print("=" * 60)
print("测试完成")
print("=" * 60)
