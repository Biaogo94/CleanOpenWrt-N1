# CleanOpenWrt-N1

[![Build firmware](https://github.com/Biaogo94/CleanOpenWrt-N1/actions/workflows/build-imm.yaml/badge.svg)](https://github.com/Biaogo94/CleanOpenWrt-N1/actions/workflows/build-imm.yaml)
[![Build environment](https://github.com/Biaogo94/CleanOpenWrt-N1/actions/workflows/build-environment.yml/badge.svg)](https://github.com/Biaogo94/CleanOpenWrt-N1/actions/workflows/build-environment.yml)

面向斐讯 N1（Amlogic S905D）的 ImmortalWrt 自动构建项目。固件基于 `openwrt-25.12` 稳定分支，使用预构建的 GHCR 在线编译环境，并集成代理、组网和板载无线中继功能。

## 主要功能

- ImmortalWrt `openwrt-25.12` 分支，构建时获取最新提交
- 默认使用 6.12 系列内核，同时提供 6.1 和 6.18 选项
- PassWall 与简体中文界面
- OpenClash
- EasyTier 核心、LuCI 管理界面和简体中文翻译
- 晶晨宝盒（`luci-app-amlogic`），支持安装 OpenWrt 到 eMMC、系统更新和配置备份
- N1 板载 Broadcom BCM43455 Wi-Fi 支持，不依赖 USB 无线网卡
- Travelmate 路由/NAT 中继和 relayd 伪桥接支持
- `iperf3`、`iw`、`iwinfo`、`irqbalance` 等诊断与调优工具
- `dl` 下载缓存和 `ccache` 编译缓存
- 自动生成 SHA256 校验文件和 GitHub Release

## 在线构建

1. 打开仓库的 [Actions](https://github.com/Biaogo94/CleanOpenWrt-N1/actions) 页面。
2. 选择 `Build ImmortalWrt for Phicomm N1`。
3. 点击 `Run workflow`。
4. 选择内核系列，通常建议保持默认的 `6.12`。
5. 构建完成后，从 [Releases](https://github.com/Biaogo94/CleanOpenWrt-N1/releases) 下载固件和 `SHA256SUMS`。

构建分为三个阶段：

1. 在 GHCR 编译环境中生成 ImmortalWrt ARMv8 rootfs。
2. 使用 `ophub/amlogic-s9xxx-openwrt` 打包为斐讯 N1 镜像。
3. 计算校验值并发布 GitHub Release。

首次完整编译时间较长。后续构建会复用下载缓存和编译缓存，但源码或软件包发生较大变化时仍可能需要重新编译。

如果 rootfs 已成功、只有 N1 镜像打包或 Release 阶段失败，可以重新运行工作流，并在 `rootfs_run_id` 中填写上一次成功生成 rootfs 的 Actions Run ID。工作流会跳过源码编译，直接复用保留期内的 Artifact 完成打包。留空则执行正常的完整构建。

## 构建环境镜像

编译依赖由仓库根目录的 `Dockerfile` 定义，并发布到：

```text
ghcr.io/biaogo94/cleanopenwrt-n1-builder:latest
```

修改 `Dockerfile`、`.dockerignore` 或镜像工作流后，GitHub Actions 会自动重建并发布镜像。固件工作流会先拉取该镜像，再扩展工作空间并执行编译。

## 内核选择

| 内核系列 | 建议用途 |
| --- | --- |
| `6.12` | 默认推荐，长期支持与硬件兼容性较均衡 |
| `6.1` | 遇到新内核兼容问题时用于回退测试 |
| `6.18` | 测试较新的驱动和内核功能，升级前应先从 USB 启动验证 |

工作流选择的是内核系列，打包阶段会从内核仓库获取该系列的可用版本。实际版本会写入固件内的 `BUILD_INFO.txt`。

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

ImmortalWrt、PassWall、OpenClash 和 EasyTier OpenWrt 软件包默认跟随各自分支的最新提交，不锁定固定版本。因此，新版本能自动进入后续构建，但不同日期的产物可能不同。

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
|-- .github/workflows/build-imm.yaml          # 固件构建、打包和发布
|-- .github/workflows/build-environment.yml   # GHCR 编译环境发布
|-- scripts/build-immortalwrt.sh              # 源码、插件、配置和编译逻辑
|-- Dockerfile                                # Ubuntu 24.04 编译环境
`-- .dockerignore
```

`n1-overlay` 会在首次启动时修复 ophub 打包器对 `mac80211.sh` 的错误
`iw` → `ipconfig` 替换、补齐 N1 的 BCM43455 CLM 链接，并将默认 AP 信道设为 149。
它还会修复 PassWall 离线订阅的空 HTTP headers 异常，并关闭 HAProxy 包自带的
81/444/60000 示例监听；PassWall 自己生成的 HAProxy 配置不受影响。

构建依赖统一锁定在 `build-lock.env`。该锁文件包含 ImmortalWrt、feeds、PassWall、
OpenClash、EasyTier、Amlogic、Builder 镜像和 N1 内核版本。更新其中任意一项前，
应先完成一轮完整 rootfs 与 N1 镜像构建验证；工作流不会自动跟随上游最新提交。
当前锁定的内核为已验证的 `6.12.103`。

## 致谢

- [ImmortalWrt](https://github.com/immortalwrt/immortalwrt)
- [OpenWrt PassWall](https://github.com/Openwrt-Passwall)
- [OpenClash](https://github.com/vernesong/OpenClash)
- [EasyTier](https://github.com/EasyTier/EasyTier)
- [ophub/amlogic-s9xxx-openwrt](https://github.com/ophub/amlogic-s9xxx-openwrt)

## 许可

本仓库采用 [Apache License 2.0](LICENSE)。上游源码、软件包和固件组件分别遵循其各自许可证。
