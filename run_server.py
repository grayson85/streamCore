#!/usr/bin/env python3
"""Simple Flask server for testing - no debug mode"""

from app import app

if __name__ == '__main__':
    print("=" * 70)
    print("🚀 StreamCore API 服务启动 (Production Mode)")
    print("=" * 70)
    print()
    app.run(host='0.0.0.0', port=5000, debug=False)
