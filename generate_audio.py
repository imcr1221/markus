import os
import asyncio
import re
from pathlib import Path
import edge_tts

VOICE = "zh-CN-XiaoxiaoNeural"

async def process_module(module_dir: Path):
    html_file = module_dir / "index.html"
    if not html_file.exists():
        return

    print(f"\n📂 正在处理模块: {module_dir.name}")

    audio_dir = module_dir / "audio"
    audio_dir.mkdir(exist_ok=True)

    # 1. 直接读取整个 HTML 文件的文本
    with open(html_file, "r", encoding="utf-8") as f:
        html_content = f.read()

    # 2. 使用正则表达式，暴力提取所有包含中文的片段（长度大于1的）
    # 这会把 HTML 正文、JS 数组里的词全部抓出来
    raw_texts = re.findall(r'[\u4e00-\u9fa5，。？！、：；a-zA-Z0-9]{2,}', html_content)
    
    # 去重并过滤掉纯英文代码
    unique_texts = []
    for t in raw_texts:
        t = t.strip()
        # 必须包含中文字符才生成
        if re.search(r'[\u4e00-\u9fa5]', t) and t not in unique_texts:
            unique_texts.append(t)

    manifest = {}
    
    # 每次重新生成前，先清空旧的音频（防止静音陷阱）
    for old_file in audio_dir.glob("*.mp3"):
        try:
            old_file.unlink()
        except:
            pass

    for i, text in enumerate(unique_texts):
        # 控制文件名长度，防止名字过长报错
        filename = f"line_{i}.mp3"
        output_path = audio_dir / filename
        manifest[text] = filename

        print(f"  🔊 生成中: {filename} -> {text[:15]}...")
        try:
            # 设置语速
            communicate = edge_tts.Communicate(text, VOICE, rate="-25%")
            await asyncio.wait_for(communicate.save(output_path), timeout=15.0)
            
            if output_path.stat().st_size < 1000:
                print(f"  ⚠️ 警告: {filename} 文件过小！")
                
        except Exception as e:
            print(f"  ❌ 单句失败: {text[:10]}... 错误: {e}")

    # 生成 manifest
    manifest_path = audio_dir / "tts-manifest.js"
    js_content = f"window.TTS_AUDIO = {repr(manifest)};"
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(js_content)
    print(f"  ✅ 已更新 {manifest_path.name}")

async def main():
    root_dir = Path(".")
    tasks = []
    for item in root_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.') and item.name not in ['audio', 'assets', 'js', '10transport']:
            tasks.append(process_module(item))
            
    # 特别处理 10transport (以防它被上面的过滤规则漏掉，这里显式加上)
    tasks.append(process_module(Path("10transport")))
            
    if not tasks:
        print("未找到任何包含 index.html 的模块目录。")
        return

    print(f"找到 {len(tasks)} 个模块，开始自动生成语音...")
    await asyncio.gather(*tasks, return_exceptions=True)
    print("\n🎉 所有模块语音生成任务完成！")

if __name__ == "__main__":
    asyncio.run(main())
