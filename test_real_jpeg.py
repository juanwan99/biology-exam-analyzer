#!/usr/bin/env python3
"""测试真实的JPEG图片上传"""
import os
import base64
from openai import OpenAI
from PIL import Image
import io

api_key = "sk-KNR6uS7DvEjWMHccFqLWJzRfxoahxyZKg9hWBHnsHLSiEAQK"
api_base = "https://www.chataiapi.com/v1"
model = "gemini-2.5-flash-preview-05-20-nothinking"

client = OpenAI(api_key=api_key, base_url=api_base)

# 创建一个真实的JPEG图片
print("创建真实的JPEG图片...")
img = Image.new('RGB', (100, 100), color='red')
buffer = io.BytesIO()
img.save(buffer, format='JPEG', quality=85)
jpeg_bytes = buffer.getvalue()
jpeg_b64 = base64.b64encode(jpeg_bytes).decode('utf-8')

print(f"JPEG图片大小: {len(jpeg_bytes)} bytes")
print(f"Base64长度: {len(jpeg_b64)}")
print(f"前50字符: {jpeg_b64[:50]}")

# 测试上传
try:
    response = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "What color is this image?"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{jpeg_b64}"}}
            ]
        }],
        max_tokens=100
    )
    print(f"✅ 成功: {response.choices[0].message.content}")
except Exception as e:
    print(f"❌ 失败: {e}")
