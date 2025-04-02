#!/usr/bin/env python3

import os
import json
import socket
import platform
import datetime
import subprocess
from typing import Dict, List, Optional, Union

import psutil
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("AIOps MCP Server")

@mcp.tool()
def get_system_metrics() -> Dict[str, Union[float, Dict[str, float]]]:
    """
    Get basic system metrics including CPU, memory, and disk usage.
    
    Returns:
        Dict containing system metrics with the following keys:
        - cpu_percent: CPU usage percentage
        - memory: Dict with memory usage information (total, available, used, percent)
        - disk: Dict with disk usage information (total, used, free, percent)
    """
    # Get CPU usage
    cpu_percent = psutil.cpu_percent(interval=1)
    
    # Get memory usage
    memory = psutil.virtual_memory()
    memory_info = {
        "total_gb": round(memory.total / (1024**3), 2),
        "available_gb": round(memory.available / (1024**3), 2),
        "used_gb": round(memory.used / (1024**3), 2),
        "percent": memory.percent
    }
    
    # Get disk usage
    disk = psutil.disk_usage('/')
    disk_info = {
        "total_gb": round(disk.total / (1024**3), 2),
        "used_gb": round(disk.used / (1024**3), 2),
        "free_gb": round(disk.free / (1024**3), 2),
        "percent": disk.percent
    }
    
    return {
        "cpu_percent": cpu_percent,
        "memory": memory_info,
        "disk": disk_info
    }

@mcp.tool()
def check_process_status(process_name: str) -> Dict[str, Union[bool, List[Dict[str, Union[int, float, str]]]]]:
    """
    Check if a specific process is running.
    
    Args:
        process_name: Name of the process to check
        
    Returns:
        Dict containing:
        - running: Boolean indicating if the process is running
        - instances: List of dictionaries with process information (pid, cpu_percent, memory_percent, create_time)
    """
    process_list = []
    running = False
    
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'create_time']):
        try:
            if process_name.lower() in proc.info['name'].lower():
                running = True
                create_time = datetime.datetime.fromtimestamp(proc.info['create_time']).strftime('%Y-%m-%d %H:%M:%S')
                process_list.append({
                    "pid": proc.info['pid'],
                    "cpu_percent": round(proc.info['cpu_percent'], 2),
                    "memory_percent": round(proc.info['memory_percent'], 2),
                    "create_time": create_time
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    return {
        "running": running,
        "instances": process_list
    }

@mcp.tool()
def list_running_services() -> List[Dict[str, Union[int, str, float]]]:
    """
    List all running services/processes with their resource usage.
    
    Returns:
        List of dictionaries containing process information (pid, name, cpu_percent, memory_percent)
    """
    services = []
    
    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            proc_info = proc.info
            if proc_info['cpu_percent'] > 0 or proc_info['memory_percent'] > 0.1:  # Filter out idle processes
                services.append({
                    "pid": proc_info['pid'],
                    "name": proc_info['name'],
                    "cpu_percent": round(proc_info['cpu_percent'], 2),
                    "memory_percent": round(proc_info['memory_percent'], 2)
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    # Sort by CPU usage (descending)
    services.sort(key=lambda x: x['cpu_percent'], reverse=True)
    
    return services[:20]  # Return top 20 processes by CPU usage

@mcp.tool()
def check_network_connectivity(host: str = "8.8.8.8", port: int = 53, timeout: float = 3.0) -> Dict[str, Union[bool, float, str]]:
    """
    Check network connectivity by attempting to connect to a specific host.
    
    Args:
        host: Host to connect to (default: 8.8.8.8, Google DNS)
        port: Port to connect to (default: 53, DNS service)
        timeout: Connection timeout in seconds (default: 3.0)
        
    Returns:
        Dict containing:
        - connected: Boolean indicating if connection was successful
        - latency: Connection latency in milliseconds (if successful)
        - error: Error message (if connection failed)
    """
    start_time = datetime.datetime.now()
    
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        latency = (datetime.datetime.now() - start_time).total_seconds() * 1000
        
        return {
            "connected": True,
            "latency_ms": round(latency, 2),
            "error": None
        }
    except socket.error as e:
        return {
            "connected": False,
            "latency_ms": None,
            "error": str(e)
        }

@mcp.tool()
def check_port_status(port: int, host: str = "127.0.0.1") -> Dict[str, Union[bool, str]]:
    """
    Check if a specific port is open on the given host.
    
    Args:
        port: Port number to check
        host: Host to check (default: 127.0.0.1, localhost)
        
    Returns:
        Dict containing:
        - open: Boolean indicating if the port is open
        - status: String describing the port status
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            # Try to get the process using this port
            process_info = None
            try:
                for conn in psutil.net_connections(kind='inet'):
                    if conn.laddr.port == port and conn.status == 'LISTEN':
                        process = psutil.Process(conn.pid)
                        process_info = f"{process.name()} (PID: {conn.pid})"
                        break
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                pass
                
            return {
                "open": True,
                "status": f"Port {port} is open" + (f", used by {process_info}" if process_info else "")
            }
        else:
            return {
                "open": False,
                "status": f"Port {port} is closed or filtered"
            }
    except socket.error as e:
        return {
            "open": False,
            "status": f"Error checking port {port}: {str(e)}"
        }

@mcp.tool()
def analyze_log_file(log_path: str, max_lines: int = 100, error_keywords: Optional[List[str]] = None) -> Dict[str, Union[List[str], int, str]]:
    """
    Analyze a log file for errors and return relevant information.
    
    Args:
        log_path: Path to the log file
        max_lines: Maximum number of lines to read from the end of the file (default: 100)
        error_keywords: List of keywords to search for in the log (default: ["error", "exception", "fail", "critical"])
        
    Returns:
        Dict containing:
        - exists: Boolean indicating if the log file exists
        - error_count: Number of lines containing error keywords
        - error_lines: List of lines containing error keywords
        - error: Error message if the file couldn't be read
    """
    if error_keywords is None:
        error_keywords = ["error", "exception", "fail", "critical"]
    
    if not os.path.exists(log_path):
        return {
            "exists": False,
            "error_count": 0,
            "error_lines": [],
            "error": f"Log file not found: {log_path}"
        }
    
    try:
        # Get the last N lines of the log file
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            # Read all lines and get the last max_lines
            lines = f.readlines()[-max_lines:]
        
        # Find lines containing error keywords
        error_lines = []
        for line in lines:
            line = line.strip()
            if any(keyword.lower() in line.lower() for keyword in error_keywords):
                error_lines.append(line)
        
        return {
            "exists": True,
            "error_count": len(error_lines),
            "error_lines": error_lines,
            "error": None
        }
    except Exception as e:
        return {
            "exists": True,
            "error_count": 0,
            "error_lines": [],
            "error": f"Error reading log file: {str(e)}"
        }

@mcp.tool()
def get_system_info() -> Dict[str, str]:
    """
    Get basic system information.
    
    Returns:
        Dict containing system information (hostname, platform, release, version, architecture, processor)
    """
    return {
        "hostname": socket.gethostname(),
        "platform": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "boot_time": datetime.datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
    }

if __name__ == "__main__":
    mcp.run(transport="sse")