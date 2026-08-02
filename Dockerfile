FROM ubuntu:24.04

LABEL org.opencontainers.image.source="https://github.com/Biaogo94/CleanOpenWrt-N1"
LABEL org.opencontainers.image.description="ImmortalWrt build environment for Phicomm N1"

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Shanghai \
    CCACHE_DIR=/cache/ccache \
    CCACHE_MAXSIZE=3G \
    FORCE_UNSAFE_CONFIGURE=1

RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends \
      ack antlr3 asciidoc autoconf automake autopoint binutils bison \
      build-essential bzip2 ca-certificates ccache clang cmake cpio curl \
      device-tree-compiler fastjar file flex g++-multilib gawk gcc-multilib \
      gettext git gperf haveged help2man intltool jq libelf-dev libglib2.0-dev \
      libgmp-dev libltdl-dev libmpc-dev libmpfr-dev libncurses-dev \
      libpython3-dev libreadline-dev libssl-dev libtool lrzsz mkisofs msmtp \
      ninja-build p7zip-full patch pkgconf python3 python3-pip qemu-utils \
      rsync scons squashfs-tools subversion swig texinfo uglifyjs unzip \
      vim wget xmlto xxd zlib1g-dev zstd \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

CMD ["/bin/bash"]
