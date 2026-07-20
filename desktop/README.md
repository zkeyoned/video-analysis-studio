# 视频分析台（macOS）

原生 SwiftUI 桌面端，调用上级目录中的 Python 视频分析工作流。

功能包括：

- 选择或拖入本地视频
- 粘贴抖音等视频链接并下载到本地知识库
- 原生视频预览和播放
- 配置抽帧间隔与最大帧数
- 通义千问、豆包、智谱 GLM 国内视觉接口预设
- 免费本地 Whisper 声音转写，并将同期台词交给视觉模型
- 讲解优先模式：先听完整语音，由 AI 按声音时间定向选择画面
- 报告、关键词、画面文字和逐段转写时间码点击跳转播放器
- 结构化关键词与完整声音转写查看
- 仅抽取关键帧，不需要 API Key
- 调用视觉模型完成 AI 分析
- 关键帧网格和时间戳查看
- 最近处理记录
- 按标题、作者、摘要、关键词和声音转写搜索知识库
- 原生设置窗口
- API Key 存储在 macOS 钥匙串中

## 构建和运行

```bash
cd "/absolute/path/to/video-agent/desktop"
./script/build_and_run.sh
```

验证应用进程：

```bash
./script/build_and_run.sh --verify
```

只构建、不打开窗口：

```bash
./script/build_and_run.sh --build-only
```

生成的应用位于：

```text
dist/视频分析台.app
```

无需 API Key 即可使用“只抽关键帧”。在应用的“设置”窗口中配置 Key 后，才能使用“开始 AI 分析”。

本地听觉首次使用前可双击上级目录的 `安装免费听觉模型.command`。安装过程不会自动开始，只有用户主动运行安装器才会安装 `whisper.cpp` 并下载模型。
