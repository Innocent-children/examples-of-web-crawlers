import requests
import re
import json
import subprocess
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import unicodedata
import platform

# 输入cookie以获取更优画质的视频，默认下载最优画质。
headers = {
        'cookie': '',
        'referer': 'https://www.bilibili.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
    }
def get_response(html_url):
    response = requests.get(url=html_url, headers=headers)
    return response


def get_response(html_url):
    response = requests.get(url=html_url, headers=headers)
    return response

def sanitize_filename(name):
    # 移除 Windows 不允许的字符
    name = re.sub(r'[\\/:*?"<>|]', '', name)
    # 移除控制字符、emoji等不可见字符
    name = ''.join(c for c in name if unicodedata.category(c)[0] != 'C' and not unicodedata.name(c, '').startswith('EMOJI'))
    return name.strip()[:100]

def get_info(html_url):
    response = get_response(html_url)
    # 提取标题
    title_match = re.search(r'<title[^>]*>(.*?)</title>', response.text)
    if title_match:
        raw_title = title_match.group(1)
        title = raw_title.split('_')[0].strip()
        title = sanitize_filename(title)
    else:
        title = 'bili_video'

    # 先尝试普通方式
    playinfo_match = re.findall(r'window\.__playinfo__=(\{.*?\})</script>', response.text)
    if playinfo_match:
        json_data = json.loads(playinfo_match[0])
        data = json_data.get("data")
    else:
        # 检查是不是 bangumi/ep 页面
        ep_match = re.search(r'/ep(\d+)', html_url)
        if not ep_match:
            raise Exception("未找到视频信息，无法解析。")
        ep_id = ep_match.group(1)
        api_url = f"https://api.bilibili.com/pgc/player/web/playurl?ep_id={ep_id}&qn=80&fnval=4048"
        api_response = requests.get(api_url, headers=headers)
        json_data = api_response.json()
        if json_data.get('code') != 0:
            raise Exception("番剧接口返回异常，无法下载。")
        # 关键处：番剧接口返回的是 result 字段
        data = json_data.get("result")
    if not data:
        raise Exception("未找到视频流信息。")

    # 优先使用 dash 流
    if "dash" in data:
        dash = data["dash"]
        audio_url = dash['audio'][0]['baseUrl']
        video_url = dash['video'][0]['baseUrl']
    # 兼容部分没有 dash 的番剧（有些接口只返回 durl）
    elif "durl" in data:
        # 这里只能下载合成流（无独立音频）
        video_url = data["durl"][0]["url"]
        audio_url = video_url    # 没有独立音频
    else:
        raise Exception("未找到视频流（dash/durl）信息。")
    return [title, audio_url, video_url]


def download_content(url, filepath, progress_callback=None):
    with requests.get(url, headers=headers, stream=True) as r:
        total = int(r.headers.get('content-length', 0))
        with open(filepath, 'wb') as f:
            downloaded = 0
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback:
                        progress_callback(downloaded, total)


def save(title, audio_url, video_url, update_progress):
    audio_path = f"{title}_only.mp3"
    video_path = f"{title}_only.mp4"

    update_progress("下载音频...", 0)
    download_content(audio_url, audio_path, lambda d, t: update_progress("下载音频中...", int(d / t * 25)))

    update_progress("下载视频...", 25)
    download_content(video_url, video_path, lambda d, t: update_progress("下载视频中...", 25 + int(d / t * 50)))

    return audio_path, video_path


def merge_data(title, update_progress):
    os.makedirs("video", exist_ok=True)
    # 检测 ffmpeg 路径
    ffmpeg_path = get_ffmpeg_path()
    command = f'"{ffmpeg_path}" -y -i "{title}_only.mp4" -i "{title}_only.mp3" -c:v copy -c:a aac -strict experimental "./video/{title}.mp4"'
    update_progress("合并音视频...", 90)
    # 使用 errors='ignore' 或 errors='replace' 来处理编码错误
    result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode != 0:
        error_msg = f"FFmpeg 错误: {result.stderr}"
        print(error_msg)
        # 在GUI中显示错误
        messagebox.showerror("错误", "音视频合并失败")
        return False  # 返回失败状态
    update_progress("完成", 100)
    os.remove(f'{title}_only.mp3')
    os.remove(f'{title}_only.mp4')
    return True  # 返回成功状态

def get_ffmpeg_path():
    project_dir = os.path.dirname(__file__)
    if platform.system() == 'Windows':
        ffmpeg_exe = 'ffmpeg.exe'
    else:
        ffmpeg_exe = 'ffmpeg'

    project_ffmpeg = os.path.join(project_dir, 'ffmpeg', 'bin', ffmpeg_exe)
    if os.path.exists(project_ffmpeg):
        return project_ffmpeg
    return ffmpeg_exe


# GUI部分
def start_download():
    url = url_entry.get()
    if not url:
        messagebox.showerror("错误", "请输入URL！")
        return

    def run():
        try:
            # 动态设置cookie
            headers['cookie'] = cookie_entry.get().strip()

            download_button.config(state="disabled")
            progress_label.config(text="解析中...")
            progress_bar["value"] = 0

            video_info = get_info(url)
            audio_path, video_path = save(video_info[0], video_info[1], video_info[2], update_progress)
            merge_data(video_info[0], update_progress)
            messagebox.showinfo("完成", "下载完成！视频已保存在 ./video 文件夹。")
        except Exception as e:
            messagebox.showerror("错误", f"出错了：{str(e)}")
        finally:
            download_button.config(state="normal")

    threading.Thread(target=run).start()


def update_progress(text, percent):
    progress_label.config(text=text)
    progress_bar["value"] = percent
    root.update_idletasks()


# 创建窗口
root = tk.Tk()
root.title("B站视频下载器")
root.geometry("400x250")

tk.Label(root, text="请输入B站视频URL：").pack(pady=5)

url_entry = tk.Entry(root, width=50)
url_entry.pack(pady=5)

tk.Label(root, text="（可选）请输入B站 Cookie：").pack(pady=5)
cookie_entry = tk.Entry(root, width=50)
cookie_entry.pack(pady=5)

download_button = tk.Button(root, text="下载", command=start_download)
download_button.pack(pady=5)

progress_label = tk.Label(root, text="")
progress_label.pack()

progress_bar = ttk.Progressbar(root, orient="horizontal", length=300, mode="determinate")
progress_bar.pack(pady=10)

root.mainloop()

