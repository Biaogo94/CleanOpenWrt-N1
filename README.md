# CleanOpenWrt-N1

[![Package firmware](https://github.com/Biaogo94/CleanOpenWrt-N1/actions/workflows/build-imm.yaml/badge.svg)](https://github.com/Biaogo94/CleanOpenWrt-N1/actions/workflows/build-imm.yaml)
[![Build rootfs](https://github.com/Biaogo94/CleanOpenWrt-N1/actions/workflows/build-rootfs.yaml/badge.svg)](https://github.com/Biaogo94/CleanOpenWrt-N1/actions/workflows/build-rootfs.yaml)
[![Build environment](https://github.com/Biaogo94/CleanOpenWrt-N1/actions/workflows/build-environment.yml/badge.svg)](https://github.com/Biaogo94/CleanOpenWrt-N1/actions/workflows/build-environment.yml)

面向斐讯 N1（Amlogic S905D）的 ImmortalWrt 自动构建项目。固件基于 `openwrt-25.12` 稳定分支，使用预构建的 GHCR 在线编译环境，并集成代理、组网和板载无线中继功能。

## 主要功能

- ImmortalWrt、feeds 和插件在 rootfs 构建开始时自动解析配置分支的最新提交
- 锁定 `6.12` 内核系列，N1 打包时自动选择该系列最新补丁版
- PassWall 与简体中文界面
- OpenClash
- EasyTier 核心、LuCI 管理界面和简体中文翻译
- 晶晨宝盒（`luci-app-amlogic`），支持安装 OpenWrt 到 eMMC、系统更新和配置备份
- N1 板载 Broadcom BCM43455 Wi-Fi 支持，不依赖 USB 无线网卡
- Travelmate 路由/NAT 中继和 relayd 伪桥接支持
- `iperf3`、`iw`、`iwinfo`、`irqbalance` 等诊断与调优工具
- `dl` 下载缓存和 `ccache` 编译缓存
- 自动生成 SHA256 校验文件和 GitHub Release

## 快速打包

1. 打开仓库的 [Actions](https://github.com/Biaogo94/CleanOpenWrt-N1/actions) 页面。
2. 选择 `Package Phicomm N1 firmware`。
3. 点击 `Run workflow`。
4. 通常保持 rootfs 输入为空，自动使用最新固件 Release 中的 rootfs 和校验清单。
5. 打包通常只需数分钟。完成后从 [Releases](https://github.com/Biaogo94/CleanOpenWrt-N1/releases) 下载固件和 `SHA256SUMS`。

快速打包只执行以下阶段：

1. 查询一次最新固件 Release，固定该 Release 的 tag 和资产 ID，再下载 ARMv8 rootfs 与同一 Release 的 `SHA256SUMS`；摘要和归档内容校验都通过才继续。
2. 使用 `ophub/amlogic-s9xxx-openwrt` 打包为斐讯 N1 镜像并注入 `n1-overlay`。
3. 计算校验值并发布 GitHub Release。

## Rootfs 构建

只有升级 ImmortalWrt、feeds、PassWall 或其他 rootfs 组件时，才手动运行
`Build latest ImmortalWrt rootfs`。该工作流可能需要数小时，会在开始时解析所有
上游分支的最新 SHA，并在本次运行中保持不变。

新 rootfs 构建成功后会发布独立 Release，并自动触发快速 N1 打包。打包成功后，
新的固件 Release 会成为后续快速打包的默认 rootfs 来源，无需手动更新 URL 或 digest。
普通的无线 overlay、打包脚本或 Release 流程修改不会运行 rootfs 编译。

构建会检查 `packages` feed 的 Go 默认版本、host 源码、实际安装目标和通用依赖是否一致。
若缺少默认 Go 版本，立即失败，不再猜测兼容性并回退到另一个版本。修复上游输入后，
重新进行升级构建；故障复盘则使用原输入重放。

### 快速检查与预检

`Fast build checks` 在相关 PR/push 时运行，也作为 rootfs 工作流的前置 job，
在拉取 Builder 和扩容之前检查 Shell、Actions 配置、锁文件和 Python 回归测试。

本地快速检查（Python 3.10+、Bash、ShellCheck、actionlint）：

```bash
bash scripts/check.sh
python3 -B -m unittest discover -s tests -v
actionlint
```

Windows Git Bash 可使用 `PYTHON=python bash scripts/check.sh`。真正的编译仍要求 Linux。

手动运行 rootfs 工作流时选择：

- `mode=preflight`：解析/重放输入、准备源码、冻结全部 feeds、重建索引、应用补丁、
  `make defconfig` 和必需功能/Go 依赖检查；不下载全部源码包、不编译、不发布。
  它需要联网准备源码，不等于几秒钟的离线检查。
- `mode=full`（默认）：同样的预检通过后才下载、编译、校验并发布。

Rust/EasyTier 补丁遇到未知上游结构会明确失败，避免静默打补丁无效。
预检不执行完整 Go 编译，不能代替最终编译器和业务包兼容性验证。

### 升级与输入重放

默认升级构建在开始时生成 `build-inputs.json`，包含本项目提交、构建文件摘要、
主源码/插件 SHA、全部实际 feeds（含 routing/telephony/video）、Builder digest、
EasyTier 二进制版本和 SHA256。源码按 SHA 获取；配置/补丁内容由构建文件摘要标识。
清单是严格校验的 JSON，不会被 `source` 或 `eval` 执行。

重放步骤：

1. 找到使用新流程运行的 rootfs run，下载其 `build-inputs` artifact。
2. 在**该清单记录的同一本项目提交**上运行工作流，填入 `replay_run_id`。
   可以使用指向该提交的分支/tag，工作流不会替你检出清单内任意代码。
3. 选择 `preflight` 或 `full`。清单、项目提交或构建文件摘要不匹配会失败；
   重放不重新查询上游最新分支、EasyTier digest 或 Builder latest。

Artifact 保存 30 天；成功的 rootfs Release 也保存清单。Artifact 过期后可下载
Release 的清单到本地，用相同项目提交及文件运行以下 Linux 命令：

```bash
python3 scripts/build_inputs.py validate --manifest build-inputs.json
builder="$(python3 -c 'import json; print(json.load(open("build-inputs.json"))["builder"])')"
docker pull "$builder"
mkdir -p .cache artifacts/diagnostics
python3 scripts/run-stage.py artifacts/diagnostics build docker run --rm \
  -e BUILD_MODE=preflight -e PYTHONDONTWRITEBYTECODE=1 \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory \
  -e GIT_CONFIG_VALUE_0=/workspace \
  -v "$PWD:/workspace" -v "$PWD/.cache:/cache" -w /workspace \
  "$builder" bash scripts/build-immortalwrt.sh
```

将 `BUILD_MODE` 改为 `full` 可完整编译。第一次本地升级可先拉取 Builder latest，
取 `docker image inspect` 返回的 RepoDigest，再运行
`python3 scripts/build_inputs.py resolve --builder IMAGE@sha256:DIGEST`。
旧版 r7 不含新清单，不能假装支持新协议重放。

这保证输入冻结与可追溯，不承诺逐字节相同；上游资源仍须可获取。快速打包仍按
6.12 系列选最新内核补丁版，**本次没有实现内核资产冻结或最终镜像精确重放**。

### 失败诊断与缓存

- 编译前单独上传 `build-inputs`；失败时仍上传 `build-diagnostics-RUN_ID`（14 天）。
- 诊断包含输入、阶段状态/耗时、最终配置、feeds、Go 选择、缓存恢复 key 和 ccache 统计。
- 阶段日志做令牌/Authorization/URL 脱敏，每个日志约 2 MiB 上限；不上传环境变量全集。
  未启动到相应阶段、任务强制取消或 runner 故障时，诊断可能不完整。
- 失败或未校验 rootfs 不进入正式发布；暂不自动上传可能很大的失败固件。
- `.cache/dl`、`.cache/go-mod`、`.cache/ccache` 分开保存。Go 路径通过 make 变量覆盖，
  不修改 upstream cache 代码。下载/Go 缓存保守绑定输入集，ccache 保留兼容性键。
- 不再按 `<1024 字节` 删除下载文件，也不自动清空缓存。普通源码由 OpenWrt 下载器
  校验；已存在的 Go 模块缓存有疑点时应定向排查，不能声称所有缓存都已重新验证。
- 对**已知可信 SHA256 的一个缓存文件**可运行：
  `python3 scripts/verify-cache.py .cache/dl RELATIVE_PATH EXPECTED_SHA256`。
  加 `--evict-corrupt` 仅删除摘要不匹配的指定文件（仍返回非零，表示需重新下载）；
  路径越界或 symlink 被拒绝。不要把它用于任意扫描删除。

性能收益应根据冷/热缓存和阶段耗时对比，本项目不预先承诺提速比例。

## 构建环境镜像

编译依赖由仓库根目录的 `Dockerfile` 定义，并发布到：

```text
ghcr.io/biaogo94/cleanopenwrt-n1-builder:latest
```

修改 `Dockerfile`、`.dockerignore` 或镜像工作流后，GitHub Actions 会自动重建并发布
`latest` 镜像。升级构建自动解析 Builder digest，并直接以 `image@sha256:...` 启动容器；
重放只拉取清单记录的 digest。快速打包工作流不使用编译容器。

## 内核版本

默认 N1 打包锁定 `build-lock.env` 中的 `6.12` 系列，并由 ophub 在该系列中选择最新
可用补丁版。若要切换到其他大版本，需要修改配置并重新完成打包与启动测试。
实际版本会写入固件内的 `BUILD_INFO.txt`。

## 无线中继

本项目只使用 N1 板载 BCM43455，不包含 USB 无线网卡驱动方案。

推荐优先使用 Travelmate 的路由/NAT 中继模式：上游 Wi-Fi 作为 WAN，N1 的有线接口或无线 AP 作为 LAN。需要上下游设备处于同一网段时，可以使用 relayd 伪桥接，但排障和稳定性通常不如路由模式。

板载单无线芯片同时连接上游并提供 AP 时需要共享信道，实际吞吐量通常会明显低于单独作为客户端或 AP。建议：

- 优先连接信号稳定的 5 GHz 上游网络
- 中国监管域下，当前 BCM43455 固件应优先使用 149、153、157 或 161 信道；实测 36–144 信道可能被固件拒绝
- 若上游 5 GHz 路由器固定在 36–144 信道，请先将上游改到 149–161，再由 Travelmate 建立连接
- 将 N1 放置在上游信号较强、通风良好的位置
- 使用 `iwinfo` 查看信号、速率和信道，使用 `iperf3` 测试局域网实际吞吐量
- 不要仅依据测速网站判断无线性能，先排除上游宽带和代理节点影响

## 版本与完整性

`build-lock.env` 只固定上游分支和内核大版本。每次 rootfs 构建开始时解析 ImmortalWrt、
feeds、PassWall、OpenClash、EasyTier 和 Amlogic 的最新 SHA，并在该次运行中冻结。
默认打包通过 GitHub API 固定本仓库最新正式固件 Release，校验值从该固定 Release
的 `SHA256SUMS` 读取；`rootfs-lock.env` 保留为旧版配置参考，不再用于运行时解析。
显式 URL 覆盖仍要求 SHA256。`rootfs-source.json` 记录来源；可能含凭据或签名的
自定义 URL 不写入发布元数据，仅保留摘要。

每次构建会在 `BUILD_INFO.txt` 中记录：

- ImmortalWrt、PassWall、OpenClash 和 EasyTier OpenWrt 的实际 Git 提交
- EasyTier 实际版本和 aarch64 发布包 SHA256
- 构建环境镜像及其 digest
- 请求和实际使用的内核版本

EasyTier 二进制在解压前会根据 GitHub Release 提供的 SHA256 digest 进行校验。下载固件后，请继续使用 Release 中的 `SHA256SUMS` 校验最终文件。

## 安装提示

- 首次使用建议先写入 USB 存储设备并完成启动、网络和插件测试
- 写入 eMMC 前务必备份原系统和重要数据
- 从 USB 启动并确认运行正常后，可进入 `系统 → 晶晨宝盒 → 安装 OpenWrt`，设备选择斐讯 N1
- 默认管理地址通常为 `http://192.168.1.1`
- 默认用户名为 `root`，首次登录后应立即设置强密码
- 刷写、更新内核或写入 eMMC 均存在设备无法启动和数据丢失风险

## 项目结构

```text
.
|-- .github/workflows/build-imm.yaml          # 快速 N1 打包和发布
|-- .github/workflows/build-rootfs.yaml       # 独立、手动的慢速 rootfs 构建
|-- .github/workflows/build-environment.yml   # GHCR 编译环境发布
|-- build-lock.env                            # 上游分支、Builder 名称与内核大版本
|-- rootfs-lock.env                           # 最新 Release rootfs 与校验清单地址
|-- .github/workflows/check.yml              # 离线快速检查及可复用 CI
|-- scripts/build-immortalwrt.sh              # 构建编排、补丁与配置
|-- scripts/build_inputs.py                  # 严格输入清单、解析、重放
|-- scripts/compile-rootfs.sh                # 预检/完整编译共用入口
|-- scripts/preflight.py                     # 有效配置、Go 安装依赖校验
|-- scripts/validate-rootfs.py               # 不解压的归档内容/完整性校验
|-- scripts/resolve-rootfs.py                # 固定 Release 与校验清单
|-- scripts/run-stage.py                    # 脱敏日志、退出状态与耗时
|-- scripts/verify-cache.py                  # 单文件摘要验证/定向清理
|-- tests/                                  # 生产接口回归测试
|-- Dockerfile                                # Ubuntu 24.04 编译环境
`-- .dockerignore
```

`n1-overlay` 会在首次启动时修复 ophub 打包器对 `mac80211.sh` 的错误
`iw` → `ipconfig` 替换、补齐 N1 的 BCM43455 CLM 链接，并将默认 AP 信道设为 149。
它还会修复 PassWall 离线订阅的空 HTTP headers 异常，并关闭 HAProxy 包自带的
81/444/60000 示例监听；PassWall 自己生成的 HAProxy 配置不受影响。

`build-lock.env` 统一声明上游分支、Builder 镜像名称和 N1 内核大版本。rootfs 工作流
自动跟随这些分支的最新提交，但会记录实际 SHA、Builder digest 和 source-set ID，确保
单次构建可追溯；下载/Go 缓存绑定输入集，编译缓存按 Builder 和兼容性键复用。
现有自动 rootfs 发布、自动 N1 打包和 Latest 策略保持不变；CI 成功不等于实机验收。

## 致谢

- [ImmortalWrt](https://github.com/immortalwrt/immortalwrt)
- [OpenWrt PassWall](https://github.com/Openwrt-Passwall)
- [OpenClash](https://github.com/vernesong/OpenClash)
- [EasyTier](https://github.com/EasyTier/EasyTier)
- [ophub/amlogic-s9xxx-openwrt](https://github.com/ophub/amlogic-s9xxx-openwrt)

## 许可

本仓库采用 [Apache License 2.0](LICENSE)。上游源码、软件包和固件组件分别遵循其各自许可证。
