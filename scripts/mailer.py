#!/usr/bin/env python3
"""
日报邮件发送脚本
用法: python3 mailer.py <report_path>
配置文件: ~/.claude/daily-report-config.json
"""

import json
import sys
import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formatdate, make_msgid
from datetime import datetime

CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.json"))


def load_config():
    """加载邮件配置"""
    if not os.path.exists(CONFIG_PATH):
        print(f"错误: 配置文件不存在: {CONFIG_PATH}")
        print("请运行 /daily-report config 配置邮件信息")
        sys.exit(1)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def send_daily_report(report_path, config):
    """发送日报邮件"""
    if not os.path.exists(report_path):
        print(f"错误: 日报文件不存在: {report_path}")
        sys.exit(1)

    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()

    today = datetime.now().strftime("%Y年%m月%d日")

    msg = MIMEText(content, "plain", "utf-8")
    msg["From"] = config["from_email"]
    msg["To"] = ", ".join(config["to_emails"])
    name = config.get("user", {}).get("name") or "日报"
    msg["Subject"] = Header(f"{name} {today} 工作日报", "utf-8")
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()

    # 连接 SMTP 发送
    smtp_server = config["smtp_server"]
    smtp_port = config.get("smtp_port", 587)
    use_tls = config.get("use_tls", True)
    use_ssl = config.get("use_ssl", False)

    if use_ssl:
        server = smtplib.SMTP_SSL(smtp_server, smtp_port)
    else:
        server = smtplib.SMTP(smtp_server, smtp_port)

    if use_tls and not use_ssl:
        server.starttls()

    server.login(config["smtp_user"], config["smtp_password"])
    server.sendmail(config["from_email"], config["to_emails"], msg.as_string())
    server.quit()

    print(f"日报邮件发送成功: -> {', '.join(config['to_emails'])}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 mailer.py <report_path>")
        sys.exit(1)

    config = load_config()
    send_daily_report(sys.argv[1], config)
