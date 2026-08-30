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

1. 下载最新固件 Release 中的 ARMv8 rootfs，并用其 `SHA256SUMS` 校验。
2. 使用 `ophub/amlogic-s9xxx-openwrt` 打包为斐讯 N1 镜像并注入 `n1-overlay`。
3. 计算校验值并发布 GitHub Release。

## Rootfs 构建

只有升级 ImmortalWrt、feeds、PassWall 或其他 rootfs 组件时，才手动运行
`Build latest ImmortalWrt rootfs`。该工作流可能需要数小时，会在开始时解析所有
上游分支的最新 SHA，并在本次运行中保持不变。

新 rootfs 构建成功后会发布独立 Release，并自动触发快速 N1 打包。打包成功后，
新的固件 Release 会成为后续快速打包的默认 rootfs 来源，无需手动更新 URL 或 digest。
普通的无线 overlay、打包脚本或 Release 流程修改不会运行 rootfs 编译。

构建开始后会检查滚动 `packages` feed 的 Go 默认版本与实际目录是否一致。若上游
提交暂时缺少对应的 `golang1.x` 目录，脚本只在本次工作树中选择该 feed 可用的最高
版本，并将实际版本写入 `BUILD_INFO.txt`，避免上游原子提交窗口导致整轮编译失败。

## 构建环境镜像

编译依赖由仓库根目录的 `Dockerfile` 定义，并发布到：

```text
ghcr.io/biaogo94/cleanopenwrt-n1-builder:latest
```

修改 `Dockerfile`、`.dockerignore` 或镜像工作流后，GitHub Actions 会自动重建并发布
`latest` 镜像。独立 rootfs 工作流自动拉取最新 Builder，并把实际 digest 写入构建信息和
缓存 key；无需手动更新 digest。快速打包工作流不使用编译容器。

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
默认 rootfs 通过 `rootfs-lock.env` 指向 GitHub 最新固件 Release，校验值从同一 Release
的 `SHA256SUMS` 动态读取。

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
|-- scripts/build-immortalwrt.sh              # 源码、插件、配置和编译逻辑
|-- Dockerfile                                # Ubuntu 24.04 编译环境
`-- .dockerignore
```

`n1-overlay` 会在首次启动时修复 ophub 打包器对 `mac80211.sh` 的错误
`iw` → `ipconfig` 替换、补齐 N1 的 BCM43455 CLM 链接，并将默认 AP 信道设为 149。
它还会修复 PassWall 离线订阅的空 HTTP headers 异常，并关闭 HAProxy 包自带的
81/444/60000 示例监听；PassWall 自己生成的 HAProxy 配置不受影响。

`build-lock.env` 统一声明上游分支、Builder 镜像名称和 N1 内核大版本。rootfs 工作流
自动跟随这些分支的最新提交，但会记录实际 SHA、Builder digest 和 source-set ID，确保
单次构建可追溯；不同 source-set 或 Builder digest 使用不同缓存，避免跨版本污染。

## 致谢

- [ImmortalWrt](https://github.com/immortalwrt/immortalwrt)
- [OpenWrt PassWall](https://github.com/Openwrt-Passwall)
- [OpenClash](https://github.com/vernesong/OpenClash)
- [EasyTier](https://github.com/EasyTier/EasyTier)
- [ophub/amlogic-s9xxx-openwrt](https://github.com/ophub/amlogic-s9xxx-openwrt)

## 许可

本仓库采用 [Apache License 2.0](LICENSE)。上游源码、软件包和固件组件分别遵循其各自许可证。
