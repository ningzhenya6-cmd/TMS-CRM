#!/bin/bash
# ============================================================
# 留学课业AI引擎 - 云服务器部署脚本
# 使用方法：
#   1. 在本机打包:  bash deploy/pack.sh
#   2. 上传到服务器: scp study-ai.tar.gz root@你的服务器IP:/opt/
#   3. 在服务器上:   ssh root@你的服务器IP
#                    cd /opt && tar xzf study-ai.tar.gz
#                    bash study-ai/deploy/setup.sh
# ============================================================
set -e
echo "请在本地先运行 deploy/pack.sh 打包，然后上传到服务器运行 setup.sh"
