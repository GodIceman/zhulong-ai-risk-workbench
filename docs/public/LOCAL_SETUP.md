# 本地安装与运行

> 当前已验证平台为 Windows 11。完整模型环境体积较大，首次安装前请预留至少 20 GB 磁盘空间。

## 1. 准备环境

- Git
- Node.js 20.19+
- Python 3.11
- [uv](https://docs.astral.sh/uv/)
- 可选：兼容 CUDA 12.8 的 NVIDIA GPU

确认命令可用：

```powershell
git --version
node --version
npm --version
python --version
uv --version
```

## 2. 获取源码

```powershell
git clone https://github.com/GodIceman/zhulong-ai-risk-workbench.git
Set-Location zhulong-ai-risk-workbench
```

## 3. 安装轻量 API 环境

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_venv.ps1
```

该脚本创建 `.venv-lrfimd` 并安装统一 API 及策略测试所需的轻量依赖。

## 4. 安装模型环境

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_video_forensics.ps1
```

该脚本会：

1. 创建 `.venv-video-forensics`；
2. 安装 PyTorch、Transformers、OpenCV 等依赖；
3. 从上游仓库获取并校验固定版本的 AEGIS 和 D3 代码；
4. 下载并核对 AEGIS checkpoint 的 SHA-256。

WaveRep 不在默认运行链中。只有进行可复现的非商业研究对比时，才使用 `-IncludeWaveRepCandidate`；其上游许可证禁止未授权的商业使用。

## 5. 安装前端

```powershell
Set-Location zhulong
npm ci
Set-Location ..
```

## 6. 启动

```powershell
./start.bat
```

等待终端显示各模型就绪，然后打开：

```text
http://127.0.0.1:3000/#/login
```

推荐使用“游客登录”进入工作台。本地注册数据只存在浏览器 IndexedDB 中，不是服务端账号系统。

## 7. 验证

```powershell
Set-Location zhulong
npm run build
Set-Location ..
./.venv-lrfimd/Scripts/python.exe -m unittest discover -s tests -v
```

模型运行时测试只有在对应权重和环境完整可用时才有意义。

## 常见问题

- **模型长时间未就绪**：首次下载可能需要数分钟；检查网络、可用磁盘和 `logs/` 中的本地日志。
- **CUDA 不可用**：确认驱动与 PyTorch CUDA 版本兼容。部分流程会回退 CPU，但速度会明显变慢。
- **端口占用**：关闭占用 `3000`、`5002`、`5003` 或 `5004` 的旧进程后重试。
- **商业使用**：主仓库为 MIT 不等于所有模型和数据均可商用；先阅读 `THIRD_PARTY_NOTICES.md`。
