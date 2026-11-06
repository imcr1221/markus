import os
import asyncio
import re
import json
from pathlib import Path
from bs4 import BeautifulSoup
import edge_tts

VOICE = "zh-CN-XiaoxiaoNeural"

async def process_module(module_dir: Path):
    html_file = module_dir / "index.html"
    if not html_file.exists():
        return

    print(f"\n📂 正在处理模块: {module_dir.name}")

    audio_dir = module_dir / "audio"
    audio_dir.mkdir(exist_ok=True)

    with open(html_file, "r", encoding="utf-8") as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, "html.parser")
    
    # ==========================================
    # 1. 智能提取文本（告别暴力正则）
    # ==========================================
    unique_texts = set()

    # 策略 A：优先提取专门写给 TTS 的 JSON 数据（强烈推荐的结构）
    tts_script = soup.find("script", id="tts-texts")
    if tts_script and tts_script.string:
        try:
            texts_list = json.loads(tts_script.string)
            for t in texts_list:
                if isinstance(t, str) and t.strip():
                    unique_texts.add(t.strip())
        except Exception as e:
            print(f"  ⚠️ 解析 tts-texts JSON 失败: {e}")

    # 策略 B：提取带有 data-tts-text 或 data-say 属性的标签
    for tag in soup.find_all(attrs={"data-tts-text": True}):
        unique_texts.add(tag["data-tts-text"].strip())
    for tag in soup.find_all(attrs={"data-say": True}):
        # 注意：data-say 里可能存的是 id 键值，如果是中文才加进去
        val = tag["data-say"].strip()
        if re.search(r'[\u4e00-\u9fa5]', val):
            unique_texts.add(val)

    # 策略 C：提取特定标签内的纯中文文本（如之前的 body/index.html）
    for tag in soup.find_all(['button', 'div', 'p', 'span', 'h1', 'h2', 'h3', 'label']):
        # 如果这个标签里面没有子标签，才提取它的纯文本，防止重复
        if not tag.find(True): 
            text = tag.get_text(strip=True)
            # 过滤：只保留包含中文，且长度在 2-50 之间的短句
            if re.search(r'[\u4e00-\u9fa5]', text) and 2 <= len(text) <= 50:
                # 排除掉乱码和UI文案
                if not text.startswith('http') and 'function' not in text:
                    unique_texts.add(text)

    unique_texts = list(unique_texts)
    print(f"  📝 提取到 {len(unique_texts)} 条需要生成的文本")

    manifest = {}
    
    # ==========================================
    # 2. 带缓存机制的生成逻辑
    # ==========================================
    for i, text in enumerate(unique_texts):
        # 使用稳定的 hash 命名，避免每次顺序变了文件名就变了
        import hashlib
        file_hash = hashlib.md5(text.encode('utf-8')).hexdigest()[:12]
        filename = f"tts_{file_hash}.mp3"
        
        output_path = audio_dir / filename
        manifest[text] = filename

        # 检查缓存：如果文件存在且大于 1000 字节，直接跳过！
        if output_path.exists() and output_path.stat().st_size > 1000:
            # print(f"  ⏭️ 已存在跳过: {filename}")
            continue

        print(f"  🔊 生成中: {filename} -> {text[:15]}...")
        try:
            # 语速调整：rate="-15%"
            communicate = edge_tts.Communicate(text, VOICE, rate="-15%")
            await asyncio.wait_for(communicate.save(output_path), timeout=15.0)
            
            if output_path.stat().st_size < 1000:
                print(f"  ⚠️ 警告: {filename} 文件过小，可能生成失败！")
                
        except Exception as e:
            print(f"  ❌ 单句失败: {text[:10]}... 错误: {e}")

    # ==========================================
    # 3. 安全地生成 tts-manifest.js
    # ==========================================
    manifest_path = audio_dir / "tts-manifest.js"
    # 使用 json.dumps 生成标准 JS 对象格式，ensure_ascii=False 保证中文不被转码
    js_content = f"window.TTS_AUDIO = {json.dumps(manifest, ensure_ascii=False, indent=2)};"
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(js_content)
    print(f"  ✅ 已更新 {manifest_path.name}")

async def main():
    root_dir = Path(".")
    tasks = []
    
    # 智能扫描所有包含 index.html 的子文件夹
    for item in root_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.') and item.name not in ['audio', 'assets', 'js', 'node_modules']:
            if (item / "index.html").exists():
                tasks.append(process_module(item))
            
    if not tasks:
        print("❌ 未找到任何包含 index.html 的模块目录。")
        return

    print(f"找到 {len(tasks)} 个模块，开始自动生成语音...")
    # return_exceptions=True 保证单个模块报错不会导致整个工作流崩溃
    await asyncio.gather(*tasks, return_exceptions=True)
    print("\n🎉 所有模块语音生成任务完成！")

if __name__ == "__main__":
    asyncio.run(main())
