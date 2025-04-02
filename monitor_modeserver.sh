#!/bin/bash

# 脚本日志文件路径（用于记录脚本本身的运行状态）
SCRIPT_LOG_FILE="./monitor_modelpool.log"
# Python 脚本路径（与脚本同目录）
PYTHON_SCRIPT="./modelpool_Servicer.py"
# PID 文件路径（与脚本同目录）
PID_FILE="./modelpool_service.pid"
# 监控脚本自身的 PID 文件
MONITOR_PID_FILE="./monitor_modelpool.pid"

# 记录日志的函数（仅用于脚本状态）
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$SCRIPT_LOG_FILE"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"  # 同时输出到终端，便于调试
}

# 清理旧进程
cleanup_old_processes() {
    log "Cleaning up old processes..."
    CURRENT_PID=$$

    # 检查并清理旧的 monitor_modelpool.sh 进程
    if [ -f "$MONITOR_PID_FILE" ]; then
        OLD_MONITOR_PID=$(cat "$MONITOR_PID_FILE")
        if [ "$OLD_MONITOR_PID" != "$CURRENT_PID" ] && ps -p "$OLD_MONITOR_PID" > /dev/null 2>&1; then
            log "Killing old monitor process with PID: $OLD_MONITOR_PID"
            kill -9 "$OLD_MONITOR_PID" 2>/dev/null
        else
            log "Monitor PID $OLD_MONITOR_PID is current process or not running, skipping..."
        fi
        # 不删除文件，留给后续写入当前 PID
    fi

    # 检查并清理旧的 modelpool_Servicer.py 进程
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if ps -p "$OLD_PID" > /dev/null 2>&1; then
            log "Killing old service process with PID: $OLD_PID"
            kill -9 "$OLD_PID" 2>/dev/null
        fi
        rm -f "$PID_FILE"
    fi

    # 额外的安全检查：通过进程名查找并清理残留的 modelpool_Servicer.py
    PIDS=$(pgrep -f "$PYTHON_SCRIPT")
    if [ -n "$PIDS" ]; then
        log "Found residual $PYTHON_SCRIPT processes: $PIDS. Killing them..."
        echo "$PIDS" | while read -r pid; do
            if ps -p "$pid" > /dev/null 2>&1; then
                log "Killing residual process with PID: $pid"
                kill -9 "$pid" 2>/dev/null
            fi
        done
    fi
}

# 启动 Python 服务
start_service() {
    log "Starting modelpool_Servicer.py..."
    python3 "$PYTHON_SCRIPT" &
    PID=$!
    echo "$PID" > "$PID_FILE"
    log "Service started with PID: $PID"
}

# 检查服务是否运行
check_service() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0  # 服务正常运行
        else
            return 1  # 服务已停止
        fi
    else
        return 1  # PID 文件不存在，服务未运行
    fi
}

# 主逻辑
log "Monitor script started."

# 先清理旧进程
cleanup_old_processes

# 记录当前监控脚本的 PID
echo "$$" > "$MONITOR_PID_FILE"

# 初次启动服务
start_service

# 监控循环
while true; do
    if ! check_service; then
        log "Service with PID $PID is not running. Restarting..."
        rm -f "$PID_FILE"
        start_service
    fi
    sleep 30  # 每 10 秒检查一次
done

## 使用方法，启动脚本：
##  ./monitor_modeserver.sh  
##
## 后台启动脚本：
##  nohup ./monitor_modeserver.sh  &