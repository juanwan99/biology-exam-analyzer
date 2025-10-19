import os
import sys

# 加载环境变量
api_key = "AIzaSyC9zMNPpF1dKQE082_Crna389enWW4X4Us"

print("=" * 50)
print("Gemini API 连接测试")
print("=" * 50)
print(f"\n🔑 API Key: {api_key[:20]}...{api_key[-4:]}")

try:
    import google.generativeai as genai
    print("✅ google-generativeai 库已安装")
except ImportError:
    print("❌ 缺少依赖，正在安装...")
    os.system("pip install google-generativeai -q")
    import google.generativeai as genai

# 配置API
genai.configure(api_key=api_key)
print("✅ API Key 已配置")

# 测试基础调用
try:
    print("\n📡 测试 Gemini 连接...")
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content("请用一句话介绍生物学")

    print("✅ Gemini 连接成功！")
    print(f"\n📝 测试响应:\n{response.text}")

    # 测试JSON返回
    print("\n" + "=" * 50)
    print("测试 JSON 格式返回")
    print("=" * 50)

    json_response = model.generate_content("""
请返回纯JSON格式（不要markdown代码块）：
{
    "test": "生物学",
    "result": "成功"
}
""")

    print(f"\n原始返回:\n{json_response.text}")

    # 尝试解析JSON
    import json
    try:
        parsed = json.loads(json_response.text)
        print(f"\n✅ JSON 解析成功: {parsed}")
    except json.JSONDecodeError:
        print("\n⚠️  返回内容不是纯JSON，可能需要调整Prompt")

    print("\n" + "=" * 50)
    print("✅ 所有测试通过！可以启动服务")
    print("=" * 50)
    sys.exit(0)

except Exception as e:
    print(f"\n❌ 错误: {str(e)}")
    print("\n可能的原因:")
    print("1. API Key 无效或已过期")
    print("2. 网络连接问题")
    print("3. API 配额已用完")
    sys.exit(1)
