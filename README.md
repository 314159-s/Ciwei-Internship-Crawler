# Ciwei Internship Crawler (基于 Playwright 的自动化爬虫)

本项目是一个基于 Python Playwright 开发的自动化爬虫工具，专门用于抓取刺猬实习（Ciwei.net）平台的岗位数据。它针对复杂的单页面应用 (SPA) 架构和登录拦截机制，实现了稳定的数据采集流程。

## 技术亮点

* **持久化会话管理**：利用 `launch_persistent_context` 技术，通过本地缓存（User Data）持久化存储登录状态，有效绕过了招聘平台频繁跳转登录页面的问题。
* **异步并发处理**：基于 `asyncio` 和 Playwright 异步驱动，提升了详情页跳转与数据提取的执行效率。
* **鲁棒性定位策略**：针对动态类名（Dynamic Class Names），采用了基于 URL 特征匹配（Attribute-based Locator）的提取方案，确保在前端框架更新时仍能保持稳定。
* **数据自动化存储**：支持将采集到的岗位名称、职责描述及详情链接自动导出为结构化的 CSV 文件，并处理了 Excel 打开时的 UTF-8 编码乱码问题。

## 🛠️ 项目结构

```text
resume/
├── main.py              # 核心爬虫逻辑
├── requirements.txt     # 项目依赖清单
├── .gitignore           # 忽略文件配置（防止隐私泄露）
└── README.md            # 项目说明文档


```
快速开始

1. 安装依赖

确保你已安装 Python 3.8+，然后在终端运行：

<pre>
pip install -r requirements.txt
playwright install chromium
</pre>

2. 运行脚本
<pre>
python main.py
</pre>

3. 操作说明
首次运行：脚本会自动打开 Chrome 浏览器。若未登录，请手动在浏览器窗口完成登录（扫码或手机验证码）。

数据抓取：一旦检测到职位列表，程序将自动开始深度抓取详情页内容并保存至 ciwei_data.csv。

 注意事项
本项目仅供学术交流与技术研究使用。


## 更新记录
* **2026-04-14**: 优化了详情页抓取逻辑，减少爬取的噪声
